"""可验证性优先的科研工作流合同工具。

核心不变量：
- 判据必须早于结果（预注册）；
- 终态必须有 seed、非空原始日志与可解析指标；
- 状态机不允许跳步，终态不可回退，每次变更留痕。
"""

from scirearch.experiment import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ExperimentError,
    create_experiment,
    load_manifest,
    set_status,
    slugify,
)
from scirearch.verify import CheckResult, check_experiment, render_report, verify_tree

__version__ = "0.1.0"

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "CheckResult",
    "ExperimentError",
    "__version__",
    "check_experiment",
    "create_experiment",
    "load_manifest",
    "render_report",
    "set_status",
    "slugify",
    "verify_tree",
]
