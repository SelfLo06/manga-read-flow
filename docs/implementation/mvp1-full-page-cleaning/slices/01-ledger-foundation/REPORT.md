# Slice 1——整页清字台账基础报告

## 已交付范围

Slice 1 新增 additive `project_full_page_cleaning_ledger_v3` migration、专用 project.db 台账 Repository，以及以下窄 UoW 操作：

- 页面级 run 及其 Slice 1 lifecycle；
- 不可变 frozen inventory 和确定性 recovery query；
- 带规范化 target attribution 的不可变 instance result 事实；
- append-only disposition supersession；
- 每个有效 chain 一份持久 correction reservation；
- 不修复 active pointer 的 unaccepted-run stale 标记。

本 Slice 未实现 combined candidate、composition、page validation、issue lifecycle 更新、active cleaned pointer acceptance、真实 case 执行、Provider 或 UI/API 行为。

## 决策与理由

- Repository 与 SQLite constraint 均禁止 `CLEANED_PASS`。case-71 `g002/s01` 与 `g002/s02` 仅持久化为 validated result。
- inventory/result/disposition/correction 均为规范化 row；image 和 mask payload 只保存 artifact 引用，不进入 SQLite BLOB。
- current disposition 使用 supersession 选择，不使用时间戳或 active flag。Recovery 按 run id 定位，不读取 `Page.status`。
- correction chain 在 ordinal 1 永久消耗唯一自动预算；相同 replay 复用该 reservation，不同 key 不能创建 ordinal 2。
- `mark_unaccepted_cleaning_run_stale` 要求 active cleaned pointer 为空。非空时返回 `ACTIVE_POINTER_STALE_REPAIR_REQUIRES_SLICE_2`，且不得修改 pointer。

## 拒绝的替代方案

- 使用 `cleaning_result_records` 作为台账事实或回填旧 Slice E/F evidence：其语义不足以构成完整持久台账，因此拒绝。
- provisional `CLEANED_PASS`：违反 Slice 1 边界，因此拒绝。
- stale handling 时清除非空 active pointer：推迟到 Slice 2 的 atomic acceptance/stale repair 操作。

## 验证证据

- `E:\APPS\anaconda\python.exe -m pytest -q tests/integration/test_full_page_cleaning_ledger_foundation.py`：20 passed。
- `E:\APPS\anaconda\python.exe -m pytest -q tests/integration/test_project_store_init.py -k "not missing_project_db_blocks_project_repositories and not repository_access_after_project_db_removed_does_not_recreate_database"`：10 passed，2 deselected。
- `python -m compileall -q src tests/integration/test_full_page_cleaning_ledger_foundation.py`：PASS。
- WSL 原生隔离删除探针：PASS；该结果区分了 Windows/UNC 文件句柄行为与 ProjectStore 删除恢复逻辑。

## 风险与开放问题

- 当前 Windows 测试解释器缺少 `cv2`，因此完整 integration suite 无法收集 Slice F 测试。
- 同一解释器在两个既有 `project.db.unlink()` ProjectStore 测试中持有 SQLite 文件句柄；这些失败属于环境限制，不能记为 Slice 1 PASS。
- artifact type/hash integrity enforcement 与 page-level completeness 仍是后续 Slice 2 validation 的输入；Slice 1 只记录其标识符和 evidence fact。

## 最终自动 Gate 裁决

`SLICE_1 = ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`。

记录的聚焦证据满足 Slice 1 的 persistence、migration、recovery、attribution、correction 和 scope-boundary 退出条件。`FULL_INTEGRATION_SUITE = ENVIRONMENT_BLOCKED`，不是 PASS。下一允许任务是 Slice 2，但不属于 Slice 1 提交。
