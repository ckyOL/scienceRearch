"""实验 manifest：预注册、状态机与来源信息。

manifest（`experiments/<id>/experiment.json`）是机读真相源；`hypothesis.md` 是它的可读镜像。
两者在创建时同时生成并登记 sha256（`preregistration` 块）——预注册是不变量，不是提示：
创建之后对判据、证伪路径或镜像的任何修改都会被 `scirearch verify` 检出。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scirearch.criteria import normalize as normalize_criterion

SCHEMA_VERSION = 2
EXPERIMENTS_DIRNAME = "experiments"
ID_PREFIX = "exp"
ID_WIDTH = 4
PREREGISTRATION_ALGORITHM = "sha256"

STATUS_PREREGISTERED = "preregistered"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_REFUTED = "refuted"
STATUS_INCONCLUSIVE = "inconclusive"
STATUS_ABANDONED = "abandoned"
TERMINAL_STATUSES = frozenset(
    {STATUS_COMPLETED, STATUS_REFUTED, STATUS_INCONCLUSIVE, STATUS_ABANDONED}
)
ALL_STATUSES = frozenset({STATUS_PREREGISTERED, STATUS_RUNNING}) | TERMINAL_STATUSES
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PREREGISTERED: frozenset({STATUS_RUNNING, STATUS_ABANDONED}),
    STATUS_RUNNING: frozenset(TERMINAL_STATUSES),
    **dict.fromkeys(sorted(TERMINAL_STATUSES), frozenset()),
}

REQUIRED_MANIFEST_KEYS = (
    "schema_version",
    "id",
    "slug",
    "hypothesis",
    "metric",
    "criteria",
    "falsification",
    "seed",
    "status",
    "created_at",
    "history",
    "preregistration",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")

RUN_SH_TEMPLATE = """#!/usr/bin/env bash
# 可重跑入口（{experiment_id}）。
# 只修改下面标记的 RUN= 一行；seed 导出、git 版本、时间戳与 tee 是合同依赖，请保持不动。
set -euo pipefail
cd "$(dirname "$0")"

export SEED="${{SEED:-{seed}}}"
RUN="{default_run}"   # <-- 唯一需要修改的行

export PYTHONHASHSEED=0
mkdir -p logs
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
{{
  echo "# cmd: ${{RUN}}"
  echo "# seed: ${{SEED}}"
  echo "# git: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "# started: ${{STAMP}}"
  eval "${{RUN}}" 2>&1
  echo "# finished: $(date -u +%Y%m%dT%H%M%SZ)"
}} | tee "logs/run-${{STAMP}}.log"
"""

HYPOTHESIS_TEMPLATE = """# {experiment_id} · {slug}

> 状态：`preregistered` ｜ 由 `scirearch new` 生成，**创建后不可编辑**（sha256 已登记在
> `experiment.json.preregistration`；改动即判为预注册违规）。判据与证伪路径必须在跑实验前写好。

## 假设

{hypothesis}

## 指标

`{metric}`

## 判据（事前承诺）

{criteria}

## 证伪路径

{falsification}

## 执行

```bash
SEED={seed} bash run.sh
```

原始输出在 `logs/`，指标在 `metrics.json`；汇总与判据判定见 `scirearch report`。
"""


class ExperimentError(Exception):
    """合同层错误：参数非法、状态转移非法、manifest 损坏等。"""


def utc_now() -> str:
    """返回秒级精度的 UTC ISO-8601 时间戳（以 Z 结尾）。"""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    """把任意标题压成小写连字符 slug；无法产生有效 slug 时抛错。"""
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    if not slug:
        raise ExperimentError(f"无法从 {text!r} 生成 slug：请提供至少一个字母或数字。")
    return slug


def git_commit(cwd: Path) -> str | None:
    """返回当前短 commit；非 git 仓库或 git 不可用时返回 None。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit or None


def experiments_dir(root: Path) -> Path:
    return root / EXPERIMENTS_DIRNAME


