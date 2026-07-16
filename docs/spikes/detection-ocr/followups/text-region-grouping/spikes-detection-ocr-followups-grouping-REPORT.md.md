# Text Region Grouping Spike — REPORT

状态：`DONE`

最终结论：`PASS_WITH_LIMITATIONS`

## 1. Executive Summary

- run_id：`20260710T142823Z-b08c9c`
- 输入 Detection/OCR run：`20260710T091753Z-0676c2`
- cycle：`cold`
- 样本：8 assets / 27 scored GT containers
- 核心结论：纯几何 grouping 可以恢复本轮 synthetic 与 real core 的 semantic text container；real core `16/16` 命中，synthetic `10/11` 命中，未出现 core split、core merge 或 reading order 错误。
- 限制：仍有 `9` 个 real extra groups，来自 unmatched / auxiliary predictions；这些不影响 core 评分，但正式系统需要 uncertainty、review 或 auxiliary 过滤路径。

## 2. Scope and Inputs

使用输入：

- `local_samples/spike_outputs/20260710T091753Z-0676c2/results.json`
- `local_samples/detection_ocr_ground_truth.json`

本轮只读取 `cold` cycle。未重跑 PaddleOCR，未重跑 manga-ocr，未修改 ground truth、原图、依赖或 `src/**`。

Grouping 阶段只使用：

- asset id；
- 页面尺寸；
- prediction id；
- bbox / polygon / score；
- 已有 fragment OCR 文本与错误状态。

未使用 GT bbox、GT direction、GT container assignment、expected text 或 OCR 文本语义参与 grouping。

## 3. Algorithm

第一版算法为纯几何规则：

1. 根据 bbox / polygon 长宽比推断 fragment orientation：`horizontal` / `vertical` / `uncertain`；
2. 根据方向兼容性、水平/垂直投影重叠、相邻 gap 建立候选边；
3. 使用连通分量形成 group；
4. 根据 fragment votes 推断 group orientation；
5. 对 group 生成 union bbox；
6. 横排按上到下、同一行左到右排序；
7. 竖排按右到左、同一列上到下排序；
8. 排序完成后才拼接已有 fragment OCR。

关键参数：

| Parameter | Value |
|---|---:|
| orientation_ratio | 1.25 |
| projection_overlap_ratio | 0.15 |
| gap_relative_limit | 0.35 |
| gap_min_px | 16 |

## 4. Evaluation Method

Evaluator 使用 Detection/OCR Spike 已有的 prediction-to-GT assignment 和 `b2_native_fragments` fragment 顺序作为评估基准。

评估分离为：

- grouping input；
- grouping algorithm；
- evaluation input；
- evaluation logic。

Grouping 函数不接收 GT region 对象。GT 只在算法输出后用于评分和可视化。

## 5. Synthetic Results

| Metric | Value |
|---|---:|
| gt_container_count | 11 |
| predicted_group_count | 10 |
| group_hit | 10 |
| group_miss | 1 |
| split_error | 0 |
| merge_error | 0 |
| orphan_fragment | 0 |
| extra_group | 0 |
| group_recall | 0.9091 |

唯一 miss 为 `s04_r03`，继承自上游 Detection miss；本轮 grouping 没有可用 fragment 可恢复该 container。

## 6. Real Core Results

| Metric | Value |
|---|---:|
| gt_container_count | 16 |
| predicted_group_count | 25 |
| group_hit | 16 |
| group_miss | 0 |
| split_error | 0 |
| merge_error | 0 |
| orphan_fragment | 0 |
| extra_group | 9 |
| group_recall | 1.0000 |

`black2_r02` 长竖排多列区域正确恢复为一个 group，未跨气泡合并。`black2_r04` 与 `black2_r05` 也未被误合并。

## 7. Reading Order Results

| Split | order_correct | order_error | order_not_evaluable |
|---|---:|---:|---:|
| Synthetic | 3 | 0 | 8 |
| Real core | 13 | 0 | 3 |
| Overall | 16 | 0 | 11 |

不可评估主要是单 fragment container 或 upstream detection miss。未观察到横排或竖排阅读顺序错误。

## 8. OCR Impact

| Split | Exact | Exact rate | Median CER | CER <= 0.30 | Mean CER delta vs GT-assisted B2 | Exact changed |
|---|---:|---:|---:|---:|---:|---:|
| Synthetic | 10/11 | 0.9091 | 0.0 | 10 | 0.0 | 0 |
| Real core | 7/16 | 0.4375 | 0.0866 | 14 | 0.0 | 0 |

自动 grouping 后的 assembled OCR 与 GT-assisted `b2_native_fragments` 没有额外 CER 损失。剩余 OCR 失败均为既有 fragment OCR/substitution 问题。

## 9. Representative Failures

| Case | Type | Observation |
|---|---|---|
| `s04_r03` | upstream detection miss | 无 fragment 可分组，计为 group_miss。 |
| `black1_r04` | existing OCR error | grouping/order 正确，CER `0.1786` 来自 OCR 标点与替换。 |
| `black2_r02` | existing OCR error | 长竖排 grouping 正确，CER `0.1471` 来自 OCR 漏/替换。 |
| auxiliary extra groups | extra_group | real pages 中 9 个 extra groups 来自 unmatched auxiliary predictions，需要正式系统标记 uncertain 或过滤。 |

## 10. Limitations

- 本算法没有气泡检测能力，无法判断 extra group 是否是用户关心的辅助文本。
- 对 unmatched auxiliary prediction 会形成 extra group，其中个别 group bbox 跨度较大。
- 未验证更复杂的倾斜、弧形、艺术字、密集多气泡交错场景。
- 算法不使用 OCR 语义，因此无法借助文本内容修正错误 grouping。
- 正式系统必须保留 grouping uncertainty、manual review、skip/warning 路径。

## 11. Architecture Impact

本轮支持进入 Single Page Real Detection + OCR Backend Slice，但应将 grouping 作为 Detection/OCR 切片内的独立纯函数/服务边界：

- Provider Adapter 仍只负责工具调用，不拥有 grouping 决策；
- ArtifactService 仍只负责 artifact 生命周期；
- WorkflowLoopEngine 后续负责 skip / retry / block；
- QualityCheckService 后续负责质量问题归因；
- grouping 输出应带 `uncertainty_tags`、fragment ids、bbox、orientation、assembled OCR，便于追踪与人工修正。

## 12. Final Verdict

```text
PASS_WITH_LIMITATIONS
```

理由：

- synthetic group hit `10/11`，达到门槛；
- real core group hit `16/16`，超过门槛；
- cross-container merge `0`；
- reading order error `0`；
- real core assembled OCR CER <= 0.30 为 `14/16`；
- assembled OCR 相比 GT-assisted B2 无退化；
- 但 real pages 存在 `9` 个 extra groups，正式系统需要 uncertainty / review / auxiliary filtering。

## 13. Recommended Next Step

允许进入：

```text
Single Page Real Detection + OCR Backend Slice
```

前提：

- 只做单 Page backend vertical slice；
- 将 grouping uncertainty 作为一等输出；
- 不在该切片中引入气泡检测、翻译、清字、嵌字、WorkflowLoopEngine 或持久化复杂化；
- 保留人工 review / warning 路径用于 auxiliary extra groups 与 upstream detection miss。
