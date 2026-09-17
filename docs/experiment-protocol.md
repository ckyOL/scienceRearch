# 实验协议

适用对象：人类研究者、`experimenter`/`replicator` 子agent、以及任何自动化流水线。
违反协议的产物不会被 `scirearch verify` 接受，也不会被 `writer` 引用。

## 1. 目录与命名

```text
experiments/exp-0001-fixed-seed-baseline/
├─ hypothesis.md     # 人读：假设、判据、证伪路径
├─ experiment.json   # 机读：manifest + 状态历史（唯一真相源）
├─ run.sh            # 可重跑入口：固定 seed、原始日志 tee 到 logs/
├─ metrics.json      # 机读指标（只由 run.sh 产出）
└─ logs/             # 原始 stdout/stderr（终态必须非空）
```

`id` 由 `scirearch new` 顺序分配（`exp-NNNN`），`slug` 为小写下划线短语。**不要手工创建实验目录**。

## 2. 五步流程

### 2.1 预注册（判据先于结果）

```bash
scirearch new <slug> --hypothesis "..." --metric "..." --criteria "..." [--criteria "..."] [--seed N]
```

- 判据必须能在 `metrics.json` 上机械判定（可写成布尔表达式或明确的数值阈值）。
- 此刻状态为 `preregistered`。**在这个状态下出现 `metrics.json` 即判为预注册违规**——判据必须是事前承诺。
- `hypothesis.md` 的"证伪路径"必填：写下"什么结果会让我放弃"。

### 2.2 执行

只修改 `run.sh` 中标记的那一行 `RUN=`；其余部分（seed 导出、git 版本、时间戳、`tee` 到 `logs/`）保持不动。

```bash
bash experiments/exp-0001-fixed-seed-baseline/run.sh
```

要求：

- **固定 seed**，并通过环境变量可覆盖（`SEED=... bash run.sh`）。
- 原始输出必须落盘到 `logs/`；不得只保留摘要。
- 长跑任务交给 omp 托管（`hub op:"start"`），不要占用交互会话。
- 中间产物写入 `data/interim/`，**不要写 `data/raw/`**（hook 会拦截）。

### 2.3 状态推进

```bash
scirearch status experiments/exp-0001-fixed-seed-baseline running
scirearch status experiments/exp-0001-fixed-seed-baseline completed \
  --metrics experiments/exp-0001-fixed-seed-baseline/metrics.json \
  --reason "判据全部满足"
```

合法转移：

| 当前 | 允许的下一状态 |
| --- | --- |
| `preregistered` | `running`, `abandoned` |
| `running` | `completed`, `refuted`, `inconclusive`, `abandoned` |
| 终态（`completed`/`refuted`/`inconclusive`/`abandoned`） | 不可变更 |

`refuted` / `inconclusive` **同样需要完整证据**（日志 + seed）——负结果是最容易被悄悄丢弃的资产。

### 2.4 校验

```bash
scirearch verify                 # 全部实验
scirearch verify --json          # 机读输出，供 CI 或子agent 消费
```

失败时逐条列出原因（缺失 seed、`logs/` 为空、`run.sh` 不可执行、预注册违规、状态非法…）。有实验存在时 CI 会强制执行。

### 2.5 汇总与写作

```bash
scirearch report          # markdown 表：id / slug / 状态 / seed / 证据 / commit
scirearch report --json
```

`writer` 只能引用 report 中状态为终态、且证据完整的实验。稿件中每个数字都应能解析到 `experiments/<id>/` 的产物。

## 3. 复核（独立且对抗）

复核者与生成者必须是**不同 agent、不同模型、不同上下文**。三个必检方向：

1. **一致性**：`metrics.json` 与 `logs/` 逐项核对；找出被丢弃的 run（未披露的筛选 = 结论失效）。
2. **统计**：显著性、多重比较、方差来源；关键区间复算一遍。
3. **泄漏与合规**：切分是否泄漏、是否触碰 `data/raw/`、是否改动过判据。

omp 侧：`critic`（只读批判）与 `replicator`（干净工作区重跑）承担 1–3；`advisor` + `.omp/WATCHDOG.md` 做持续在线复核；`/collab` 供人类实时旁观。

## 4. 提交契约（子agent 产出）

`experimenter` 通过 `yield` 提交，字段与 `experiment.json` 对应：

```json
{
  "hypothesis": "固定 seed 下基线方差小于 1%",
  "command": "SEED=1729 bash experiments/exp-0001-fixed-seed-baseline/run.sh",
  "seed": 1729,
  "metrics": { "std_accuracy": 0.0031, "runs": 5 },
  "artifacts": ["experiments/exp-0001-fixed-seed-baseline/logs/run-20260917T101500Z.log"],
  "verdict": "supported",
  "caveats": ["仅覆盖 5 个 seed，未做多重比较校正"]
}
```

约束：

- `artifacts` 必须是仓库内可寻址路径（或外部存储 URL + hash）。
- `verdict=supported` 不代表结论成立，只代表判据满足；接受与否由复核与人类决定。
- `caveats` 为空时也要显式给出 `[]`——沉默不等于没有保留意见。

## 5. 常见违规

| 违规 | 后果 | 处理 |
| --- | --- | --- |
| 先跑实验、后写判据 | 预注册违规，`verify` 失败 | 重建实验目录，判据重新预注册 |
| 手改 `metrics.json` | 证据链断裂 | 重跑；数字一律由 `run.sh` 产出 |
| 只保留汇总日志 | 无法回溯 | 重新执行并保留原始 stdout |
| 丢弃 refuted 结果 | 选择性报告 | 保留为终态；report 中如实呈现 |
| 用强模型既生成又复核 | 自我一致性偏差 | 换 agent/模型/上下文重审 |
