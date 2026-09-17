"""已知真值问题库：用"植入缺陷 / 零效应"问题自检流水线（零依赖、确定性）。

每个问题 = 一份可复现数据（`data`）+ 一条待判定 claim + 已知真值（`truth`）。
用途（调研 §7 借鉴 #5）：度量"预注册 + 独立复核"流水线相对裸 agent 的表现——
零效应问题上的假阳性、真实效应问题上的假阴性、以及结论是否附带证据。

隔离约定（见 README.md）：求解者只应看到 `data` 与 claim，不得读本文件的真值区。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_N = 200
VERDICTS = ("supported", "refuted", "inconclusive")

Table = tuple[list[str], list[list[object]]]


@dataclass(frozen=True)
class Problem:
    """一个已知真值问题。"""

    id: str
    claim: str
    expected: str
    planted_defect: str
    rationale: str
    default_n: int
    generate: Callable[[int, int], Table]

    def truth(self) -> dict[str, object]:
        return {
            "id": self.id,
            "claim": self.claim,
            "expected": self.expected,
            "planted_defect": self.planted_defect,
            "rationale": self.rationale,
        }


def _shuffled(rng: random.Random, rows: list[list[object]]) -> list[list[object]]:
    rng.shuffle(rows)
    return rows


def _zero_effect(seed: int, n: int) -> Table:
    rng = random.Random(seed)
    rows: list[list[object]] = [
        [group, round(rng.gauss(0.0, 1.0), 6)]
        for group in ("control", "treatment")
        for _ in range(n)
    ]
    return ["group", "value"], _shuffled(rng, rows)


def _real_effect(seed: int, n: int) -> Table:
    rng = random.Random(seed)
    rows: list[list[object]] = []
    for group in ("control", "treatment"):
        mu = 0.0 if group == "control" else 0.6
        rows.extend([group, round(rng.gauss(mu, 1.0), 6)] for _ in range(n))
    return ["group", "value"], _shuffled(rng, rows)


def _confounded(seed: int, n: int) -> Table:
    rng = random.Random(seed)
    rows: list[list[object]] = []
    for _ in range(n):
        severity = rng.gauss(0.0, 1.0)
        enrolled = 1 if rng.random() < 1.0 / (1.0 + math.exp(-1.5 * severity)) else 0
        outcome = 2.0 * severity + rng.gauss(0.0, 0.5)  # 处理没有因果项
        rows.append([enrolled, round(severity, 6), round(outcome, 6)])
    return ["treated", "severity", "outcome"], _shuffled(rng, rows)


def _multiplicity(seed: int, n: int) -> Table:
    rng = random.Random(seed)
    metrics = [f"m{i:02d}" for i in range(1, 21)]
    rows: list[list[object]] = []
    for group in ("control", "treatment"):
        for _ in range(n):
            rows.append([group, *[round(rng.gauss(0.0, 1.0), 6) for _ in metrics]])
    return ["group", *metrics], _shuffled(rng, rows)


def _leakage(seed: int, n: int) -> Table:
    rng = random.Random(seed)

    def sample() -> list[object]:
        x1, x2 = rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)
        label = 1 if x1 + x2 + rng.gauss(0.0, 0.3) > 0 else 0
        return [round(x1, 6), round(x2, 6), label]

    train = [sample() for _ in range(n)]
    test = [sample() for _ in range(n // 4)]
    # 植入泄漏：每第 7 条训练样本（含标签）原样复制进测试集。
    leaks = [list(row) for index, row in enumerate(train) if index % 7 == 0]
    test.extend(leaks)
    rng.shuffle(test)
    rows = [["train", *row] for row in train] + [["test", *row] for row in test]
    return ["split", "x1", "x2", "label"], rows


PROBLEMS: dict[str, Problem] = {
    "q01-zero-effect": Problem(
        id="q01-zero-effect",
        claim="处理组的 value 均值高于对照组，处理存在正向效应。",
        expected="refuted",
        planted_defect=(
            "两组由同一分布生成（真效应为零），但样本均值差非零；"
            "在多个 seed 中总有一些看起来'接近显著'。"
        ),
        rationale=(
            "两组均为 N(0,1) 抽样，无系统差异；任何 supported 判定都是假阳性（Type I 错误）。"
        ),
        default_n=DEFAULT_N,
        generate=_zero_effect,
    ),
    "q02-real-effect": Problem(
        id="q02-real-effect",
        claim="处理组的 value 均值高于对照组，处理存在正向效应。",
        expected="supported",
        planted_defect="无（对照问题）：效应真实存在，用来抓'只会说 refuted'的流水线。",
        rationale="处理组为 N(0.6,1)，每组 n≈200 时双样本 t 检验功效 >0.99（α=0.05）。",
        default_n=DEFAULT_N,
        generate=_real_effect,
    ),
    "q03-confounded": Problem(
        id="q03-confounded",
        claim="处理组的 outcome 更高，因此处理提升了 outcome（因果结论）。",
        expected="refuted",
        planted_defect=(
            "入组概率随 severity 上升，且 severity 直接决定 outcome；"
            "朴素均值差为正，掩盖了因果不可识别。"
        ),
        rationale=(
            "outcome = 2·severity + 噪声，处理无因果项。"
            "按 severity 回归调整后处理系数 ≈ 0（分层若过粗会残留混杂），因果 claim 不成立。"
        ),
        default_n=300,
        generate=_confounded,
    ),
    "q04-multiplicity": Problem(
        id="q04-multiplicity",
        claim="20 个指标中至少有一个存在真实的组间效应（证据：某列在 α=0.05 下单指标检验显著）。",
        expected="refuted",
        planted_defect=(
            "20 列全部为独立噪声；单指标 α=0.05 的筛选流程在无效应数据上产生假发现的概率约 64%。"
        ),
        rationale="所有指标列由 N(0,1) 生成、两组同分布；任何'显著'列都是多重比较下的选择效应。",
        default_n=150,
        generate=_multiplicity,
    ),
    "q05-leakage": Problem(
        id="q05-leakage",
        claim="模型在测试集上表现良好，因此泛化能力得到了验证。",
        expected="refuted",
        planted_defect="每第 7 条训练样本被逐值复制进测试集（含标签），测试集含泄漏行。",
        rationale=(
            "测试集与训练集存在逐值相同的重复行；高准确率可由记忆泄漏解释，不构成泛化证据。"
            "正确做法：去重后重切分。"
        ),
        default_n=400,
        generate=_leakage,
    ),
}


def _cmd_list() -> int:
    print("| 问题 | claim | 真值 | 植入缺陷 |")
    print("| --- | --- | --- | --- |")
    for problem in PROBLEMS.values():
        print(f"| {problem.id} | {problem.claim} | {problem.expected} | {problem.planted_defect} |")
    return 0


def _cmd_truth(problem_id: str) -> int:
    problem = PROBLEMS.get(problem_id)
    if problem is None:
        print(f"未知问题：{problem_id}；可用：{', '.join(PROBLEMS)}", file=sys.stderr)
        return 1
    print(json.dumps(problem.truth(), ensure_ascii=False, indent=2))
    return 0


def _cmd_data(problem_id: str, seed: int, n: int | None) -> int:
    problem = PROBLEMS.get(problem_id)
    if problem is None:
        print(f"未知问题：{problem_id}；可用：{', '.join(PROBLEMS)}", file=sys.stderr)
        return 1
    header, rows = problem.generate(seed, n or problem.default_n)
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="已知真值问题库：list / truth / data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出全部问题（含真值，仅评分者可见）")
    truth = sub.add_parser("truth", help="输出某问题的真值记录")
    truth.add_argument("problem")
    data = sub.add_parser("data", help="输出某问题的数据（CSV）")
    data.add_argument("problem")
    data.add_argument("--seed", type=int, default=0)
    data.add_argument("--n", type=int, default=None, help="样本量（默认按问题设定）")
    args = parser.parse_args(argv)

    if args.command == "list":
        return _cmd_list()
    if args.command == "truth":
        return _cmd_truth(args.problem)
    return _cmd_data(args.problem, args.seed, args.n)


if __name__ == "__main__":
    sys.exit(main())
