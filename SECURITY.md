# 安全策略

## 报告漏洞

请通过 `<maintainer@example.com>` 私下报告，或在 GitHub 上开启 Security Advisory。**不要**为安全问题开公开 issue。我们会在 7 天内确认，并在修复发布后致谢（如你愿意署名）。

## 支持范围

| 组件 | 在范围内 |
| --- | --- |
| `src/scirearch/`（合同 CLI） | 是 |
| `.omp/hooks/pre/`（护栏） | 是 |
| `.github/workflows/`（CI 配置） | 是 |
| 第三方依赖 | 否（请上报上游） |

## 本项目的特殊风险

本仓库以 agent 驱动实验为常态，因此以下风险被显式承认为**安全边界**，绕过它们即视为漏洞：

1. **子agent 无审批 UI**：omp 对子agent 强制 `tools.approvalMode: yolo`，危险命令不会弹窗确认。`.omp/hooks/pre/` 中的 `tool_call` 拦截是唯一自动闸门；hook 被绕过或失效（例如路径变体、命令包装）属于安全问题。
2. **数据完整性**：`data/raw/` 必须只读。任何能写入或删除 `data/raw/` 的路径（含 shell 重定向、`tee`、归档解包）都应被拦截。
3. **证据伪造**：`metrics.json` 与 `logs/` 的写入路径必须只由 `run.sh` 产生。若某种操作能让 `scirearch verify` 对伪造证据判为通过，属于安全问题。
4. **注入面**：实验脚本会执行外部输入（数据集、模型权重、论文附带代码）。请在隔离工作区（`isolated: true`）中执行不可信代码，并避免把不可信文本直接作为 shell 命令。
5. **凭据**：不要在 `experiments/`、`notes/` 或 agent 提示词中留下 API key；omp 的记忆/共享管线会对外发内容做密钥脱敏，但不要依赖它。

## 已知非目标

- 不防御拥有本机 shell 权限的攻击者（他们可以直接改文件）。
- 不保证提交到 `data/` 的数据的许可证合规性（由导入者负责）。
