# Slice 2——组合、验证与原子验收

**状态：`NEXT_ALLOWED_SLICE`；尚未实现。**

## 范围

新增规范化 combined-candidate membership、从 original artifact 开始的确定性 composition、针对 missing/duplicate/overlap/wrong-instance write 的 page-level validation、issue lifecycle relation、stale propagation，以及唯一可以更新 `Page.active_cleaned_artifact_id` 的原子路径。

## 退出 Gate

被接受的页面必须同时具备 frozen inventory、唯一 current disposition、fresh validated member、有效 official artifact、没有 blocking issue，以及在 expected-state guard 下通过的 page validator。Crash recovery 必须保留 unselected candidate 的可审计性，且不得按时间戳选择。

创建本范围文档不授权任何 Slice 2 实现；实施必须由独立 Slice 2 任务明确授权。
