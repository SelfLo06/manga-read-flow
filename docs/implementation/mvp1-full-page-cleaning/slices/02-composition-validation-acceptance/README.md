# Slice 2——组合、验证与原子验收

**状态：`ACCEPTED`。** 自动裁决见 [GATE.md](GATE.md)，交付与验证证据见 [REPORT.md](REPORT.md)。

本 Slice 已获授权。迁移分期遵循[迁移分期修订 v0.1.1](../../../../design/full-page-cleaning-ledger/final/migration-staging-amendment-v0.1.1.md)：保留 Slice 1 foundation migration 的 id、DDL 与 checksum，以独立 `project_full_page_cleaning_acceptance_v3` completion record 补齐完整逻辑 v3；不得升级 v4。

## 范围

新增规范化 combined-candidate membership、从 original artifact 开始的确定性 composition、针对 missing/duplicate/overlap/wrong-instance write 的 page-level validation、issue lifecycle relation、stale propagation，以及唯一可以更新 `Page.active_cleaned_artifact_id` 的原子路径。

completion migration 必须创建 combined candidate/member、page validation、专用 issue relations 与 acceptance selection 所需表、约束和索引。Full v3 readiness 同时要求 foundation 与 completion marker/checksum 正确；foundation-only Project 应迁移后保留既有 ledger 数据。

## 退出 Gate

被接受的页面必须同时具备 frozen inventory、唯一 current disposition、fresh validated member、有效 official artifact、没有 blocking issue，以及在 expected-state guard 下通过的 page validator。Crash recovery 必须保留 unselected candidate 的可审计性，且不得按时间戳选择。

Gate 还必须证明 fresh/foundation-only migration、checksum、失败回滚、幂等与 downgrade protection；确定性 composition 不覆盖 original；`CLEANED_PASS` 只能在完整 acceptance transaction 内创建；stale transaction 以 CAS guard 原子清理 active pointer。真实 case-71/72、Slice 3 与 Combined Code Health Review 均不在本 Slice。

上述退出条件已满足。随后在 Linux `manga-read-flow` Conda 环境重跑完整 integration，得到 `117 passed`；此前的 `cv2` 收集问题和 Windows/UNC SQLite 文件句柄删除限制均已解除。完整 unit suite 仍有两个非 Slice 2 失败，详见报告，不影响本 Slice Gate。下一允许任务是 Slice 3；本 Slice 未开始该任务。
