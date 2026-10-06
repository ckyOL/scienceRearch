# 更新日志

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- **角色可用性闸门 `make roles-check`**（`scripts/roles-check.sh`）：逐角色真发一次最小请求，验证
  「provider 已认证 + 模型在订阅计划内 + `@别名` 无悬空」，并强制模板卫生——提交进库的 `.omp/config.yml`
  不得含 `modelRoles`、本机角色表 `.omp/settings.json` 必须存在且已被 `.gitignore`、角色契约
  `.omp/settings.json.example` 里的角色必须由本机表覆盖。动机是两层**静默**失败：`omp models` 列出的
  模型不等于有权调用（计划外模型只在真发请求时返回 `403 MODEL_NOT_IN_PLAN`），而子agent 分派遇到不可用
  角色不报错、直接回退到父会话模型（`review` 与 `worker` 会落到同一个模型上，复核独立性失效且无告警）。
- **模型角色分层约定**：模板只提交项目策略 `.omp/config.yml` 与角色契约 `.omp/settings.json.example`；
  具体模型 id 属本机事实，放被 `.gitignore` 的 `.omp/settings.json`
  （`cp .omp/settings.json.example .omp/settings.json` 后填写），与 `*.example` / `*.dist` 惯例一致
  （WordPress `wp-config-sample.php`、Symfony `parameters.yml.dist`、Laravel `.env.example`、PHPUnit `phpunit.xml.dist`）。

- **使用指南**（[docs/getting-started.md](docs/getting-started.md)）：首次配置（前置条件、`modelRoles`
  角色映射、护栏加载位置、required check）、端到端第一次实验走查（含预检与终态选择）、与子agent 协作的
  硬约束、**实测报错 → 处理**的故障排查表、命令速查与不变量清单。
- **预注册冻结（manifest schema v2）**：`scirearch new` 要求 `-f/--falsification`，并把 `criteria`、
  `hypothesis.md` 与预注册记录（假设/指标/判据/证伪路径/seed）的三个 sha256 写入 manifest；
  `verify` 检出任何事后修改。
- **判据机械化**：`指标 运算符 数值` 形式的判据在 `metrics.json` 上三态求值（满足 / 违反 / 不可判定）；
  自由文本判据在 `report` 中标注 `[人工]`，由复核者裁定。
- **状态一致性门**：`completed` 不得有判据违反、`refuted` 必须有违反，否则 `verify` 退出码 2。
- **git 时序防火墙**：预注册提交必须严格早于结果提交，且冻结提交中的预注册块不得漂移
  （浅克隆 / 未提交降级为警告；CI 以 `fetch-depth: 0` 裁定）。
- **负知识索引**：`report` 汇总已证伪判据（按 `criteria_sha256`）；`new` 命中历史证伪时告警并写入
  `prior_refutations`。
- **已知真值问题库**：`analysis/known-truth/`（零效应 / 真实效应 / 混杂 / 多重比较 / 泄漏）与评分器，
  用于度量"预注册 + 独立复核"相对裸 agent 的收益。
- **项目级预注册**：`docs/project-preregistration.md` 登记项目主张与自注册 kill 判据。
- `scirearch verify` 退出码语义：0 通过 / 1 合同非法 / 2 判据与状态冲突（ArmProof 语义）。

- **思想实验通道（manifest schema v3）**：`scirearch new --kind thought-experiment` 支持**原则上可证伪、
  当前无法实验**的假说：`-b/--blockers` 必填（写清什么条件缺失使它无法实验），状态机为
  `speculative → {rejected, promoted, abandoned}`，证据是 `reasoning.md`（终态冻结 sha256）+
  `review.json`（独立复核逐条裁定**全部**判据，`rulings[].ruling ∈ {satisfied, violated, unclear}`）。
  机器层面禁止 `metrics.json`、禁止 `completed`/`refuted`、禁止跨类型状态；
  `promoted` 必须指向**真实存在的 `kind=experiment` 记录**（`--superseded-by exp-NNNN`，悬空引用即失败），
  且只表示"已转入可执行实验"，不表示假设成立。动机：此前"跑不了"的假说没有合法落点——
  连 `abandoned` 都要求 metrics + 日志 + seed，唯一"能收口"的方式是塞一个自由文本判据 + 手写
  `metrics.json` 骗过 `completed`（实测可复现，属合同漏洞）。`report` 对思想实验显式标注
  "不构成经验证据，不得作为 `paper/` 结论引用"。
