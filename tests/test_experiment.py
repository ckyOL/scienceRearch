"""预注册与状态机的行为测试。"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scirearch.experiment import (
    SCHEMA_VERSION,
    ExperimentError,
    StatusRejected,
    canonical_text_sha256,
    create_experiment,
    criteria_sha256,
    find_prior_refutations,
    load_manifest,
    next_experiment_id,
    preregistration_record_sha256,
    set_status,
    slugify,
)


def _create(root: Path, slug: str = "baseline", **overrides: object) -> Path:
    kwargs: dict[str, object] = {
        "hypothesis": "固定 seed 下方差小于 1%",
        "metric": "std(accuracy)",
        "criteria": ["std < 0.01", "无 NaN"],
        "falsification": "5 个 seed 的 std 大于 0.01 则放弃该假设",
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
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["status"] == "preregistered"
    assert manifest["seed"] == 1729
    assert manifest["criteria"] == ["std < 0.01", "无 NaN"]
    assert manifest["falsification"] == "5 个 seed 的 std 大于 0.01 则放弃该假设"
    assert manifest["history"][-1]["status"] == "preregistered"
    assert manifest["git_commit"] is None  # tmp_path 不是 git 仓库
    assert "prior_refutations" not in manifest

    hypothesis = (exp_dir / "hypothesis.md").read_text(encoding="utf-8")
    assert "std < 0.01" in hypothesis
    assert "5 个 seed 的 std 大于 0.01 则放弃该假设" in hypothesis

    block = manifest["preregistration"]
    assert block["algorithm"] == "sha256"
    assert block["criteria_sha256"] == criteria_sha256(manifest["criteria"])
    assert block["hypothesis_md_sha256"] == canonical_text_sha256(hypothesis)
    assert block["record_sha256"] == preregistration_record_sha256(
        hypothesis=manifest["hypothesis"],
        metric=manifest["metric"],
        criteria=manifest["criteria"],
        falsification=manifest["falsification"],
        seed=manifest["seed"],
    )

    run_sh = exp_dir / "run.sh"
    assert run_sh.stat().st_mode & stat.S_IXUSR
    assert "SEED:-1729" in run_sh.read_text(encoding="utf-8")


def test_hashes_pin_content_not_formatting() -> None:
    # 空白折叠：格式变体视为同一判据（负知识索引不能因空格差异而漏配）。
    assert criteria_sha256(["std < 0.01"]) == criteria_sha256(["std<0.01"])
    # 顺序与内容受保护：增删、改序都改变哈希。
    assert criteria_sha256(["a < 1", "b < 2"]) != criteria_sha256(["b < 2", "a < 1"])
    assert criteria_sha256(["a < 1"]) != criteria_sha256(["a < 1", "b < 2"])
    # 记录哈希覆盖证伪路径：只改证伪路径也必须改变哈希。
    common = {"hypothesis": "h", "metric": "m", "criteria": ["a < 1"], "seed": 1}
    assert preregistration_record_sha256(falsification="x", **common) != (
        preregistration_record_sha256(falsification="y", **common)
    )


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


def test_missing_falsification_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExperimentError, match="证伪路径"):
        _create(tmp_path, falsification="   ")


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
    _write_log(exp_dir)
    manifest = set_status(exp_dir, "completed", metrics_path=metrics, reason="判据满足")

    assert manifest["status"] == "completed"
    assert manifest["history"][-1]["reason"] == "判据满足"
    assert manifest["history"][-1]["metrics"].endswith("metrics.json")
    # 状态推进不得触碰预注册块。
    assert manifest["preregistration"] == load_manifest(exp_dir)["preregistration"]


def test_status_machine_rejects_skips_and_terminal_changes(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)
    metrics = _write_metrics(exp_dir)
    _write_log(exp_dir)

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
    _write_log(exp_dir)

    set_status(exp_dir, "running")
    manifest = set_status(exp_dir, "refuted", metrics_path=metrics, reason="方差超标")

    assert manifest["status"] == "refuted"
    assert [entry["status"] for entry in manifest["history"]] == [
        "preregistered",
        "running",
        "refuted",
    ]


def test_status_refuses_verdict_that_contradicts_criteria(tmp_path: Path) -> None:
    exp_dir = _create(tmp_path)
    metrics = _write_metrics(exp_dir, {"std": 0.42})
    _write_log(exp_dir)
    set_status(exp_dir, "running")

    with pytest.raises(StatusRejected, match="判据被违反却标记为 completed") as excinfo:
        set_status(exp_dir, "completed", metrics_path=metrics)

    assert excinfo.value.status == "completed"
    assert excinfo.value.conflicts and not excinfo.value.problems
    # 拒绝即不落盘：status 与 history 都保持原样（终态不可回退，写了就无法修复）。
    manifest = load_manifest(exp_dir)
    assert manifest["status"] == "running"
    assert [entry["status"] for entry in manifest["history"]] == ["preregistered", "running"]


def test_reproposed_refuted_criteria_hit_negative_knowledge(tmp_path: Path) -> None:
    refuted = _create(tmp_path, slug="first", criteria=["std < 0.01"])
    metrics = _write_metrics(refuted, {"std": 0.42})
    _write_log(refuted)
    set_status(refuted, "running")
    set_status(refuted, "refuted", metrics_path=metrics)

    assert find_prior_refutations(tmp_path, criteria_sha256(["std < 0.01"])) == ["exp-0001"]

    # 空白变体命中同一判据；不同判据不命中。
    repeat = _create(tmp_path, slug="repeat", criteria=["std<0.01"])
    assert load_manifest(repeat)["prior_refutations"] == ["exp-0001"]
    other = _create(tmp_path, slug="other", criteria=["std < 0.05"])
    assert "prior_refutations" not in load_manifest(other)
