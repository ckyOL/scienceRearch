"""合同校验与汇总：把"结论是否可被验证"变成可执行判断。

判定分三类，对应 `scirearch verify` 的退出码：
- 合同问题（problems）→ 退出码 1：缺证据、非法状态、预注册哈希漂移、git 时序违规；
- 判据冲突（inconsistencies）→ 退出码 2：状态与可求值判据不一致
  （completed 却违反、refuted 却全部满足）；
- 警告（warnings）：浅克隆、未提交等不可判定项——不阻断本地流程，由 CI 用完整历史裁定。

机器判定是完整性控制，不是独立 attestation：它证明合同与判据自洽，不证明结论正确。
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scirearch import githistory
from scirearch.criteria import (
    DECIDED_BY_HUMAN,
    DECIDED_BY_MACHINE,
    REASON_FREE_TEXT,
    REASON_MISSING_METRIC,
    REASON_NON_NUMERIC,
    REASON_REVIEW,
    STATE_PENDING,
    STATE_SATISFIED,
    STATE_UNDECIDABLE,
    STATE_VIOLATED,
    Outcome,
    evaluate,
    normalize,
)
from scirearch.experiment import (
    ALL_KINDS,
    ALL_STATUSES,
    EVIDENCE_STATUSES,
    EXPERIMENTS_DIRNAME,
    ID_PREFIX,
    KIND_EXPERIMENT,
    KIND_LABELS,
    KIND_STATUSES,
    KIND_THOUGHT,
    METRICS_FILENAME,
    PREREGISTRATION_ALGORITHM,
    PRIOR_KNOWLEDGE_STATUSES,
    REASONING_FILENAME,
    REQUIRED_MANIFEST_KEYS,
    RESULT_FILENAMES,
    REVIEW_FILENAME,
    REVIEW_STATUSES,
    SCHEMA_VERSION,
    STATUS_COMPLETED,
    STATUS_PREREGISTERED,
    STATUS_PROMOTED,
    STATUS_REFUTED,
    STATUS_REJECTED,
    TERMINAL_STATUSES,
    ExperimentError,
    canonical_text_sha256,
    criteria_sha256,
    find_experiment_dir,
    has_text_content,
    load_manifest,
    preregistration_record_sha256,
)

VERDICT_STATUSES = frozenset({STATUS_COMPLETED, STATUS_REFUTED})

# 复核裁定取值：与 review.json 的 rulings[].ruling 对应。
RULING_SATISFIED = "satisfied"
RULING_VIOLATED = "violated"
RULING_UNCLEAR = "unclear"
RULINGS = (RULING_SATISFIED, RULING_VIOLATED, RULING_UNCLEAR)
_RULING_STATES = {
    RULING_SATISFIED: STATE_SATISFIED,
    RULING_VIOLATED: STATE_VIOLATED,
    RULING_UNCLEAR: STATE_UNDECIDABLE,
}

EXIT_PASS = 0
EXIT_CONTRACT = 1
EXIT_CRITERIA_CONFLICT = 2


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class CheckResult:
    """单个记录的合同校验结果。"""

    id: str
    slug: str
    path: str
    status: str
    ok: bool
    kind: str = KIND_EXPERIMENT
    problems: tuple[str, ...] = ()
    inconsistencies: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    criteria: tuple[Outcome, ...] = ()
    seed: int | None = None
    commit: str | None = None
    criteria_sha256: str | None = None
    has_metrics: bool = False
    has_reasoning: bool = False
    has_review: bool = False
    log_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "path": self.path,
            "kind": self.kind,
            "status": self.status,
            "ok": self.ok,
            "problems": list(self.problems),
            "inconsistencies": list(self.inconsistencies),
            "warnings": list(self.warnings),
            "criteria": [o.to_dict() for o in self.criteria],
            "seed": self.seed,
            "commit": self.commit,
            "criteria_sha256": self.criteria_sha256,
            "has_metrics": self.has_metrics,
            "has_reasoning": self.has_reasoning,
            "has_review": self.has_review,
            "log_files": self.log_files,
        }


@dataclass
class _State:
    problems: list[str] = field(default_factory=list)
    inconsistencies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    criteria: list[Outcome] = field(default_factory=list)
    kind: str = KIND_EXPERIMENT
    seed: int | None = None
    commit: str | None = None
    criteria_sha256: str | None = None
    has_metrics: bool = False
    has_reasoning: bool = False
    has_review: bool = False
    log_files: int = 0

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def conflict(self, message: str) -> None:
        self.inconsistencies.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _count_logs(exp_dir: Path) -> int:
    logs = exp_dir / "logs"
    if not logs.is_dir():
        return 0
    return sum(1 for p in logs.rglob("*") if p.is_file() and p.stat().st_size > 0)


def _check_manifest_shape(manifest: dict[str, Any], state: _State) -> str:
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        state.fail(f"manifest 缺少字段：{', '.join(missing)}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        state.fail(f"schema_version 应为 {SCHEMA_VERSION}，实际 {manifest.get('schema_version')!r}")
    kind = manifest.get("kind")
    if kind not in ALL_KINDS:
        state.fail(f"未知类型 kind={kind!r}；只允许：{', '.join(ALL_KINDS)}")
    elif isinstance(kind, str):
        state.kind = kind
    for key in ("hypothesis", "metric", "falsification"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            state.fail(f"{key} 必须是非空字符串")
    criteria = manifest.get("criteria")
    if not isinstance(criteria, list) or not [
        c for c in criteria if isinstance(c, str) and c.strip()
    ]:
        state.fail("criteria 必须包含至少一条非空判据（判据先于结果）")
    elif isinstance(criteria, list):
        keys = [normalize(c) for c in criteria if isinstance(c, str) and c.strip()]
        if len(set(keys)) != len(keys):
            state.fail("criteria 存在重复判据（空白折叠后相同）：判据必须互异")
    prior = manifest.get("prior_refutations")
    if prior is not None and (
        not isinstance(prior, list) or not all(isinstance(p, str) and p.strip() for p in prior)
    ):
        state.fail("prior_refutations 必须是记录 id 列表（由 scirearch new 写入）")
    superseded_by = manifest.get("superseded_by")
    if superseded_by is not None and not _nonempty_str(superseded_by):
        state.fail("superseded_by 必须是非空字符串（转成的正式实验 id）")
    if state.kind == KIND_THOUGHT and not _nonempty_str(manifest.get("blockers")):
        state.fail("思想实验缺少 blockers：必须写明什么条件缺失使它现在无法实验")
    seed = manifest.get("seed")
    if isinstance(seed, bool) or (seed is not None and not isinstance(seed, int)):
        state.fail(f"seed 必须是整数或 null，实际 {seed!r}")
    elif isinstance(seed, int):
        state.seed = seed
    commit = manifest.get("git_commit")
    state.commit = commit if isinstance(commit, str) else None
    status = manifest.get("status")
    if isinstance(status, str) and status not in ALL_STATUSES:
        state.fail(f"未知状态 {status!r}；只允许：{', '.join(sorted(ALL_STATUSES))}")
    elif isinstance(status, str) and status not in KIND_STATUSES[state.kind]:
        state.fail(
            f"状态 {status!r} 不属于{KIND_LABELS[state.kind]}："
            f"{KIND_LABELS[state.kind]}的合法状态是 {', '.join(sorted(KIND_STATUSES[state.kind]))}"
        )
    return status if isinstance(status, str) else ""


def _check_history(manifest: dict[str, Any], status: str, state: _State) -> None:
    history = manifest.get("history")
    if not isinstance(history, list) or not history:
        state.fail("history 缺失或为空：每次状态变更都必须留痕")
        return
    last = history[-1]
    if not isinstance(last, dict) or last.get("status") != status:
        state.fail(
            f"history 与 status 不一致：status={status!r}，history 末条={last!r}"
            "（疑似绕过 CLI 手工改动）"
        )


def _with_pending(manifest: dict[str, Any], pending: Mapping[str, Any]) -> dict[str, Any]:
    """返回"若写入 pending 片段"的 manifest 投影：不落盘，只让后续检查按目标状态求值。"""
    return {**manifest, **pending}


def _check_preregistration(exp_dir: Path, manifest: dict[str, Any], state: _State) -> None:
    """预注册 = 不变量：重算创建时登记的 hash，任何漂移都判失败。"""
    block = manifest.get("preregistration")
    if not isinstance(block, dict):
        state.fail(
            "manifest 缺少 preregistration 块：schema v2 要求登记预注册哈希"
            "（用 scirearch new 重建）"
        )
        return
    if block.get("algorithm") != PREREGISTRATION_ALGORITHM:
        state.fail(
            f"preregistration.algorithm 应为 {PREREGISTRATION_ALGORITHM!r}，"
            f"实际 {block.get('algorithm')!r}"
        )
    for key in ("criteria_sha256", "hypothesis_md_sha256", "record_sha256"):
        value = block.get(key)
        if not isinstance(value, str) or len(value) != 64:
            state.fail(f"preregistration.{key} 必须是 sha256 十六进制串")
    stored_criteria_hash = block.get("criteria_sha256")
    if isinstance(stored_criteria_hash, str):
        state.criteria_sha256 = stored_criteria_hash

    kind = manifest.get("kind")
    criteria = manifest.get("criteria")
    hypothesis = manifest.get("hypothesis")
    metric = manifest.get("metric")
    falsification = manifest.get("falsification")
    blockers = manifest.get("blockers")
    seed = manifest.get("seed")
    seed_ok = seed is None or (isinstance(seed, int) and not isinstance(seed, bool))
    if not (
        kind in ALL_KINDS
        and isinstance(criteria, list)
        and all(isinstance(c, str) for c in criteria)
        and isinstance(hypothesis, str)
        and isinstance(metric, str)
        and isinstance(falsification, str)
        and (blockers is None or isinstance(blockers, str))
        and seed_ok
    ):
        return  # 字段类型异常已由 shape 检查报告，这里不再重复

    clean_criteria = [c for c in criteria if c.strip()]
    if block.get("criteria_sha256") != criteria_sha256(clean_criteria):
        state.fail("预注册漂移：criteria 的 sha256 与登记值不一致（判据创建后不得修改）")

    mirror = exp_dir / "hypothesis.md"
    if not mirror.is_file():
        state.fail("缺少 hypothesis.md（预注册镜像）")
    else:
        try:
            mirror_text = mirror.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            state.fail("hypothesis.md 不是 UTF-8 文本（预注册镜像被损坏）")
        else:
            if block.get("hypothesis_md_sha256") != canonical_text_sha256(mirror_text):
                state.fail(
                    "预注册漂移：hypothesis.md 的 sha256 与登记值不一致（预注册镜像创建后不得编辑）"
                )

    expected_record = preregistration_record_sha256(
        kind=kind,
        hypothesis=hypothesis,
        metric=metric,
        criteria=clean_criteria,
        falsification=falsification,
        blockers=blockers if isinstance(blockers, str) else None,
        seed=state.seed,
    )
    if block.get("record_sha256") != expected_record:
        state.fail(
            "预注册漂移：kind/hypothesis/metric/criteria/falsification/blockers/seed "
            "与登记哈希不一致（预注册记录创建后不得修改）"
        )


def _check_evidence(exp_dir: Path, status: str, state: _State) -> dict[str, Any] | None:
    metrics_path = exp_dir / METRICS_FILENAME
    state.has_metrics = metrics_path.is_file()
    state.log_files = _count_logs(exp_dir)
    state.has_reasoning = has_text_content(exp_dir / REASONING_FILENAME)
    state.has_review = (exp_dir / REVIEW_FILENAME).is_file()

    metrics: dict[str, Any] | None = None
    if state.has_metrics:
        try:
            metrics_text = metrics_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            state.fail(f"metrics.json 不可读：{type(exc).__name__}")
        else:
            try:
                payload = json.loads(metrics_text)
            except json.JSONDecodeError as exc:
                state.fail(f"metrics.json 不是合法 JSON：{exc}")
            else:
                if not isinstance(payload, dict) or not payload:
                    state.fail("metrics.json 必须是非空 JSON 对象")
                else:
                    metrics = payload

    # 预注册的牙齿：判据承诺在先，结果不得先于状态推进出现。
    if status == STATUS_PREREGISTERED and state.has_metrics:
        state.fail("预注册违规：status=preregistered 时已存在 metrics.json（判据必须早于结果）")

    # 思想实验永不携带经验证据：出现 metrics.json 说明它其实可测——应转为正式实验。
    if state.kind == KIND_THOUGHT and state.has_metrics:
        state.fail(
            "思想实验不得携带 metrics.json：经验证据属于正式实验"
            "（`scirearch new` 建实验，再用 promoted --superseded-by 指向它）"
        )

    if status in EVIDENCE_STATUSES:
        if not state.has_metrics:
            state.fail("终态缺少 metrics.json")
        if state.log_files == 0:
            state.fail("终态缺少非空原始日志（logs/ 为空）")
        if state.seed is None:
            state.fail("终态缺少 seed")
    return metrics


def _evaluate_criteria(
    manifest: dict[str, Any], metrics: dict[str, Any] | None, status: str, state: _State
) -> None:
    """三态求值 + 状态一致性门：completed 不得有违反；refuted 必须有违反。"""
    raw = manifest.get("criteria")
    if not isinstance(raw, list):
        return
    texts = [c for c in raw if isinstance(c, str) and c.strip()]
    if not texts:
        return
    if state.kind == KIND_THOUGHT:
        # 思想实验永不产出 metrics.json：判据由复核者在 review.json 中逐条裁定。
        state.criteria = [
            Outcome(
                criterion=normalize(c),
                state=STATE_UNDECIDABLE,
                decided_by=DECIDED_BY_HUMAN,
                reason=REASON_REVIEW,
                detail="待复核者裁定（思想实验不由机器求值）",
            )
            for c in texts
        ]
        return
    outcomes = evaluate(texts, metrics)
    state.criteria = outcomes

    if status not in VERDICT_STATUSES:
        return

    for outcome in outcomes:
        if outcome.reason in (REASON_MISSING_METRIC, REASON_NON_NUMERIC):
            state.fail(f"可求值判据无法裁决：`{outcome.criterion}`（{outcome.detail}）")

    decided = [o for o in outcomes if o.state in (STATE_SATISFIED, STATE_VIOLATED)]
    violated = [o for o in decided if o.state == STATE_VIOLATED]
    if status == STATUS_COMPLETED and violated:
        detail = "；".join(f"`{o.criterion}`（{o.detail}）" for o in violated)
        state.conflict(f"判据被违反却标记为 completed：{detail}。应改判 refuted，或修正证据。")
    if status == STATUS_REFUTED and decided and not violated:
        detail = "；".join(f"`{o.criterion}`" for o in decided)
        state.conflict(
            f"可判定判据全部满足却标记为 refuted：{detail}。"
            "状态与预注册判据不一致（若因其他观察否定假设，应改判 inconclusive）。"
        )


def _check_reasoning_freeze(
    exp_dir: Path, manifest: dict[str, Any], status: str, state: _State
) -> None:
    """终态冻结：history 必须登记 reasoning.md 的 sha256，且内容与之一致。"""
    if status not in REVIEW_STATUSES:
        return
    reasoning = exp_dir / REASONING_FILENAME
    try:
        text = reasoning.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return  # 缺失或不可读已由 _check_review 报告
    if not text.strip():
        return
    history = manifest.get("history")
    entry = history[-1] if isinstance(history, list) and history else None
    recorded = entry.get("reasoning_sha256") if isinstance(entry, dict) else None
    if not _nonempty_str(recorded) or len(recorded) != 64:
        state.fail("history 缺少 reasoning_sha256：终态必须冻结论证内容（重写状态以登记）")
        return
    if recorded != canonical_text_sha256(text):
        state.fail("论证漂移：reasoning.md 的 sha256 与终态登记的哈希不一致（裁决后不得编辑）")


def _check_review(exp_dir: Path, manifest: dict[str, Any], status: str, state: _State) -> None:
    """思想实验终态：非空论证 + 独立复核记录（逐条裁定判据 + 生成/复核分离）。"""
    if status not in REVIEW_STATUSES:
        return
    if not state.has_reasoning:
        state.fail(f"终态缺少非空论证（{REASONING_FILENAME}）")
    review_path = exp_dir / REVIEW_FILENAME
    if not review_path.is_file():
        state.fail(f"终态缺少独立复核记录（{REVIEW_FILENAME}）")
        return
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        state.fail(f"{REVIEW_FILENAME} 不是合法 JSON：{exc}")
        return
    if not isinstance(review, dict) or not review:
        state.fail(f"{REVIEW_FILENAME} 必须是非空 JSON 对象")
        return

    parties: dict[str, tuple[str, str]] = {}
    for role in ("reviewer", "generator"):
        party = review.get(role)
        if (
            not isinstance(party, dict)
            or not _nonempty_str(party.get("agent"))
            or not _nonempty_str(party.get("model"))
        ):
            state.fail(f"{REVIEW_FILENAME} 的 {role} 必须是含非空 agent 与 model 的对象")
            continue
        parties[role] = (str(party["agent"]).strip(), str(party["model"]).strip())
    if len(parties) == 2:
        reviewer, generator = parties["reviewer"], parties["generator"]
        if (
            reviewer[0].casefold() == generator[0].casefold()
            or reviewer[1].casefold() == generator[1].casefold()
        ):
            state.fail(
                f"{REVIEW_FILENAME} 的复核者与生成者未分离（agent 或 model 相同）："
                "复核必须换 agent、换模型（该字段自声明，属完整性控制而非 attestation）"
            )

    if review.get("verdict") != status:
        state.fail(f"{REVIEW_FILENAME} 的 verdict={review.get('verdict')!r} 与状态 {status} 不一致")

    texts = [c for c in manifest.get("criteria", []) if isinstance(c, str) and c.strip()]
    expected = {normalize(c): c for c in texts}
    rulings = review.get("rulings")
    if not isinstance(rulings, list) or not rulings:
        state.fail(f"{REVIEW_FILENAME} 必须逐条裁定判据（rulings 非空）")
        return
    confirmed: dict[str, str] = {}
    notes: dict[str, str] = {}
    for item in rulings:
        if not isinstance(item, dict):
            state.fail(f"{REVIEW_FILENAME} 的 rulings 元素必须是对象")
            continue
        criterion, ruling, note = item.get("criterion"), item.get("ruling"), item.get("note")
        if not _nonempty_str(criterion) or ruling not in RULINGS or not _nonempty_str(note):
            state.fail(
                f"{REVIEW_FILENAME} 的 rulings 元素必须是 "
                f"{{criterion, ruling∈{list(RULINGS)}, note}}"
            )
            continue
        key = normalize(str(criterion))
        if key in confirmed:
            state.fail(f"{REVIEW_FILENAME} 重复裁定同一条判据：`{criterion}`")
            continue
        confirmed[key] = str(ruling)
        notes[key] = str(note)
        if key not in expected:
            state.fail(
                f"{REVIEW_FILENAME} 裁定了未登记的判据：`{criterion}`（判据创建即冻结，不得追加）"
            )
    missing = [expected[key] for key in expected if key not in confirmed]
    if missing:
        state.fail(f"{REVIEW_FILENAME} 未逐条裁定判据：缺 {', '.join(f'`{m}`' for m in missing)}")

    # 复核裁定 → report 的三态（与机器判定同样标 [人工]）。
    state.criteria = [
        Outcome(
            criterion=expected[key],
            state=_RULING_STATES[confirmed[key]],
            decided_by=DECIDED_BY_HUMAN,
            reason=REASON_REVIEW,
            detail=notes.get(key, "复核裁定"),
        )
        for key in expected
        if key in confirmed
    ]

    if (
        status == STATUS_REJECTED
        and confirmed
        and not any(ruling == RULING_VIOLATED for ruling in confirmed.values())
    ):
        state.conflict(
            "判据无一条被复核者裁定为违反却标记为 rejected："
            "应改判 promoted / abandoned，或补足论证与裁定。"
        )

    if status == STATUS_PROMOTED:
        target = manifest.get("superseded_by")
        if not _nonempty_str(target):
            state.fail("promoted 缺少 superseded_by（转成的正式实验 id）")
            return
        target_dir = find_experiment_dir(exp_dir.parent, str(target))
        if target_dir is None:
            state.fail(f"superseded_by={target} 未解析到唯一的实验目录（悬空引用）")
            return
        if target_dir == exp_dir:
            state.fail("superseded_by 指向自身")
            return
        try:
            target_manifest = load_manifest(target_dir)
        except ExperimentError as exc:
            state.fail(f"superseded_by={target} 的 manifest 不可读：{exc}")
        else:
            target_kind = target_manifest.get("kind")
            if target_kind != KIND_EXPERIMENT:
                state.fail(
                    f"superseded_by={target} 不是可执行实验（kind={target_kind!r}）："
                    "promoted 必须指向 kind=experiment 的正式实验"
                )
            elif str(target_manifest.get("id")) != str(target):
                state.fail(
                    f"superseded_by={target} 与目标 manifest 的 id"
                    f"（{target_manifest.get('id')!r}）不一致：引用必须指向同一条记录"
                )


def _check_run_sh(exp_dir: Path, state: _State) -> None:
    if state.kind == KIND_THOUGHT:
        if (exp_dir / "run.sh").is_file():
            state.warn(
                "思想实验目录出现 run.sh：若该假说已可执行，请建正式实验并用 promoted 指向它"
            )
        return
    run_sh = exp_dir / "run.sh"
    if not run_sh.is_file():
        state.fail("缺少可重跑入口 run.sh")
        return
    if not os.access(run_sh, os.X_OK):
        state.fail("run.sh 不可执行（chmod +x run.sh）")


def _check_git_firewall(
    exp_dir: Path, manifest: dict[str, Any], status: str, state: _State
) -> None:
    """git 时序防火墙：预注册提交必须严格早于结果提交，且冻结后未被编辑。"""
    if status not in TERMINAL_STATUSES:
        return
    repo = githistory.repo_state(exp_dir)
    if not repo.in_repo:
        state.warn("git 时序不可判定：实验目录不在 git 工作树内（提交后由 CI 裁定）")
        return
    if repo.shallow:
        state.warn("git 时序不可判定：仓库是浅克隆（CI 需 fetch-depth: 0）")
        return

    manifest_rel = f"{repo.prefix}experiment.json"
    result_name = RESULT_FILENAMES.get(state.kind, RESULT_FILENAMES[KIND_EXPERIMENT])
    result_rel = f"{repo.prefix}{result_name}"
    has_result = state.has_metrics if state.kind == KIND_EXPERIMENT else state.has_review
    prereg_commit = githistory.first_add_commit(exp_dir, manifest_rel)
    if prereg_commit is None:
        state.warn("git 时序不可判定：experiment.json 未被 git 跟踪（先提交预注册，再跑实验）")
    else:
        blob = githistory.blob_text(exp_dir, prereg_commit, manifest_rel)
        committed_block: Any = None
        if blob is not None:
            try:
                committed_manifest = json.loads(blob)
            except json.JSONDecodeError:
                committed_manifest = None
            if isinstance(committed_manifest, dict):
                committed_block = committed_manifest.get("preregistration")
        current_block = manifest.get("preregistration")
        if not isinstance(committed_block, dict):
            state.warn(f"git 时序不可判定：冻结提交 {prereg_commit[:8]} 中的预注册块不可读")
        elif isinstance(current_block, dict):
            drifted = sorted(
                key
                for key in set(committed_block) | set(current_block)
                if committed_block.get(key) != current_block.get(key)
            )
            if drifted:
                state.fail(
                    f"git 时序违规：预注册块在冻结提交 {prereg_commit[:8]} 之后被编辑"
                    f"（漂移字段：{', '.join(drifted)}）"
                )

        result_commit = githistory.first_add_commit(exp_dir, result_rel) if has_result else None
        if has_result and result_commit is None:
            state.warn(f"git 时序不可判定：{result_name} 未提交（提交后由 CI 裁定）")
        if result_commit is not None and (
            result_commit == prereg_commit
            or githistory.is_ancestor(exp_dir, result_commit, prereg_commit)
        ):
            state.fail(
                f"git 时序违规：结果提交不晚于预注册提交 {prereg_commit[:8]}"
                "（预注册必须严格早于结果；squash 合并会把两次提交压成一次）"
            )


def check_experiment(exp_dir: Path, *, pending: Mapping[str, Any] | None = None) -> CheckResult:
    """校验单个记录目录，返回结构化结果（不抛异常）。

    `pending` 供 `set_status` 在**写入前**模拟目标状态：传入"若写入"的 manifest 片段
    （status / history / superseded_by），使 CLI 能拒绝一个会被本函数判失败的推进。
    终态不可回退，"先写后报"等于把冲突永久钉死。
    """
    state = _State()
    name = exp_dir.name
    exp_id = name.split("-", 1)[0] if name.startswith(f"{ID_PREFIX}-") else name
    slug = name.removeprefix(f"{exp_id}-")

    try:
        manifest = load_manifest(exp_dir)
    except ExperimentError as exc:
        state.fail(str(exc))
        return CheckResult(
            id=exp_id,
            slug=slug,
            path=str(exp_dir),
            status="unknown",
            ok=False,
            problems=tuple(state.problems),
            inconsistencies=tuple(state.inconsistencies),
            warnings=tuple(state.warnings),
        )

    if pending is not None:
        manifest = _with_pending(manifest, pending)
    status = _check_manifest_shape(manifest, state)
    _check_history(manifest, status, state)
    _check_preregistration(exp_dir, manifest, state)
    metrics = _check_evidence(exp_dir, status, state)
    _evaluate_criteria(manifest, metrics, status, state)
    _check_review(exp_dir, manifest, status, state)
    _check_reasoning_freeze(exp_dir, manifest, status, state)
    _check_run_sh(exp_dir, state)
    _check_git_firewall(exp_dir, manifest, status, state)

    return CheckResult(
        id=str(manifest.get("id", exp_id)),
        slug=str(manifest.get("slug", slug)),
        path=str(exp_dir),
        kind=state.kind,
        status=status or "unknown",
        ok=not state.problems and not state.inconsistencies,
        problems=tuple(state.problems),
        inconsistencies=tuple(state.inconsistencies),
        warnings=tuple(state.warnings),
        criteria=tuple(state.criteria),
        seed=state.seed,
        commit=state.commit,
        criteria_sha256=state.criteria_sha256,
        has_metrics=state.has_metrics,
        has_reasoning=state.has_reasoning,
        has_review=state.has_review,
        log_files=state.log_files,
    )


def find_experiments(root: Path) -> list[Path]:
    """按 id 排序返回实验目录列表。"""
    base = root / EXPERIMENTS_DIRNAME
    if not base.is_dir():
        return []
    return sorted(p for p in base.glob(f"{ID_PREFIX}-*") if p.is_dir())


def verify_tree(root: Path) -> list[CheckResult]:
    """校验仓库内全部实验（空仓库返回空列表，交由调用方决定是否算失败）。"""
    return [check_experiment(p) for p in find_experiments(root)]


def exit_code(results: Sequence[CheckResult]) -> int:
    """0 = 通过；1 = 合同非法；2 = 判据与状态冲突（ArmProof 语义，见实验协议）。"""
    if any(r.inconsistencies for r in results):
        return EXIT_CRITERIA_CONFLICT
    if any(r.problems for r in results):
        return EXIT_CONTRACT
    return EXIT_PASS


def negative_index(results: Sequence[CheckResult]) -> list[dict[str, str]]:
    """负知识索引：被否定的判据（`refuted` 实验 / `rejected` 思想实验），重提前必须先命中它。

    只收录 `verify` 通过的记录：合同不完整的终态（手写/旧版 CLI 写下的）不构成已确立的否定。
    """
    index: list[dict[str, str]] = []
    for r in results:
        if not r.ok or r.status not in PRIOR_KNOWLEDGE_STATUSES or not r.criteria_sha256:
            continue
        index.append(
            {
                "id": r.id,
                "slug": r.slug,
                "kind": r.kind,
                "status": r.status,
                "criteria_sha256": r.criteria_sha256,
                "criteria": "、".join(o.criterion for o in r.criteria) or "（未登记判据文本）",
            }
        )
    return index


def _criteria_summary(outcomes: Sequence[Outcome]) -> str:
    if not outcomes:
        return "—"
    counts = Counter(o.state for o in outcomes)
    parts: list[str] = []
    for state, label in (
        (STATE_SATISFIED, "满足"),
        (STATE_VIOLATED, "违反"),
        (STATE_PENDING, "待定"),
    ):
        if counts.get(state):
            parts.append(f"{counts[state]} {label}")
    human = sum(1 for o in outcomes if o.decided_by == DECIDED_BY_HUMAN)
    machine = sum(
        1 for o in outcomes if o.state == STATE_UNDECIDABLE and o.decided_by == DECIDED_BY_MACHINE
    )
    if machine:
        parts.append(f"{machine} 不可判定")
    if human:
        parts.append(f"{human} 人工")
    return " · ".join(parts)


def _contract_cell(result: CheckResult) -> str:
    if result.inconsistencies:
        return "判据冲突"
    if result.problems:
        return "问题"
    if result.warnings:
        return "警告"
    return "通过"


def _outcome_text(outcome: Outcome) -> str:
    if outcome.decided_by == DECIDED_BY_HUMAN and outcome.reason == REASON_REVIEW:
        if outcome.state == STATE_SATISFIED:
            return f"满足（复核裁定：{outcome.detail}）[人工]"
        if outcome.state == STATE_VIOLATED:
            return f"违反（复核裁定：{outcome.detail}）[人工]"
        return f"待复核者裁定（{outcome.detail}）[人工]"
    if outcome.state == STATE_SATISFIED:
        return f"满足（{outcome.detail}）[机器]"
    if outcome.state == STATE_VIOLATED:
        return f"违反（{outcome.detail}）[机器]"
    if outcome.state == STATE_PENDING:
        return "待定（尚未产出 metrics.json）"
    if outcome.reason == REASON_FREE_TEXT:
        return "人工裁定（自由文本判据）[人工]"
    return f"不可判定（{outcome.detail}）[机器]"


def _evidence_cell(result: CheckResult) -> str:
    if result.kind == KIND_THOUGHT:
        parts = [REASONING_FILENAME if result.has_reasoning else "—"]
        if result.has_review:
            parts.append(REVIEW_FILENAME)
        return "+".join(parts)
    return f"{'metrics' if result.has_metrics else '—'}+{result.log_files}log"


def render_report(results: list[CheckResult]) -> str:
    """把校验结果渲染成 markdown 汇总表（写作阶段的数据来源）。"""
    if not results:
        return "无记录。\n"
    lines = [
        "| 记录 | 类型 | 状态 | 判据（机器/人工） | seed | 证据 | 提交 | 合同 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.id} {r.slug} | {KIND_LABELS.get(r.kind, r.kind)} | {r.status} "
            f"| {_criteria_summary(r.criteria)} "
            f"| {r.seed if r.seed is not None else '—'} | {_evidence_cell(r)} "
            f"| {r.commit or '—'} | {_contract_cell(r)} |"
        )
    passed = sum(1 for r in results if r.ok)
    conflicts = sum(1 for r in results if r.inconsistencies)
    warned = sum(1 for r in results if r.warnings)
    lines.append("")
    lines.append(
        f"共 {len(results)} 条记录：{passed} 通过 / {len(results) - passed} 失败"
        f"（其中 {conflicts} 个判据冲突、{warned} 个含不可判定警告）。"
    )

    criteria_lines = [
        f"- {r.id} `{o.criterion}` → {_outcome_text(o)}" for r in results for o in r.criteria
    ]
    if criteria_lines:
        lines += ["", "### 判据判定", *criteria_lines]

    for title, attr, mark in (
        ("判据冲突（状态与预注册判据不一致）", "inconsistencies", "❗"),
        ("合同问题", "problems", "❌"),
        ("警告（不可判定项）", "warnings", "⚠️"),
    ):
        items = [f"- {mark} {r.id}: {msg}" for r in results for msg in getattr(r, attr)]
        if items:
            lines += ["", f"### {title}", *items]

    index = negative_index(results)
    if index:
        lines += ["", "### 负知识索引（被否定的判据）"]
        for entry in index:
            lines.append(
                f"- {entry['id']} {entry['status']}"
                f"（{KIND_LABELS.get(entry['kind'], entry['kind'])}）：`{entry['criteria']}`"
                f"（criteria_sha256={entry['criteria_sha256'][:12]}…）—— 重提前需给出新证据"
            )

    if any(r.kind == KIND_THOUGHT for r in results):
        lines += [
            "",
            "> 思想实验（`speculative` / `rejected` / `promoted`）不构成经验证据："
            "只能作为开放问题登记，不得作为 `paper/` 的结论引用。",
        ]

    lines += [
        "",
        "> 机器判定覆盖合同规则与可求值判据（完整性控制）；自由文本判据与结论接受由独立复核裁定，"
        "不是自动 attestation。",
    ]
    return "\n".join(lines) + "\n"
