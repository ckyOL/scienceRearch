---
name: paper-template
description: 论文/报告骨架与可复现性清单：证据可解析断言、图表来源、限制章节。写作阶段读取。
---

# 稿件骨架

```markdown
# 标题

## 摘要
（一句话结论 + 一句最强证据 + 一句主要限制）

## 1. 问题与假设
- H1: …（对应 experiments/exp-0001-…，预注册于 <日期>）

## 2. 方法
- 数据：`data/raw/...`（版本/哈希）
- 切分：…（泄漏检查结论）
- 指标与判据：与 `experiment.json.criteria` 逐条一致

## 3. 结果
| 假设 | 实验 | 状态 | 指标 | 判据 | 产物 |
| --- | --- | --- | --- | --- | --- |
| H1 | exp-0001 | completed | std=0.0031 | <0.01 ✅ | logs/run-….log |

## 4. 限制与负结果
- 被证伪的假设与其证据（不得省略）
- caveats 汇总

## 5. 复现方式
```bash
uv sync --dev && make check
SEED=1729 bash experiments/exp-0001-…/run.sh
scirearch verify
```

## 附录：断言—证据对照
| 正文断言 | experiment_id | artifact |
| --- | --- | --- |
```

# 可复现性清单（提交前逐条打勾）

- [ ] 稿件中每个数字都能在 `experiments/<id>/` 找到出处（附录对照表完整）
- [ ] 所有引用实验均为终态且 `scirearch verify` 通过（退出码 0）
- [ ] `report` 标 `[人工]` 的判据已由复核者逐条裁定；未把机器判定写成"结论已验证"
- [ ] `refuted` / `inconclusive` 结果与 `caveats` 如实呈现
- [ ] 复现命令从零可跑（新克隆 + `make check` + 单条 `run.sh`）
- [ ] 环境信息（Python 版本、关键依赖、硬件）与 commit 哈希已记录
- [ ] 外部文献引用可核查（arXiv/DOI/URL），无凭记忆编造

# 写作红线

- 不得出现无法解析的数字；不得把 `refuted` 描述成"趋势一致"。
- 不得用同一 agent/模型既生成结论又裁定结论。
- 不得把 `agent` 的产出当作已验证事实转述。
