# 150 Cleaning 实验索引

只列仍影响当前裁决或仍有可复用代码的实验；逐次 run 细节保存在 `data/local/runs`/`reviews`，不作为项目事实源。

| ID | 范围 | 当前裁决 | 保留入口/证据 |
| --- | --- | --- | --- |
| EXP-150-001 | Cleaning benchmark 与人工复核数据 | 数据和 evaluator 可复用；不等于产品 gate | `tools/experiments/150-cleaning/`、`data/local/datasets/150-cleaning/` |
| EXP-150-002 | Visual Contract A–D 与 single-page slices | 受限机制证据保留；禁止泛化为整页能力 | `tools/experiments/150-cleaning/visual_contract/`、`data/local/reviews/150-cleaning/` |
| EXP-150-003 | Text-seeded association Goal 4–7 / E1–E2 | 局部 routing/harness 可复用；自动 association/mask/cleaning 未授权 | `tools/experiments/120-grouping/`、`data/local/reviews/120-grouping/` |
| EXP-150-004 | Physical Bubble Boundary Stage A | 诊断完成；当前 arms NO_GO；能力需重设计 | `tools/experiments/150-cleaning/physical_boundary/`、`data/local/runs/150-cleaning/physical-boundary-v0.1/` |
| EXP-150-005 | page_edge_bubble_001 first-divergence | 原 auto baseline 因 Detection 自动适配不可用而 fail-closed，属于 earliest execution gap，未观察到算法首个分歧；已弃用的 YOLOE 运行仅保留为历史记录，不作为当前能力结论。全页 Paddle Detection 产生 13 个候选，bbox 几何覆盖 required `12052/12052`；复用 Grouping spike 后生成 7 个 text group，目标 `paddle-0009/0010/0011` 同属一组且无外部候选，未观察到 text-group 分歧。PhysicalBoundaryEvidence v0.2 双样本后置评价为 `FAIL`：page-edge 未表达 `page_truncated:left`，black2 将两个 touching-but-distinct oracle text group 错误 merge 到同一 BubbleInstance candidate；不授权后续 text support、Cleaner 或产品状态变更。accepted oracle 下 Cleaner isolation 仍仅为 `PASS_WITHIN_CASE` | `tools/experiments/150-cleaning/page_edge_bubble_first_divergence/`、`data/local/runs/150-cleaning/physical-boundary-v0.2/` |

下一实验应是独立 `PhysicalBoundaryEvidence v0.2`：预先冻结闭合气泡、近页边、page truncation、panel line、彩色边框/文字和抗锯齿 controls；报告 boundary confusion matrix、support precision/recall 与逐像素 provenance。未通过前不运行 Stage B Cleaner。
