# 整页清字台账迁移分期修订 v0.1.1

状态：`ACCEPTED`

本修订只冻结 `project_full_page_cleaning_ledger_v3` 的物理迁移分期，不重新设计整页清字领域模型，也不推翻 Slice 1。若本文与 v0.1 基线中“单条 v3 migration”措辞冲突，以本文的分期合同为准；其余设计继续以 v0.1 基线为准。

## 1. 裁决

逻辑 schema 版本保持：

```text
project_full_page_cleaning_ledger_v3
```

完整逻辑 v3 由以下两条按顺序执行、各自拥有不可变 checksum 的物理 migration record 共同组成：

1. `project_full_page_cleaning_ledger_v3`：Slice 1 foundation facts；
2. `project_full_page_cleaning_acceptance_v3`：Slice 2 completion facts。

现有 foundation migration 的 id、DDL、checksum 和已写入 ledger 的 row 均不可改写。completion migration 不要求 v4，也不得改变 `project_metadata.project_schema_version`。

## 2. 能力与物理记录

Foundation record 包含 `PageCleaningRun`、inventory、disposition、instance result、result-to-inventory attribution、correction chain/reservation 和 Slice 1 recovery facts。

Completion record 包含 combined candidate、规范化 member、page validation 及其 evidence/summary 关系、QualityIssue 与 run/inventory/result/candidate/validation/reservation/decision 的关系、accepted candidate/member/validation selection，以及 Slice 2 acceptance transaction 所需 constraint/index。

两条记录都是完整 v3 的必需部分。completion facts 不是可选扩展；仅检查 `project_metadata.project_schema_version == project_full_page_cleaning_ledger_v3` 不足以认定 full v3 ready。

## 3. Readiness 与迁移路径

Full v3 readiness 必须同时满足：

- logical schema version 与 v3 兼容；
- required migration set 中两条 marker 都存在；
- 两条 checksum 均匹配当前不可变定义；
- 两阶段所需表、约束和索引存在；
- 不存在 partial migration。

已有 Slice 1 数据库若 logical version=v3、foundation marker 正确而 completion marker 缺失，应分类为：

```text
V3_FOUNDATION_ONLY
PROJECT_MIGRATION_REQUIRED
```

这不是 checksum corruption，也不是 v4。readiness-only 调用返回 `PROJECT_MIGRATION_REQUIRED`；负责正常打开的 ProjectStore 应在身份与 foundation checksum 校验后，自动应用 completion migration，再复核完整 required migration set，避免无限 migration-required 循环。

Fresh Project 固定按 foundation → completion 的顺序执行，最后确认 logical version=v3 并校验两条 marker。已完整迁移的 Project 重复打开为 no-op。

## 4. 事务与失败语义

completion migration 在一份独立 SQLite migration transaction 内创建全部 Slice 2 DDL，并在同一 transaction 写入自身 marker/checksum。任一 DDL、constraint/index 或 ledger write 失败时整体回滚，不得留下成功 marker；foundation facts 和现有项目数据保持不变。

foundation 或 completion checksum mismatch 均阻止后续 mutation。未知 future logical version 必须触发 downgrade protection；未知 migration row 不得删除或覆盖。

禁止：

- 修改 foundation checksum 或把 Slice 2 DDL追加到 foundation migration；
- 删除、重建或覆盖已有 foundation marker；
- 只检测 table exists 而绕过 migration ledger；
- 只建表而不登记 completion marker；
- 以文件版本、Page.status、目录或当前代码推断 migration 完成；
- 通过 v4 表示 completion 进度。

## 5. 理由与拒绝方案

选择第二条 v3 completion record，是因为 Slice 1 foundation 已经以不可变 checksum 提交并可能存在于真实 Project 中；新 record 能保留已应用迁移的可验证性，同时让逻辑领域版本继续保持设计既定的 v3。

拒绝以下方案：

- 改写现有 v3 checksum：破坏已应用 migration 的不可变性；
- 升级到 v4：把物理实施分期误表示为领域 schema 变更；
- 静默补表：数据库状态无法由 migration ledger 解释；
- 将 completion tables 视为可选：会让同为 v3 的数据库具备不同且不可判定的 acceptance 能力。

## 6. 验证场景

实现必须覆盖：fresh 两记录顺序与 checksum；foundation-only 保留已有 ledger 数据并升级；full v3 重复打开幂等；两条 checksum mismatch；completion 中途失败不写 marker；失败后 foundation 数据完整；future schema downgrade protection；full readiness 不因 logical version 单项匹配而误报。

## 7. 风险与开放问题

主要风险是旧 readiness 逻辑只比较 logical version、迁移失败后误入重复循环，以及 acceptance tables 与 marker 未原子提交。以上均必须由 required migration set、单迁移事务和失败/重放测试收口。

本修订没有新的 blocking open question。artifact 类型词汇和 UI 查询 DTO 仍按 v0.1 的非阻塞开放问题处理，不影响 migration staging。
