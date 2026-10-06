# 实验协议

第一次使用本仓库（环境、omp 角色与护栏配置、端到端走查、故障排查）先读
[getting-started.md](getting-started.md)；本文是契约细节。

适用对象：人类研究者、`experimenter`/`replicator` 子agent、以及任何自动化流水线。
违反协议的产物不会被 `scirearch verify` 接受，也不会被 `writer` 引用。

## 1. 目录与命名

```text
experiments/exp-0001-fixed-seed-baseline/     # kind=experiment
├─ hypothesis.md     # 人读镜像：假设 / 判据 / 证伪路径（创建即冻结，不可编辑）
├─ experiment.json   # 机读真相源：manifest + preregistration 哈希 + 状态历史
├─ run.sh            # 可重跑入口：固定 seed、原始日志 tee 到 logs/（只改 RUN= 一行）
├─ metrics.json      # 机读指标（只由 run.sh 产出，禁止手工编辑）
└─ logs/             # 原始 stdout/stderr（终态必须非空）

experiments/exp-0002-mechanism/               # kind=thought-experiment
├─ hypothesis.md     # 人读镜像（含"阻碍实验的条件"）
├─ experiment.json   # manifest + preregistration + history
├─ reasoning.md      # 论证 / 反例搜索 / 可测试化路径（终态冻结 sha256）
├─ review.json       # 独立复核：逐条裁定判据（rejected / promoted 必需）
└─ （不得出现 metrics.json）
```

`id` 由 `scirearch new` 顺序分配（`exp-NNNN`），`slug` 为小写下划线短语。**不要手工创建实验目录**。

两类记录共用同一套冻结与留痕机制，但裁决方式不同（`--kind` 在 `new` 时确定，创建后不可改）：

| kind | 适用 | 证据 | 状态 |
| --- | --- | --- | --- |
| `experiment`（默认） | 可执行、可测量的假设 | `run.sh` → `metrics.json` + `logs/` + `seed` | `preregistered → running → {completed, refuted, inconclusive, abandoned}` |
| `thought-experiment` | 当前无法实验的假说（必须在 `blockers` 里写明卡在哪） | `reasoning.md` + `review.json`（人工复核） | `speculative → {rejected, promoted, abandoned}` |

**思想实验不构成经验证据**：它没有 `metrics.json`（出现即判失败），不得作为 `paper/` 的结论引用；
条件具备时应转为正式实验并用 `promoted --superseded-by exp-NNNN` 留下转换痕迹。

### 1.1 预注册是不变量，不是提示

`scirearch new` 在创建时登记三个 sha256（`experiment.json.preregistration`）：

| 哈希 | 覆盖内容 | 检出什么 |
| --- | --- | --- |
| `criteria_sha256` | 判据集合（顺序 + 内容；空白折叠后规范化） | 事后改判据、增删判据 |
| `hypothesis_md_sha256` | `hypothesis.md` 全文（CRLF 归一） | 事后编辑人读镜像 |
| `record_sha256` | kind / 假设 / 指标 / 判据 / 证伪路径 / 阻碍条件 / seed | 事后修改任何预注册字段（含把实验改标为思想实验） |

三者任一漂移即判失败；同时在 git 上校验"冻结提交"（见 §2.5）。

## 2. 流程

### 2.1 预注册（判据先于结果）

```bash
scirearch new <slug> \
  --hypothesis "固定 seed 下基线方差小于 1%" \
  --metric "std(accuracy) over 5 seeds" \
  --criteria "std_accuracy < 0.01" --criteria "无 NaN" \
  --falsification "5 个 seed 的 std 大于 0.01 即放弃该假设" \
  --seed 1729
```

- **证伪路径是必填项**（`-f`）：先写下"什么结果会让你放弃"，再创建实验。
- `hypothesis.md` 与 manifest 同时生成、同时冻结；创建后不要编辑（改动会被 `verify` 检出）。
- 判据两种形态：

| 形态 | 示例 | 判定方式 |
| --- | --- | --- |
| 可求值 | `std_accuracy < 0.01`、`results.std >= 1e-3` | 在 `metrics.json` 上三态求值（§2.4） |
| 自由文本 | `无 NaN`、`图表无系统性偏移` | 由复核者人工裁定，`report` 标注为 `[人工]` |

