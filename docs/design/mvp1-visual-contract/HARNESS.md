# MVP-1 Visual Contract v0.1 — HARNESS

状态：`DESIGN_HARNESS`
目的：以反例优先方式验证领域关系、证据合同、质量门禁和一次局部修正边界。

## 1. 通用输入与输出

每个场景的输入至少包含：

- page/source artifact identity 与 hash；
- `DetectionFragment`、`TextGroup`、`TextSegment` identity；
- cluster/instance candidate identity 与 revision；
- Cleaning eligibility 及 evidence refs；
- mask/region artifact refs 与 hash；
- TypesettingBlock、RenderedGlyphMask identity；
- ProcessingProfileSnapshot、attempt 和 validator contract version。

每个场景输出必须能够逐页对账：

```text
detected → grouped → translated → associated → eligible/excluded
         → cleaned → rendered → validated
```

对账约束：每个 `TextSegment` 必须恰好出现于一个 active `BubbleInstance` assignment，或一个显式 exclusion；eligible segment 必须恰好渲染一次。

## 2. 场景矩阵

| # | 场景与输入 | 预期对象关系 | Owner | 必需证据 | 预期 QualityIssue / 结果 | 一次局部修正 | 验收标准 |
|---:|---|---|---|---|---|---|---|
| 1 | `case-71`：一个接触簇、上下两段 | 1 cluster → 2 BubbleInstance；每实例 1 segment；不共享 safe/typesetting region | topology stage；QualityCheck 对账 | cluster/instance masks、segment assignment、两组独立 cleaning/glyph masks | 合并则 `bubble_instance_merge_error`，blocking | rerun topology split，再使 eligibility/layout stale | 2 段唯一归属；无跨实例清字/排版；两个实例分别验证 |
| 2 | `case-72`：OCR/译文齐全，部分普通气泡为 E2/E3 | 7 BubbleInstance、8 TextSegment；3 eligible、5 excluded，全部在 ledger | eligibility stage | risk reasons、rules、features、threshold version、exclusion refs | 普通气泡无充分理由被排除：`ordinary_bubble_false_exclusion`，blocking；真实 unsupported 可 explainable skip | rerun per-instance eligibility | 原文残留被解释为 eligibility exclusion，不误报 OCR miss；普通气泡假阴性可定位 |
| 3 | 接触簇 N≥3 | 1 cluster → N BubbleInstance，N 不固定 | topology stage | instance adjacency、visible/virtual boundary revision | 少分/多分：merge/split error，blocking | rerun cluster topology | N 个实例身份稳定，segment 唯一归属，局部失败不毒死其他实例 |
| 4 | 单 BubbleInstance 多列 | 1 instance → 多 TextSegment/列 → 多 LayoutSlot | grouping/assignment + typesetting | same-instance evidence、column order、slot mapping | 错拆实例：`bubble_instance_split_error`，blocking | rerun assignment/topology | 不因多列而分成多个气泡；每列可独立布局且仍属同实例 |
| 5 | 单 BubbleInstance 两独立段落 | 1 instance → 2 segment → 2 block → 2 slot；每个 block 内可多行 | typesetting preparation | paragraph identity/order、block/slot mapping | 丢段 `segment_missing`；重复段 `segment_rendered_multiple_times`，blocking | rerun block construction | 两段身份、顺序、段落边界不丢失 |
| 6 | 普通独立 E1 白气泡 | 1 standalone instance/segment，E1 | eligibility + cleaning + typesetting | reason/rules/features、text/protected/safe masks、RequiredTextEvidence、PostCleaningResidueReport、actual changed pixels、glyph mask | residue/damage/overflow 均 blocking | 按 root stage 只重跑一次 | deliberate residue 被拒绝；clean control 无残字；结构安全；glyph 在实例 region 内；布局可接受 |
| 7 | 明确 unsupported SFX/艺术字 | instance/support 可为空；segment 显式 excluded | qualification/eligibility | content role、unsupported reason、source-preserved evidence | `unsupported_but_explainable_skip`，non-blocking exclusion | 不自动修正 | 原图局部保留；不生成清字/排版；不阻塞其他普通气泡 |
| 8 | deliberate segment missing | 某 eligible segment 无 TypesettingBlock/RenderedGlyphMask | reconciliation validator | expected vs actual ledger、active revision | `segment_missing`，blocking | rerun block construction/rendering | Validator 必须拒绝，不能以最终图存在为通过 |
| 9 | deliberate duplicate rendering | 1 segment → 2 active glyph outputs | reconciliation validator | segment-to-block/glyph multiplicity | `segment_rendered_multiple_times`，blocking | invalidate duplicate，rerun rendering | active 输出中每 eligible segment 恰好一次 |
| 10 | deliberate wrong-instance rendering | segment assignment=A，glyph region=B | assignment/render validator | instance ID + region revision on block/glyph | `wrong_instance_rendering`，blocking | rerun typesetting preparation/rendering | 即使 glyph 位于 parent cluster 内也必须拒绝 |
| 11 | deliberate glyph overflow | glyph mask 穿出 instance region | actual-glyph validator | glyph mask、region mask、overflow pixels/hash | `glyph_overflow`，blocking；touch 可独立 issue | rerun line break/font size once | overflow pixels=0；边距满足冻结 profile |
| 12 | renderer 用正确 instance region，validator 错用父 cluster | renderer revision ≠ validator revision | validator input contract | renderer/validator region IDs、revision/hash | `validator_input_mismatch`，blocking | 修正 validator binding 后重验，不重渲染 | mismatch 在计算指标前被拒绝；父 cluster 不能使假通过 |
| 13 | cluster 总体高风险，但其中一实例安全 E1 | cluster → 多实例；risk 按实例重评 | eligibility stage | cluster risk + per-instance features/rules | 安全实例被连带排除：`ordinary_bubble_false_exclusion` | rerun per-instance eligibility | 高风险实例保持 review/skip，安全实例可独立 E1 |
| 14 | 同一气泡多个文字组 | 多 group/segment → 同一 BubbleInstance | topology/association | same-container evidence、assignment revision | 错拆：`bubble_instance_split_error`，blocking | rerun same-container association | 不以 LayoutSlot 或文字组数量替代实例拓扑 |
| 15 | 多个接触气泡被错误合并 | 多 segment → 多 BubbleInstance within cluster | topology stage | competing sources、visible/virtual boundaries、assignment | `bubble_instance_merge_error` / `wrong_instance_assignment`，blocking | rerun topology split | 每个真实实例拥有独立 mask、cleaning、region、glyph validation |

