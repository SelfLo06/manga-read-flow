# Typesetting Input Contract & Validator Grounding — GATE

## 当前 verdict

`PENDING_HUMAN_REGION_AND_MAPPING_REVIEW`

## 自动门禁

| Gate | 结果 |
|---|---|
| 冻结输入 hash 一致 | PASS |
| 真实 MangaOCR 执行 | PASS |
| 真实 Page-level Translation API 执行 | PASS |
| fragment 100% 可追踪且无重复 | PASS（31/31） |
| 一个 container 可保留多个 segment | PASS |
| excluded block 有明确原因 | PASS |
| region 为独立 artifact candidate | PASS |
| validator safe 正例通过 | PASS |
| validator 显式负例全部拒绝 | PASS |
| stage 与 total timing 完整 | PASS |

## 人工门禁

以下项目尚未裁决：

- `case-71` 五个 region 是否都属于对应气泡；
- `case-72` 三个 E1 region 是否都属于对应气泡；
- `case-71/container-002` 两个 segment 是否正确；
- OCR/译文是否存在跨块映射；
- 是否允许进入字号/换行/留白优化。

## Gate 解释

- 人工结果为 `GO`：只允许进入当前两页上的布局规则优化与真实 glyph validator 压力测试。
- 人工结果为 `GO_WITH_CHANGES`：先修明确的 region/segment/mapping 问题，再重复同一 Harness。
- 人工结果为 `NO_GO`：停止布局优化，回到输入合同或 region perception；不得用字号、换行参数掩盖上游错误。

任何结果都不自动批准正式 Workflow 集成、E2/E3 清字、全页规模推广或 AUTO_ACCEPT。
