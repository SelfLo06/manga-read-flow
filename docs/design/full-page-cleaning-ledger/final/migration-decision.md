# 迁移裁决——整页清字台账 v0.1（含 v0.1.1 分期修订）

```text
MIGRATION_REQUIRED = YES
TARGET_PROJECT_SCHEMA_VERSION = project_full_page_cleaning_ledger_v3
FOUNDATION_MIGRATION = project_full_page_cleaning_ledger_v3
COMPLETION_MIGRATION = project_full_page_cleaning_acceptance_v3
FULL_V3_REQUIRES_BOTH_RECORDS = YES
BACKFILL_POLICY = NO_SEMANTIC_BACKFILL
OLD_PROJECT_OPEN_POLICY = APPLY_COMPATIBLE_PROJECT_MIGRATION_OR_BLOCK_WORKFLOW
ROLLBACK_POLICY = NO_AUTOMATIC_DOWNGRADE
IMPLEMENTATION_BLOCKERS = NONE_FOR_SCHEMA_DESIGN
```

选择新增规范化 v3 tables（方案 B）。方案 A 会把 immutable inventory、多个 instance result、disposition history、member 与 page validation 混入现有单页 `cleaning_result_records`；方案 C 令 manifest 成为第二事实源且要求 acceptance 解析可能缺失的大 JSON。二者拒绝。

## 升级与兼容性

按 project.db 独立 migration ledger 顺序执行两条不可变记录。Slice 1 已提交的 foundation record 保持 id、DDL 和 checksum 不变；Slice 2 completion record 在独立 transaction 中创建剩余表、FK/unique/index，并与其 marker/checksum 原子提交。`project_metadata.project_schema_version` 始终保持 `project_full_page_cleaning_ledger_v3`，但 full readiness 还必须校验两条 required marker 及 checksum。完整规则见 [迁移分期修订 v0.1.1](migration-staging-amendment-v0.1.1.md)。

foundation-only Project 返回 `PROJECT_MIGRATION_REQUIRED`，或由正常 ProjectStore open 路径自动应用 completion migration 后再返回 ready。completion 失败不得留下成功 marker，也不得损坏 foundation facts。schema 未 ready、任一 checksum 不符或 migration 失败时，Project 为 `project_migration_failed`/repair-only，workflow repositories 不暴露；不得从 Page.status、artifact 目录或 table existence 猜测完成。

旧 Project 可迁移其 schema，但**不得**把 Spike E/F 记录、FORM、local artifact 或旧 `cleaning_result_records` 语义回填为 full-page run/pass：它们没有冻结 inventory、member、完整 disposition 或全页 validator。实现可保留 legacy evidence references，标为 `legacy_non_reconstructable`，不可用于新 acceptance/reuse。

不支持自动 downgrade；恢复依赖完整备份/代码回退，不能删除审计事实。升级测试必须覆盖 fresh 两记录、foundation-only→full v3、重复打开幂等、两条 checksum mismatch、completion transaction 失败、future schema 保护与旧 evidence 可读但不被误选。
