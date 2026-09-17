# experiments/

每个假设一个目录，由 `scirearch new` 生成，**不要手工创建**：

```text
exp-0001-fixed-seed-baseline/
├─ hypothesis.md     # 人读：假设 / 判据 / 证伪路径
├─ experiment.json   # 机读真相源：manifest + 状态历史（含 seed、commit、criteria）
├─ run.sh            # 可重跑入口：固定 seed、记录 git 版本与时间戳、tee 到 logs/
├─ metrics.json      # 指标：只能由 run.sh 产出，禁止手工编辑
└─ logs/             # 原始 stdout/stderr：终态必须非空
```

## 状态机

`preregistered → running → {completed | refuted | inconclusive}`，另有 `abandoned`。
终态不可回退；每次变更写入 `history`（含时间、原因、指标路径）。

## 证据策略

- **日志入库**：`logs/` 是终态的必要证据，默认提交（`.gitignore` 未忽略）。
- 单次运行日志超过 10MB 时，改为外部存储，并在 `experiment.json` 的 `history` 或 PR 描述中登记 URL + sha256。
- `metrics.json` 与日志必须一致可复算；不一致即视为证据链断裂。

## 常用命令

```bash
scirearch new <slug> -H "假设" -m "指标" -c "判据" --seed N
bash experiments/<id>/run.sh
scirearch status <id> running
scirearch status <id> completed --metrics experiments/<id>/metrics.json --reason "判据满足"
scirearch verify
scirearch report
```

协议详见 [../docs/experiment-protocol.md](../docs/experiment-protocol.md)。
