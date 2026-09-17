"""命令行入口：new / status / verify / report。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scirearch.experiment import (
    ALL_STATUSES,
    EXPERIMENTS_DIRNAME,
    ExperimentError,
    create_experiment,
    resolve_experiment,
    set_status,
)
from scirearch.verify import check_experiment, render_report, verify_tree

__version__ = "0.1.0"


def find_root(start: Path) -> Path:
    """向上查找仓库根：包含 `experiments/` 或 `.git` 的最近目录。"""
    for candidate in (start, *start.parents):
        if (candidate / EXPERIMENTS_DIRNAME).is_dir() or (candidate / ".git").exists():
            return candidate
    raise ExperimentError(f"从 {start} 向上未找到仓库根（需含 experiments/ 或 .git）")


def _add_root(parser: argparse.ArgumentParser) -> None:
    # default=SUPPRESS 是关键：子解析器不得用自己的默认值覆盖父解析器已解析出的 --root。
    parser.add_argument(
        "--root",
        type=Path,
        default=argparse.SUPPRESS,
        help="仓库根目录（默认从当前目录向上查找）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scirearch",
        description="实验预注册与合同校验（判据先于结果，终态必须有 seed 与原始日志）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_root(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="创建预注册实验")
    _add_root(new)
    new.add_argument("slug", help="实验短标识（小写下划线/连字符）")
    new.add_argument("-H", "--hypothesis", required=True, help="可证伪的假设")
    new.add_argument("-m", "--metric", required=True, help="裁决用的单一指标")
    new.add_argument(
        "-c",
        "--criteria",
        action="append",
        required=True,
        help="判据，可重复（例如 -c 'std < 0.01' -c '无 NaN'）",
    )
    new.add_argument("--seed", type=int, default=None, help="随机种子")
    new.add_argument("--run-cmd", default=None, help="写入 run.sh 的默认命令")

    status = sub.add_parser("status", help="推进实验状态")
    _add_root(status)
    status.add_argument("experiment", help="实验目录或 exp-NNNN 前缀")
    status.add_argument("status", choices=sorted(ALL_STATUSES), help="目标状态")
    status.add_argument("--metrics", type=Path, default=None, help="终态必需的指标文件")
    status.add_argument("--reason", default=None, help="变更原因（写入 history）")

    verify = sub.add_parser("verify", help="校验实验合同")
    _add_root(verify)
    verify.add_argument("paths", nargs="*", type=Path, help="实验目录（默认全部）")
    verify.add_argument("--json", action="store_true", help="输出 JSON")
    verify.add_argument(
        "--allow-empty",
        action="store_true",
        help="仓库无实验时不算失败（CI 首次运行需要）",
    )

    report = sub.add_parser("report", help="输出汇总表")
    _add_root(report)
    report.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def _cmd_new(args: argparse.Namespace, root: Path) -> int:
    exp_dir = create_experiment(
        root,
        args.slug,
        hypothesis=args.hypothesis,
        metric=args.metric,
        criteria=args.criteria,
        seed=args.seed,
        run_cmd=args.run_cmd,
    )
    print(f"已创建预注册实验：{exp_dir.relative_to(root)}")
    print("下一步：填写 hypothesis.md 的证伪路径 → 编辑 run.sh 的 RUN= 一行 → 执行")
    return 0


def _cmd_status(args: argparse.Namespace, root: Path) -> int:
    exp_dir = resolve_experiment(root, args.experiment)
    manifest = set_status(
        exp_dir,
        args.status,
        reason=args.reason,
        metrics_path=args.metrics,
    )
    print(f"{manifest['id']}：{manifest['status']}（已写入 history）")
    if manifest["status"] in {"completed", "refuted", "inconclusive", "abandoned"}:
        print("提示：运行 `scirearch verify` 确认证据完整。")
    return 0


def _cmd_verify(args: argparse.Namespace, root: Path) -> int:
    results = [check_experiment(p) for p in args.paths] if args.paths else verify_tree(root)
    if not results:
        if args.allow_empty:
            print(f"未发现实验（{EXPERIMENTS_DIRNAME}/ 为空）；--allow-empty 已放行。")
            return 0
        print("未发现实验：请先 `scirearch new`，或在 CI 中使用 --allow-empty。", file=sys.stderr)
        return 1
    if args.json:
        payload = {
            "ok": all(r.ok for r in results),
            "count": len(results),
            "failed": sum(1 for r in results if not r.ok),
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_report(results), end="")
    return 0 if all(r.ok for r in results) else 1


def _cmd_report(args: argparse.Namespace, root: Path) -> int:
    results = verify_tree(root)
    if args.json:
        print(
            json.dumps(
                {"count": len(results), "experiments": [r.to_dict() for r in results]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_report(results), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    explicit_root: Path | None = getattr(args, "root", None)
    try:
        root = (explicit_root or find_root(Path.cwd())).resolve()
    except ExperimentError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    handlers = {
        "new": _cmd_new,
        "status": _cmd_status,
        "verify": _cmd_verify,
        "report": _cmd_report,
    }
    try:
        return handlers[args.command](args, root)
    except ExperimentError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