def canonical_text_sha256(text: str) -> str:
    """对文本求 sha256：CRLF 归一为 LF 后按 UTF-8 编码（跨平台稳定）。"""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def criteria_sha256(criteria: list[str]) -> str:
    """判据集合的规范哈希：逐条折叠空白后按序 JSON 编码（顺序与内容都受保护）。"""
    canonical = [normalize_criterion(c) for c in criteria]
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def preregistration_record_sha256(
    *,
    hypothesis: str,
    metric: str,
    criteria: list[str],
    falsification: str,
    seed: int | None,
) -> str:
    """机读预注册记录的规范哈希：覆盖假设、指标、判据、证伪路径与 seed。"""
    record = {
        "hypothesis": hypothesis.strip(),
        "metric": metric.strip(),
        "criteria": [normalize_criterion(c) for c in criteria],
        "falsification": falsification.strip(),
        "seed": seed,
    }
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def preregistration_block(
    *,
    hypothesis: str,
    metric: str,
    criteria: list[str],
    falsification: str,
    seed: int | None,
    hypothesis_md: str,
) -> dict[str, Any]:
    """构造 manifest 的 `preregistration` 块（三个哈希各司其职，见实验协议文档）。"""
    return {
        "algorithm": PREREGISTRATION_ALGORITHM,
        "criteria_sha256": criteria_sha256(criteria),
        "hypothesis_md_sha256": canonical_text_sha256(hypothesis_md),
        "record_sha256": preregistration_record_sha256(
            hypothesis=hypothesis,
            metric=metric,
            criteria=criteria,
            falsification=falsification,
            seed=seed,
        ),
    }


def find_prior_refutations(root: Path, criteria_hash: str) -> list[str]:
    """负知识查询：返回判据哈希相同且已判 `refuted` 的历史实验 id。"""
    hits: list[str] = []
    for child in sorted(experiments_dir(root).glob(f"{ID_PREFIX}-*")):
        if not child.is_dir():
            continue
        try:
            manifest = load_manifest(child)
        except ExperimentError:
            continue
        if manifest.get("status") != STATUS_REFUTED:
            continue
        block = manifest.get("preregistration")
        if isinstance(block, dict) and block.get("criteria_sha256") == criteria_hash:
            hits.append(str(manifest.get("id", child.name)))
    return hits


def next_experiment_id(root: Path) -> str:
    """扫描已有 `exp-NNNN-*` 目录，返回下一个顺序 id。"""
    highest = 0
    for child in experiments_dir(root).glob(f"{ID_PREFIX}-*"):
        match = re.match(rf"{ID_PREFIX}-(\d+)", child.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{ID_PREFIX}-{highest + 1:0{ID_WIDTH}d}"


def resolve_experiment(root: Path, target: str) -> Path:
    """接受实验目录路径或 `exp-NNNN` 前缀，返回实验目录。"""
    candidate = Path(target)
    if candidate.is_dir():
        return candidate
    matches = sorted(experiments_dir(root).glob(f"{target}*")) if target else []
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ExperimentError(f"找不到实验：{target}")
    raise ExperimentError(f"前缀 {target!r} 匹配多个实验：{[m.name for m in matches]}")


def create_experiment(
    root: Path,
    slug: str,
    *,
    hypothesis: str,
    metric: str,
    criteria: list[str],
    falsification: str,
    seed: int | None = None,
    run_cmd: str | None = None,
) -> Path:
    """创建预注册实验目录（manifest + hypothesis.md + run.sh），返回其路径。"""
    clean_criteria = [c.strip() for c in criteria if c and c.strip()]
    if not clean_criteria:
        raise ExperimentError("至少需要一条判据；判据必须在跑实验之前给出。")
    if not hypothesis.strip():
        raise ExperimentError("假设不能为空。")
    if not metric.strip():
        raise ExperimentError("指标不能为空。")
    if not falsification.strip():
        raise ExperimentError("证伪路径不能为空：先写下什么结果会让你放弃该假设，再创建实验。")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ExperimentError("seed 必须是整数。")

    experiment_id = next_experiment_id(root)
    exp_dir = experiments_dir(root) / f"{experiment_id}-{slugify(slug)}"
    if exp_dir.exists():
        raise ExperimentError(f"实验目录已存在：{exp_dir}")

    hypothesis_md = HYPOTHESIS_TEMPLATE.format(
        experiment_id=experiment_id,
        slug=exp_dir.name.removeprefix(f"{experiment_id}-"),
        hypothesis=hypothesis.strip(),
        metric=metric.strip(),
        criteria="\n".join(f"- [ ] {c}" for c in clean_criteria),
        falsification=falsification.strip(),
        seed=seed if seed is not None else "<待定>",
    )
    block = preregistration_block(
        hypothesis=hypothesis,
        metric=metric,
        criteria=clean_criteria,
        falsification=falsification,
        seed=seed,
        hypothesis_md=hypothesis_md,
    )
    prior_refutations = find_prior_refutations(root, str(block["criteria_sha256"]))

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": experiment_id,
        "slug": exp_dir.name.removeprefix(f"{experiment_id}-"),
        "hypothesis": hypothesis.strip(),
        "metric": metric.strip(),
        "criteria": clean_criteria,
        "falsification": falsification.strip(),
        "seed": seed,
        "status": STATUS_PREREGISTERED,
        "created_at": utc_now(),
        "git_commit": git_commit(root),
        "preregistration": block,
        "history": [
            {"status": STATUS_PREREGISTERED, "at": utc_now(), "reason": "预注册", "actor": "cli"}
        ],
    }
    if prior_refutations:
        manifest["prior_refutations"] = prior_refutations

    exp_dir.mkdir(parents=True)
    save_manifest(exp_dir, manifest)
    (exp_dir / "hypothesis.md").write_text(hypothesis_md, encoding="utf-8")
    run_sh = exp_dir / "run.sh"
    run_sh.write_text(
        RUN_SH_TEMPLATE.format(
            experiment_id=experiment_id,
            seed=seed if seed is not None else 0,
            default_run=run_cmd or "python -m your_module.train --seed ${SEED}",
        ),
        encoding="utf-8",
    )
    run_sh.chmod(0o755)
    return exp_dir


