# Detection + OCR Real Tool Spike — HARNESS

## 1. 输入完整性

运行前后必须校验：

- ground-truth validator 通过；
- 8 个资产存在；
- 27 个计分 region 具有有效 bbox 和 expected text；
- ground truth 与输入图片 SHA-256 未变化。

## 2. OCR 规范化

只允许：

- 删除 ASCII 普通空格；
- 删除换行。

必须保留：

- 日文标点；
- `ー`、`〜`、省略号；
- 英文字母大小写；
- 数字。

指标：

```text
exact_match
CER = LevenshteinDistance(expected, actual) / len(expected)
```

## 3. Detection 匹配

GT 是 semantic container，预测通常是文字行框，因此普通 bbox IoU 不能作为唯一指标。

预测框分配规则：

1. 预测框中心位于 GT bbox 内；
2. 否则 `intersection / prediction_area >= 0.5`；
3. 匹配多个 GT 时选覆盖率最高者；
4. 不使用 expected text 或 OCR text。

核心指标：

- GT hit / miss；
- region recall；
- 每个 GT 内 prediction 数量；
- fragmented GT 数量；
- unmatched prediction 数量；
- clear false positive / auxiliary text / uncertain。

第一轮不报告普通 precision、F1 或 mAP。

## 4. Experiment B 两条路径

### Oracle container group

将几何匹配到同一 GT 的 prediction 求 union bbox 后 OCR。

该结果只用于错误归因，不代表正式系统已解决 container grouping。

### Native fragments

每个 prediction 单独 OCR，再按固定几何顺序拼接：

- 横排：上到下、左到右；
- 竖排：右到左、上到下。

## 5. 必须覆盖的场景

- 普通对话；
- 旁白框；
- 小气泡；
- 竖排；
- 彩色文字；
- 复杂背景；
- 弱对比；
- 倾斜文字。

## 6. 性能与环境证据

记录：

- PaddleOCR 初始化时间；
- manga-ocr 初始化时间；
- 每页 Detection 时间；
- 每 region OCR 时间；
- 每页端到端时间；
- cold / warm run；
- GPU、CUDA、Python 和关键包版本；
- `pip check` 摘要；
- OOM、异常和重复运行稳定性。

## 7. 决策参考线

### GO

建议同时满足：

- synthetic Detection hit >= 10/11；
- real core Detection hit >= 14/16；
- real pure OCR median CER <= 0.15；
- real pure OCR 中至少 13/16 的 CER <= 0.25；
- real end-to-end 中至少 12/16 的 CER <= 0.30；
- 无系统性场景完全失效；
- warm page p50 <= 10s；
- 至少两次完整运行稳定完成。

### CONDITIONAL_GO

核心可用，但存在明确场景限制、grouping 缺口、性能问题或环境拆分需求。

### FURTHER_SPIKE

证据不足、结果不稳定，或环境问题与工具能力无法区分。

### NO_GO

Detection、纯 OCR、端到端表现或运行稳定性明显不足以支撑 MVP。

## 8. Harness 通过条件

- A/B 实验均完成；
- 27 个 region 均有结果或明确错误记录；
- Detection 与 OCR 错误可分离；
- 指标可从结果文件重新计算；
- 输入未被修改；
- 每个失败案例有分类；
- 最终报告只给出一个退出结论。
