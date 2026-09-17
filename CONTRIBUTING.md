# 贡献指南

## 环境

```bash
uv sync --dev          # 或：python -m pip install -e ".[dev]"
make help              # 全部命令
```

最低 Python 版本 3.11（`pyproject.toml` 的 `requires-python`）。`scirearch` 运行时零依赖，请勿引入运行时依赖；开发依赖（pytest / ruff）按需增补。

## 提交前

```bash
make check             # = ruff format --check + ruff check + pytest + scirearch verify
```

`make fmt` 可直接修复格式问题。实验类改动额外要求：

- 判据先于结果（`preregistered` 状态下不得存在 `metrics.json`）。
- 预注册（判据 / `hypothesis.md` / 证伪路径）创建后未被编辑（sha256 冻结）。
- **预注册提交严格早于结果提交**；实验类 PR 用 merge commit / rebase 合并，不要 squash。
- `seed` 已登记，`logs/` 含非空原始日志，`run.sh` 可执行。
- 未手工编辑 `metrics.json`。
- 文档/稿件中的数字可解析到实验产物。

## 变更类型与要求

| 类型 | 要求 |
| --- | --- |
| 合同规则（`src/scirearch/`） | 必须带**会随实现失败**的行为测试；在 `docs/experiment-protocol.md` 同步说明 |
| omp 设施（`.omp/`） | 说明触发场景与失败模式；hook 需写明被拦截的路径/命令模式 |
| 实验（`experiments/`） | 遵循 [实验协议](docs/experiment-protocol.md)，PR 模板中的证据清单全勾 |
| 文档 | 与实现同步；引用外部结论须给出可核查出处（论文 arXiv 编号或 omp 文档路径） |

不接受的测试：断言实现细节（字段拷贝、默认值、转发、mock 回声）、只证明"不抛异常"、为凑覆盖率而写。测试要守住的是**外部可观察的契约**。

## 提交信息

Conventional Commits 风格，类型限定 `feat|fix|docs|test|chore|refactor|experiment`：

```text
feat(verify): 终态实验缺少 seed 时判为失败
experiment: exp-0007 复现基线方差（refuted）
docs(protocol): 补充负结果保留要求
```

## 评审

1. 每个 PR 至少一名非作者评审；涉及实验结果时，评审者须**独立复算**关键数字。
2. 评审关注顺序：证据完整性 > 结论正确性 > 代码风格。
3. 含实验的 PR：核对 `scirearch verify` 退出码（0/1/2）与 `report` 中标注 `[人工]` 的判据——
   后者必须有复核者的裁定记录，不能被当成"已验证"。
4. 破坏性变更（合同收紧、目录结构调整）需在 PR 描述中给出迁移方式。

## 安全

见 [SECURITY.md](SECURITY.md)。特别注意：子agent 以 `yolo` 审批模式执行，`.omp/hooks/pre/` 是唯一自动拦截点。
