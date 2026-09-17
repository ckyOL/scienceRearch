## 变更内容

<!-- 一段话：改了什么、为什么 -->

## 类型

- [ ] 工具链/合同（`src/`、`tests/`）
- [ ] omp 设施（`.omp/`：agents / skills / hooks / 配置）
- [ ] 实验（`experiments/`）
- [ ] 文档

## 证据闸门

- [ ] `make check` 全绿（格式 + lint + 测试 + `scirearch verify`）
- [ ] 涉及实验结果：**判据先于结果**，`seed` 已登记，`logs/` 含非空原始日志
- [ ] 实验类 PR：预注册提交早于结果提交，且本 PR **不以 squash 方式合并**（时序证据会失效）
- [ ] 没有任何手工编辑过的 `metrics.json`（数字一律由 `run.sh` 产出）
- [ ] 文档或稿件中的每个数字都能解析到 `experiments/<id>/` 中的产物；`report` 标 `[人工]` 的判据已由复核者裁定
- [ ] 新增/修改的校验规则带有会随实现失败的行为测试

## 关联

Closes #<!-- issue 编号 -->
