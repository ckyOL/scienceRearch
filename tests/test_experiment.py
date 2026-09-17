"""预注册与状态机的行为测试。"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scirearch.experiment import (
    ExperimentError,
    create_experiment,
    load_manifest,
    next_experiment_id,
    set_status,
    slugify,
)


def _create(root: Path, slug: str = "baseline", **overrides: object) -> Path:
    kwargs: dict[str, object] = {
        "hypothesis": "固定 seed 下方差小于 1%",
        "metric": "std(accuracy)",
        "criteria": ["std < 0.01", "无 NaN"],
        "seed": 1729,
    }
    kwargs.update(overrides)
    return create_experiment(root, slug, **kwargs)  # type: ignore[arg-type]


def _write_metrics(exp_dir: Path, payload: dict[str, object] | None = None) -> Path:
    path = exp_dir / "metrics.json"
    path.write_text(json.dumps(payload or {"std": 0.0031}), encoding="utf-8")
    return path


def _write_log(exp_dir: Path) -> None:
    logs = exp_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "run-1.log").write_text(
        "# cmd: python train.py\nepoch 1 accuracy 0.9\n", encoding="utf-8"
    )


def test_create_writes_full_preregistration_bundle(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)

    assert exp_dir.parent == tmp_path / "experiments"
    assert exp_dir.name == "exp-0001-baseline"

    manifest = load_manifest(exp_dir)
    assert manifest["schema_version"] == 1
    assert manifest["status"] == "preregistered"
    assert manifest["seed"] == 1729
    assert manifest["criteria"] == ["std < 0.01", "无 NaN"]
    assert manifest["history"][-1]["status"] == "preregistered"
    assert manifest["git_commit"] is None  # tmp_path 不是 git 仓库

    hypothesis = (exp_dir / "hypothesis.md").read_text(encoding="utf-8")
    assert "std < 0.01" in hypothesis

    run_sh = exp_dir / "run.sh"
    assert run_sh.stat().st_mode & stat.S_IXUSR
    assert "SEED:-1729" in run_sh.read_text(encoding="utf-8")


def test_ids_increment_and_slugs_are_normalized(tmp_path: Path) -> None:
    first = _create(tmp_path, slug="Fixed Seed / Baseline")
    second = _create(tmp_path, slug="another")

    assert first.name == "exp-0001-fixed-seed-baseline"
    assert second.name == "exp-0002-another"
    assert next_experiment_id(tmp_path) == "exp-0003"
    assert slugify("  A B  ") == "a-b"
    with pytest.raises(ExperimentError):
        slugify("///")


def test_missing_criteria_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExperimentError, match="判据"):
        _create(tmp_path, criteria=["   "])


def test_terminal_status_requires_parsable_metrics(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)
    set_status(exp_dir, "running")

    with pytest.raises(ExperimentError, match="--metrics"):
        set_status(exp_dir, "completed")

    bad = exp_dir / "metrics.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ExperimentError, match="不是合法 JSON"):
        set_status(exp_dir, "completed", metrics_path=bad)

    metrics = _write_metrics(exp_dir)
    manifest = set_status(exp_dir, "completed", metrics_path=metrics, reason="判据满足")

    assert manifest["status"] == "completed"
    assert manifest["history"][-1]["reason"] == "判据满足"
    assert manifest["history"][-1]["metrics"].endswith("metrics.json")


def test_status_machine_rejects_skips_and_terminal_changes(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)
    metrics = _write_metrics(exp_dir)

    with pytest.raises(ExperimentError, match="非法状态转移"):
        set_status(exp_dir, "completed", metrics_path=metrics)

    set_status(exp_dir, "running")
    set_status(exp_dir, "completed", metrics_path=metrics)

    with pytest.raises(ExperimentError, match="终态"):
        set_status(exp_dir, "running")

    with pytest.raises(ExperimentError, match="未知状态"):
        set_status(exp_dir, "approved")


def test_refuted_runs_keep_their_evidence(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)
    metrics = _write_metrics(exp_dir, {"std": 0.42})

    set_status(exp_dir, "running")
    manifest = set_status(exp_dir, "refuted", metrics_path=metrics, reason="方差超标")

    assert manifest["status"] == "refuted"
    assert [entry["status"] for entry in manifest["history"]] == [
        "preregistered",
        "running",
        "refuted",
    ]
