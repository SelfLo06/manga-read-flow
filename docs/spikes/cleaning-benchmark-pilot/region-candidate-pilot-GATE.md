# Region Candidate Pilot Gate — 等待人工抽检

- [x] 已停止旧的 48 区域候选运行：`failed / incomplete_text_instance`。
- [x] 本轮仅从 Exploration 选择 5 页，并生成 10 个 `ready_for_review` 容器/完整文字实例候选。
- [x] 另有 1 个 `candidate_generation_uncertain`；该项只保留在 CSV，不进入人工复核工作簿。
- [x] 未修改 `manual-review-resolution.csv`、`page-selection.csv` 或 dataset audit `page-pairing.jsonl`。
- [x] 未运行 Detector、OCR、LaMa、外部 API 或生产 Workflow。
- [ ] 人工抽检：至少 90% 候选覆盖完整文字实例。
- [ ] 人工抽检：无明显跨气泡/跨文本框合并。
- [ ] 人工抽检：无字符被 crop 边界截断，且所有候选 context 足够。
- [ ] 自动 + 人工抽检：重复候选率低于 5%。

在以上门禁全部通过前，禁止重新生成完整 `region-review.csv`，并始终禁止生成 `benchmark-manifest.jsonl`。
