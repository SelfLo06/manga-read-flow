# Detection + OCR Real Tool Spike — PLAN

## 1. 最小资产

```text
docs/spikes/detection-ocr/
├── GOAL.md
├── HARNESS.md
├── PLAN.md
└── REPORT.md

tools/spikes/detection_ocr/
└── spike.py

tests/unit/
└── test_detection_ocr_spike.py
```

优先保持单一 CLI。只有匹配或指标逻辑形成独立职责时再拆文件。

## 2. 执行顺序

```text
Preflight
-> Experiment A: GT crop OCR
-> Detection-only
-> Experiment B1: oracle group
-> Experiment B2: native fragments
-> cold/warm performance repeat
-> summarize
-> verify input hashes
-> fill REPORT
```

## 3. 实验矩阵

| ID | 输入 | Detection | Crop | OCR | 目的 |
|---|---|---|---|---|---|
| A-SYN | 11 synthetic GT regions | 无 | GT bbox | manga-ocr | synthetic 纯 OCR |
| A-REAL | 16 real core GT regions | 无 | GT bbox | manga-ocr | real 纯 OCR |
| D-SYN | 4 synthetic pages | PaddleOCR | 无 | 无 | Detection |
| D-REAL | 4 real pages | PaddleOCR | 无 | 无 | Detection |
| B1 | 8 pages | PaddleOCR | GT 归因后的 union crop | manga-ocr | 碎片化归因 |
| B2 | 8 pages | PaddleOCR | 原生 prediction crop | manga-ocr | 行框与顺序问题 |

## 4. 单元测试

不调用真实模型，至少覆盖：

- normalization；
- exact match / CER；
- center-in-container；
- prediction coverage；
- 多 GT 冲突；
- unmatched；
- union crop 边界；
- 横排/竖排排序；
- 输出目录越界保护。

## 5. 结果目录

```text
local_samples/spike_outputs/{run_id}/
├── results.json
├── regions.csv
├── raw/
├── crops/
├── visualizations/
└── logs/
```

`results.json` 是 canonical result，CSV 为每个 GT region 一行的扁平视图。

## 6. 最小结果字段

### Run

- run_id；
- Git branch / commit / working tree；
- 环境与包版本；
- 参数；
- 输入 hash；
- 开始/结束时间。

### Asset

- asset_id、split、尺寸；
- Detection 时间；
- predictions；
- unmatched 分类。

### Region

- region_id、bbox、direction；
- expected / normalized expected；
- Detection hit、prediction_count、fragmented；
- GT OCR、oracle OCR、native OCR；
- exact、CER、耗时、错误；
- failure tags。

## 7. 失败标签

```text
detection_miss
detection_fragmented
detection_cross_container
detection_false_positive
grouping_required
reading_order_error
ocr_empty
ocr_substitution
ocr_insertion
ocr_deletion
vertical_text_failure
small_text_failure
color_text_failure
low_contrast_failure
skew_failure
complex_background_failure
runtime_error
out_of_memory
```

## 8. 验证命令

```bash
conda run -n manga-read-flow python tools/validate_detection_ocr_ground_truth.py

conda run -n manga-read-flow pytest tests/unit/test_detection_ocr_spike.py -q

conda run -n manga-read-flow python tools/spikes/detection_ocr/spike.py run-all \
  --ground-truth local_samples/detection_ocr_ground_truth.json \
  --output-root local_samples/spike_outputs

conda run -n manga-read-flow python tools/spikes/detection_ocr/spike.py verify-inputs \
  --run-dir local_samples/spike_outputs/{run_id}

conda run -n manga-read-flow python -m json.tool \
  local_samples/spike_outputs/{run_id}/results.json

conda run -n manga-read-flow pytest -q
```

## 9. 停止条件

- GT validator 失败；
- 输入 hash 变化；
- 需要修改 `src/manga_read_flow/**`；
- 需要访问 SQLite；
- 需要修改依赖；
- 输出可能覆盖输入；
- expected text 被用于几何匹配或调参；
- 模型无法稳定初始化；
- 需要实现复杂 grouping 才能继续第一轮。
