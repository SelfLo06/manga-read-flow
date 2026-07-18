# 迁移裁决——整页清字台账 v0.1

```text
MIGRATION_REQUIRED = YES
TARGET_PROJECT_SCHEMA_VERSION = project_full_page_cleaning_ledger_v3
BACKFILL_POLICY = NO_SEMANTIC_BACKFILL
OLD_PROJECT_OPEN_POLICY = APPLY_COMPATIBLE_PROJECT_MIGRATION_OR_BLOCK_WORKFLOW
ROLLBACK_POLICY = NO_AUTOMATIC_DOWNGRADE
IMPLEMENTATION_BLOCKERS = NONE_FOR_SCHEMA_DESIGN
```

选择新增规范化 v3 tables（方案 B）。方案 A 会把 immutable inventory、多个 instance result、disposition history、member 与 page validation 混入现有单页 `cleaning_result_records`；方案 C 令 manifest 成为第二事实源且要求 acceptance 解析可能缺失的大 JSON。二者拒绝。

## 升级与兼容性

按 project.db 独立 migration ledger 一次执行：创建新表、FK/unique/index、记录 checksum，并在同一 migration transaction 更新 `project_metadata.project_schema_version`。schema 未 ready、checksum 不符或 migration 失败时，Project 为 `project_migration_failed`/repair-only，workflow repositories 不暴露；不得从 Page.status 或 artifact 目录猜测完成。

旧 Project 可迁移其 schema，但**不得**把 Spike E/F 记录、FORM、local artifact 或旧 `cleaning_result_records` 语义回填为 full-page run/pass：它们没有冻结 inventory、member、完整 disposition 或全页 validator。实现可保留 legacy evidence references，标为 `legacy_non_reconstructable`，不可用于新 acceptance/reuse。

不支持自动 downgrade；恢复依赖完整备份/代码回退，不能删除审计事实。升级测试必须覆盖空库、v2→v3、重复打开幂等、checksum mismatch、migration transaction 失败与旧 evidence 可读但不被误选。
