# 更新日志

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
