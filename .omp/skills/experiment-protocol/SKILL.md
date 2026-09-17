---
name: experiment-protocol
description: 实验协议 SOP：预注册、seed、日志留痕、状态推进、复核与写作闸门。执行或复核任何 experiment 前读取。
---

# 实验协议（SOP）

完整版见 `docs/experiment-protocol.md`；这里是执行时的速查。

## 目录形态

```text
experiments/exp-0001-slug/
├─ hypothesis.md     # 人读：假设、判据、证伪路径
├─ experiment.json   # 机读真相源：manifest + history
├─ run.sh            # 可重跑入口（只改 RUN= 一行）
├─ metrics.json      # 只由脚本产出
└─ logs/             # 原始 stdout/stderr，终态必须非空
```

## 五步

1. `scirearch new <slug> -H "假设" -m "指标" -c "判据" --seed N` —— 判据先于结果。
2. 编辑 `run.sh` 的 `RUN=` 一行；`bash run.sh` 执行，seed 经 `SEED=` 覆盖。
3. `scirearch status <id> running` → 完成后 `... completed --metrics <path> --reason "..."`（否定结果用 `refuted`）。
4. `scirearch verify` —— 不通过不得报告 supported。
5. `scirearch report --json` —— 写作阶段只引用这里的终态实验。

## 合法状态转移

| 当前 | 可转到 |
| --- | --- |
| `preregistered` | `running`, `abandoned` |
| `running` | `completed`, `refuted`, `inconclusive`, `abandoned` |
| 终态 | 不可变更 |

## 子agent 产出契约（yield）

```json
{
  "hypothesis_id": "exp-0001",
  "command": "SEED=1729 bash experiments/exp-0001-fixed-seed-baseline/run.sh",
  "seed": 1729,
  "metrics": { "std": 0.0031 },
  "artifacts": ["experiments/exp-0001-fixed-seed-baseline/logs/run-20260917T101500Z.log"],
  "verdict": "supported",
  "caveats": []
}
```

## 并行与隔离

- 多个假设并行：调用方用 `task` batch 或 eval `workpool`，每项一个 `experimenter`；`isolated: true` 保证互不污染。
- 长跑任务用 `hub op:"start"` 托管，`hub op:"logs"` 跟随输出，不要在交互会话里阻塞等待。
- 复核与生成必须换 agent（`critic` / `replicator`）、换模型、换上下文。

## 禁止

手工改 `metrics.json`；事后追加或放宽判据；只保留摘要日志；丢弃 `refuted` 结果；用同一上下文自我复核。
