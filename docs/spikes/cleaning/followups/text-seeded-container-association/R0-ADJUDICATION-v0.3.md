# Text-Seeded Container Association — R0 Adjudication v0.3

日期：2026-07-15
状态：`PASS_FOR_CONTAINER_ASSOCIATION_SPIKE`

## 1. 证据收口

本轮采用分层证据，不把 Annotator B 缺少 overlay 解释为语义或容器拓扑置信度下降：

1. Annotator A/B 的独立选择题用于冻结 TEXT/NOT_TEXT、内容角色、文字组数量、方向、container type、container count、same/different-container topology 及 boundary/risk category。
2. Annotator A 的 overlay 冻结为 coarse `TARGET_REGION` reference，只表达目标文字组应归属的容器或有限 support、容器数量以及接触容器的人工分隔。
3. Annotator B 未提供 overlay，因此不能计算双人像素边界一致性，也不能冻结精确 boundary uncertainty band；该限制不回写为语义或拓扑不确定。

## 2. 冻结结果

| R0 ID | 语义 | 容器拓扑 | 冻结的 boundary/risk category |
| --- | --- | --- | --- |
| `R0-not-text` | NOT_TEXT；0 group | 0 container | 疑似非文字结构；复杂纹理 false-seed 风险 |
| `R0-free-text` | 对话；1 个竖排 group；free text | 0 container；有限 support | 无容器边界；复杂背景风险 |
| `R0-broken-or-occluded-boundary` | 对话；目标内 2 个竖排 group；implicit container | 1 container；same-container | 局部缺失/遮挡；boundary 不稳定 |
| `R0-textured-decorative-risk` | 标题/装饰文字；2 个横排 group；free text | 0 container；有限 support | 复杂背景高风险；预期 abstain |
| `R0-same-container-multicol` | 对话；2 个竖排 group；explicit container | 1 container；same-container | 完整连续外边界；多叶 false-split 风险 |
| `R0-contact-different-containers` | 对话；2 个竖排 group；implicit/contact-risk | 2 containers；different-container | 相邻/接触；人工分隔；局部边界不稳定 |

选择题分歧均在 coordinator adjudication 中逐项保留并说明。Case 03 按 A coarse target scope 裁定中央目标；Case 05 依据连续外轮廓且无内部隔断裁为一个容器；Case 06 冻结 different-container topology，但不冻结精确边界断点或路径。

## 3. 允许与禁止的 R0 指标

允许：

- 分类正确性；
- 容器数量正确性；
- same/different-container 正确性；
- 是否跨容器泄漏；
- 是否正确 abstain；
- 相对 A coarse reference 的定性或宽容差评估。

禁止宣称：

- pixel-accurate segmentation accuracy；
- 精确 boundary F1；
- 双人边界一致性；
- 已冻结的 uncertainty-band 数值。

## 4. 正式结论

```text
R0 verdict                         = PASS_FOR_CONTAINER_ASSOCIATION_SPIKE
Semantic labels                    = FROZEN
Container topology                 = FROZEN
Coarse target-region references    = FROZEN_FROM_ANNOTATOR_A
Pixel-accurate boundary GT         = NOT_FROZEN
Inter-annotator boundary agreement = UNAVAILABLE
```

该 verdict 只允许 R0 进入 container association Spike，不表示 association 算法、pixel text mask、safe edit region 或 Cleaning 已通过。
