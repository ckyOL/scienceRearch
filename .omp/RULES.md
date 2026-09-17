# 硬规则（每请求常驻，不可绕过）

1. `data/raw/` 只读。禁止对其写入、删除、移动、解包或重定向（hook 会拦截；绕过即安全事件）。
2. 不得手工创建或编辑 `metrics.json`；不得直接改 `experiment.json` 的 `status`（用 `scirearch status`）。数字只能由 `run.sh` 产出。
3. 判据先于结果：`status=preregistered` 的实验内不得出现 `metrics.json`。事后追加判据视为伪造。
4. 写进 `paper/`、`docs/` 或任何汇报的每个数字，必须能解析到 `experiments/<id>/` 的产物（`metrics.json`、`logs/` 或 manifest）。
5. 生成与复核必须分离：同一 agent、同一模型、同一上下文不得既产出结论又裁定结论。
6. `refuted` / `inconclusive` 结果必须与 `completed` 一样完整留痕，禁止选择性丢弃。