- `scirearch status --review <path>` / `--superseded-by <id>`：思想实验终态的收口参数；
  `review.json` 的 `reviewer`/`generator`（agent 与 model 都必须不同）为自声明的生成/复核分离标记
  （完整性控制，非 attestation）。
- `scirearch report` 的负知识索引改为覆盖**被否定**的判据（`refuted` 实验 + `rejected` 思想实验），
  条目含 `kind`/`status`；`new` 的负知识告警同时给出来源状态与类型。
- `.omp/agents/critic` 新增 `review_rulings` 输出字段与思想实验复核职责（只读产出裁定，由调用方原样落盘）；
  `hypothesizer` 的假设 schema 新增 `kind`/`blockers`（跑不了的方向必须给出阻碍条件）。
- 测试：`tests/test_thought_experiment.py`（type 隔离、metrics 禁令、复核裁定完整性、生成/复核分离、
  论证冻结、promotion 悬空引用、abandoned 免证据、负知识索引、git 时序、CLI 组合校验）。
- **独立模型复核驱动的加固**（异模型审计 findings，逐条处置）：判据不得重复（空白折叠后互异）；
  `superseded_by` 先做 id 格式校验（防路径穿越/通配符），并要求目标 manifest 的 `id` 与引用一致；
  复核者/生成者身份比较先 strip + casefold（防 `"critic "` 之类的伪分离）；`metrics.json` / `review.json`
  不可读（非 UTF-8、权限、I/O）改为结构化失败而不是抛异常；负知识索引只收录 `verify` 通过的记录
  （手工写下的非法终态不构成已确立的否定）。

### 变更

- **`abandoned` 不再要求 `--metrics` / 日志 / seed，改为要求 `--reason`**：放弃不产出结论，也不需要证据；
  此前"决定不跑"的记录无法合法收口，只能永远挂在 `preregistered`。
- 预注册记录哈希（`record_sha256`）覆盖面扩大：新增 `kind` 与 `blockers`——把实验改标为思想实验同样会被检出。
- `scirearch report --json` 的正文字段 `experiments` → `records`、`refuted_index` → `negative_index`
  （一条记录可能是实验或思想实验，旧名已不准确）；`verify`/`report` 的表格新增"类型"列，
  `verify --json` 的结果对象新增 `kind`/`has_reasoning`/`has_review`。
- `.omp/config.yml` 不再包含任何具体模型 id：只留项目策略（并发、隔离、advisor、memory、checkpoint、
  `agentModelOverrides`）与 `modelRoleStorage: global`（防止 `/model` 的角色写入落进模板文件）。
  模型表移到本机 `.omp/settings.json`，模板新增契约文件 `.omp/settings.json.example`，
  `.gitignore` 忽略 `.omp/settings.json`。
- **更正一处错误描述**：`docs/getting-started.md` §2.2 此前称"角色别名解析失败会在 spawn 时报模型不可用、
  不会静默降级"——实测相反（静默回退到父会话模型；只有 CLI `omp -p --model '@角色'` 会硬报错）。
  §2.2 同时重写为「模板 config + 本机角色表 + 契约」三层说明，故障排查表补充角色/闸门相关条目，
  README 的模板必做清单增至 5 项（新增"配好本机模型角色表并跑闸门"）。