- 此刻状态为 `preregistered`。**在这个状态下出现 `metrics.json` 即判为预注册违规**。
- 若同一判据曾被否定（`refuted` 实验 / `rejected` 思想实验），`new` 会命中负知识索引：stderr 告警，并在
  manifest 写入 `prior_refutations`——重提前必须在假设里说明新证据（§2.7）。

**当前无法实验的假说**（`kind=thought-experiment`，§2.8）：

```bash
scirearch new <slug> --kind thought-experiment \
  --hypothesis "机制 M 是主因" \
  --metric "论证自洽性 / 与 exp-0003 的一致性" \
  --criteria "论证自洽" --criteria "不与既有结论冲突" \
  --falsification "出现反例或与既有结论冲突即放弃该机制解释" \
  --blockers "缺少可控干预手段：只能观察，不能随机分配"
```

- **`-b/--blockers` 是思想实验的必填项**：写清什么条件缺失使它现在无法实验。没有它，任何"懒得跑"的主张
  都能挂成思想实验——这个字段就是防这道滑坡的。反过来，`--blockers` 不能用于可执行实验。
- 思想实验不接受 `--seed` / `--run-cmd`（没有执行），状态从 `speculative` 起步，判据一律不由机器求值。
- 思想实验**不得**出现 `metrics.json`；一旦有了可测量指标，就 `scirearch new` 建正式实验并用
  `promoted --superseded-by exp-NNNN` 转过去。

### 2.2 先提交预注册，再跑实验

```bash
git add experiments/exp-0001-fixed-seed-baseline && git commit -m "prereg: exp-0001"
```

git 历史是时序证据：**预注册提交必须严格早于结果提交**（实验=`metrics.json`、思想实验=`review.json`
的首次提交），且冻结提交之后预注册块不得被编辑。这是 CI 上的强制检查（§2.5）。

实验类提交请用 merge commit / rebase 合入：**squash 会把预注册与结果压成同一个提交**，
时序证据随之失效，`verify` 将判为违规。

### 2.3 执行

只修改 `run.sh` 中标记的那一行 `RUN=`；其余部分（seed 导出、git 版本、时间戳、`tee` 到
`logs/`）保持不动。

```bash
bash experiments/exp-0001-fixed-seed-baseline/run.sh
```

要求：

- **固定 seed**，并通过环境变量可覆盖（`SEED=... bash run.sh`）。
- 原始输出必须落盘到 `logs/`；不得只保留摘要。
- 长跑任务交给 omp 托管（`hub op:"start"`），不要占用交互会话。
- 中间产物写入 `data/interim/`，**不要写 `data/raw/`**（hook 会拦截）。

### 2.4 判据求值（三态）

`verify` 把每条可求值判据在 `metrics.json` 上求值为三态之一：

| 状态 | 含义 | 表现 |
| --- | --- | --- |
| 满足 / 违反 | 指标存在且为数值，比较成立 / 不成立 | `report` 附实际值与 `[机器]` |
| 不可判定 | 指标缺失或不是数值；或判据为自由文本 | 缺失 = 合同问题；自由文本 = `[人工]` |
| 待定 | 实验尚未产出 `metrics.json` | 非终态的正常形态 |
| 复核裁定（仅思想实验） | 三态来自 `review.json` 的 `rulings` | `report` 标 `[人工]`；思想实验永不产出 `metrics.json` |

求值只读：不修改判据、不触碰 `metrics.json`。数字由此**只经过脚本与 CLI，不经过模型转写**。

### 2.5 状态推进与校验

```bash
scirearch status experiments/exp-0001-fixed-seed-baseline running
scirearch status experiments/exp-0001-fixed-seed-baseline completed \
  --metrics experiments/exp-0001-fixed-seed-baseline/metrics.json \
  --reason "判据全部满足"

# 思想实验
scirearch status experiments/exp-0002-mechanism rejected \
  --review experiments/exp-0002-mechanism/review.json --reason "前提自相矛盾"
scirearch status experiments/exp-0002-mechanism promoted \
  --review experiments/exp-0002-mechanism/review.json \
  --superseded-by exp-0003 --reason "已能构造对照条件"
```

合法转移（按 kind 分流，跨类型状态一律拒绝）：

| kind | 当前 | 允许的下一状态 |
| --- | --- | --- |
| `experiment` | `preregistered` | `running`, `abandoned` |
| `experiment` | `running` | `completed`, `refuted`, `inconclusive`, `abandoned` |
| `thought-experiment` | `speculative` | `rejected`, `promoted`, `abandoned` |
| 任意 | 终态 | 不可变更 |

