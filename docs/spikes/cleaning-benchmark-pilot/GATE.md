# Cleaning Benchmark Pilot Gate（等待人工复核）

- [x] 输入图片未覆盖；输入树 hash 运行前后相同。
- [x] 17 个 unresolved 条目均生成本地 review bundle（17/17）。
- [x] 页面仅来自 work-003/work-004（24 页）；未访问 Dev / Frozen Test 作为样本。
- [x] 所有自动候选进入 region-review.csv（48 项），无 silent skip。
- [x] 当前区域候选运行已停止：`region-review-candidates-v0.1` 标记为 `failed`，原因 `incomplete_text_instance`；不得要求人工逐条 reject。
- [x] difference mask 明确标为 candidate，不是 ground truth。
- [x] 未自动填写人工结论或 eligibility 通过状态。
- [x] review bundle、crop、mask 仅输出至 Git 忽略目录。
- [ ] 区域候选粒度门禁未通过：不得继续现有 region-review，也不得生成 benchmark-manifest.jsonl。

输入 SHA-256：`63d3fc6e68b62d93a786518fbf0e5a7005449f779d4619de5d6331d9c119239e` / `63d3fc6e68b62d93a786518fbf0e5a7005449f779d4619de5d6331d9c119239e`
