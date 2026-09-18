# 更新日志

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

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

- `scirearch new` 的证伪路径不再是"事后填写"的提示，而是预注册的一部分（必填、冻结）。
- `scirearch status` 在推进后立即回显合同问题；`scirearch report` 增列判据判定、负知识索引与
  机器/人工标注（完整性控制 ≠ attestation）。
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
