"""合同校验的行为测试：每条规则都必须能随实现失败。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scirearch.experiment import (
    create_experiment,
    load_manifest,
    save_manifest,
    set_status,
)
from scirearch.verify import (
    EXIT_CRITERIA_CONFLICT,
    EXIT_PASS,
    check_experiment,
    exit_code,
    refuted_index,
    render_report,
    verify_tree,
)


def _preregister(
    root: Path,
    *,
    seed: int | None = 1729,
    slug: str = "baseline",
    criteria: list[str] | None = None,
) -> Path:
    return create_experiment(
        root,
        slug,
        hypothesis="固定 seed 下方差小于 1%",
        metric="std(accuracy)",
        criteria=criteria if criteria is not None else ["std < 0.01"],
        falsification="方差超过 1% 则放弃",
        seed=seed,
    )


def _write_metrics(exp_dir: Path, payload: dict[str, object] | None = None) -> Path:
    path = exp_dir / "metrics.json"
    path.write_text(json.dumps(payload or {"std": 0.0031}), encoding="utf-8")
    return path


def _write_log(exp_dir: Path, text: str = "epoch 1 accuracy 0.9\n") -> None:
    logs = exp_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "run-1.log").write_text(text, encoding="utf-8")


def _force_status(exp_dir: Path, status: str, *, metrics_path: Path | None = None) -> None:
    """绕过 CLI 直接写下状态：模拟旧版 CLI / 手工编辑，用于验证 verify 的检出能力。"""
    manifest = load_manifest(exp_dir)
    if manifest["status"] == "preregistered":
        manifest["history"].append({"status": "running", "actor": "cli"})
    manifest["status"] = status
    entry: dict[str, object] = {"status": status, "actor": "cli"}
    if metrics_path is not None:
        entry["metrics"] = str(metrics_path)
    manifest["history"].append(entry)
    save_manifest(exp_dir, manifest)


def _force_terminal(exp_dir: Path, status: str, *, metrics: dict[str, object]) -> None:
    """写齐 metrics 与日志后绕过 CLI 落终态（供"状态与判据冲突"类用例构造现场）。"""
    path = _write_metrics(exp_dir, metrics)
    _write_log(exp_dir)
    _force_status(exp_dir, status, metrics_path=path)


def _run_to_terminal(exp_dir: Path, status: str, *, metrics: dict[str, object]) -> None:
    path = _write_metrics(exp_dir, metrics)
    _write_log(exp_dir)
    set_status(exp_dir, "running")
    set_status(exp_dir, status, metrics_path=path)


def test_preregistered_experiment_passes(tmp_path: Path) -> None:
    result = check_experiment(_preregister(tmp_path))

    assert result.ok, result.problems
    assert result.status == "preregistered"
    assert result.id == "exp-0001"
    assert [o.state for o in result.criteria] == ["pending"]


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
    _force_status(exp_dir, "completed", metrics_path=metrics)  # 旧版 CLI 允许无日志的终态

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
    _force_status(exp_dir, "completed", metrics_path=metrics)

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
    _force_status(exp_dir, "completed", metrics_path=metrics)

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


def test_completed_with_violated_criterion_is_a_conflict(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    _force_terminal(exp_dir, "completed", metrics={"std": 0.42})

    result = check_experiment(exp_dir)

    assert not result.ok
    assert exit_code([result]) == EXIT_CRITERIA_CONFLICT
    assert any("判据被违反却标记为 completed" in c for c in result.inconsistencies)
    assert result.problems == ()


def test_refuted_with_violated_criterion_passes(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    _run_to_terminal(exp_dir, "refuted", metrics={"std": 0.42})

    result = check_experiment(exp_dir)

    assert result.ok, (*result.problems, *result.inconsistencies)
    assert exit_code([result]) == EXIT_PASS
    assert [o.state for o in result.criteria] == ["violated"]


def test_refuted_with_all_criteria_satisfied_is_a_conflict(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    _force_terminal(exp_dir, "refuted", metrics={"std": 0.0031})

    result = check_experiment(exp_dir)

    assert exit_code([result]) == EXIT_CRITERIA_CONFLICT
    assert any("全部满足却标记为 refuted" in c for c in result.inconsistencies)


def test_criterion_referencing_missing_metric_is_a_contract_problem(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    _force_terminal(exp_dir, "completed", metrics={"other": 1})

    result = check_experiment(exp_dir)

    assert any("无法裁决" in problem for problem in result.problems)
    assert exit_code([result]) == 1


def test_free_text_criterion_is_marked_for_human_review(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path, criteria=["无 NaN"])
    _run_to_terminal(exp_dir, "completed", metrics={"std": 0.0031})

    result = check_experiment(exp_dir)
    report = render_report([result])

    assert result.ok, result.problems
    assert [o.decided_by for o in result.criteria] == ["human"]
    assert "人工裁定（自由文本判据）[人工]" in report


def test_criteria_drift_in_manifest_is_detected(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["criteria"] = ["std < 0.5"]
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("criteria 的 sha256 与登记值不一致" in p for p in result.problems)


def test_mirror_edit_is_detected(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    mirror = exp_dir / "hypothesis.md"
    mirror.write_text(mirror.read_text(encoding="utf-8") + "\n事后加一句\n", encoding="utf-8")

    result = check_experiment(exp_dir)

    assert any("hypothesis.md 的 sha256 与登记值不一致" in p for p in result.problems)


def test_falsification_edit_is_detected(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["falsification"] = "事后放宽的证伪路径"
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("预注册记录" in p for p in result.problems)


def test_invalid_seed_reports_shape_problem_without_hash_noise(tmp_path: Path) -> None:
    exp_dir = _preregister(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["seed"] = "不是整数"
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("seed 必须是整数" in problem for problem in result.problems)
    # 类型错误已由 shape 检查报告；预注册记录哈希不应再产生级联噪声。
    assert not any("预注册记录" in problem for problem in result.problems)


def test_negative_index_binds_refuted_criteria_to_experiment(tmp_path: Path) -> None:
    refuted = _preregister(tmp_path, slug="falsified")
    _run_to_terminal(refuted, "refuted", metrics={"std": 0.42})

    results = verify_tree(tmp_path)
    index = refuted_index(results)
    report = render_report(results)

    assert [entry["id"] for entry in index] == ["exp-0001"]
    assert index[0]["criteria_sha256"] == check_experiment(refuted).criteria_sha256
    assert "负知识索引（已证伪判据）" in report
    assert "重提前需给出新证据" in report


def test_verify_tree_and_report_cover_all_experiments(tmp_path: Path) -> None:
    good = _preregister(tmp_path, slug="good")
    _run_to_terminal(good, "completed", metrics={"std": 0.0031})
    _preregister(tmp_path, slug="bad")
    (tmp_path / "experiments" / "exp-0002-bad" / "run.sh").unlink()

    results = verify_tree(tmp_path)
    report = render_report(results)

    assert [r.id for r in results] == ["exp-0001", "exp-0002"]
    assert "共 2 个实验：1 通过 / 1 失败" in report
    assert "| exp-0001 good | completed | 1 满足 | 1729 | metrics+1log |" in report
    assert "exp-0002: 缺少可重跑入口 run.sh" in report
    assert "不是自动 attestation" in report


def test_verify_tree_is_empty_for_fresh_repo(tmp_path: Path) -> None:
    assert verify_tree(tmp_path) == []
    assert render_report([]) == "无实验。\n"
