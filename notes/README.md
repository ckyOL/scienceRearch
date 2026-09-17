# notes/：探索笔记与死路归档

`notes/` 不构成证据（见 [docs/architecture.md](../docs/architecture.md)）；它的职责是
**保留失败路径**，让"这条路已经走过"变成可检索的资产，而不是丢失的记忆（调研 §7 借鉴 #8）。

## 约定

- 每个被放弃的方向建一个文件：`notes/dead-ends/<slug>.md`。
- 文件必须包含四段：**尝试**（做了什么）、**结论**（为什么此路不通）、**证据**（命令 / 日志 /
  实验 id，须可寻址）、**重试条件**（什么新证据出现时才值得重来）。
- 被判为 `refuted` 的实验同时进入 `scirearch report` 的负知识索引（按 `criteria_sha256` 去重）；
  再次提出同一判据时，`scirearch new` 会命中历史结论并写进 `prior_refutations`。
- 死路结论要引用实验 id（`exp-NNNN`）或具体命令输出，禁止只写"试过，不行"。
