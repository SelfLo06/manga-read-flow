# Slice 1——整页清字台账基础

**Gate 状态：`ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`。** 自动退出证据记录在 [GATE.md](GATE.md)，交付摘要记录在 [REPORT.md](REPORT.md)。完整集成测试仍为 `ENVIRONMENT_BLOCKED`，不是 PASS。Slice 2 是下一允许任务，但不属于 Slice 1。

## 目标

持久化并恢复页面级 Cleaning run、不可变 segment inventory、不可变逐实例结果事实、当前最终 segment disposition，以及一份持久 correction reservation。系统必须能够仅通过 project.db 查询这些事实，不得按时间戳选择 artifact，也不得从 Page status 推断完成状态。

## 允许修改

- project migration/bootstrap 与 ProjectRepositories 装配；
- 专用整页清字台账 Repository 和窄 UoW 门面；
- 聚焦的台账集成测试；
- 本 Slice 的范围、报告和 Gate 文档。

## 明确排除

不实现 combined candidate/member 表、composition、page validator、issue lifecycle 集成、active pointer 写入、真实 case 执行、Cleaner、Provider、UI/API、Typesetting、Export 或 Batch 行为。

Slice 1 禁止 `CLEANED_PASS`。g002/s01 与 g002/s02 只能表示为 `InstanceCleaningResult.state = validated | ready_for_composition`；在 Slice 2 持久化 accepted combined-member、page-validation 和 acceptance 事实之前，它们没有最终 disposition。Slice 1 的 stale 操作命名为 `mark_unaccepted_cleaning_run_stale`，要求 active cleaned pointer 为空；否则返回 `ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2`，且不得改变任何 pointer。带保护条件的 stale-pointer repair 属于 Slice 2。

## 退出条件

- v3 migration 为 additive、幂等，保留既有 Project identity/data，并在 migration 失败或 checksum 不匹配时阻止 Repository 访问；
- run replay、inventory replay、result replay、disposition supersession 和 correction replay 可持久恢复并查询；
- 明确拒绝第二次自动 correction；
- stale 标记保留历史且不修改 active pointer；
- case-71 与 case-72 可表示为完整唯一 inventory 和明确 blocker；
- 聚焦 migration/Repository/UoW 测试通过。