各状态需要的证据：

| 目标 | 必需 | 说明 |
| --- | --- | --- |
| `completed` / `refuted` / `inconclusive` | `--metrics`（规范路径）+ 非空 `logs/` + `seed` | `refuted` / `inconclusive` **同样需要完整证据**——负结果是最容易被悄悄丢弃的资产 |
| `rejected` / `promoted` | `--review`（规范路径）+ 非空 `reasoning.md`；`promoted` 另需 `--superseded-by` | 见 §2.8 |
| `abandoned` | `--reason` | 放弃不产出结论，也**不需要** metrics / 日志 / 复核记录（此前要求 metrics，等于让"跑不了"的假说无法合法收口）。目录里**既有**的产物不删除，但它不产出 verdict、不进负知识索引、不可被引用 |

**写入前闸门（先模拟，后落盘）：** `status` 在写入前按目标状态模拟一次完整校验，任何会被
`scirearch verify` 判失败的推进**直接拒绝、状态不变**，退出码与 verify 同语义：

| 退出码 | 触发 | 例 |
| --- | --- | --- |
| `1` | 合同非法（证据/预注册/时序） | 判据满足但 `logs/` 为空；终态缺 seed；`--metrics` 不在 `experiments/<id>/metrics.json`；`review.json` 漏判判据或复核者与生成者同 agent/模型 |
| `2` | 判据冲突 | 判据被违反却写 `completed`；判据全部满足却写 `refuted`；无一条判据被裁定违反却写 `rejected` |

这条闸门存在的理由：**终态不可回退**。若"先写状态、再回显问题"，实验会被永久钉在一个不合法的
状态上——既过不了 `verify`，也无法改判 `refuted`/`inconclusive`，只能重建实验。
因此正确用法是：`verify <实验目录>` 先看清判据三态（`running` 状态下即可查看），再选终态。

**边界**：闸门与落盘之间没有锁或事务——并发修改证据文件（另一进程改写 `review.json`、删除
`reasoning.md`、动 git 工作树）不在合同保证范围内。约定是实验目录**单写者**；并行实验用
`isolated: true` 的独立工作区，结果经 merge 成为证据。

`--metrics` 必须指向 `experiments/<id>/metrics.json`：**`verify` 只读这个规范路径**，
把指标文件放在别处虽然能被 `status` 读到，但会被判为"终态缺少 metrics.json"。
`--review` 同理，必须指向 `experiments/<id>/review.json`。

完整报告用：

```bash
scirearch verify                 # 全部记录
scirearch verify --json          # 机读输出，供 CI 或子agent 消费
```

**状态与判据必须一致（判据即预注册的决策规则）：**

- `completed` ⇒ 所有可求值判据都满足；出现违反即判"判据冲突"。
- `refuted` ⇒ 至少一条可求值判据被违反；全部满足却报 `refuted` 同样是冲突。
- `rejected` ⇒ 复核裁定中至少一条判据为 `violated`；全部 `satisfied` 却报 `rejected` 同样是冲突
  （若因其他理由放弃，应写 `abandoned`）。
- `inconclusive` / `promoted` ⇒ 判据无法裁决或证据不足时的合法终态，不要求判据一致性。

**退出码（ArmProof 语义）：**

| 码 | 含义 |
| --- | --- |
| `0` | 全部通过 |
| `1` | 合同非法：缺证据、预注册哈希漂移、git 时序违规、指标缺失、状态非法… |
| `2` | 判据冲突：状态与可求值判据不一致（argparse 用法错误同样返回 2） |

**git 时序防火墙（全部终态，含思想实验）：**

1. 预注册提交（`experiment.json` 首次出现）必须严格早于结果提交（实验=`metrics.json`、
   思想实验=`review.json` 首次出现）；
2. 冻结提交中的 `preregistration` 块必须与当前 manifest 一致（改判据+重算哈希也逃不过）；
3. 不可判定项（未提交、浅克隆、非 git 目录）记为**警告**，不阻断本地流程——
   强制点在 CI：`experiment contract` job 以 `fetch-depth: 0` 检出完整历史。

### 2.6 汇总与写作

```bash
scirearch report          # markdown：判据判定 + 问题/警告 + 负知识索引
scirearch report --json   # 机读：records / criteria / inconsistencies / negative_index
```

