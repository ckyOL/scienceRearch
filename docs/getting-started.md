# 使用指南：从配置到第一次实验

面向**第一次拿到本仓库的人**（直接使用，或用 GitHub Template 建自己的库）。读完应当能：
装好环境 → 配好 omp 角色与护栏 → 预注册一个实验 → 跑出可校验的证据 → 知道哪里会失败、失败时看什么。

边界：本文回答"怎么配、怎么用"；**契约细节**（校验规则、退出码语义、复核要求）见
[experiment-protocol.md](experiment-protocol.md)；目录职责与设计取舍见 [architecture.md](architecture.md)。

---

## 0. 五分钟跑通

```bash
uv sync --dev                 # 或：python -m venv .venv && pip install -e ".[dev]"
uv run scirearch --version    # scirearch 0.1.0
make help                     # 全部开发命令
make check                    # 提交前闸门：格式 + lint + 测试 + 合同校验
```

`make check` 里的 `scirearch verify` 带 `--allow-empty`（仓库尚无实验时放行，与 CI 一致）。
到这一步为止，仓库是"可用的空壳"：没有任何实验，也没有任何结论。

---

## 1. 前置条件

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| Python | ≥ 3.11 | CI 跑 3.11 与 3.13；`scirearch` 运行时**零依赖**（纯标准库），保证任意环境可执行 |
| git | 必需 | git 时序防火墙依赖提交历史；非 git 目录/浅克隆降级为**警告**，强制点在 CI |
| uv（推荐）或 pip | 二选一 | `uv sync --dev` / `pip install -e ".[dev]"` |
| Oh My Pi (omp) | 可选，但推荐 | `.omp/` 下的子agent、hooks、skills 由 omp 加载。没有 omp 时，CLI 与目录约定照常可用，代价是失去角色分工与自动护栏 |

```bash
uv run scirearch --help       # new / status / verify / report
uv run scirearch verify --json   # 机读合同状态；当前无实验 → stderr 提示"未发现实验"，退出码 1
```

---

## 2. 第一次配置

### 2.1 用模板建自己的库（若适用）