## 3. 全局门禁

### 3.1 必须阻塞

- 普通对白/旁白 segment 缺失、重复、无归属或错误实例；
- cluster 被用作最终 BubbleInstance；
- 明显 Cleaning residue；
- protected structure 或气泡边界损坏；
- renderer/validator region identity 或 revision 不一致；
- actual glyph overflow、跨实例或缺字；
- 普通气泡静默 exclusion；
- evidence artifact 缺失、hash 不匹配或无法复现。

### 3.2 可 warning/review

- 不影响完整性和边界安全的轻微 occupancy/visual-center 偏差；
- 在冻结阈值附近的 boundary touch uncertainty；
- 支持范围内但需一次布局修正的断行、字号或留白问题。

### 3.3 可明确排除

- 已声明 unsupported 的复杂 SFX、艺术字和无可靠支持区域内容；
- 排除必须保留 role、reason、evidence 和 source-preserved 状态；
- exclusion 不得让同页其他 BubbleInstance 失效。

## 4. HARNESS 通过条件

1. 15/15 场景都有唯一 owner、证据和预期 issue；
2. 所有 deliberate negative 均在自动合同层被拒绝；
3. 所有普通对白丢失路径均为 blocking；
4. N≥3、单实例多列、单实例多段三种 cardinality 同时可表达；
5. Cleaner/Renderer/Validator 都绑定明确 BubbleInstance revision；
6. local correction 最多一次，之后只能 pass 或 block；
7. supported exclusion 与产品运行期人工 review 不混淆；
8. 无需 Batch、跨页、复杂 retry 或正式 UI 才能执行验证。