`writer` 只能引用终态、且 `verify` 通过（或问题已在 PR 中处置）的**实验**（`completed`/`refuted`/`inconclusive`）。
稿件中每个数字都应能解析到 `experiments/<id>/` 的产物；`report` 里标注为 `[人工]` 的判据，
引用时必须同时给出复核者的裁定记录。

**思想实验不是证据**：`speculative` / `rejected` / `promoted` 不得作为结论引用（`report` 会显式标注）。
它们只能出现在开放问题、研究议程或"已排除的解释"讨论里，并且必须写明其裁决来自复核裁定而非测量。

**机器判定 ≠ 独立 attestation**：`verify` 只证明合同与判据自洽（完整性控制），
不证明结论正确；结论接受由独立复核者（`critic`/`replicator`）裁定。

### 2.7 负知识：被否定的判据不会消失

- `report` 汇总所有 `refuted`（实验）与 `rejected`（思想实验）的判据哈希（`criteria_sha256`）为负知识索引；
- 再次提出同一判据时，`scirearch new` 命中索引并写入 `prior_refutations`（含来源状态与类型）；
- 重提是允许的，但必须给出新证据（新数据、新设计、原实验的已知缺陷、新的论证或反例），并在假设中写明；
- `notes/dead-ends/` 保留非实验形式的死路（见 `notes/README.md`）。

### 2.8 思想实验（`kind=thought-experiment`）

用于**原则上可证伪、但当前无法执行**的假说：先把它按预注册规则登记，写清阻碍条件，再由独立复核者
逐条裁定判据——要么 `rejected`，要么 `promoted` 转成正式实验。它绝不产出经验结论。

流程：

```bash
# 1) 预注册（判据 + 证伪路径 + 阻碍条件，创建即冻结）
scirearch new <slug> --kind thought-experiment \
  -H "机制 M 是主因" -m "论证自洽性 / 与 exp-0003 的一致性" \
  -c "论证自洽" -c "不与既有结论冲突" \
  -f "出现反例或与既有结论冲突即放弃" \
  -b "缺少可控干预手段"

# 2) 先提交预注册，再在 reasoning.md 写论证（前提 / 论证 / 反例搜索 / 可测试化路径）

# 3) 派独立复核者（不同 agent、不同模型）逐条裁定判据，产出 review.json

# 4) 收口
scirearch status <id> rejected --review experiments/<id>/review.json --reason "前提 2 与前提 1 冲突"
# 或：先 scirearch new 建正式实验，再
scirearch status <id> promoted --review experiments/<id>/review.json --superseded-by exp-NNNN
```

`review.json`（终态必需，位于 `experiments/<id>/review.json`）：

```json
{
  "reviewer": { "agent": "critic", "model": "provider/model-x" },
  "generator": { "agent": "hypothesizer", "model": "provider/model-y" },
  "verdict": "rejected",
  "rulings": [
    { "criterion": "论证自洽", "ruling": "violated", "note": "前提 2 与前提 1 冲突" },
    { "criterion": "不与既有结论冲突", "ruling": "unclear", "note": "文献不足以判断" }
  ],
  "signed_at": "2026-09-22T00:00:00Z"
}
```

约束（违反即 `verify` 失败，退出码 1）：

- `rulings[].ruling ∈ {satisfied, violated, unclear}`，且必须**逐条覆盖** manifest 的判据；
  多了、少了、重复、文本对不上都判失败（判据创建即冻结，不得在复核阶段追加）。
- `reviewer.agent` 与 `generator.agent` **且** `model` 必须不同——生成/复核分离。该字段是自声明，
  属完整性控制而非 attestation：它的作用是让"自我复核"在结构上可见，而不是密码学证明。
- `verdict` 必须等于目标状态；`rejected` 要求至少一条 `violated`（否则判据冲突，退出码 2）。
- `reasoning.md` 必须在终态前非空；终态时其 sha256 记入 `history`，此后编辑即判"论证漂移"。
- `promoted` 必须给 `--superseded-by exp-NNNN`，且该 id 必须解析到**存在的、`kind=experiment` 的**记录；
  悬空引用或指向另一个思想实验都判失败。`promoted` 只表示"已转入可执行实验"，**不表示假设成立**。
- 思想实验目录出现 `metrics.json` 即判失败：经验证据只能走正式实验（顺带提醒：出现 `run.sh` 会得到一条
  建议转正的警告）。
- 终态仍需 git 时序：预注册提交必须严格早于 `review.json` 的首次提交。

## 3. 复核（独立且对抗）

