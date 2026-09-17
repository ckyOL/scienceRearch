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
            *extra,
        ]
    )


def test_new_then_verify_round_trip(tmp_path: Path, capsys) -> None:
    assert _new(tmp_path, "--seed", "1729") == 0
    assert (tmp_path / "experiments" / "exp-0001-baseline" / "experiment.json").is_file()

    assert main(["--root", str(tmp_path), "verify"]) == 0
    assert "exp-0001 baseline" in capsys.readouterr().out


def test_verify_json_reports_violations(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()  # 丢弃 new 的输出，只解析 verify 的 JSON
    exp_dir = tmp_path / "experiments" / "exp-0001-baseline"
    (exp_dir / "metrics.json").write_text('{"std": 1}', encoding="utf-8")

    assert main(["--root", str(tmp_path), "verify", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["failed"] == 1
    assert any("预注册违规" in p for p in payload["results"][0]["problems"])


def test_verify_allows_empty_repo_only_with_flag(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "verify"]) == 1
    assert main(["--root", str(tmp_path), "verify", "--allow-empty"]) == 0


def test_status_transition_from_cli_requires_metrics(tmp_path: Path, capsys) -> None:
    _new(tmp_path, "--seed", "1729")
    exp_dir = tmp_path / "experiments" / "exp-0001-baseline"

    assert main(["--root", str(tmp_path), "status", "exp-0001", "running"]) == 0
    # 终态缺 --metrics：拒绝并返回用法级错误码
    assert main(["--root", str(tmp_path), "status", "exp-0001", "completed"]) == 2
    assert "--metrics" in capsys.readouterr().err

    metrics = exp_dir / "metrics.json"
    metrics.write_text('{"std": 0.0031}', encoding="utf-8")
    logs = exp_dir / "logs"
    logs.mkdir()
    (logs / "run-1.log").write_text("ok\n", encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "status",
                "exp-0001",
                "completed",
                "--metrics",
                str(metrics),
                "--reason",
                "判据满足",
            ]
        )
        == 0
    )
    assert main(["--root", str(tmp_path), "verify"]) == 0


def test_report_json_lists_experiments(tmp_path: Path, capsys) -> None:
    _new(tmp_path)
    capsys.readouterr()  # 丢弃 new 的输出

    assert main(["--root", str(tmp_path), "report", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["experiments"][0]["slug"] == "baseline"


def test_unknown_experiment_is_a_clean_error(tmp_path: Path, capsys) -> None:
    _new(tmp_path)

    assert main(["--root", str(tmp_path), "status", "exp-9999", "running"]) == 2
    assert "找不到实验" in capsys.readouterr().err
