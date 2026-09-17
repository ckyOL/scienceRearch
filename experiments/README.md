# experiments/

每个假设一个目录，由 `scirearch new` 生成，**不要手工创建**：

```text
exp-0001-fixed-seed-baseline/
├─ hypothesis.md     # 人读镜像：假设 / 判据 / 证伪路径（创建即冻结，不可编辑）
├─ experiment.json   # 机读真相源：manifest + preregistration 哈希 + 状态历史
├─ run.sh            # 可重跑入口：固定 seed、记录 git 版本与时间戳、tee 到 logs/
├─ metrics.json      # 指标：只能由 run.sh 产出，禁止手工编辑
└─ logs/             # 原始 stdout/stderr：终态必须非空
```

## 预注册冻结（schema v2）

创建时登记三个 sha256：`criteria`（判据集合）、`hypothesis.md`（人读镜像）、预注册记录
（假设/指标/判据/证伪路径/seed）。任何事后修改都会被 `scirearch verify` 检出——包括
"改判据 + 顺手重算哈希"：git 历史中的冻结提交会拆穿它。

**先提交预注册，再跑实验**：预注册提交必须严格早于 `metrics.json` 的首次提交。
实验类提交不要 squash 合并（会把两次提交压成一次，时序证据失效）。

## 状态机

`preregistered → running → {completed | refuted | inconclusive}`，另有 `abandoned`。
终态不可回退；每次变更写入 `history`（含时间、原因、指标路径）。

## 判据

- **可求值形式**：`指标 运算符 数值`（如 `std_accuracy < 0.01`、`results.std >= 1e-3`），
  在 `metrics.json` 上三态求值（满足 / 违反 / 不可判定）；
- **自由文本**：机器不求值，`report` 标注 `[人工]`，由复核者裁定；
- 状态必须与判据一致：`completed` ⇒ 判据全满足；`refuted` ⇒ 至少一条被违反；
  不一致即 `verify` 退出码 2。

## 证据策略

- **日志入库**：`logs/` 是终态的必要证据，默认提交（`.gitignore` 未忽略）。
- 单次运行日志超过 10MB 时，改为外部存储，并在 `experiment.json` 的 `history` 或 PR 描述中登记 URL + sha256。
- `metrics.json` 与日志必须一致可复算；不一致即视为证据链断裂。

## 常用命令

```bash
scirearch new <slug> -H "假设" -m "指标" -c "std_accuracy < 0.01" -f "证伪路径" --seed N
bash experiments/<id>/run.sh
scirearch status <id> running
scirearch status <id> completed --metrics experiments/<id>/metrics.json --reason "判据满足"
scirearch verify   # 退出码：0 通过 / 1 合同非法 / 2 判据冲突
scirearch report   # 判据判定 + 负知识索引
```

协议详见 [../docs/experiment-protocol.md](../docs/experiment-protocol.md)。