本仓库已开启 GitHub **Template repository**；`gh repo create my-research --template ckyOL/scienceRearch --clone`。
模板**不带上游 commit 历史**，正好让 git 时序防火墙从你的第一次提交开始记账。建库后必做 5 件事
（占位符、LICENSE/CITATION、项目级 kill 判据、分支保护、本机模型角色表）见 README 的
「[用它作为模板](../README.md#用它作为模板)」；其中第 4 件（把 `experiment contract` 设为 required
status check）不做，闸门就只是日志行。

### 2.2 omp：模型角色与并发（模板 config + 本机角色表）

omp 以**当前工作目录**下的 `.omp/` 为项目根（`hooks/`、`agents/`、`config.yml` 都按 `<cwd>/.omp` 加载，
不向上查找祖先目录），所以**请在仓库根启动 omp**。会向上查找的只有 skills 与 `RULES.md` / `AGENTS.md`
这类上下文文件。见 `omp://config-usage.md`。

本仓库是**模板库**，所以配置分两层——**具体模型 id 是本机事实（provider 是否已认证、订阅计划是否包含），不入库**：

| 文件 | 是否入库 | 放什么 |
| --- | --- | --- |
| `.omp/config.yml` | **提交**（模板） | 项目行为：并发、隔离、`advisor`/`memory`/`checkpoint`、`agentModelOverrides`（agent→角色）。**不写任何具体模型 id** |
| `.omp/settings.json.example` | **提交**（模板） | 角色**契约**：本仓库需要哪些角色（值全是占位符）。改动它等于扩大契约 |
| `.omp/settings.json` | **ignore**（本机） | 由 example 复制而来，填入本机真实 `modelRoles`：每个角色指到你已认证且在计划内的模型 |

这就是 `*.example` / `*.dist` 那套惯例（WordPress `wp-config-sample.php`、Symfony `parameters.yml.dist`、Laravel `.env.example`、PHPUnit `phpunit.xml.dist`）：**示例入库、真实文件本机、契约文件随上游演进**——
Symfony 官方甚至会在两者分叉时提示你补新参数，`make roles-check` 对角色表做同样的事：

```bash
cp .omp/settings.json.example .omp/settings.json   # 首次；本机表所在文件已被 .gitignore
```

优先级由 omp 决定：项目 `.omp/settings.json` > 用户 `~/.omp/agent/config.yml` > 内建默认；
但项目 `.omp/config.yml` **高于** `.omp/settings.json` —— 所以别在两处定义同名角色。
`.omp/config.yml` 里的 `modelRoleStorage: global` 是为了防止 `/model` 的角色写入落进模板文件。
agent 文件只引用 `@角色` 别名，换模型不动 agent 定义。

| 角色 | 谁在用 | 选型要求 |
| --- | --- | --- |
| `default` | 主会话、`hypothesizer`、`writer` | 能力均衡；**本仓库里 `omp` 的初始模型就是它** |
| `smol` | `scout-lit`（只读侦察，量大且便宜）；prewalk 交接目标 | 最便宜的可用模型 |
| `worker` | `experimenter`、`replicator`（跑实验、复现） | 执行力强、便宜，长跑不心疼 |
| `review` | `critic`（对抗性复核） | 与 `worker` **不同模型族**，否则独立性打折 |
| `advisor` | `advisor: true` 的 agent（experimenter/critic/replicator/hypothesizer） | 在线旁路复核，必须与 `review` **也不同族**——同族只是同一个模型给两次意见 |
| `tiny` `task` `plan` `commit` `slow` `vision` | harness 自己：标题/记忆、bundled `task` agent 与 eval `agent()` 默认、计划模式、提交信息、`--slow`、收图 | 没覆盖就**继承用户层配置**（通常是编程向模型）→ 要么覆盖，要么知道它此刻是什么 |

第一次拿到模板：

```bash
cp .omp/settings.json.example .omp/settings.json   # 真实表在本机，已被 .gitignore
$EDITOR .omp/settings.json                          # 每个角色填本机已认证且在计划内的模型
make roles-check                                    # 缺表 / 缺角色 / 计划外，都会 fail loud
```

example 里的 11 个角色就是**契约**（缺哪个都算分叉，闸门会报 `契约角色 X 未在 .omp/settings.json 里定义`）：
`.omp/agents/` 直接引用 `default`/`smol`/`worker`/`review`/`advisor`，其余六个 `tiny` `task` `plan` `commit` `slow` `vision`
是 harness 自用（标题/记忆、eval `agent()` 默认、计划模式、提交信息、深推档、收图），**不覆盖就继承用户层，通常就是编程向模型**。
提交进库的 `.omp/config.yml` 则只有策略部分：

```yaml
modelRoleStorage: global              # /model 改角色写到用户层，别写进模板
task:
  maxConcurrency: 8                   # 并发实验数：按 CPU/GPU/额度收敛，不要吃满
  isolation:
    enabled: true                     # 并行实验的硬前提：isolated spawn 走独立工作区
  agentModelOverrides:                # bundled agent 的 frontmatter 无 model → 默认继承父会话模型
    task: "@task"                     # 这里按角色钉死，避免"隐式 agent 用了主会话模型"
    scout: "@smol"
    sonic: "@smol"
    reviewer: "@review"
    security-reviewer: "@review"
advisor:
  enabled: true
memory:
  backend: local
checkpoint:
  enabled: true
```

改完怎么确认生效：`make roles-check` —— 逐角色**真发一次最小请求**，并检查
① `.omp/config.yml` 没写 `modelRoles`（模板卫生）② `.omp/settings.json` 存在、没被提交、已被 ignore
③ example 的契约角色全部由本机表提供（缺失**不算通过**：那种"全绿"只是用户层模型在过关）
④ `@别名` 无悬空 ⑤ 每个角色「provider 已认证 + 模型在订阅计划内」，输出还会标出角色值来自 `local` 还是上层。
两层**静默**失败必须先知道（均为实测）：

1. `omp models` 列出的模型 ≠ 你有权调用。计划外模型只在真发请求时返回 `403 MODEL_NOT_IN_PLAN`
   （实测某账号 commandcode 计划里 `claude-*`、`gpt-5.4*` 即如此）→ 别肉眼看列表，跑闸门。
2. 子agent 分派时角色值不可用**不报错**：该条目被跳过，最终回退到**父会话模型**，分层静默失效
   （实测：`scout-lit` 的 `@smol` 回退成了主会话模型，`critic`/`experimenter` 同理 → 生成与复核落到同一个模型上）。
   只有 CLI 的 `omp -p --model '@角色'` 会硬报错（`No API key found for <provider>`）。

`default` 不可用时，主会话会回退到**本机保存的默认模型**（可能同样在计划外 → 一启动就 403），所以 `default` 必须指向计划内模型。
并发上限、隔离开关的具体字段语义见 `omp://config-usage.md`。

### 2.3 护栏与安全边界（必读）

- **子agent 的审批模式是 `yolo`**（headless 无交互确认），因此 `.omp/hooks/pre/` 是**唯一**自动拦截点。
- 护栏文件必须放在 `.omp/hooks/pre/`（或 `post/`）下：omp 的 native provider **只扫描这两个子目录**，
  直接放在 `.omp/hooks/` 里的文件不会加载、也**不报错**（见 `omp://hooks.md`）。本仓库的
  `guard-data-write.ts` 位置正确。
- 拦截生效时你会看到类似文字：`data/raw 只读：拒绝对 data/raw/... 的写入`，或
  `拦截命令（删除 data/raw）：data/raw 只读`。看到这句话说明护栏在工作，不是 bug。
- 派实验执行者**必须带 `isolated: true`**（独立工作区，产出分支/patch），避免并行实验互相污染主工作树。
- 人工闸门就是你自己：用 `/collab` 实时旁观，或按 [.omp/WATCHDOG.md](../.omp/WATCHDOG.md) 的清单抽查。

### 2.4 不可写清单（一句话版）

| 对象 | 谁可以写 | 你（人）**不要**做 |
| --- | --- | --- |
| `data/raw/` | 仅人工导入脚本 | 写入/删除/移动/解包/重定向（hook 拦截；绕过即安全事件） |
| `metrics.json` | 只能由 `run.sh` 产出 | 手工编辑（证据链断裂，数字不可信） |
| `experiment.json` 的 `status` | 只能由 `scirearch status` 改（写入前会被闸门校验） | 直接编辑（`history` 与 `status` 不一致会被 `verify` 检出） |
| `hypothesis.md` / 判据 / 证伪路径 / seed | 创建时一次性写入 | 创建后任何编辑（sha256 漂移，`verify` 退出码 1） |
| `paper/`、`docs/`、汇报里的数字 | 必须能解析到 `experiments/<id>/` 的产物 | 手写数字 |

---

## 3. 第一次实验（端到端，含真实输出）

以下是完整走查；命令与输出取自本仓库的实际运行（输出为节选）。

### 步骤 1 · 预注册（判据先于结果）

```bash
uv run scirearch new fixed-seed-baseline \
  -H "固定 seed 下基线方差小于 1%" \
  -m "std(accuracy) over 5 seeds" \
  -c "std_accuracy < 0.01" -c "无 NaN" \
  -f "5 个 seed 的 std 大于 0.01 即放弃该假设" \
  --seed 1729
```

```text
已创建预注册实验：experiments/exp-0001-fixed-seed-baseline
判据：1 条机器可判定 / 1 条自由文本（自由文本由复核者人工裁定）
预注册哈希：criteria=0e631b57a56e… hypothesis.md=4f621e84c6e5…
下一步：先提交预注册（git 时序是证据）→ 编辑 run.sh 的 RUN= 一行 → 执行
```

- `-f`（证伪路径）是**必填**：先写"什么结果会让你放弃"，再创建。
- 判据两种形态：`指标 运算符 数值`（机器三态求值）、自由文本（`report` 标 `[人工]`，人工裁定）。
- 目录由 CLI 生成（`experiments/exp-NNNN-<slug>/`），**不要手工创建实验目录**。

### 步骤 2 · 先提交预注册

```bash
git add experiments/exp-0001-fixed-seed-baseline
git commit -m "prereg: exp-0001"
```

git 历史是时序证据：预注册提交必须**严格早于**结果提交。实验类提交用 merge commit / rebase，
**不要 squash**（压成一个提交 = 时序证据失效）。

### 步骤 3 · 只改 `run.sh` 的一行 + 写你的脚本

`run.sh` 是生成好的骨架，合同依赖它导出 seed、记录 git 版本与时间戳、并把原始输出 `tee` 到 `logs/`：

```bash
#!/usr/bin/env bash
# 可重跑入口（exp-0001）。
# 只修改下面标记的 RUN= 一行；seed 导出、git 版本、时间戳与 tee 是合同依赖，请保持不动。
set -euo pipefail
cd "$(dirname "$0")"

export SEED="${SEED:-1729}"
RUN="python -m your_module.train --seed ${SEED}"   # <-- 唯一需要修改的行
...
```

你只需要把 `RUN=` 换成真实命令。`SEED` 已导出到环境，脚本里读 `os.environ["SEED"]` 或走 `--seed` 参数都行：

```python
# experiments/exp-0001-fixed-seed-baseline/train.py（示例，真实实验换成你的训练/评估脚本）
import json, os, random, statistics
from pathlib import Path

seed = int(os.environ["SEED"])
acc = [0.9 + random.Random(seed + i).uniform(-0.004, 0.004) for i in range(5)]
print("runs:", [round(a, 5) for a in acc])
Path("metrics.json").write_text(
    json.dumps({"std_accuracy": round(statistics.pstdev(acc), 5), "runs": 5}) + "\n"
)
```

用法：`RUN="python3 train.py"`。临时换 seed：`SEED=99 bash experiments/exp-0001-fixed-seed-baseline/run.sh`。

### 步骤 4 · 执行

```bash
bash experiments/exp-0001-fixed-seed-baseline/run.sh
```

```text
# cmd: python3 train.py
# seed: 1729
# git: f50eac8
# started: 20260920T082923Z
runs: [0.90397, 0.8975, 0.89986, 0.89798, 0.8971]
# finished: 20260920T082923Z
```

原始 stdout/stderr 落盘到 `logs/run-<UTC 时间戳>.log`；`metrics.json` 由脚本写出（禁止手改）。
长跑任务（训练/仿真）请交给 omp 托管（`hub op:"start"`，见 §4.3），不要占着交互会话。

### 步骤 5 · 预检（推荐，但不再是唯一防线）

```bash
uv run scirearch status exp-0001 running
uv run scirearch verify experiments/exp-0001-fixed-seed-baseline
```

```text
| 实验 | 状态 | 判据（机器/人工） | seed | 证据 | 提交 | 合同 |
| --- | --- | --- | --- | --- | --- | --- |
| exp-0001 fixed-seed-baseline | running | 1 满足 · 1 人工 | 1729 | metrics+1log | — | 通过 |

### 判据判定
- exp-0001 `std_accuracy < 0.01` → 满足（std_accuracy=0.00253）[机器]
- exp-0001 `无 NaN` → 人工裁定（自由文本判据）[人工]
```

`running` 状态下 `verify` 就会给出判据的三态结果（退出码 0）——看清了再定终态。

### 步骤 6 · 定终态

```bash
uv run scirearch status exp-0001 completed \
  --metrics experiments/exp-0001-fixed-seed-baseline/metrics.json \
  --reason "5 个 seed 的 std 满足判据"
```

| 目标状态 | 何时用 | 机器检查 |
| --- | --- | --- |
| `completed` | 可求值判据**全部满足** | 出现违反即判"判据冲突"（退出码 2） |
| `refuted` | **至少一条**可求值判据被违反 | 全部满足却报 `refuted` 同样冲突 |
| `inconclusive` | 判据无法裁决、证据不足，或假设被别的观察否定 | 合法终态，证据要求与 `completed` 相同 |
| `abandoned` | 主动放弃（未产出结论） | 同样要求 metrics + 日志 + seed |

> **`status` 是闸门，不是记事本。** 写入前它会按目标状态模拟一次完整校验：**任何会被 `verify`
> 判失败的推进直接拒绝，状态保持不变**——退出码 `1`（合同非法：缺日志/缺 seed/`--metrics` 不在规范路径…）
> 或 `2`（判据冲突）。这是必须的：**终态不可回退**，若先写状态再报问题，实验会被永久钉在一个不合法的
> 状态上，既过不了 `verify` 也无法改判，只能重建。
>
> `--metrics` 必须是 `experiments/<id>/metrics.json`：**`verify` 只读这个路径**（放在别处会被判"终态缺少
> metrics.json"）。

### 步骤 7 · 提交结果，让时序检查转绿

```bash
git add -A && git commit -m "experiment: exp-0001 completed"
uv run scirearch verify
```

提交前 `verify` 会给一条**警告**（不阻断本地）：`git 时序不可判定：metrics.json 未提交`；
结果提交之后变为 `通过`，退出码 0。CI 以 `fetch-depth: 0` 的完整历史裁定同一件事。

### 步骤 8 · 汇总

```bash
uv run scirearch report          # markdown：判据判定 + 问题/警告 + 负知识索引
uv run scirearch report --json   # 机读：criteria / inconsistencies / refuted_index
```

`report` 里标 `[人工]` 的判据必须由复核者逐条裁定，**不要**把它当成"已验证"。

---

## 4. 日常：把实验交给 agent

### 4.1 角色表（`.omp/agents/`）

| 角色 | 模型别名 | 干什么 | 何时用 |
| --- | --- | --- | --- |
| `scout-lit` | `@smol` | 文献/代码/数据只读侦察 | 动手前摸清现状 |
| `hypothesizer` | `@default` | 产出可证伪假设 + 事前判据 | 把一个方向拆成 K 条竞争假设 |
| `experimenter` | `@worker` | 执行**单个**假设，产出可重跑证据（**spawn 时带 `isolated: true`**） | 实验落地 |
| `replicator` | `@worker` | 干净工作区从零重跑，报告指标是否落在预注册判据内 | 盖章前的外部有效性检查 |
| `critic` | `@review` | 对抗性审计（只读，禁改文件） | 结论提交前的独立复核 |
| `writer` | `@default` | 把已验证证据组织成报告/稿件片段（`tools` 无 `bash`/`eval`，无法自行产生数字） | 写作阶段 |

### 4.2 派活的硬约束

1. **生成与复核分离**：同一 agent、同一模型、同一上下文不得既产出结论又裁定结论。
   最低配：`experimenter`（worker 模型）→ `critic` 或 `replicator`（review/换模型 + 干净上下文）。
2. **`experimenter` 必须 `isolated: true`**：并行实验各自独立工作区，结果经 merge 成为证据。
3. **子agent 不继承对话历史**：共享背景写进 `task` 的 `context`（Goal / Constraints / Contract），
   或先写到 `local://<name>.md` 再引用。
4. **一次一个假设**：`experimenter` 不做跨实验汇总、不并行展开；多个实验由你在外层批量分派。
5. **产出走 schema**：`experimenter` 的 `output` 要求 `hypothesis_id/command/seed/metrics/artifacts/verdict/caveats`
   齐全（`caveats` 为空也要显式 `[]`）。

### 4.3 长任务与追问

- 训练/仿真等长跑进程：`hub op:"start"` 托管（`ready.log` 匹配启动行），再用 `hub logs`/`hub wait` 观察；
  **不要**把长跑塞进交互会话。
- 想追问同一个实验员而不是重派：用 `hub send` 唤醒原有 agent（保留上下文），或读 `history://<id>`。
- 想实时旁观：`/collab`。

---

## 5. 校验、汇总与写作闸门

```bash
uv run scirearch verify              # 全部实验
uv run scirearch verify --json       # 机读，供 CI 或子agent 消费
uv run scirearch verify <实验目录>    # 单个实验
```

| 退出码 | 含义 | 典型触发 |
| --- | --- | --- |
| `0` | 通过（可能有警告） | 判据自洽、证据齐全、时序可证明或不可判定 |
| `1` | 合同非法 | 缺 seed/日志/`run.sh`、预注册哈希漂移、`preregistered` 状态下已有 `metrics.json`、指标缺失、状态非法 |
| `2` | 判据冲突 | `completed` 却存在违反，或 `refuted` 却全部满足 |

写作闸门：`writer` 只引用**终态且 `verify` 通过**的实验；每个数字都要能解析到 `experiments/<id>/`
的产物（`metrics.json`、`logs/` 或 manifest）。**`verify` 通过 ≠ 结论正确**：它是完整性控制
（合同 + 可求值判据自洽），不是独立 attestation；结论接受由独立复核者裁定。

---

## 6. 故障排查（报错文案均为实测）

| 症状 / 报错 | 原因 | 处理 |
| --- | --- | --- |
| `❌ 预注册违规：status=preregistered 时已存在 metrics.json` | 先跑实验后写判据/先产出结果 | 删除 `metrics.json` 并回到流程；判据必须早于结果，重做时按步骤 1 重新预注册 |
| `❌ 预注册漂移：criteria 的 sha256 与登记值不一致` | 事后改了判据 | 撤销改动；确需新判据 → 新建实验 |
| `❌ 预注册漂移：hypothesis.md 的 sha256 …（预注册镜像创建后不得编辑）` | 编辑了人读镜像 | 同上（连加注释、改标点也会被抓） |
| `❌ 预注册漂移：hypothesis/metric/criteria/falsification/seed 与登记哈希不一致` | 改了 manifest 里的预注册字段（含"改完重算哈希"） | 撤销；git 冻结提交另有独立检查 |
| `错误：拒绝写入状态 completed（状态未变更）：判据被违反却标记为 completed …` | 结论与判据不一致 | 按判据改判：有违反 → `refuted`；无法裁决 → `inconclusive`；判据确实错了只能新建实验（判据冻结）。**状态没有被写下去**，所以没有留下不可回退的非法终态 |
| `错误：拒绝写入状态 refuted（状态未变更）：可判定判据全部满足却标记为 refuted …` | 结论与判据不一致 | 全部满足应写 `completed`；确因其他观察否定假设则写 `inconclusive` |
| `⚠️ git 时序不可判定：metrics.json 未提交` | 结果尚未提交（或非 git/浅克隆） | 本地不阻断；提交后复查；CI 需 `fetch-depth: 0` |
| `预注册违规` 出现在"预注册与结果同一个提交" | squash 合并把两次提交压成一次 | 拆成两次提交；实验类 PR 用 merge/rebase |
| `错误：拒绝写入状态 …：终态缺少非空原始日志（logs/ 为空）` | 终态必须有原始 stdout | 先 `bash experiments/<id>/run.sh` 产出日志再推进（证据文件不受冻结限制，可补） |
| `错误：拒绝写入状态 …：终态缺少 seed` | `new` 时没有 `--seed`，而 seed 属于冻结的预注册记录 | 无法补登：新建实验并按原判据登记 seed，或重新预注册 |
| `错误：拒绝写入状态 …：终态缺少 metrics.json` | `--metrics` 指向了规范路径之外的副本 | 让 `run.sh` 把指标写到 `experiments/<id>/metrics.json`（`verify` 只读该路径） |
| `错误：拒绝写入状态 …：预注册漂移 …` | 判据/镜像/manifest 被改过 | 先撤销改动（`git checkout -- experiments/<id>`）再推进；预注册字段不可事后修改 |
| `终态缺少非空原始日志（logs/ 为空）` / `终态缺少 seed`（来自 `verify`） | 绕过 CLI（旧版 / 手工编辑）写下的终态 | 补日志后复查；seed 缺失或判据冲突只能重建实验 |
| `run.sh 不可执行（chmod +x run.sh）` | 权限位丢了 | `chmod +x experiments/<id>/run.sh` |
| `缺少可重跑入口 run.sh` | 文件被删/改名 | 从其他实验复制骨架并改 `RUN=` |
| `错误：指标文件不存在：experiments/.../metrics.json` | `--metrics` 相对 **cwd** 解析，不是相对 `--root` | 用绝对路径，或在仓库根执行命令 |
| `非法状态转移 preregistered -> completed` | 跳步 | 先 `running`，再定终态 |
| `非法状态转移 completed -> refuted；从 completed 只能转到：（终态，不可变更）` | 终态回退 | 终态不可回退。`status` 的写入前闸门已挡住"会被判失败的终态"，因此这种状态只可能来自绕过 CLI 的写入（旧版 / 手工编辑）→ 新建实验重做 |
| `⚠ 负知识命中：同一判据曾在 exp-0001（refuted）被证伪` | 重提已被证伪的判据 | 允许，但必须在假设里说明**新证据**（新数据/新设计/原实验缺陷）；`experiment.json` 会记 `prior_refutations` |
| `未发现实验：请先 scirearch new，或在 CI 中使用 --allow-empty` | 仓库还没有实验 | 本地先建实验；CI 已带 `--allow-empty` |
| `data/raw 只读：拒绝对 … 的写入` | 护栏命中（正常行为） | 派生物写 `data/interim/` 或 `experiments/<id>/` |
| `verify` 说 `history 与 status 不一致` | 有人手工改了 `status` | 用 `scirearch status` 推进；必要时重建实验目录 |
| 子agent 实际跑的模型与 `modelRoles` 不符（例：`critic` 跑成了主会话模型） | 角色值不可用（provider 未认证 / 不在计划内）→ 分派时**静默回退到父会话模型** | `make roles-check` 定位；换成本机已认证且在计划内的模型（§2.2） |
| 在仓库里直接 `omp` 启动就 `403 MODEL_NOT_IN_PLAN` | `modelRoles.default` 指向计划外模型，或不可用后回退到本机保存的默认模型 | 把 `default` 指向计划内模型，或启动时 `--model` 显式指定；`make roles-check`（§2.2） |
| `omp -p --model '@角色'` 报 `No API key found for <provider>` | 该角色的 provider 没认证（CLI 硬报错；子agent 分派则静默回退，不报这一条） | `omp login` 或换成已认证 provider 的模型；跑 `make roles-check` |
| `roles-check` 报 `config.yml 里出现了 modelRoles` | 模板文件被写了具体模型：会盖掉本机 `.omp/settings.json`，且随模板库分发 | 把这段 `modelRoles` 移到 `.omp/settings.json`（§2.2）；`config.yml` 只留项目策略 |
| `roles-check` 报 `settings.json 未被 git 忽略` / `已被 git 跟踪` | 本机模型表有进库风险 | 恢复 `.gitignore` 的 `.omp/settings.json` 行；已提交过则 `git rm --cached .omp/settings.json` |
| `roles-check` 报 `缺少本机角色表 .omp/settings.json` | 新克隆还没建本机表（此时"全绿"只会是用户层模型在过关，所以闸门直接停） | `cp .omp/settings.json.example .omp/settings.json` 后填写，再重跑 |
| `roles-check` 报 `契约角色 X 未在 .omp/settings.json 里定义` | 模板新增了角色（契约文件变了），本地表没跟上 → 该角色会静默继承用户层 | 把缺的角色补进 `.omp/settings.json`（值取本机可用模型） |

排查顺序建议：`scirearch verify --json <实验目录>` 看 `problems`（合同）与 `inconsistencies`（判据），
再逐条对照本表；`report` 看全局与负知识索引。

---

## 7. 命令速查

```bash
# 环境
uv sync --dev && make check

# 预注册 → 提交 → 执行 → 定终态 → 校验 → 汇总
uv run scirearch new <slug> -H "假设" -m "指标" -c "std_accuracy < 0.01" -f "证伪路径" --seed N
git add experiments/<id> && git commit -m "prereg: <id>"
bash experiments/<id>/run.sh
uv run scirearch status <id> running
uv run scirearch verify experiments/<id>          # 预检（定终态前）
uv run scirearch status <id> completed --metrics experiments/<id>/metrics.json --reason "…"
git add -A && git commit -m "experiment: <id>"
uv run scirearch verify
uv run scirearch report

# Makefile
make help | make fmt | make lint | make test | make verify | make report | make roles-check | make check

# omp 侧
omp models            # 列出本机可用模型（注意：可用 ≠ 计划内；计划外模型只在真发请求时 403）
omp config list       # 查看/核对设置
make roles-check      # 角色表闸门：逐角色真发一次最小请求，验证「已认证 + 计划内 + 别名不悬空」
```

---

## 8. 术语与不变量

| 术语 | 含义 |
| --- | --- |
| 预注册 | 假设、指标、判据、证伪路径、seed 在跑实验**之前**写下并冻结（三个 sha256），事后修改即违规 |
| 判据 | 事前承诺的决策规则；可求值形式在 `metrics.json` 上三态求值（满足/违反/不可判定），自由文本由人工裁定并标 `[人工]` |
| 负知识 | 已证伪判据按 `criteria_sha256` 进入索引；重提前必须带新证据 |
| 时序防火墙 | 预注册提交严格早于结果提交；冻结块不得漂移（CI 以完整历史裁定） |
| 完整性控制 ≠ attestation | `verify` 证明合同与判据自洽，不证明结论正确；接受与否由独立复核裁定 |
| 隔离工作区 | `isolated: true` 的 spawn：子agent 在独立 git 工作区执行，结果经 merge 成为证据 |

不变量（任何环节都不得违反）：判据先于结果、预注册创建即冻结、终态必须有 seed 与非空原始日志、
终态不可回退、生成与复核分离、负结果同等留痕、`data/raw/` 只读。

需要更细的规则时读：[experiment-protocol.md](experiment-protocol.md)（协议全文）、
[architecture.md](architecture.md)（分层与取舍）、[../experiments/README.md](../experiments/README.md)（实验目录）、
[../CONTRIBUTING.md](../CONTRIBUTING.md)（贡献与评审）。
