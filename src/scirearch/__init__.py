"""可验证性优先的科研工作流合同工具。

两类记录（`kind`）：
- **实验**（`experiment`）：由 `metrics.json` 裁决，
  `preregistered → running → {completed, refuted, inconclusive}`；
- **思想实验**（`thought-experiment`）：暂无法实验的假说，由 `reasoning.md` + 独立复核
  `review.json` 裁定，`speculative → {rejected, promoted}`（`promoted` 必须指向转成的正式实验）。
  思想实验不构成经验证据，永不携带 `metrics.json`。

核心不变量：
- 判据必须早于结果（预注册），且创建后不可修改：判据、证伪路径与 hypothesis.md
  的 sha256 在创建时登记，git 时序另证预注册提交严格早于结果提交；
- 经验终态必须有 seed、非空原始日志与可解析指标；思想实验终态必须有非空论证与独立复核记录；
- 状态机不允许跳步、不允许跨类型，终态不可回退，每次变更留痕；
- 可求值判据（`指标 运算符 数值`）在 metrics.json 上三态求值：
  满足 / 违反 / 不可判定；状态与判据冲突即失败（verify 退出码 2）。
"""

from scirearch.experiment import (
    ALL_KINDS,
    ALLOWED_TRANSITIONS,
    KIND_EXPERIMENT,
    KIND_LABELS,
    KIND_THOUGHT,
    TERMINAL_STATUSES,
    ExperimentError,
    create_experiment,
    load_manifest,
    set_status,
    slugify,
)
from scirearch.verify import (
    CheckResult,
    check_experiment,
    negative_index,
    render_report,
    verify_tree,
)

__version__ = "0.1.0"

__all__ = [
    "ALLOWED_TRANSITIONS",
    "ALL_KINDS",
    "KIND_EXPERIMENT",
    "KIND_LABELS",
    "KIND_THOUGHT",
    "TERMINAL_STATUSES",
    "CheckResult",
    "ExperimentError",
    "__version__",
    "check_experiment",
    "create_experiment",
    "load_manifest",
    "negative_index",
    "render_report",
    "set_status",
    "slugify",
    "verify_tree",
]
