"""合同校验与汇总：把"结论是否可被验证"变成可执行判断。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scirearch.experiment import (
    EXPERIMENTS_DIRNAME,
    ID_PREFIX,
    REQUIRED_MANIFEST_KEYS,
    SCHEMA_VERSION,
    STATUS_PREREGISTERED,
    TERMINAL_STATUSES,
    ExperimentError,
    load_manifest,
)


@dataclass(frozen=True)
class CheckResult:
    """单个实验的合同校验结果。"""

    id: str
    slug: str
    path: str
    status: str
    ok: bool
    problems: tuple[str, ...] = ()
    seed: int | None = None
    commit: str | None = None
    has_metrics: bool = False
    log_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "path": self.path,
            "status": self.status,
            "ok": self.ok,
            "problems": list(self.problems),
            "seed": self.seed,
            "commit": self.commit,
            "has_metrics": self.has_metrics,
            "log_files": self.log_files,
        }


@dataclass
class _State:
    problems: list[str] = field(default_factory=list)
    seed: int | None = None
    commit: str | None = None
    has_metrics: bool = False
    log_files: int = 0

    def fail(self, message: str) -> None:
        self.problems.append(message)


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
    for key in ("hypothesis", "metric"):
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            state.fail(f"{key} 必须是非空字符串")
    criteria = manifest.get("criteria")
    if not isinstance(criteria, list) or not [
        c for c in criteria if isinstance(c, str) and c.strip()
    ]:
        state.fail("criteria 必须包含至少一条非空判据（判据先于结果）")
    seed = manifest.get("seed")
    if isinstance(seed, bool) or (seed is not None and not isinstance(seed, int)):
        state.fail(f"seed 必须是整数或 null，实际 {seed!r}")
    elif isinstance(seed, int):
        state.seed = seed
    commit = manifest.get("git_commit")
    state.commit = commit if isinstance(commit, str) else None
    status = manifest.get("status")
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


def _check_evidence(exp_dir: Path, status: str, state: _State) -> None:
    metrics_path = exp_dir / "metrics.json"
    state.has_metrics = metrics_path.is_file()
    state.log_files = _count_logs(exp_dir)

    if state.has_metrics:
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            state.fail(f"metrics.json 不是合法 JSON：{exc}")
        else:
            if not isinstance(metrics, dict) or not metrics:
                state.fail("metrics.json 必须是非空 JSON 对象")

    # 预注册的牙齿：判据承诺在先，结果不得先于状态推进出现。
    if status == STATUS_PREREGISTERED and state.has_metrics:
        state.fail("预注册违规：status=preregistered 时已存在 metrics.json（判据必须早于结果）")

    if status in TERMINAL_STATUSES:
        if not state.has_metrics:
            state.fail("终态缺少 metrics.json")
        if state.log_files == 0:
            state.fail("终态缺少非空原始日志（logs/ 为空）")
        if state.seed is None:
            state.fail("终态缺少 seed")


def _check_run_sh(exp_dir: Path, state: _State) -> None:
    run_sh = exp_dir / "run.sh"
    if not run_sh.is_file():
        state.fail("缺少可重跑入口 run.sh")
        return
    if not os.access(run_sh, os.X_OK):
        state.fail("run.sh 不可执行（chmod +x run.sh）")


def check_experiment(exp_dir: Path) -> CheckResult:
    """校验单个实验目录，返回结构化结果（不抛异常）。"""
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
        )

    status = _check_manifest_shape(manifest, state)
    _check_history(manifest, status, state)
    _check_evidence(exp_dir, status, state)
    _check_run_sh(exp_dir, state)

    return CheckResult(
        id=str(manifest.get("id", exp_id)),
        slug=str(manifest.get("slug", slug)),
        path=str(exp_dir),
        status=status or "unknown",
        ok=not state.problems,
        problems=tuple(state.problems),
        seed=state.seed,
        commit=state.commit,
        has_metrics=state.has_metrics,
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


def render_report(results: list[CheckResult]) -> str:
    """把校验结果渲染成 markdown 汇总表（写作阶段的数据来源）。"""
    if not results:
        return "无实验。\n"
    lines = [
        "| 实验 | 状态 | seed | 证据 | commit | 合同 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        evidence = f"{'metrics' if r.has_metrics else '—'}+{r.log_files}log"
        lines.append(
            f"| {r.id} {r.slug} | {r.status} | {r.seed if r.seed is not None else '—'} "
            f"| {evidence} | {r.commit or '—'} | {'✅' if r.ok else '❌'} |"
        )
    passed = sum(1 for r in results if r.ok)
    lines.append("")
    lines.append(f"共 {len(results)} 个实验：{passed} 通过 / {len(results) - passed} 失败。")
    for r in results:
        for problem in r.problems:
            lines.append(f"- ❌ {r.id}: {problem}")
    return "\n".join(lines) + "\n"
