# known-truth：已知真值问题库

用途：给"预注册 + 独立复核"流水线做**自检**——它声称能抓住的失效模式（零效应假阳性、多重比较、
混杂因果、数据泄漏），在这里都有已知真值可对照；与裸 agent 在同一批问题上的正确率之差，
就是这套机制的实测收益（调研 §7 借鉴 #5）。

## 组成

| 文件 | 作用 |
| --- | --- |
| `bank.py` | 问题库：5 个问题，各含确定性数据生成器、claim、植入缺陷、真值与理由 |
| `grade.py` | 评分器：对照真值给提交的 verdict 打分，统计假阳性 / 假阴性 / 弃权 |

## 用法

```bash
python analysis/known-truth/bank.py list                        # 真值一览（仅评分者）
python analysis/known-truth/bank.py truth q03-confounded        # 单个问题的真值记录
python analysis/known-truth/bank.py data q03-confounded --seed 0   # 数据（CSV，stdout）
python analysis/known-truth/grade.py submissions.json           # 评分（exit 0 全对 / 1 有错）
```

## 协议

1. **隔离**：求解者（裸 agent 或流水线）只能拿到 `data` 输出与 claim；不得读 `bank.py`
   的真值区、`truth` 子命令与本 README 的问题表。违反即该次运行作废（与"预注册期看结果"同罪）。
2. **提交**：每个问题产出一个 `verdict ∈ {supported, refuted, inconclusive}` 与 `evidence`
   （可寻址的命令或日志）。汇总为 `submissions.json`，见 `grade.py` 头部注释。
3. **评分**：与真值一致 = 正确；对假 claim 报 `supported` = 假阳性；对真 claim 报 `refuted`
   = 假阴性；`inconclusive` = 弃权；缺项 = 缺失。
4. **归档**：一次对比 = 一个 experiment（`scirearch new` → `run.sh` 跑两条流水线 →
   `grade.py` 的计数写入 `metrics.json`）。结论为负（机制无收益）照样按终态归档。
5. **基线**：同一 seed、同一模型档位下跑两条线——(a) 裸 agent；(b) 预注册 + 独立复核。
   两线之差才是"机制收益"，单跑一条没有意义。

## 已知限制（诚实声明）

- 真值与生成器在同一文件：隔离靠协议，而非技术强制。更强的做法是把真值托管到探查不到的位置
  （参照 nullius 的 custodian 设计），本仓库暂未采用。
- 5 个问题覆盖 4 类失效模式，样本量小：结论只能当方向性信号；建议每题 3+ seed，并重复两线对比。
- `q04` 中"某列显著"随 seed 波动：评分只看 verdict，不看具体 p 值。