def load_manifest(exp_dir: Path) -> dict[str, Any]:
    """读取并解析 manifest；失败时抛出带路径的 ExperimentError。"""
    path = exp_dir / "experiment.json"
    if not path.is_file():
        raise ExperimentError(f"缺少 manifest：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExperimentError(f"manifest 不是合法 JSON：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise ExperimentError(f"manifest 必须是 JSON 对象：{path}")
    return data


def save_manifest(exp_dir: Path, manifest: dict[str, Any]) -> None:
    """原子性写入 manifest（先写临时文件再替换）。"""
    path = exp_dir / "experiment.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def set_status(
    exp_dir: Path,
    new_status: str,
    *,
    reason: str | None = None,
    metrics_path: Path | None = None,
) -> dict[str, Any]:
    """推进实验状态；非法转移或缺少必要证据时抛 ExperimentError。"""
    if new_status not in ALL_STATUSES:
        raise ExperimentError(f"未知状态 {new_status!r}；可用：{', '.join(sorted(ALL_STATUSES))}")
    manifest = load_manifest(exp_dir)
    current = manifest.get("status")
    allowed = ALLOWED_TRANSITIONS.get(str(current), frozenset())
    if new_status not in allowed:
        raise ExperimentError(
            f"非法状态转移 {current} -> {new_status}；"
            f"从 {current} 只能转到：{', '.join(sorted(allowed)) or '（终态，不可变更）'}"
        )
    if new_status in TERMINAL_STATUSES:
        if metrics_path is None:
            raise ExperimentError(f"进入终态 {new_status} 必须提供 --metrics（可解析的指标文件）。")
        if not metrics_path.is_file():
            raise ExperimentError(f"指标文件不存在：{metrics_path}")
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ExperimentError(f"指标文件不是合法 JSON：{metrics_path}（{exc}）") from exc
        if not isinstance(metrics, dict) or not metrics:
            raise ExperimentError(f"指标文件必须是非空 JSON 对象：{metrics_path}")
    entry: dict[str, Any] = {"status": new_status, "at": utc_now(), "actor": "cli"}
    if reason:
        entry["reason"] = reason
    if metrics_path is not None:
        entry["metrics"] = str(metrics_path)
    manifest["status"] = new_status
    manifest.setdefault("history", []).append(entry)
    save_manifest(exp_dir, manifest)
    return manifest
