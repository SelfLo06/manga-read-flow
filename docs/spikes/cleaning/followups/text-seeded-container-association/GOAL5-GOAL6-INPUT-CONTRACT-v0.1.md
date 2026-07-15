# Goal 5 → Goal 6 Input Contract v0.1

状态：`FROZEN_BY_GOAL5`

## 1. 目的

本 contract 只定义 Goal 6 最小清字试验可以读取什么，以及何时必须跳过。它不预先选择 Pixel Text Mask 或 fill 算法，也不授权产品集成。

## 2. 冻结候选

Goal 6 的主试验候选只取 Goal 5 独立 evaluation 中以下三例：

| Asset | Route | Topology | Spatial input | 用途 |
| --- | --- | --- | --- | --- |
| case-51 | `COARSE_CONTAINER_SEARCH` | same | 1 coarse container | 同容器多组文字 |
| case-52 | `COARSE_CONTAINER_SEARCH` | different | 3 coarse containers | 多容器隔离与防泄漏 |
| case-53 | `BOUNDED_SUPPORT` | not applicable | 1 bounded support | 无气泡文字局部处理 |

`case-54` 只作为 skip control：`REGIONLESS_ABSTENTION`、0 region、`goal6_trial_eligible=false`，不得生成 Pixel Text Mask 或清字结果。

Calibration case 不作为 Goal 6 主效果结论；若仅用于开发 smoke check，必须与正式试验结果分开报告。

## 3. 必需输入字段

每个候选必须从冻结 Goal 5 artifact 读取：

```text
asset_id
source/crop SHA-256
S1 fragment geometry + upstream group + score
route
container_regions_or_null XOR support_regions_or_null
topology + topology_evidence
recommended_decision = REVIEW_REQUIRED
goal6_trial_eligible = true
Goal 5 result SHA-256
calibration lock SHA-256
routed module SHA-256
```

OCR 字符串仍不是空间安全证据。Goal 6 不得把人工标签、asset ID 或 reviewer verdict 输入算法。

## 4. 路由语义

- coarse container 是 Pixel Text Mask 的搜索上限/上下文，不是可直接编辑的 mask；
- bounded support 是无气泡文字的有限局部计算域，不得补造容器；
- different topology 的每个 container 必须独立生成 mask 和 safe edit region，不得跨容器联合 fill；
- same topology 可以共享 container context，但仍需为文字像素建立保守 mask；
- uncertain 或 regionless 必须跳过。

## 5. Goal 6 进入门禁

仅当以下条件全部成立才可进入单例人工试验：

1. source、S1、Goal 5 result 与 lock hash 全部匹配；
2. `goal6_trial_eligible=true`；
3. route 非 regionless，且恰有一种 spatial region 非空；
4. topology 非 uncertain；
5. fragment 可追踪且没有越界、重复或 silent drop；
6. Goal 6 新生成的 Pixel Text Mask 完全位于对应 coarse container/support 内；
7. safe edit region 不跨 different-container 边界；
8. 证据不足时保持原图并 `SKIP`。

## 6. Goal 6 输出要求

每个主候选至少保存并在最终报告中展示：

```text
原 crop
S1 seed + Goal 5 container/support overlay
Goal 6 Pixel Text Mask / safe edit region overlay
清字后结果
SKIP/REVIEW reason 与最小指标表
```

可视化图只需覆盖三类主任务和一个 skip control，不要求大规模图库；表格仍需记录 mask 越界、跨容器泄漏、保留文字、非文字损伤与 abstention。

## 7. 禁止与停止条件

- 不得直接把 coarse region 全部清除；
- 不得让 bounded support 变成伪气泡；
- 不得清理 case-54 或任何 regionless/uncertain case；
- 不得接入 CleanerProvider、Workflow、Repository 或 ArtifactService；
- 不得使用 `AUTO_ACCEPT`、覆盖原图或生成 benchmark manifest；
- 不得因效果图不好回调 Goal 5 router、阈值、ROI 或 S1。

若 Goal 6 无法在 coarse region 内生成保守 Pixel Text Mask，或出现跨容器编辑、明显非文字损伤、原文字残留却被误报成功，则该 case 必须失败/弃权；不能通过扩大 edit region 强行通过。

## 8. 开放决策

Goal 6 开始前仍需单独冻结：Pixel Text Mask 候选算法、safe edit region 规则、允许的最小 fill 方法、人工审查表、图像输出格式与 Goal 6 verdict。Goal 5 不替这些问题作答。
