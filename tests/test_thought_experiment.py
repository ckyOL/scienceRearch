"""思想实验（kind=thought-experiment）：从"跑不了"到"可合法收口"的合同测试。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scirearch.cli import main
from scirearch.experiment import (
    KIND_EXPERIMENT,
    KIND_THOUGHT,
    ExperimentError,
    StatusRejected,
    canonical_text_sha256,
    create_experiment,
    load_manifest,
    save_manifest,
    set_status,
)
from scirearch.verify import check_experiment, negative_index, render_report, verify_tree

GIT = shutil.which("git")

HYPOTHESIS = "机制 M 是主因（当前无法构造对照条件）"
METRIC = "论证自洽性 / 与既有结论的一致性"
BLOCKERS = "缺少可控干预手段：只能观察，不能随机分配"
CRITERIA = ["论证自洽", "不与既有结论冲突"]


def _experiment(root: Path, slug: str, *, criteria: list[str] | None = None) -> Path:
    return create_experiment(
        root,
        slug,
        hypothesis="固定 seed 下方差小于 1%",
        metric="std(accuracy)",
        criteria=criteria if criteria is not None else ["std < 0.01"],
        falsification="方差超过 1% 则放弃",
        seed=1729,
    )


def _thought(
    root: Path,
    slug: str = "mechanism",
    *,
    criteria: list[str] | None = None,
    blockers: str | None = BLOCKERS,
    seed: int | None = None,
) -> Path:
    return create_experiment(
        root,
        slug,
        kind=KIND_THOUGHT,
        hypothesis=HYPOTHESIS,
        metric=METRIC,
        criteria=criteria if criteria is not None else list(CRITERIA),
        falsification="出现反例或与既有结论冲突即放弃该机制解释",
        blockers=blockers,
        seed=seed,
    )


def _write_reasoning(exp_dir: Path, text: str = "## 论证\n\n前提 1；前提 2；结论成立。\n") -> None:
    (exp_dir / "reasoning.md").write_text(text, encoding="utf-8")


def _write_review(
    exp_dir: Path,
    *,
    verdict: str,
    rulings: list[Any] | None = None,
    reviewer: tuple[str, str] = ("critic", "model-review"),
    generator: tuple[str, str] = ("hypothesizer", "model-generate"),
) -> Path:
    payload = {
        "reviewer": {"agent": reviewer[0], "model": reviewer[1]},
        "generator": {"agent": generator[0], "model": generator[1]},
        "verdict": verdict,
        "rulings": rulings
        if rulings is not None
        else [
            {"criterion": CRITERIA[0], "ruling": "violated", "note": "前提自相矛盾"},
            {"criterion": CRITERIA[1], "ruling": "unclear", "note": "文献不足以判断"},
        ],
        "signed_at": "2026-09-22T00:00:00Z",
    }
    path = exp_dir / "review.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    assert GIT is not None
    subprocess.run([GIT, *args], cwd=root, check=True, capture_output=True)


def test_new_creates_speculative_record_with_reasoning_instead_of_run_sh(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    manifest = load_manifest(exp_dir)

    assert manifest["kind"] == KIND_THOUGHT
    assert manifest["status"] == "speculative"
    assert manifest["blockers"] == BLOCKERS
    assert manifest["seed"] is None
    assert (exp_dir / "reasoning.md").is_file()
    assert not (exp_dir / "run.sh").exists()
    assert "阻碍实验的条件" in (exp_dir / "hypothesis.md").read_text(encoding="utf-8")
    # 无 metrics、无 logs、无 seed 地挂在 speculative 是合法开放态，不是证据。
    assert check_experiment(exp_dir).ok


def test_blockers_are_required_for_thought_and_forbidden_for_experiments(tmp_path: Path) -> None:
    with pytest.raises(ExperimentError, match="阻碍条件"):
        _thought(tmp_path, blockers="   ")
    with pytest.raises(ExperimentError, match="--blockers"):
        create_experiment(
            tmp_path,
            "plain",
            hypothesis="方差小于 1%",
            metric="std(accuracy)",
            criteria=["std < 0.01"],
            falsification="方差超过 1% 则放弃",
            blockers=BLOCKERS,
        )

    assert not (tmp_path / "experiments" / "exp-0001-plain").exists()


def test_thought_experiment_rejects_seed_and_run_cmd(tmp_path: Path) -> None:
    with pytest.raises(ExperimentError, match="不接受 --seed"):
        _thought(tmp_path, seed=7)
    with pytest.raises(ExperimentError, match="不接受 --run-cmd"):
        create_experiment(
            tmp_path,
            "runnable",
            kind=KIND_THOUGHT,
            hypothesis=HYPOTHESIS,
            metric=METRIC,
            criteria=list(CRITERIA),
            falsification="出现反例即放弃",
            blockers=BLOCKERS,
            run_cmd="python train.py",
        )


def test_metrics_json_is_forbidden_in_a_thought_experiment(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    (exp_dir / "metrics.json").write_text('{"std": 0.1}', encoding="utf-8")

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("思想实验不得携带 metrics.json" in problem for problem in result.problems)


def test_statuses_do_not_mix_between_kinds(tmp_path: Path) -> None:
    thought = _thought(tmp_path)
    experiment = _experiment(tmp_path, "baseline")

    with pytest.raises(ExperimentError, match="思想实验不得进入状态 completed"):
        set_status(thought, "completed", metrics_path=tmp_path / "metrics.json")
    with pytest.raises(ExperimentError, match="实验不得进入状态 speculative"):
        set_status(experiment, "speculative")

    assert load_manifest(thought)["status"] == "speculative"
    assert load_manifest(experiment)["status"] == "preregistered"


def test_rejected_requires_a_review_record(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)

    with pytest.raises(ExperimentError, match="--review"):
        set_status(exp_dir, "rejected", reason="论证不成立")

    assert load_manifest(exp_dir)["status"] == "speculative"


def test_rejected_requires_a_nonempty_reasoning_artifact(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir, "   \n")
    review = _write_review(exp_dir, verdict="rejected")

    with pytest.raises(ExperimentError, match="缺少非空论证"):
        set_status(exp_dir, "rejected", review_path=review, reason="论证不成立")


def test_rejected_requires_at_least_one_violated_ruling(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(
        exp_dir,
        verdict="rejected",
        rulings=[
            {"criterion": CRITERIA[0], "ruling": "satisfied", "note": "论证自洽"},
            {"criterion": CRITERIA[1], "ruling": "unclear", "note": "无法判断"},
        ],
    )

    with pytest.raises(StatusRejected, match="rejected") as excinfo:
        set_status(exp_dir, "rejected", review_path=review, reason="论证不成立")

    assert excinfo.value.conflicts
    assert not excinfo.value.problems
    assert load_manifest(exp_dir)["status"] == "speculative"


def test_hand_written_rejected_status_is_detected(tmp_path: Path) -> None:
    """绕过 CLI 写下终态（旧版 CLI / 手工编辑）：verify 仍须检出缺失的论证冻结记录。"""
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    _write_review(exp_dir, verdict="rejected")
    manifest = load_manifest(exp_dir)
    manifest["status"] = "rejected"
    manifest["history"].append({"status": "rejected", "actor": "manual"})
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("reasoning_sha256" in problem for problem in result.problems)


def test_review_must_live_at_the_canonical_path(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")
    outside = tmp_path / "review-copy.json"
    outside.write_text(review.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ExperimentError, match="--review 必须指向"):
        set_status(exp_dir, "rejected", review_path=outside, reason="驳回")

    assert load_manifest(exp_dir)["status"] == "speculative"


def test_rejected_freezes_reasoning_and_edits_are_detected(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")

    manifest = set_status(exp_dir, "rejected", review_path=review, reason="前提自相矛盾")

    reasoning_text = (exp_dir / "reasoning.md").read_text(encoding="utf-8")
    assert manifest["status"] == "rejected"
    assert manifest["history"][-1]["reasoning_sha256"] == canonical_text_sha256(reasoning_text)
    assert check_experiment(exp_dir).ok

    _write_reasoning(exp_dir, "改写后的论证\n")

    result = check_experiment(exp_dir)

    assert not result.ok
    assert any("论证漂移" in problem for problem in result.problems)


def test_review_must_rule_every_criterion(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(
        exp_dir,
        verdict="rejected",
        rulings=[{"criterion": CRITERIA[0], "ruling": "violated", "note": "自相矛盾"}],
    )

    with pytest.raises(StatusRejected, match="未逐条裁定判据") as excinfo:
        set_status(exp_dir, "rejected", review_path=review, reason="驳回")

    assert any(CRITERIA[1] in problem for problem in excinfo.value.problems)


def test_review_verdict_must_match_the_target_status(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="promoted")

    with pytest.raises(StatusRejected, match="verdict"):
        set_status(exp_dir, "rejected", review_path=review, reason="驳回")


def test_review_requires_generator_and_reviewer_separation(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    same_agent = _write_review(
        exp_dir, verdict="rejected", reviewer=("hypothesizer", "model-review")
    )

    with pytest.raises(StatusRejected, match="未分离"):
        set_status(exp_dir, "rejected", review_path=same_agent, reason="驳回")

    same_model = _write_review(exp_dir, verdict="rejected", reviewer=("critic", "model-generate"))

    with pytest.raises(StatusRejected, match="未分离"):
        set_status(exp_dir, "rejected", review_path=same_model, reason="驳回")


def test_promoted_requires_an_existing_experiment_target(tmp_path: Path) -> None:
    thought = _thought(tmp_path)
    _write_reasoning(thought)
    review = _write_review(
        thought,
        verdict="promoted",
        rulings=[
            {"criterion": CRITERIA[0], "ruling": "satisfied", "note": "论证自洽"},
            {"criterion": CRITERIA[1], "ruling": "unclear", "note": "待实验判定"},
        ],
    )

    with pytest.raises(ExperimentError, match="promoted 必须提供 --superseded-by"):
        set_status(thought, "promoted", review_path=review, reason="已可实验")

    with pytest.raises(StatusRejected, match="未解析到唯一的实验目录"):
        set_status(thought, "promoted", review_path=review, superseded_by="exp-0009", reason="x")

    target = _experiment(tmp_path, "followup")
    manifest = set_status(
        thought,
        "promoted",
        review_path=review,
        superseded_by=load_manifest(target)["id"],
        reason="已可构造对照条件，转入正式实验",
    )

    assert manifest["status"] == "promoted"
    assert manifest["superseded_by"] == "exp-0002"
    assert check_experiment(thought).ok
    assert "不构成经验证据" in render_report(verify_tree(tmp_path))


def test_promoted_target_must_be_an_experiment(tmp_path: Path) -> None:
    first = _thought(tmp_path, "first")
    second = _thought(tmp_path, "second")
    _write_reasoning(first)
    review = _write_review(first, verdict="promoted")

    with pytest.raises(StatusRejected, match="不是可执行实验"):
        set_status(
            first,
            "promoted",
            review_path=review,
            superseded_by=load_manifest(second)["id"],
            reason="指向了另一个思想实验",
        )


def test_run_sh_in_a_thought_experiment_is_only_a_warning(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    (exp_dir / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    result = check_experiment(exp_dir)

    assert result.ok
    assert any("run.sh" in warning for warning in result.warnings)


def test_deleting_the_promotion_target_is_detected(tmp_path: Path) -> None:
    """promoted 的引用完整性：目标实验被删除后，verify 必须报悬空引用。"""
    thought = _thought(tmp_path)
    _write_reasoning(thought)
    target = _experiment(tmp_path, "followup")
    review = _write_review(thought, verdict="promoted")
    set_status(
        thought,
        "promoted",
        review_path=review,
        superseded_by=load_manifest(target)["id"],
        reason="转实验",
    )
    assert check_experiment(thought).ok

    shutil.rmtree(target)

    result = check_experiment(thought)
    assert not result.ok
    assert any("悬空引用" in problem for problem in result.problems)


def test_abandoned_closes_without_evidence_but_needs_a_reason(tmp_path: Path) -> None:
    experiment = create_experiment(
        tmp_path,
        "unseeded",
        hypothesis="方差小于 1%",
        metric="std(accuracy)",
        criteria=["std < 0.01"],
        falsification="方差超过 1% 则放弃",
        seed=None,
    )

    with pytest.raises(ExperimentError, match="--reason"):
        set_status(experiment, "abandoned")

    with pytest.raises(ExperimentError, match="只接受 --reason"):
        set_status(experiment, "abandoned", reason="数据拿不到", metrics_path=Path("metrics.json"))

    assert set_status(experiment, "abandoned", reason="数据拿不到").get("status") == "abandoned"
    # 放弃不是结论：不需要 metrics / logs / seed，且不进入负知识索引。
    assert check_experiment(experiment).ok
    assert negative_index(verify_tree(tmp_path)) == []

    thought = _thought(tmp_path, "dropped")
    assert set_status(thought, "abandoned", reason="问题不再重要")["status"] == "abandoned"
    assert check_experiment(thought).ok


def test_rejected_thought_experiment_enters_negative_knowledge(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")
    set_status(exp_dir, "rejected", review_path=review, reason="前提自相矛盾")

    results = verify_tree(tmp_path)
    index = negative_index(results)

    assert [entry["id"] for entry in index] == ["exp-0001"]
    assert index[0]["kind"] == KIND_THOUGHT
    assert index[0]["status"] == "rejected"

    report = render_report(results)
    assert "| exp-0001 mechanism | 思想实验 | rejected |" in report
    assert "违反（复核裁定：前提自相矛盾）[人工]" in report

    repeat = _thought(tmp_path, "repeat")
    assert load_manifest(repeat)["prior_refutations"] == ["exp-0001"]


@pytest.mark.skipif(GIT is None, reason="需要 git 可执行文件")
def test_review_in_the_prereg_commit_is_refused_by_the_gate(tmp_path: Path) -> None:
    """预注册与复核挤进同一提交：时序证据永久失效，闸门拒绝写入终态。"""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "p@p")
    _git(tmp_path, "config", "user.name", "p")
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "prereg + review（同一提交）")

    with pytest.raises(StatusRejected, match="时序违规"):
        set_status(exp_dir, "rejected", review_path=review, reason="驳回")

    assert load_manifest(exp_dir)["status"] == "speculative"


@pytest.mark.skipif(GIT is None, reason="需要 git 可执行文件")
def test_prereg_before_review_commits_passes(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "p@p")
    _git(tmp_path, "config", "user.name", "p")
    exp_dir = _thought(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "prereg")
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "review")

    set_status(exp_dir, "rejected", review_path=review, reason="驳回")

    result = check_experiment(exp_dir)
    assert result.ok
    assert result.warnings == ()


def test_cli_creates_and_closes_a_thought_experiment(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "new",
                "mechanism",
                "--kind",
                KIND_THOUGHT,
                "-H",
                HYPOTHESIS,
                "-m",
                METRIC,
                "-c",
                CRITERIA[0],
                "-f",
                "出现反例即放弃",
                "--blockers",
                BLOCKERS,
            ]
        )
        == 0
    )
    assert "已创建预注册思想实验" in capsys.readouterr().out

    exp_dir = tmp_path / "experiments" / "exp-0001-mechanism"
    _write_reasoning(exp_dir)
    review = _write_review(
        exp_dir,
        verdict="rejected",
        rulings=[{"criterion": CRITERIA[0], "ruling": "violated", "note": "自相矛盾"}],
    )

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "status",
                "exp-0001",
                "rejected",
                "--review",
                str(review),
                "--reason",
                "前提自相矛盾",
            ]
        )
        == 0
    )
    assert main(["--root", str(tmp_path), "verify"]) == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "report", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"][0]["kind"] == KIND_THOUGHT
    assert payload["records"][0]["has_review"] is True
    assert payload["negative_index"][0]["status"] == "rejected"


def test_cli_rejects_blockers_missing_and_metrics_on_a_thought_experiment(
    tmp_path: Path, capsys
) -> None:
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "new",
                "mechanism",
                "--kind",
                KIND_THOUGHT,
                "-H",
                HYPOTHESIS,
                "-m",
                METRIC,
                "-c",
                CRITERIA[0],
                "-f",
                "出现反例即放弃",
            ]
        )
        == 1
    )
    assert "阻碍条件" in capsys.readouterr().err

    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(exp_dir, verdict="rejected")
    metrics = exp_dir / "metrics.json"
    metrics.write_text('{"std": 0.1}', encoding="utf-8")

    code = main(
        [
            "--root",
            str(tmp_path),
            "status",
            "exp-0001",
            "rejected",
            "--review",
            str(review),
            "--metrics",
            str(metrics),
            "--reason",
            "驳回",
        ]
    )

    assert code == 1
    assert "不得提供 --metrics" in capsys.readouterr().err
    assert load_manifest(exp_dir)["status"] == "speculative"


def test_experiment_kind_is_recorded_and_defaults_to_experiment(tmp_path: Path) -> None:
    exp_dir = _experiment(tmp_path, "baseline")
    manifest = load_manifest(exp_dir)

    assert manifest["kind"] == KIND_EXPERIMENT
    assert "blockers" not in manifest
    assert (exp_dir / "run.sh").exists()
    assert not (exp_dir / "reasoning.md").exists()
    assert check_experiment(exp_dir).kind == KIND_EXPERIMENT


def test_kind_and_blockers_are_frozen(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["blockers"] = "换一个理由"
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("预注册漂移" in problem for problem in result.problems)


def test_kind_flip_is_detected(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    manifest = load_manifest(exp_dir)
    manifest["kind"] = KIND_EXPERIMENT
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("预注册漂移" in problem for problem in result.problems)
    assert any("不属于实验" in problem for problem in result.problems)


def test_metrics_json_that_is_not_utf8_is_a_contract_problem(tmp_path: Path) -> None:
    exp_dir = _experiment(tmp_path, "baseline")
    (exp_dir / "metrics.json").write_bytes(b"\xff\xfe\x00")

    result = check_experiment(exp_dir)  # 不得抛异常

    assert not result.ok
    assert any("不可读" in problem for problem in result.problems)


def test_duplicate_criteria_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ExperimentError, match="判据重复"):
        _experiment(tmp_path, "dupes", criteria=["std < 0.01", "std<0.01"])

    exp_dir = _experiment(tmp_path, "plain")
    manifest = load_manifest(exp_dir)
    manifest["criteria"] = ["std < 0.01", "std<0.01"]
    save_manifest(exp_dir, manifest)

    result = check_experiment(exp_dir)

    assert any("重复判据" in problem for problem in result.problems)


def test_promotion_reference_must_match_the_target_id(tmp_path: Path) -> None:
    thought = _thought(tmp_path)
    _write_reasoning(thought)
    target = _experiment(tmp_path, "followup")
    target_manifest = load_manifest(target)
    target_manifest["id"] = "exp-0099"
    save_manifest(target, target_manifest)
    review = _write_review(thought, verdict="promoted")

    with pytest.raises(StatusRejected, match="不一致"):
        set_status(
            thought, "promoted", review_path=review, superseded_by="exp-0002", reason="引用错位"
        )


def test_promotion_reference_rejects_path_traversal(tmp_path: Path) -> None:
    thought = _thought(tmp_path)
    _write_reasoning(thought)
    review = _write_review(thought, verdict="promoted")

    for hostile in (
        "../exp-0001-mechanism",
        "exp-0001/../exp-0001-mechanism",
        "exp-0001\n",
        "exp-0001*",
        "*",
    ):
        # 结尾换行会被 strip 成自身 id（→ 指向自身），其余一律判为悬空引用。
        with pytest.raises(StatusRejected, match=r"未解析到唯一的实验目录|指向自身"):
            set_status(
                thought,
                "promoted",
                review_path=review,
                superseded_by=hostile,
                reason="路径穿越",
            )


def test_reviewer_separation_ignores_whitespace_and_case(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    review = _write_review(
        exp_dir,
        verdict="rejected",
        reviewer=(" Critic ", "MODEL-REVIEW"),
        generator=("critic", "model-review"),
    )

    with pytest.raises(StatusRejected, match="未分离"):
        set_status(exp_dir, "rejected", review_path=review, reason="大小写变体")


def test_malformed_reviews_are_rejected(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    cases: list[list[Any]] = [
        [{"criterion": CRITERIA[0], "ruling": "maybe", "note": "值非法"}],
        [{"criterion": CRITERIA[0], "ruling": "violated", "note": "  "}],
        [
            {"criterion": CRITERIA[0], "ruling": "violated", "note": "第一次"},
            {"criterion": CRITERIA[0], "ruling": "violated", "note": "重复"},
        ],
        [{"criterion": "没登记过的判据", "ruling": "violated", "note": "越界"}],
        ["not-an-object"],
    ]
    for rulings in cases:
        review = _write_review(exp_dir, verdict="rejected", rulings=rulings)
        with pytest.raises(StatusRejected):
            set_status(exp_dir, "rejected", review_path=review, reason="逐条裁定不合格")

    assert load_manifest(exp_dir)["status"] == "speculative"


def test_incomplete_terminal_records_stay_out_of_the_negative_index(tmp_path: Path) -> None:
    exp_dir = _thought(tmp_path)
    _write_reasoning(exp_dir)
    manifest = load_manifest(exp_dir)
    manifest["status"] = "rejected"  # 手工写下：无 review.json、无 reasoning_sha256
    manifest["history"].append({"status": "rejected", "actor": "manual"})
    save_manifest(exp_dir, manifest)

    results = verify_tree(tmp_path)

    assert not results[0].ok
    assert negative_index(results) == []
