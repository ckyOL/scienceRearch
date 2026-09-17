"""git 时序防火墙：预注册提交必须严格早于结果提交，且冻结后不得编辑。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scirearch.experiment import (
    create_experiment,
    criteria_sha256,
    load_manifest,
    preregistration_record_sha256,
    save_manifest,
    set_status,
)
from scirearch.verify import check_experiment

GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(GIT is None, reason="需要 git 可执行文件")


def _git(root: Path, *args: str) -> None:
    assert GIT is not None
    subprocess.run(
        [GIT, "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True
    )


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "--no-gpg-sign",
        "-m",
        message,
    )


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")


def _preregister(root: Path, slug: str = "baseline") -> Path:
    return create_experiment(
        root,
        slug,
        hypothesis="固定 seed 下方差小于 1%",
        metric="std(accuracy)",
        criteria=["std < 0.01"],
        falsification="方差超过 1% 则放弃",
        seed=1729,
    )


def _finish(exp_dir: Path, status: str, metrics: dict[str, object]) -> None:
    metrics_path = exp_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    logs = exp_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "run-1.log").write_text("epoch 1 accuracy 0.9\n", encoding="utf-8")
    set_status(exp_dir, "running")
    set_status(exp_dir, status, metrics_path=metrics_path)


def test_prereg_commit_before_results_is_provable(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    exp_dir = _preregister(tmp_path)
    _commit(tmp_path, "prereg")
    _finish(exp_dir, "completed", {"std": 0.0031})
    _commit(tmp_path, "results")

    result = check_experiment(exp_dir)

    assert result.ok, (*result.problems, *result.inconsistencies)
    assert result.warnings == ()


def test_same_commit_for_prereg_and_results_is_a_violation(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    exp_dir = _preregister(tmp_path)
    _finish(exp_dir, "completed", {"std": 0.0031})
    _commit(tmp_path, "prereg 与结果挤在一个提交里")

    result = check_experiment(exp_dir)

    assert any("时序违规" in problem for problem in result.problems)


def test_criteria_edit_after_freeze_is_caught_by_history(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    exp_dir = _preregister(tmp_path)
    _commit(tmp_path, "prereg")
    _finish(exp_dir, "completed", {"std": 0.0031})
    _commit(tmp_path, "results")

    # 攻击者同时重算本地哈希：只改判据、不更新哈希会被本地检查拦住，
    # 全部重算则只有 git 历史能证明"冻结后编辑"。
    manifest = load_manifest(exp_dir)
    manifest["criteria"] = ["std < 0.5"]
    block = manifest["preregistration"]
    block["criteria_sha256"] = criteria_sha256(manifest["criteria"])
    block["record_sha256"] = preregistration_record_sha256(
        hypothesis=manifest["hypothesis"],
        metric=manifest["metric"],
        criteria=manifest["criteria"],
        falsification=manifest["falsification"],
        seed=manifest["seed"],
    )
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert not any("sha256 与登记值不一致" in p for p in result.problems)
    assert any("冻结提交" in problem for problem in result.problems)


def test_uncommitted_terminal_experiment_warns_without_blocking(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    exp_dir = _preregister(tmp_path)
    _finish(exp_dir, "completed", {"std": 0.0031})

    result = check_experiment(exp_dir)

    assert result.ok, (*result.problems, *result.inconsistencies)
    assert any("git 时序不可判定" in warning for warning in result.warnings)


def test_outside_git_repo_warns_without_blocking(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path / "plain")
    _finish(exp_dir, "completed", {"std": 0.0031})

    result = check_experiment(exp_dir)

    assert result.ok, (*result.problems, *result.inconsistencies)
    assert any("git 时序不可判定" in warning for warning in result.warnings)
