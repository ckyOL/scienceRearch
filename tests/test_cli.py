"""CLI 契约测试：退出码与输出是唯一可观察契约。"""

from __future__ import annotations

import json
from pathlib import Path

from scirearch.cli import main


def _new(root: Path, *extra: str) -> int:
    return main(
        [
            "--root",
            str(root),
            "new",
            "baseline",
            "--hypothesis",
            "固定 seed 下方差小于 1%",
            "--metric",
            "std(accuracy)",
            "--criteria",
            "std < 0.01",
            "--falsification",
            "方差超过 1% 则放弃",
            *extra,
        ]
    )


def _finish(root: Path, status: str, metrics: str) -> int:
    exp_dir = root / "experiments" / "exp-0001-baseline"
    (exp_dir / "metrics.json").write_text(metrics, encoding="utf-8")
    logs = exp_dir / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "run-1.log").write_text("epoch 1 accuracy 0.9\n", encoding="utf-8")
    current = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))["status"]
    if current == "preregistered":
        assert main(["--root", str(root), "status", "exp-0001", "running"]) == 0
    return main(
        [
            "--root",
            str(root),
            "status",
            "exp-0001",
            status,
            "--metrics",
            str(exp_dir / "metrics.json"),
            "--reason",
            "测试",
        ]
    )


def test_new_then_verify_round_trip(tmp_path: Path, capsys) -> None:
    assert _new(tmp_path, "--seed", "1729") == 0
    assert (tmp_path / "experiments" / "exp-0001-baseline" / "experiment.json").is_file()

    assert main(["--root", str(tmp_path), "verify"]) == 0
    assert "exp-0001 baseline" in capsys.readouterr().out


def test_new_reports_criteria_forms_and_prereg_hashes(tmp_path: Path, capsys) -> None:
    assert _new(tmp_path, "--criteria", "无 NaN") == 0
    out = capsys.readouterr().out

    assert "1 条机器可判定 / 1 条自由文本" in out
    assert "预注册哈希：criteria=" in out


def test_verify_json_reports_violations(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()  # 丢弃 new 的输出，只解析 verify 的 JSON
    exp_dir = tmp_path / "experiments" / "exp-0001-baseline"
    (exp_dir / "metrics.json").write_text('{"std": 1}', encoding="utf-8")

    assert main(["--root", str(tmp_path), "verify", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["exit"] == 1
    assert payload["failed"] == 1
    assert any("预注册违规" in p for p in payload["results"][0]["problems"])


def test_verify_exit_code_two_for_criteria_conflict(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()
    assert _finish(tmp_path, "completed", '{"std": 0.42}') == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "verify", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit"] == 2
    assert payload["conflicts"] == 1
    assert payload["results"][0]["inconsistencies"]


def test_verify_exit_code_one_for_contract_problem(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()
    (tmp_path / "experiments" / "exp-0001-baseline" / "run.sh").unlink()

    assert main(["--root", str(tmp_path), "verify"]) == 1
    assert "缺少可重跑入口 run.sh" in capsys.readouterr().out


def test_verify_allows_empty_repo_only_with_flag(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "verify"]) == 1
    assert main(["--root", str(tmp_path), "verify", "--allow-empty"]) == 0


def test_status_transition_from_cli_requires_metrics(tmp_path: Path, capsys) -> None:
    _new(tmp_path, "--seed", "1729")
    capsys.readouterr()
    exp_dir = tmp_path / "experiments" / "exp-0001-baseline"

    assert main(["--root", str(tmp_path), "status", "exp-0001", "running"]) == 0
    # 终态缺 --metrics：拒绝并返回合同错误码
    assert main(["--root", str(tmp_path), "status", "exp-0001", "completed"]) == 1
    assert "--metrics" in capsys.readouterr().err

    assert _finish(tmp_path, "completed", '{"std": 0.0031}') == 0
    assert main(["--root", str(tmp_path), "verify"]) == 0
    assert exp_dir.is_dir()


def test_status_reports_contract_failures_immediately(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()

    assert _finish(tmp_path, "completed", '{"std": 0.42}') == 0
    err = capsys.readouterr().err

    assert "判据被违反却标记为 completed" in err


def test_report_json_lists_experiments_and_negative_knowledge(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()
    assert _finish(tmp_path, "refuted", '{"std": 0.42}') == 0
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "report", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["experiments"][0]["slug"] == "baseline"
    assert payload["refuted_index"][0]["id"] == "exp-0001"
    assert "attestation" in payload["notice"]


def test_reproposed_refuted_criteria_warns_and_records(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()
    assert _finish(tmp_path, "refuted", '{"std": 0.42}') == 0

    assert _new(tmp_path) == 0
    captured = capsys.readouterr()

    assert "负知识命中" in captured.err
    manifest = json.loads(
        (tmp_path / "experiments" / "exp-0002-baseline" / "experiment.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["prior_refutations"] == ["exp-0001"]


def test_unknown_experiment_is_a_clean_error(tmp_path: Path, capsys) -> None:
    _new(tmp_path)

    assert main(["--root", str(tmp_path), "status", "exp-9999", "running"]) == 1
    assert "找不到实验" in capsys.readouterr().err
