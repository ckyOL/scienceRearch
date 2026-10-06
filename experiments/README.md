# experiments/

每条记录一个目录，由 `scirearch new` 生成，**不要手工创建**：

```text
exp-0001-fixed-seed-baseline/        # kind=experiment：可执行实验
├─ hypothesis.md     # 人读镜像：假设 / 判据 / 证伪路径（创建即冻结，不可编辑）
├─ experiment.json   # 机读真相源：manifest + preregistration 哈希 + 状态历史
├─ run.sh            # 可重跑入口：固定 seed、记录 git 版本与时间戳、tee 到 logs/
├─ metrics.json      # 指标：只能由 run.sh 产出，禁止手工编辑
└─ logs/             # 原始 stdout/stderr：终态必须非空

exp-0002-mechanism/                  # kind=thought-experiment：思想实验
├─ hypothesis.md     # 人读镜像（含"阻碍实验的条件"）
├─ experiment.json   # manifest + preregistration + history
├─ reasoning.md      # 论证 / 反例搜索 / 可测试化路径（终态冻结 sha256）
├─ review.json       # 独立复核：逐条裁定判据（rejected / promoted 必需）
└─ （不得出现 metrics.json：思想实验不携带经验证据）
```

## 两类记录

| kind | 适用 | 裁决方式 | 状态 |
| --- | --- | --- | --- |
| `experiment` | 可执行、可测量的假设 | `metrics.json` 三态求值（机器） | `preregistered → running → {completed, refuted, inconclusive, abandoned}` |
| `thought-experiment` | 当前无法实验的假说（`-b/--blockers` 写明卡在哪） | `reasoning.md` + `review.json` 逐条复核裁定（人工） | `speculative → {rejected, promoted, abandoned}` |

**思想实验不构成经验证据**：`report` 会标注，不得作为 `paper/` 的结论引用；一旦条件具备就建正式实验，并用
`promoted --superseded-by exp-NNNN` 把它转过去（`promoted` 只表示"已可实验"，不表示假设成立）。
思想实验目录永不出现 `metrics.json`——出现即 `verify` 失败。

## 预注册冻结（schema v3）

创建时登记三个 sha256：`criteria`（判据集合）、`hypothesis.md`（人读镜像）、预注册记录
（kind / 假设 / 指标 / 判据 / 证伪路径 / 阻碍条件 / seed）。任何事后修改都会被 `scirearch verify` 检出——包括
"改判据 + 顺手重算哈希"：git 历史中的冻结提交会拆穿它。

**先提交预注册，再跑实验/写复核**：预注册提交必须严格早于结果提交
（实验=`metrics.json`、思想实验=`review.json` 的首次提交）。
实验类提交不要 squash 合并（会把两次提交压成一次，时序证据失效）。

## 状态机

实验：`preregistered → running → {completed | refuted | inconclusive | abandoned}`。
思想实验：`speculative → {rejected | promoted | abandoned}`。终态不可回退；每次变更写入 `history`（含时间、原因、证据路径）。

**推进是闸门**：`scirearch status` 在写入前按目标状态模拟一次完整校验，任何会被 `scirearch verify`
判失败的推进**直接拒绝、状态不变**（退出码 1 合同非法 / 2 判据冲突）。因为终态不可回退，
"先写状态、再报问题"会把实验永久钉在一个既不合法、也无法改判的状态上。

证据要求（按状态）：

| 目标 | 必需 |
| --- | --- |
| `completed` / `refuted` / `inconclusive` | `--metrics`（必须是 `experiments/<id>/metrics.json`）、非空 `logs/`、`seed` |
| `rejected` / `promoted` | `--review`（必须是 `experiments/<id>/review.json`）、非空 `reasoning.md`；`promoted` 还需 `--superseded-by exp-NNNN` |
| `abandoned` | 只需 `--reason`（放弃不产出结论，也不需要证据） |

`review.json` 形态：

```json
{
  "reviewer": { "agent": "critic", "model": "provider/model-x" },
  "generator": { "agent": "hypothesizer", "model": "provider/model-y" },
  "verdict": "rejected",
  "rulings": [{ "criterion": "论证自洽", "ruling": "violated", "note": "前提 2 与前提 1 冲突" }],
  "signed_at": "2026-09-22T00:00:00Z"
}
```

- `ruling ∈ {satisfied, violated, unclear}`，必须**逐条覆盖** manifest 里的全部判据（多、少、错文本都判失败）；
- `rejected` 要求至少一条 `violated`（对应 `refuted` 的语义）；`promoted` 不设此要求；
- `reviewer` 与 `generator` 的 agent **且** model 必须不同（生成/复核分离；该字段自声明，属完整性控制而非 attestation）；
- 终态时 `reasoning.md` 的 sha256 写入 `history`，此后编辑即判"论证漂移"。

## 判据

- **实验·可求值形式**：`指标 运算符 数值`（如 `std_accuracy < 0.01`、`results.std >= 1e-3`），
  在 `metrics.json` 上三态求值（满足 / 违反 / 不可判定）；
- **自由文本**：机器不求值，`report` 标注 `[人工]`，由复核者裁定；
- **思想实验**：判据一律不由机器求值（没有 `metrics.json`），三态来自 `review.json` 的裁定，`report` 标注 `[人工]`；
- 状态必须与判据一致：`completed` ⇒ 可求值判据全满足；`refuted` ⇒ 至少一条被违反；`rejected` ⇒ 至少一条被裁定违反；
  不一致即 `verify` 退出码 2。

## 证据策略

- **日志入库**：实验的 `logs/` 是终态的必要证据，默认提交（`.gitignore` 未忽略）。
- 单次运行日志超过 10MB 时，改为外部存储，并在 `experiment.json` 的 `history` 或 PR 描述中登记 URL + sha256。
- `metrics.json` 与日志必须一致可复算；不一致即视为证据链断裂。
- 被否定的判据（`refuted` / `rejected`）按 `criteria_sha256` 进入负知识索引，重提前必须给出新证据。

## 常用命令

```bash
# 实验
scirearch new <slug> -H "假设" -m "指标" -c "std_accuracy < 0.01" -f "证伪路径" --seed N
bash experiments/<id>/run.sh
scirearch status <id> running
scirearch status <id> completed --metrics experiments/<id>/metrics.json --reason "判据满足"

# 思想实验（当前无法实验的假说）
scirearch new <slug> --kind thought-experiment -H "假设" -m "裁决依据" -c "判据" -f "证伪路径" -b "阻碍条件"
scirearch status <id> rejected --review experiments/<id>/review.json --reason "前提自相矛盾"
scirearch status <id> promoted --review experiments/<id>/review.json --superseded-by exp-NNNN --reason "已可实验"

scirearch verify   # 退出码：0 通过 / 1 合同非法 / 2 判据冲突
scirearch report   # 判据判定 + 负知识索引（标注思想实验不构成证据）
```

协议详见 [../docs/experiment-protocol.md](../docs/experiment-protocol.md)。