- `run.sh` 模板改为 `export SEED`：此前 `SEED` 只作为 shell 变量赋值，脚本读 `os.environ["SEED"]`
  会失败，只有在 `RUN=` 里显式引用 `${SEED}` 才能拿到 seed。现在两种写法都成立（模板注释里的
  "seed 导出" 与实现一致）。
- `scirearch new` 的证伪路径不再是"事后填写"的提示，而是预注册的一部分（必填、冻结）。
- **`scirearch status` 改为写入前闸门**：推进前按目标状态模拟一次完整校验，任何会被 `scirearch verify`
  判失败的推进**直接拒绝、状态不变**，退出码与 verify 同语义（1 合同非法 / 2 判据冲突）。
  此前是"先写入、再回显问题"——终态不可回退，一次手滑就把实验永久钉在判据冲突或证据缺失上
  （既过不了 `verify`，也无法再改判 `refuted`/`inconclusive`）。`verify` 的检出能力不变：
  绕过 CLI 写下的状态（旧版 CLI / 手工编辑）照样判失败。
- `scirearch status --metrics` 要求指标文件位于 `experiments/<id>/metrics.json`：`verify` 只读该规范路径，
  把副本放在别处会被判"终态缺少 metrics.json"，现在在写入前就被拒绝。
- `scirearch report` 增列判据判定、负知识索引与机器/人工标注（完整性控制 ≠ attestation）。
- CI `experiment contract` job 改用 `fetch-depth: 0`；模板使用说明新增"把该 job 设为 required
  status check"这一步。
- 实验协议、架构、omp 设施（RULES / WATCHDOG / experimenter / critic / replicator / skill）同步更新。
- 仓库开启 GitHub **Template repository**（`is_template=true`）；README 增补"用它作为模板"
  （`gh repo create --template`）与模板后必做步骤（占位符、上游专属 kill 判据、required check）。
- 调研文档（[docs/research-agent-with-omp.md](docs/research-agent-with-omp.md)）增补：GitHub 开源生态对照（§1.1，含同题项目机制表）、借鉴清单与落地优先级（§7）、参考区生态项目列表、§7 实施进度。

### 迁移

- manifest schema v1 → v2：v1 实验缺少 `preregistration` / `falsification`，会被 `verify` 拒绝
  （本仓库尚无既有实验，无实际迁移成本）。旧实验如需保留，用 `scirearch new` 按原始判据与证伪路径
  重建目录并重新登记冻结哈希；已产出的证据（`logs/`、`metrics.json`）可手工复制入新目录，
  但需接受"冻结时间点为重建时"这一事实。
- manifest schema v2 → v3：v2 记录缺少 `kind`，且预注册记录哈希不含 `kind`/`blockers`，会被 `verify` 拒绝
  （本仓库尚无既有记录，无实际迁移成本）。迁移方式同 v1 → v2：用 `scirearch new` 按原始假设、判据、
  证伪路径与 seed 重建；`experiments/` 目录下的既有证据文件可复制入新目录。

## [0.1.0] - 2026-09-17

### 新增

- `scirearch` CLI：`new`（预注册脚手架）、`status`（状态机推进）、`verify`（合同校验）、`report`（汇总）。
- 实验合同：判据先于结果、终态必须有 seed 与非空原始日志、`run.sh` 可执行、状态不可跳转、变更留痕。
- omp 设施：6 个研究角色 agent（`scout-lit` / `hypothesizer` / `experimenter` / `replicator` / `critic` / `writer`）、
  2 个技能（`experiment-protocol` / `paper-template`）、`data/raw` 写入护栏 hook、advisor 复核清单与项目配置。
- 仓库模板：CI（lint / 双版本测试 / 合同校验）、issue 表单（含"预注册假设"模板）、PR 证据清单、Dependabot、社区文档。
- 文档：领域调研（[docs/research-agent-with-omp.md](docs/research-agent-with-omp.md)）、架构、实验协议。

[Unreleased]: https://github.com/ckyOL/scienceRearch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ckyOL/scienceRearch/releases/tag/v0.1.0
