# 实验协议

适用对象：人类研究者、`experimenter`/`replicator` 子agent、以及任何自动化流水线。
违反协议的产物不会被 `scirearch verify` 接受，也不会被 `writer` 引用。

## 1. 目录与命名

```text
experiments/exp-0001-fixed-seed-baseline/
├─ hypothesis.md     # 人读镜像：假设 / 判据 / 证伪路径（创建即冻结，不可编辑）
├─ experiment.json   # 机读真相源：manifest + preregistration 哈希 + 状态历史
├─ run.sh            # 可重跑入口：固定 seed、原始日志 tee 到 logs/（只改 RUN= 一行）
├─ metrics.json      # 机读指标（只由 run.sh 产出，禁止手工编辑）
└─ logs/             # 原始 stdout/stderr（终态必须非空）
```

`id` 由 `scirearch new` 顺序分配（`exp-NNNN`），`slug` 为小写下划线短语。**不要手工创建实验目录**。

### 1.1 预注册是不变量，不是提示

`scirearch new` 在创建时登记三个 sha256（`experiment.json.preregistration`）：

| 哈希 | 覆盖内容 | 检出什么 |
| --- | --- | --- |
| `criteria_sha256` | 判据集合（顺序 + 内容；空白折叠后规范化） | 事后改判据、增删判据 |
| `hypothesis_md_sha256` | `hypothesis.md` 全文（CRLF 归一） | 事后编辑人读镜像 |
| `record_sha256` | 假设 / 指标 / 判据 / 证伪路径 / seed | 事后修改任何预注册字段 |

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
- 若同一判据曾被判 `refuted`，`new` 会命中负知识索引：stderr 告警，并在 manifest 写入
  `prior_refutations`——重提前必须在假设里说明新证据（§2.7）。

### 2.2 先提交预注册，再跑实验

```bash
git add experiments/exp-0001-fixed-seed-baseline && git commit -m "prereg: exp-0001"
```

git 历史是时序证据：**预注册提交必须严格早于结果提交**（`metrics.json` 的首次提交），
且冻结提交之后预注册块不得被编辑。这是 CI 上的强制检查（§2.5）。

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

求值只读：不修改判据、不触碰 `metrics.json`。数字由此**只经过脚本与 CLI，不经过模型转写**。

### 2.5 状态推进与校验

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
`status` 会立刻回显合同问题（如有），完整报告用：

```bash
scirearch verify                 # 全部实验
scirearch verify --json          # 机读输出，供 CI 或子agent 消费
```

**状态与判据必须一致（判据即预注册的决策规则）：**

- `completed` ⇒ 所有可求值判据都满足；出现违反即判"判据冲突"。
- `refuted` ⇒ 至少一条可求值判据被违反；全部满足却报 `refuted` 同样是冲突。
- `inconclusive` ⇒ 判据无法裁决或证据不足时的合法终态。

**退出码（ArmProof 语义）：**

| 码 | 含义 |
| --- | --- |
| `0` | 全部通过 |
| `1` | 合同非法：缺证据、预注册哈希漂移、git 时序违规、指标缺失、状态非法… |
| `2` | 判据冲突：状态与可求值判据不一致（argparse 用法错误同样返回 2） |

**git 时序防火墙（终态实验）：**

1. 预注册提交（`experiment.json` 首次出现）必须严格早于结果提交（`metrics.json` 首次出现）；
2. 冻结提交中的 `preregistration` 块必须与当前 manifest 一致（改判据+重算哈希也逃不过）；
3. 不可判定项（未提交、浅克隆、非 git 目录）记为**警告**，不阻断本地流程——
   强制点在 CI：`experiment contract` job 以 `fetch-depth: 0` 检出完整历史。

### 2.6 汇总与写作

```bash
scirearch report          # markdown：判据判定 + 问题/警告 + 负知识索引
scirearch report --json   # 机读：criteria / inconsistencies / refuted_index
```

`writer` 只能引用终态、且 `verify` 通过（或问题已在 PR 中处置）的实验。稿件中每个数字都应能
解析到 `experiments/<id>/` 的产物；`report` 里标注为 `[人工]` 的判据，引用时必须同时给出
复核者的裁定记录。

**机器判定 ≠ 独立 attestation**：`verify` 只证明合同与判据自洽（完整性控制），
不证明结论正确；结论接受由独立复核者（`critic`/`replicator`）裁定。

### 2.7 负知识：被证伪的判据不会消失

- `report` 汇总所有 `refuted` 实验的判据哈希（`criteria_sha256`）为负知识索引；
- 再次提出同一判据时，`scirearch new` 命中索引并写入 `prior_refutations`；
- 重提是允许的，但必须给出新证据（新数据、新设计、原实验的已知缺陷），并在假设中写明；
- `notes/dead-ends/` 保留非实验形式的死路（见 `notes/README.md`）。

## 3. 复核（独立且对抗）

复核者与生成者必须是**不同 agent、不同模型、不同上下文**。四个必检方向：

1. **一致性**：`metrics.json` 与 `logs/` 逐项核对；找出被丢弃的 run（未披露的筛选 = 结论失效）。
2. **预注册**：`verify --json` 的 `inconsistencies`/`problems` 是否为空；判据是否与决策规则一致；
   `[人工]` 标注的判据是否被逐条裁定。
3. **统计**：显著性、多重比较、方差来源；关键区间复算一遍。
4. **泄漏与合规**：切分是否泄漏、是否触碰 `data/raw/`、是否改动过判据。

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
| `completed` 但判据被违反（或反之） | 判据冲突（退出码 2） | 改判 `refuted`/`inconclusive`，或修正证据 |
| 可求值判据引用的指标缺失 | 合同问题 | 让 `run.sh` 产出该指标，或把判据降级为自由文本 |
| 丢弃 refuted 结果 | 选择性报告 | 保留为终态；report 中如实呈现 |
| 用强模型既生成又复核 | 自我一致性偏差 | 换 agent/模型/上下文重审 |

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
