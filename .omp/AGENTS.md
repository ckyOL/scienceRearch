# ScienceRearch · 项目上下文

可验证性优先的科研仓库。**结论的价值取决于它能否被独立复核**，因此这里的一切都围绕证据链组织。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `experiments/<id>/` | 每个假设一个目录：`hypothesis.md`（人读）、`experiment.json`（机读真相源）、`run.sh`（可重跑入口）、`metrics.json`、`logs/` |
| `src/scirearch/` | 合同工具：预注册、状态机、校验、汇总 |
| `data/raw/` | 原始数据，**只读** |
| `data/{interim,processed}/` | 派生物，可重建，不入库 |
| `analysis/` | 从 `experiments/` 重建的统计与图表；`known-truth/` 为自检问题库（真值区求解者不得读） |
| `paper/` | 稿件 |
| `notes/` | 探索笔记与死路归档（`dead-ends/`，不构成证据） |
| `docs/` | 调研、架构、实验协议、使用指南（`getting-started.md`：配置/协作/故障排查）、项目级预注册与 kill 判据 |

## 常用命令

```bash
make check                                    # 提交前闸门：格式 + lint + 测试 + 合同校验
scirearch new <slug> -H "假设" -m "指标" -c "std_accuracy < 0.01" -f "证伪路径" --seed N
scirearch status <exp-id> running|completed|refuted|inconclusive --metrics <path> --reason "..."
scirearch verify [--json]                     # 退出码：0 通过 / 1 合同非法 / 2 判据与状态冲突
scirearch report [--json]                     # 判据判定 + 负知识索引
```

## 与 agent 协作的约定

- 实验执行派 `experimenter`，**调用时带 `isolated: true`**；复核派 `critic` / `replicator`，必须与生成者不同 agent、不同模型、不同上下文。
- 子agent 不继承对话历史：共享背景写进 `task` 的 `context`，或写到 `local://` 文件后引用。
- 实验类产出用 `yield` 提交，字段见 `.omp/skills/experiment-protocol/SKILL.md` 与 `docs/experiment-protocol.md`。
- 预注册（判据 / `hypothesis.md` / 证伪路径 / seed）创建即冻结（sha256）；**先提交预注册，再跑实验**
  （git 时序是证据，squash 合并会使其失效）；曾被证伪的判据重提前必须给出新证据。
- 需要方法论细节时读 `skill://experiment-protocol`；写作时读 `skill://paper-template`。
- 硬约束见 `.omp/RULES.md`（每请求常驻），不要绕过。
