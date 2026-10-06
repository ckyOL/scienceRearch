---
name: experiment-protocol
description: 实验协议 SOP：预注册、seed、日志留痕、状态推进、复核与写作闸门（含思想实验通道）。执行或复核任何 experiment 前读取。
---

# 实验协议（SOP）

完整版见 `docs/experiment-protocol.md`；这里是执行时的速查。

## 两类记录（`--kind`，创建后不可改）

| kind | 适用 | 证据 | 状态 |
| --- | --- | --- | --- |
| `experiment`（默认） | 可执行、可测量的假设 | `run.sh` → `metrics.json` + `logs/` + `seed` | `preregistered → running → {completed, refuted, inconclusive, abandoned}` |
| `thought-experiment` | 当前无法实验的假说（`-b` 写明卡在哪） | `reasoning.md` + `review.json`（人工复核） | `speculative → {rejected, promoted, abandoned}` |

**思想实验不构成经验证据**：不得作为 `paper/` 结论引用，目录里**不得出现 `metrics.json`**。

## 目录形态

```text
experiments/exp-0001-slug/          # 实验
├─ hypothesis.md  experiment.json  run.sh  metrics.json  logs/
experiments/exp-0002-slug/          # 思想实验
├─ hypothesis.md  experiment.json  reasoning.md  review.json
```

## 五步（实验）

1. `scirearch new <slug> -H "假设" -m "指标" -c "std_accuracy < 0.01" -f "证伪路径" --seed N`
   —— 判据与证伪路径先于结果，**创建即冻结**（sha256 登记，事后编辑会被 `verify` 检出）。
2. **先提交预注册**（`git commit`），再编辑 `run.sh` 的 `RUN=` 一行并执行；
   seed 经 `SEED=` 覆盖。顺序反了就是 git 时序违规；实验类提交不要 squash 合并。
3. `scirearch status <id> running` → 完成后 `... completed --metrics experiments/<id>/metrics.json --reason "..."`
   （否定结果用 `refuted`）。可求值判据由机器三态求值：`completed` 不得有违反，
   `refuted` 必须有违反。**推进是闸门**：写入前按目标状态模拟一次 `verify`，会被判失败的推进
   直接拒绝（退出码 1 合同 / 2 判据冲突）且**状态不变**——按报错补证据或改判，绝不绕过 CLI 改 manifest。
4. `scirearch verify` —— 退出码 0 通过 / 1 合同非法 / 2 判据冲突；不通过不得报告 supported。
5. `scirearch report --json` —— 写作阶段只引用这里的 `completed`/`refuted`/`inconclusive`；
   标 `[人工]` 的判据需复核者裁定。

## 五步（思想实验）

1. `scirearch new <slug> --kind thought-experiment -H "假设" -m "裁决依据" -c "判据" -f "证伪路径" -b "阻碍条件"`
   —— 不接受 `--seed` / `--run-cmd`；状态从 `speculative` 起步。
2. 提交预注册 → 在 `reasoning.md` 写**前提 / 论证 / 反例搜索 / 可测试化路径**。
3. 派独立复核者（不同 agent、不同模型）逐条裁定判据 → `review.json`
   （`reviewer`/`generator` 的 agent 与 model 都必须不同；`ruling ∈ {satisfied, violated, unclear}`）。
4. 收口：`status <id> rejected --review experiments/<id>/review.json --reason "..."`；
   或先建正式实验再 `status <id> promoted --review ... --superseded-by exp-NNNN`。
5. `scirearch verify` 必须通过。`promoted` 只表示"已可实验"，**不表示假设成立**。

## 合法状态转移

| kind | 当前 | 可转到 |
| --- | --- | --- |
| experiment | `preregistered` | `running`, `abandoned` |
| experiment | `running` | `completed`, `refuted`, `inconclusive`, `abandoned` |
| thought | `speculative` | `rejected`, `promoted`, `abandoned` |
| 任意 | 终态 | 不可变更 |

`abandoned` 只需 `--reason`（放弃不产出结论）；`completed`/`refuted`/`inconclusive` 需要
`metrics.json` + 非空 `logs/` + `seed`；`rejected`/`promoted` 需要非空 `reasoning.md` + `review.json`。
`rejected` 时 `reasoning.md` 的 sha256 被冻结进 `history`，此后编辑即判漂移。

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

手工改 `metrics.json`；事后追加或放宽判据；只保留摘要日志；丢弃 `refuted`/`rejected` 结果；
用同一上下文自我复核；把思想实验当结论引用。
