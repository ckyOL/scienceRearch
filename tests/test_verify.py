"""合同校验的行为测试：每条规则都必须能随实现失败。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scirearch.experiment import create_experiment, load_manifest, save_manifest, set_status
from scirearch.verify import check_experiment, render_report, verify_tree


def _preregister(root: Path, *, seed: int | None = 1729, slug: str = "baseline") -> Path:
    return create_experiment(
        root,
        slug,
        hypothesis="固定 seed 下方差小于 1%",
        metric="std(accuracy)",
        criteria=["std < 0.01"],
        seed=seed,
    )


def _write_metrics(exp_dir: Path) -> Path:
    path = exp_dir / "metrics.json"
    path.write_text(json.dumps({"std": 0.0031}), encoding="utf-8")
    return path


def _write_log(exp_dir: Path, text: str = "epoch 1 accuracy 0.9\n") -> None:
    logs = exp_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "run-1.log").write_text(text, encoding="utf-8")


def test_preregistered_experiment_passes(tmp_path: Path) -> None:
    result = check_experiment(_preregister(tmp_path))

    assert result.ok, result.problems
    assert result.status == "preregistered"
    assert result.id == "exp-0001"


def test_results_before_preregistration_is_a_violation(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    _write_metrics(exp_dir)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("预注册违规" in problem for problem in result.problems)


def test_terminal_status_requires_seed_logs_and_metrics(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    metrics = _write_metrics(exp_dir)
    set_status(exp_dir, "running")
    set_status(exp_dir, "completed", metrics_path=metrics)

    result = check_experiment(exp_dir)
    assert not result.ok
    assert any("原始日志" in problem for problem in result.problems)

    _write_log(exp_dir)
    assert check_experiment(exp_dir).ok


def test_terminal_without_seed_fails(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path, seed=None)
    metrics = _write_metrics(exp_dir)
    _write_log(exp_dir)
    set_status(exp_dir, "running")
    set_status(exp_dir, "completed", metrics_path=metrics)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("seed" in problem for problem in result.problems)


def test_non_executable_run_sh_is_detected(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    os.chmod(exp_dir / "run.sh", 0o644)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("可执行" in problem for problem in result.problems)


def test_empty_log_file_does_not_count_as_evidence(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    metrics = _write_metrics(exp_dir)
    _write_log(exp_dir, text="")
    set_status(exp_dir, "running")
    set_status(exp_dir, "completed", metrics_path=metrics)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert result.log_files == 0


def test_broken_manifest_is_reported_not_raised(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    (exp_dir / "experiment.json").write_text("{ oops", encoding="utf-8")

    result = check_experiment(exp_dir)

    assert not result.ok
    assert result.status == "unknown"
    assert any("JSON" in problem for problem in result.problems)


def test_hand_edited_status_is_detected_via_history(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["status"] = "completed"  # 绕过 CLI 手工改状态
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("history 与 status 不一致" in problem for problem in result.problems)


def test_verify_tree_and_report_cover_all_experiments(tmp_path: Path) -> None:
    good = _preregister(tmp_path, slug="good")
    metrics = _write_metrics(good)
    _write_log(good)
    set_status(good, "running")
    set_status(good, "completed", metrics_path=metrics)
    _preregister(tmp_path, slug="bad")
    (tmp_path / "experiments" / "exp-0002-bad" / "run.sh").unlink()

    results = verify_tree(tmp_path)
    report = render_report(results)

    assert [r.id for r in results] == ["exp-0001", "exp-0002"]
    assert "共 2 个实验：1 通过 / 1 失败。" in report
    assert "| exp-0001 good | completed | 1729 | metrics+1log |" in report
    assert "exp-0002: 缺少可重跑入口 run.sh" in report


def test_verify_tree_is_empty_for_fresh_repo(tmp_path: Path) -> None:
    assert verify_tree(tmp_path) == []
    assert render_report([]) == "无实验。\n"
