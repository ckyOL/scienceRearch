"""对照已知真值给流水线提交的 verdict 打分。

用法：
    python analysis/known-truth/grade.py submissions.json [--json]

submissions.json 形如：
    {"q01-zero-effect": {"verdict": "refuted", "evidence": "已按组做 t 检验，p=0.61"}}

退出码：0 全部正确 / 1 存在错误。评分口径见 README.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bank import PROBLEMS, VERDICTS


def _load_submissions(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"submissions 必须是 JSON 对象：{path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对照真值给 submissions 打分")
    parser.add_argument("submissions", type=Path, help="提交文件（JSON）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    submissions = _load_submissions(args.submissions)
    rows = []
    counts = {"correct": 0, "false_positive": 0, "false_negative": 0, "abstain": 0, "missing": 0}
    for problem_id, problem in PROBLEMS.items():
        entry = submissions.get(problem_id)
        verdict = entry.get("verdict") if isinstance(entry, dict) else None
        evidence = entry.get("evidence", "") if isinstance(entry, dict) else ""
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            outcome = "missing"
        elif verdict == problem.expected:
            outcome = "correct"
        elif verdict == "inconclusive":
            outcome = "abstain"
        elif problem.expected == "refuted":
            outcome = "false_positive"
        else:
            outcome = "false_negative"
        counts[outcome] += 1
        rows.append(
            {
                "problem": problem_id,
                "expected": problem.expected,
                "submitted": verdict if isinstance(verdict, str) else "—",
                "outcome": outcome,
                "evidence": evidence,
            }
        )

    total = len(PROBLEMS)
    if args.json:
        print(json.dumps({"counts": counts, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print("| 问题 | 真值 | 提交 | 判定 | 证据 |")
        print("| --- | --- | --- | --- | --- |")
        for row in rows:
            print(
                f"| {row['problem']} | {row['expected']} | {row['submitted']} "
                f"| {row['outcome']} | {row['evidence']} |"
            )
        print("")
        print(
            f"共 {total} 个问题：{counts['correct']} 正确 / "
            f"{counts['false_positive']} 假阳性 / {counts['false_negative']} 假阴性 / "
            f"{counts['abstain']} 弃权 / {counts['missing']} 缺失。"
        )
    return 0 if counts["correct"] == total else 1


if __name__ == "__main__":
    sys.exit(main())
