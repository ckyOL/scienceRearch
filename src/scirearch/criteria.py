"""判据机械化：把预注册判据变成可在 `metrics.json` 上求值的检查。

可求值形式：`<指标路径> <运算符> <数值>`，例如 `std_accuracy < 0.01`、`results.std >= 1e-3`。
其余判据保留为自由文本：机器不求值（`decided_by=human`），由复核者人工裁定。

求值输出三态：`satisfied` / `violated` / `undecidable`；实验尚未产出指标时为 `pending`。
判据文本与 `metrics.json` 都不得被这里修改——本模块是纯函数式的只读层。
"""

from __future__ import annotations

import operator
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

STATE_SATISFIED = "satisfied"
STATE_VIOLATED = "violated"
STATE_UNDECIDABLE = "undecidable"
STATE_PENDING = "pending"

DECIDED_BY_MACHINE = "machine"
DECIDED_BY_HUMAN = "human"

REASON_FREE_TEXT = "free_text"
REASON_MISSING_METRIC = "missing_metric"
REASON_NON_NUMERIC = "non_numeric"

CRITERION_RE = re.compile(
    r"^\s*(?P<path>[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)*)"
    r"\s*(?P<op><=|>=|==|!=|<|>)\s*"
    r"(?P<value>[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)

_COMPARATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


@dataclass(frozen=True)
class Criterion:
    """一条可机器求值的判据（解析结果）。"""

    text: str
    path: tuple[str, ...]
    op: str
    value: float

    def render(self) -> str:
        return f"{'.'.join(self.path)} {self.op} {self.value:g}"


@dataclass(frozen=True)
class Outcome:
    """一条判据的求值结果。"""

    criterion: str
    state: str
    decided_by: str
    reason: str = ""
    detail: str = ""
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "state": self.state,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "detail": self.detail,
            "value": self.value,
        }


def normalize(text: str) -> str:
    """规范化判据文本，用于哈希与重复判据识别。

    可求值判据按解析结果渲染（`std<0.01` ≡ `std < 0.01`）；自由文本仅折叠空白。
    """
    parsed = parse(text)
    if parsed is not None:
        return parsed.render()
    return " ".join(text.split())


def parse(text: str) -> Criterion | None:
    """解析可求值判据；自由文本返回 None。"""
    match = CRITERION_RE.match(text)
    if match is None:
        return None
    return Criterion(
        text=" ".join(text.split()),
        path=tuple(match["path"].split(".")),
        op=match["op"],
        value=float(match["value"]),
    )


def resolve(metrics: Mapping[str, Any], path: Sequence[str]) -> tuple[bool, Any]:
    """按点分路径在 metrics 中查找，返回 (是否找到, 值)。"""
    node: Any = metrics
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_one(text: str, metrics: Mapping[str, Any] | None) -> Outcome:
    """求值单条判据；`metrics=None` 表示实验尚未产出指标。"""
    parsed = parse(text)
    if parsed is None:
        return Outcome(
            criterion=normalize(text),
            state=STATE_UNDECIDABLE,
            decided_by=DECIDED_BY_HUMAN,
            reason=REASON_FREE_TEXT,
            detail="自由文本判据：机器不求值，需复核者裁定",
        )
    if metrics is None:
        return Outcome(
            criterion=parsed.text,
            state=STATE_PENDING,
            decided_by=DECIDED_BY_MACHINE,
            detail="尚未产出 metrics.json",
        )
    found, value = resolve(metrics, parsed.path)
    path_text = ".".join(parsed.path)
    if not found:
        return Outcome(
            criterion=parsed.text,
            state=STATE_UNDECIDABLE,
            decided_by=DECIDED_BY_MACHINE,
            reason=REASON_MISSING_METRIC,
            detail=f"metrics.json 中缺少指标 `{path_text}`",
        )
    if not _is_number(value):
        return Outcome(
            criterion=parsed.text,
            state=STATE_UNDECIDABLE,
            decided_by=DECIDED_BY_MACHINE,
            reason=REASON_NON_NUMERIC,
            detail=f"指标 `{path_text}` 不是数值（{type(value).__name__}）",
        )
    satisfied = _COMPARATORS[parsed.op](float(value), parsed.value)
    return Outcome(
        criterion=parsed.text,
        state=STATE_SATISFIED if satisfied else STATE_VIOLATED,
        decided_by=DECIDED_BY_MACHINE,
        detail=f"{path_text}={value:g}",
        value=float(value),
    )


def evaluate(texts: Iterable[str], metrics: Mapping[str, Any] | None) -> list[Outcome]:
    """按序求值一组判据。"""
    return [evaluate_one(text, metrics) for text in texts]
