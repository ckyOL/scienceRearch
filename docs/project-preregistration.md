# 项目级预注册（自注册 kill 判据）

> 来源：调研 §7 借鉴 #6（honest-signal 的 self-registered kill criteria）。
> 登记：2026-09-17 ｜ 到期判定：2027-03-17 ｜ 状态：有效

项目级主张同样会漂移：没有事先写下的"什么结果算失败"，事后解释总能自圆其说。
本文件把项目自身的主张变成**可核验**的判据，到期按判据机械判定；结论（尤其负结论）
与实验一样完整留痕、公开归档。

## 1. 主张与 kill 判据

| # | 主张 | kill 判据（可核验） | 到期 | 判定方式 |
| --- | --- | --- | --- | --- |
| P1 | 合同层（预注册哈希 + 判据求值 + git 时序）能被外部研究者采用 | 到期前无任何外部仓库/研究者实际使用（依赖引用、README 引用、issue、或外部 `experiments/` 目录均可作数） | 2027-03-17 | §2 命令 |
| P2 | 机械化判据能捕获真实违规，且收益可测 | 在已知真值问题库上，"预注册 + 独立复核"相对裸 agent 的正确率无优势 | 2027-03-17 | `analysis/known-truth/` 双线对比 |
| P3 | 合同闸门在自身仓库被依赖（不是日志行） | 出现绕过 `experiment contract` 合并的实验类 PR | 持续 | 分支保护 required check 状态 |

## 2. 判定命令（可复现）

```bash
# P1：外部引用计数（需已登录的 gh；0 = kill 判据成立）
gh api -X GET search/code -f q='"scirearch verify" -repo:ckyOL/scienceRearch' --jq .total_count
gh api -X GET search/code -f q='"ckyOL/scienceRearch" -repo:ckyOL/scienceRearch' --jq .total_count
```

P2 的对比跑成一次 experiment：同一 seed、同一模型档位下跑两条线（裸 agent / 预注册+独立复核），
`grade.py` 的计数写入 `metrics.json`，按 `scirearch` 合同归档。

## 3. 到期后的动作（先写下，再执行）

- **P1 成立** → 承认"合同 CLI 作为分发形态"未达成，按调研 §1.1 的推论转向 skills 形态分发
  （把合同规则打包为 skill + 零依赖冻结/审计脚本），并在 CHANGELOG 与调研文档记录该结论。
- **P2 无优势** → 在调研文档公开该负结果，并重新评估"判据机械化"是否值得保留在合同层。
- **P3 成立** → 记录为 incident（合并发生在哪个 PR、为什么闸门未拦截），并补齐分支保护配置。

以上三种结论为负时同样完整归档；禁止静默丢弃或改写判据。

## 4. 修订规则

本文件可以随项目演进修订，但每次修订必须在 CHANGELOG 中留痕，且不得在没有理由记录的情况下
推后到期日期。
