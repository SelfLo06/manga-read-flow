# Detection + OCR Real Tool Spike — REPORT

状态：`NOT_RUN`

最终结论：`PENDING`

## 1. Executive Summary

- run_id：
- 运行时间：
- 样本：8 assets / 27 scored regions
- 最终结论：
- 核心理由：

## 2. Environment

| Item | Value |
|---|---|
| OS | |
| Python / Conda | |
| GPU / Driver / CUDA | |
| PyTorch | |
| Paddle / PaddleOCR | |
| manga-ocr | |
| Pillow / OpenCV | |

`pip check` 摘要：

## 3. Input Integrity

- GT validator：
- ground-truth hash before / after：
- image hashes unchanged：
- 实际计分 regions：
- 排除的 auxiliary regions：

## 4. Experiment A — Pure OCR

| Split | Regions | Exact rate | Median CER | Mean CER | CER <= 0.25 |
|---|---:|---:|---:|---:|---:|
| Synthetic | | | | | |
| Real core | | | | | |

主要失败案例：

| Asset / Region | Expected | Actual | CER | Failure tags |
|---|---|---|---:|---|

## 5. Detection-only

| Split | GT | Hit | Miss | Recall | Fragmented | Clear FP |
|---|---:|---:|---:|---:|---:|---:|
| Synthetic | 11 | | | | | |
| Real core | 16 | | | | | |

## 6. Experiment B — Detection + OCR

### Oracle container group

| Split | Regions | Misses | Exact rate | Median CER | CER <= 0.30 |
|---|---:|---:|---:|---:|---:|
| Synthetic | | | | | |
| Real core | | | | | |

### Native fragments

| Split | Regions | Fragmented | Exact rate | Median CER | Order failures |
|---|---:|---:|---:|---:|---:|
| Synthetic | | | | | |
| Real core | | | | | |

## 7. Failure Attribution

| Failure source | Count | MVP impact |
|---|---:|---|
| Detection miss | | |
| Fragmentation / grouping | | |
| OCR on valid crop | | |
| Reading order | | |
| Runtime / environment | | |

## 8. Scenario Analysis

| Scenario | Result | Failure mode | MVP implication |
|---|---|---|---|
| Horizontal | | | |
| Vertical | | | |
| Small text | | | |
| Color text | | | |
| Complex background | | | |
| Low contrast | | | |
| Skewed text | | | |

## 9. Performance

| Metric | Cold | Warm p50 | Warm max |
|---|---:|---:|---:|
| Paddle initialization | | | |
| manga-ocr initialization | | | |
| Detection per page | | | |
| OCR per crop | | | |
| End-to-end per page | | | |

稳定性与资源情况：

## 10. Architecture / MVP Impact

回答：

- PaddleOCR 输出是否接近 semantic container；
- 是否需要独立 line-to-container grouping；
- manga-ocr 是否适合作为主 OCR；
- 是否需要备用 OCR；
- 哪些场景需要 warning、manual correction 或 skip；
- 是否建议拆分 torch / paddle 环境。

## 11. Exit Decision

```text
GO | CONDITIONAL_GO | FURTHER_SPIKE | NO_GO
```

证据：

- Detection：
- Pure OCR：
- Detection + OCR：
- Performance：
- Environment：
- MVP impact：

## 12. Next Step

只选择一个：

- 进入最小 DetectorProvider / OCRProvider 设计；
- 追加针对性 Spike；
- 替换某个候选工具；
- 先做环境拆分 Spike；
- 停止当前工具组合。
