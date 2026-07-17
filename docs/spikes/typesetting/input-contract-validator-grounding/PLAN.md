# Typesetting Input Contract & Validator Grounding — PLAN

1. 锁定两页 S1、Cleaning diagnostics、清字页、Prompt 和字体哈希。
2. 从冻结 group 构建保真 segment；特别检查 case-71 大容器多段。
3. 运行 MangaOCR 与两次 Page-level Translation，记录实际译文和耗时。
4. 生成完整 provenance ledger，给每个排除对象写 reason。
5. 生成独立 typesetting-region mask candidate、overlay 和 hash。
6. 执行 safe/overflow/touch/wrong-container 验证并记录耗时。
7. 由用户只审查 region、段落映射和真实译文对应关系。
8. 根据门禁决定是否恢复排版算法优化。

## 预期产物

```text
data/local/typesetting-input-contract-v0.1/<run-id>/
├── input-lock.json
├── ocr-results.json
├── translation-results.json
├── provenance-ledger.json
├── regions/
├── overlays/
├── validator-results.json
├── timings.json
├── summary.json
└── FORM.md
```