复核者与生成者必须是**不同 agent、不同模型、不同上下文**。四个必检方向：

1. **一致性**：`metrics.json` 与 `logs/` 逐项核对；找出被丢弃的 run（未披露的筛选 = 结论失效）。
2. **预注册**：`verify --json` 的 `inconsistencies`/`problems` 是否为空；判据是否与决策规则一致；
   `[人工]` 标注的判据是否被逐条裁定。
3. **统计**：显著性、多重比较、方差来源；关键区间复算一遍。
4. **泄漏与合规**：切分是否泄漏、是否触碰 `data/raw/`、是否改动过判据。

**思想实验的复核**（§2.8）额外要求：复核者必须真的去推翻论证——搜索反例、检查前提是否隐含结论、
核对与既有结论的冲突；`rulings` 里每条裁定都要给出理由（`note`）。`critic` 是只读的：它产出裁定，
由调用方**按其原样**写入 `review.json`（不得代改裁定内容或补写 `reviewer` 身份）。

omp 侧：`critic`（只读批判）与 `replicator`（干净工作区重跑）承担 1–4；`advisor` +
`.omp/WATCHDOG.md` 做持续在线复核；`/collab` 供人类实时旁观。

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
| 事后改判据 / 改 `hypothesis.md` / 改证伪路径 | 哈希漂移（`problems`） | 撤销改动；确需新判据则新建实验 |
| 预注册与结果挤进同一提交（含 squash 合并） | git 时序违规 | 拆成两次提交；实验类 PR 用 merge/rebase |
| 手改 `metrics.json` | 证据链断裂 | 重跑；数字一律由 `run.sh` 产出 |
| 只保留汇总日志 | 无法回溯 | 重新执行并保留原始 stdout |
| `completed` 但判据被违反（或反之） | 判据冲突（退出码 2） | `status` 已在写入前拒绝；改判 `refuted`/`inconclusive`，或修正证据。仅当状态是绕过 CLI（旧版 CLI / 手工编辑）写下时才需要重建实验 |
| 试图写下会被 `verify` 判失败的终态 | `status` 拒绝，退出码 1（合同）或 2（判据冲突），状态不变 | 先 `verify <实验目录>` 预检；按提示补证据或改判状态 |
| 可求值判据引用的指标缺失 | 合同问题 | 让 `run.sh` 产出该指标，或把判据降级为自由文本 |
| 丢弃 refuted 结果 | 选择性报告 | 保留为终态；report 中如实呈现 |
| 用强模型既生成又复核 | 自我一致性偏差 | 换 agent/模型/上下文重审 |
| 思想实验目录里放 `metrics.json` | 合同问题（退出码 1） | 经验证据只能走正式实验：`new` 建实验，再把思想实验 `promoted --superseded-by` 指向它 |
| `review.json` 漏判/多判判据，或 `verdict` 与状态不符 | 合同问题（退出码 1） | 逐条覆盖 manifest 判据；判据不允许在复核阶段追加（要改判据只能新建记录） |
| 复核者与生成者同 agent 或同模型 | 合同问题（退出码 1） | 换 agent 且换模型；该字段自声明，人工复核仍不可省 |
| 裁决后编辑 `reasoning.md` | 论证漂移（退出码 1） | 撤销改动；要改结论只能新建记录（终态不可回退） |
| `promoted` 指向不存在的 id 或另一个思想实验 | 合同问题（退出码 1） | 先 `scirearch new` 建正式实验，再 `--superseded-by` 指向它的 id |
| 把"能跑但不想跑"的假说挂成思想实验 | 证据逃避 | `--blockers` 必须写出具体缺失条件；若不成立，就是正式实验 |

## 6. 闸门必须被依赖

CI 里的 `experiment contract` job 只有在被设为 **required status check** 之后才是闸门，
否则门跑红也照样能合并——它只是日志行（honest-signal 的实测事故）。

设置方式（仓库管理员，二选一）：

```bash
# CLI：要求 main 上必须通过 "experiment contract" 才能合并
gh api -X PUT repos/{owner}/{repo}/branches/main/protection \
  -F "required_status_checks[strict]=true" \
  -F "required_status_checks[contexts][]=experiment contract"
```

或在 GitHub UI：Settings → Branches → Branch protection rules → Require status checks →
勾选 `experiment contract`。

配套要求：`contract` job 使用 `fetch-depth: 0`（浅克隆下 git 时序检查降级为警告）。
