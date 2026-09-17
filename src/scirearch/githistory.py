"""git 时序证据：预注册必须严格早于结果，且冻结后不可编辑。

只在实验目录内执行只读 git 命令（`rev-parse` / `log` / `show` / `merge-base`）。
任何失败都降级为"不可判定"，由调用方决定其严重性（本仓库：警告，CI 用完整历史裁定）。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT = 10


@dataclass(frozen=True)
class RepoState:
    """实验目录所处的 git 状态。"""

    in_repo: bool
    shallow: bool
    prefix: str  # 仓库根到该目录的相对前缀（以 / 结尾；位于根目录时为空串）


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # git 缺失或超时
        return subprocess.CompletedProcess(["git", *args], 127, "", str(exc))


def repo_state(cwd: Path) -> RepoState:
    """检测工作树状态；不可判定时 `in_repo=False`。"""
    inside = _git(cwd, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return RepoState(in_repo=False, shallow=False, prefix="")
    shallow = _git(cwd, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    prefix = _git(cwd, "rev-parse", "--show-prefix").stdout.strip()
    return RepoState(in_repo=True, shallow=shallow, prefix=prefix)


def first_add_commit(cwd: Path, rel_path: str) -> str | None:
    """返回引入该路径的最早提交（`rel_path` 相对仓库根）；未跟踪时返回 None。"""
    out = _git(cwd, "log", "--diff-filter=A", "--format=%H", "--", f":(top){rel_path}")
    lines = [line for line in out.stdout.splitlines() if line.strip()]
    if out.returncode != 0 or not lines:
        return None
    return lines[-1]


def blob_text(cwd: Path, rev: str, rel_path: str) -> str | None:
    """读取某提交中的文件内容（`rel_path` 相对仓库根）。"""
    out = _git(cwd, "show", f"{rev}:{rel_path}")
    return out.stdout if out.returncode == 0 else None


def is_ancestor(cwd: Path, ancestor: str, descendant: str) -> bool:
    """`ancestor` 是否为 `descendant` 的祖先（含相等时为 True，故调用方先排除相等）。"""
    return _git(cwd, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0
