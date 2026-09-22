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

### 变更

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
