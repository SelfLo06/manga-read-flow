# MVP-1 Visual Contract Detailed Design v0.1

状态：`ACCEPTED_DESIGN_BASELINE`
适用阶段：MVP-1 高质量单页视觉闭环
设计类型：领域模型、输入输出合同、质量门禁与一次局部修正边界
实现状态：未实现

## 1. 目的与范围

本设计冻结一套单页视觉合同，使系统能对普通对白气泡和普通旁白框回答：每个文字段去了哪里、属于哪个视觉气泡实例、为何允许或禁止清字、实际改了哪些像素、排版使用哪个空间、glyph 实际落在哪里、为何通过或阻塞、失败后局部重跑哪个阶段，以及这些事实如何被保存和恢复。

本设计选择：

```text
stable identity + immutable revision
+ page-scoped coherent visual contract
+ per-instance qualification / eligibility
+ artifact-backed pixel evidence
+ actual-glyph validation
+ one correction chain / one automatic rerun
```

本轮不实现算法、产品代码、migration、API、UI、Provider、测试或实验。MVP-1 可以消费可信 OCR/译文；OCR/翻译自动准确率、多页、Batch、性能、复杂 fallback、正式 Web、复杂 SFX/艺术字和发布级精修不在范围内。

## 2. 来源文档

基线：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/prompt-patterns/design/detailed-design-pattern.md`

架构：

- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`

实证：

- `docs/spikes/detection-ocr/REPORT.md`
- `docs/spikes/detection-ocr/followups/text-region-grouping/REPORT.md`
- `docs/spikes/cleaning/CLEANING-HANDOFF.md`
- `docs/spikes/cleaning/CLEANING-DESIGN-RATIONALE.md`
- `docs/spikes/cleaning/algorithm-lock-v0.1.md`
- `docs/spikes/cleaning/REPORT.md`
- `docs/spikes/cleaning/followups/real-bubble-fill/real-bubble-fill-REPORT.md`
- `docs/spikes/cleaning/followups/text-seeded-container-association/goal4-focused-correction/GOAL4-FOCUSED-CORRECTION-REPORT-v0.1.md` 与 `GOAL4-GATE-v0.1.md`
- `docs/spikes/cleaning/followups/text-seeded-container-association/goal5-routed-association/GOAL5-ROUTED-ASSOCIATION-REPORT-v0.1.md` 与 `GOAL5-GATE-v0.1.md`
- `docs/spikes/cleaning/followups/text-seeded-container-association/goal6-minimal-cleaning/GOAL6-FINAL-REPORT-v0.1.md`
- `docs/spikes/cleaning/followups/text-seeded-container-association/goal7-local-routing/GOAL7-FINAL-REPORT-v0.1.md`
- `docs/spikes/cleaning/followups/text-seeded-container-association/large-scale-e1-e2-comparison/REPORT-v0.1.md`
- `docs/spikes/typesetting/REPORT.md` 与 `GATE.md`
- `docs/spikes/typesetting/input-contract-validator-grounding/HARNESS.md`、`REPORT.md` 与 `GATE.md`
- `data/local/typesetting-input-contract-v0.1/run-v0.4/FORM.md`

提交版 Input Contract REPORT/GATE 停在 `PENDING_HUMAN_REGION_AND_MAPPING_REVIEW`；后续 FORM 已选择 `GO_WITH_CHANGES`，现行 SRS/HLD/PROJECT-PLAN 也已吸收该裁决。本设计把二者解释为历史报告状态与后续人工补充证据，不修改旧报告。

## 3. 当前证据与限制

### 3.1 已确认

- Detection/OCR 与 Grouping 能提供有价值的文字位置、方向、分组和完整性先验；OCR 字符串正确不等于像素 mask 正确。
- Goal 7 证明 per-group/local-cluster routing 与 bounded local B1 可在资源上稳定执行；`255/255 non-empty` 不等于语义正确。
- Goal 7 已出现 `WRONG_OR_LEAK`，因此 `LOCAL_B1_CANDIDATE` 不是 confirmed container、BubbleInstance mask 或 safe edit region。
- Goal 6 只为少量冻结 E1 输入提供正向清字证据；`changed_outside_effective=0` 只是必要条件。
- 40 页实验确认 page-global routing/full-page B1 失败，并证明 mask 外零修改可以与明显残字同时存在。
- Input Contract run 证明两页 31/31 fragment 可追踪；case-72 单页为 7 个实例候选、8 个 segment，其中 3 个 E1 eligible、5 个 E2/E3 excluded。
- 后续人工确认 OCR/译文没有串块、绿色 region 位于对应真实气泡内部；但 case-71 的旧 `container-002` 实际包含两个接触而独立的视觉气泡。
- 首轮 Typesetting 假通过来自错误/过宽恢复 region 上的机器指标自洽；v0.4 只证明点级显式负例合同，尚未证明真实整段 glyph、字号、断行、留白或视觉中心质量。

### 3.2 尚未证明

- 自动 local candidate qualification 与 BubbleInstance 拆分算法的泛化质量；
- Pixel Text Mask、protected mask、residue detector 的全局阈值；
- 普通气泡 E2/E3 的自动推广；
- actual-glyph 整段压力测试和自然排版阈值；
- 正式持久化 DDL、Repository API 与 UI 编辑体验。

这些限制不妨碍冻结合同，但禁止把设计描述成现有算法已经达到的能力。

## 4. 术语和对象模型

```text
PageVisualContractRevision
├── DetectionFragment
├── TextGroup
├── TextSegment
│   └── exactly one ContentOwnerRef
├── ContactBubbleCluster
│   └── 1..N BubbleInstanceRevision
├── standalone BubbleInstanceRevision (cluster_id = null)
├── SegmentDisposition
│   ├── assigned → exactly one BubbleInstanceRevision
│   └── excluded → exactly one explicit exclusion
├── InstanceQualificationRevision
├── CleaningEligibilityAssessment
├── CleaningCandidate / CleaningResultEvidence
├── TypesettingRegionRevision
├── LayoutPlanRevision
│   └── LayoutSlot / TypesettingBlock
└── RenderedGlyphEvidence
    ├── GlyphCoverageArtifact
    └── GlyphWriteMaskArtifact
```

核心职责：

| 对象 | 职责 | 禁止替代 |
|---|---|---|
| `DetectionFragment` | detector 产生的局部文字几何证据 | Pixel Text Mask |
| `TextGroup` | 一个 grouping revision 内的 fragment 集合、方向与局部顺序 | BubbleInstance |
| `TextSegment` | 可独立 OCR/翻译、归属、排除和渲染对账的最小内容单元 | TextGroup、LayoutSlot |
| `ContactBubbleCluster` | 相邻/接触/串联气泡的父簇与共享边界上下文 | 最终清字、排版或验证 region |
| `BubbleInstance` | 视觉上独立的气泡或旁白框身份 | 其可变几何；几何属于 revision |
| `LayoutSlot` | 单个 BubbleInstance 内一个 segment 的排版约束 | BubbleInstance |
| `SegmentDisposition` | active segment 的唯一 assignment 或 exclusion | 修改 segment 内容 |
| `InstanceQualificationRevision` | 判断 association candidate 是否足以成为实例空间输入 | Cleaning 风险类别 |
| `RenderedGlyphEvidence` | glyph logical identity、owner、revision 与 artifact refs | glyph bitmap bytes |

## 5. 对象 cardinality

```text
ContactBubbleCluster 1 → 1..N BubbleInstance
BubbleInstance       1 → 0..N TextSegment
BubbleInstance       1 → 0..N LayoutSlot
eligible TextSegment 1 → 1 TypesettingBlock
TypesettingBlock     1 → 1 LayoutSlot
TypesettingBlock     1 → 1 RenderedGlyphEvidence
```

规则：

1. `N` 不固定为 2；接受态 contact cluster 通常 `N >= 2`。
2. 独立普通气泡允许 `cluster_id = null`，不得伪造 contact cluster。
3. 一个 BubbleInstance 可有多列或多段文字；文字段数量不决定实例数量。
4. MVP-1 中每个 eligible segment 恰好对应一个 block 和一个 slot；block 内可以多行。
5. 需要一个 segment 跨多个独立 slot 的场景当前 block，不隐式引入 segment-part。
6. accepted supported BubbleInstance 必须至少有一个 segment；空候选只能是显式诊断/排除状态。
7. LayoutSlot 不拥有边界、清字或实例归属语义。

case-71 的冻结解释是：一个 `ContactBubbleCluster`、两个 `BubbleInstance`、两个 `TextSegment`，每段唯一归属一个实例。不能继续用一个 parent container 加两个 slot 表达。

## 6. Identity 和 revision

所有逻辑对象同时具有：

- stable opaque identity；
- immutable revision identity；
- payload/content hash；
- source revision refs；
- producer attempt、contract/schema version。

不得从 bbox、数组序号、文件名、时间戳或坐标推导 identity。

| 变化 | identity | revision/stale |
|---|---|---|
| 同一实例边界局部修正 | 保留 instance identity | 新 instance revision；受影响下游 stale |
| 实例被拆成多个实例 | 原实例 superseded；新实例新 identity | 新 topology revision；旧下游 stale |
| 多实例合并为一个实例 | 原实例 superseded；合并结果新 identity | 新 topology revision |
| segment 重归属 | segment/instance identity 保留 | 新 assignment revision；old/new instance 下游 stale |
| segment 真正拆分/合并 | 原 segment superseded；新 segment 新 identity | 新 content/assignment revision |
| slot 移动或重排 | segment/instance identity 不变 | 新 LayoutPlanRevision |

每个 `TextSegment` 必须绑定恰好一个不可变 `ContentOwnerRef`：

```text
owner_type / owner_id
source_span_ref
ocr_result_ref / ocr_text_sha256
translation_result_ref / translation_text_sha256
```

正式产品中 owner 应是现有 `TextBlock` 或未来经 schema review 选择的单一 segment owner；二者不能同时拥有 active OCR/Translation。两个需要独立编辑/翻译的 segment 不得只共享一个无法区分 source span 和结果版本的 owner。无法建立唯一 owner时，segment 阻塞进入 Cleaning/Typesetting。

## 7. Provenance 与逐页 reconciliation

完整链：

```text
DetectionFragment
→ TextGroup
→ TextSegment
→ ContactBubbleCluster / BubbleInstance
→ CleaningCandidate / explicit exclusion
→ TypesettingBlock / explicit exclusion
→ RenderedGlyphEvidence
→ ValidationResult
```

每个 active `TextSegment` 在同一个 visual contract revision 中必须恰好有一条 `SegmentDisposition`：

```text
ASSIGNED:
  segment_id
  bubble_instance_id / revision_id
  assignment_revision_id
  evidence_refs

EXCLUDED:
  segment_id
  exclusion_class
  excluded_reason
  evidence_refs
  source_preserved = true
```

`UNASSIGNED` 只允许出现在未接受 candidate；进入质量判断时转为 blocking `segment_unassigned`。

逐页 ledger 必须同时保存 count 和逐 ID row：

```text
detected
grouped
segmented / translated
assigned / excluded / unassigned
eligible / cleaning_excluded
cleaned
render_expected / rendered / duplicate
validated / blocked
```

计数必须能下钻到 ID、revision 与 reason。缺失和重复不能互相抵消。case-72 的场景口径固定为 7 BubbleInstance、8 TextSegment、3 eligible、5 excluded；31 fragments/14 segments 只属于两页 run 总计。

## 8. Source of truth

### 8.1 下一 bounded Spike

- 一个 schema-versioned、hash-locked `VisualContractSnapshot` JSON 是该 run 内 identity/relation/revision 的唯一事实来源；
- candidate 与 accepted verdict 分离；
- 不接产品 active pointer、recovery 或 export；
- 不按 mtime、文件名或目录顺序选 current；
- mask/image/glyph bytes 作为独立 immutable artifacts。

### 8.2 正式 MVP-1 Workflow

| 事实 | 唯一来源 |
|---|---|
| 当前视觉关系与选择 | project.db 中 `Page.active_visual_contract_revision_id` + purpose-specific relational facts |
| 当前 OCR/Translation | 唯一 content owner 的 active result refs |
| mask/region/glyph/changed pixels | ArtifactService 登记的 bytes + hash |
| artifact path/storage state | `ProcessingArtifact` metadata |
| cleaned/typeset 已选择结果 | 现有 Page active artifact pointers |
| 是否 fresh/export-effective | active visual revision、dependency hashes、artifact integrity、open issue gate |
| acceptance 当时快照 | immutable manifest/ledger audit artifact |

正式阶段 manifest 不是第二关系主源，不含可独立推进的 `is_active`。DB 与 manifest identity/hash 不一致产生 blocking evidence-contract issue；禁止自动择新、双向回写或按时间覆盖。

Active pointer 表示“已选择”；是否当前可用还必须满足 freshness、integrity 和 issue gate。上游改变后可保留 last-selected artifact 供历史预览，但必须 stale，不能进入 pure/warning readiness。

## 9. DTO / contract

### 9.1 VisualDependencyFingerprint

Cleaner、Typesetter 和 Validator 共享一个规范化依赖指纹：

```text
page_id / source_artifact_id / source_sha256
visual_contract_revision_id / topology_revision_id
bubble_instance_id / bubble_instance_revision_id
segment_assignment_revision_id
content_owner_refs[] / text hashes
profile_snapshot_id / profile_hash
coordinate_space_id / width / height
```

Cleaner 额外绑定 eligibility 与 effective-mask revision/hash；Renderer/Validator 额外绑定同一个 typesetting-region revision/hash、layout/render revision。Cleaner 不消费 typesetting region。

### 9.2 PageVisualContractRevision

最小逻辑字段：

```text
visual_contract_revision_id / parent_revision_id / schema_version
page/source refs + hashes
upstream run/revision refs
fragments[] / groups[] / segments[]
clusters[] / bubble_instance_revisions[]
segment_dispositions[]
qualification_refs[] / eligibility_refs[]
cleaning / typesetting / validation result refs
reconciliation rows + summary
dependency_fingerprint
producer attempt/profile/config refs
status: candidate | accepted | superseded | stale | rejected
manifest_artifact_ref / manifest_sha256
```

### 9.3 InstanceQualificationRevision

由 association/topology component 产生 candidate，QualityCheckService 验证，WorkflowLoopEngine 决定是否接受：

```text
qualification_id / revision
bubble_instance_id / revision
candidate_source_kind
content_role / role_confidence
boundary evidence refs
semantic correctness / leakage evidence
status: QUALIFIED | UNQUALIFIED | ABSTAINED
reason_codes[]
dependency_fingerprint
```

`LOCAL_B1_CANDIDATE` 非空不能单独得到 `QUALIFIED`。qualification 改变会使该实例 eligibility、mask、Cleaning、region、layout、render 与 validation stale。

## 10. Cleaning eligibility

qualification 先于 eligibility：

```text
local association candidate
→ InstanceQualificationRevision
→ per-instance CleaningEligibilityAssessment
→ MaskBundle
→ CleaningAttempt
→ CleaningValidationEvidence
```

每个 assessment 至少保存：

```text
assessment_id / revision
bubble_instance_id / revision
segment_assignment_revision
qualification_ref
content_role
eligibility_class
risk_reasons[]
triggered_rules[]
feature_values{}
threshold_version / policy_hash
recommended_action
excluded_reason
evidence_refs[]
input_fingerprint
```

E1–E4 语义：

| 类别 | 风险含义 | MVP-1 默认动作 |
|---|---|---|
| E1 | qualified 普通实例，完整文字可在 safe region 内编辑 | 允许一次 Cleaning attempt，仍须后验验证 |
| E2 | 边界、小字、邻接或轻度结构风险 | comparison/correction only，不自动采用 |
| E3 | 复杂背景、真实结构穿过或无法安全覆盖 | exclude automatic，不得假装成功 |
| E4 | 当前 profile 明确不支持的 SFX/艺术字等 | preserve-source skip |

规则：

- cluster 的最高风险不得广播给成员；split/merge 后逐实例重评；
- protected overlap 必须记录像素数、相对 text-core/effective 比例、结构类型、连通性、是否连接 required text、扣除后的覆盖率；
- 既禁止“存在任意 overlap 就整实例 E3”，也禁止“小 overlap 一律扣除并 E1”；
- 彩色文字、小字号、边界距离或轻微 overlap 不能作为无 safety consequence 的单一硬否决；
- 普通对白/旁白 exclusion 缺 rules/features/threshold/evidence 时产生 `ordinary_bubble_false_exclusion`。

## 11. Mask / region contract

必须严格区分：

| 对象 | 语义 | 可否直接写入 |
|---|---|---:|
| `ClusterMask` | 父簇搜索/上下文 | 否 |
| `BubbleInstanceMask` | qualified instance interior revision | 仅作为 safe 上界 |
| `VisibleBoundaryMask` | 直接观测边界 | 否，保护 |
| `VirtualBoundaryMask` | 竞争传播推断分界 | 否，保护 |
| `BoundaryUncertaintyMask` | 边界不确定带 | 否，禁止自动编辑 |
| `PixelTextMask` | per-segment core/accepted-soft/uncertain 文字像素 | 仅 core+accepted-soft 可候选 |
| `ProtectedMask` | 边界、分镜线、人物/结构、邻居边界 | 否 |
| `SafeEditMask` | instance 内允许编辑的空间上界 | 否 |
| `EffectiveEditMask` | 本次 Cleaner 唯一允许写入的最终集合 | 是 |
| `AttemptWriteMask` | compositor 请求写入的集合 | 事后证据 |
| `ActualChangedPixelMask` | output 与 input 实际不同的像素 | 事后事实 |
| `TypesettingRegionMask` | BubbleInstance 内独立可排版 region | 仅 Typesetter/Validator |
| `GlyphCoverageArtifact` | 未裁剪最终 glyph alpha coverage | Validator 输入 |
| `GlyphWriteMaskArtifact` | compositor 实际 glyph 写入集合 | Validator/写回证据 |

派生约束：

```text
M_protected = visible_boundary
            ∪ virtual_boundary
            ∪ boundary_uncertainty
            ∪ neighbor_boundary
            ∪ panel_line
            ∪ high_confidence_structure

M_safe = erode(M_instance, margin_policy) \ M_protected
M_text_editable = M_text_core ∪ M_text_accepted_soft
M_effective = M_text_editable ∩ M_safe
```

硬不变量：

```text
M_effective ⊆ M_text_editable ⊆ M_instance
M_effective ∩ (M_protected ∪ M_boundary_uncertainty ∪ M_text_uncertain) = ∅
M_actual_delta \ M_effective = ∅
```

若扣除 protected/uncertain 后 required text coverage 不完整，必须 correction、降级或 block，不能用缩小 mask 制造“零损伤通过”。Overlay 仅为诊断 artifact，必须标明 all-context/applied/skipped，不是 mask source of truth。

### 11.1 Cleaning residue 最低证据

每个 eligible segment 必须有 `RequiredTextEvidence`：

```text
segment_id
source_image_ref / hash
pixel_text_mask_ref / revision / hash
required_core_components[]
accepted_soft_edge_coverage
coordinate_space
producer/version
```

每个 Cleaning result 必须有 `PostCleaningResidueReport`：

```text
report_id
validator/metric version
source/output refs + hashes
required_text_evidence refs
residual_component refs
residual_score / coverage per segment
evidence artifact refs
profile/threshold version
```

Evidence 缺失、hash/revision/坐标不一致、eligible segment 未覆盖或 deliberate residue 未被拒绝均 blocking。`ActualChangedPixelMask`、`changed_outside_effective=0` 与 residue report 三者互不替代。

下一 bounded Spike 必须包含同一冻结 E1 输入的两类控制：完整 clean negative control 应通过；向 output 故意恢复/保留 required-text component 的 deliberate-residue positive 应触发 `cleaning_residue`。数值阈值仅在 calibration 子集写入不可变 profile。固定页人工 `ACCEPTABLE` 是里程碑证据，不是每次产品运行必填。

## 12. Typesetting contract

`TypesettingRegionRevision` 最少绑定：

```text
region_id / revision
page / coordinate space / dimensions
bubble_instance_id / revision
topology / assignment revision
mask_artifact_ref / sha256
source_boundary_revision
generation/inset profile version
qualification status/evidence
producer attempt / contract version
```

禁止替代物：parent cluster、BubbleInstance/TextBlock bbox、Cleaning text/safe/effective mask、overlay 恢复 region、旧 revision 或同名异 hash mask。

`LayoutPlanRevision` 绑定 active translation、cleaned page、font/style/profile、instance/region/assignment revision。每个 block 保存 segment、content owner、slot、字号、行距、字距、描边、断行、glyph expectation。

硬约束：

- eligible segment 恰好一 block/一 slot；excluded segment 零 block；
- block/slot 不跨 instance；同实例 block 保序且不发生不可解释重叠；
- 中文闭标点不置于行首、开标点不置于行尾；
- 除单字符 segment 外不得单字孤行；
- 缺字不得以空白替代；
- 不能仅最大化字号，必须同时考虑 occupancy、留白、断行和局部视觉中心；
- 同实例多 segment 使用各自 slot-local center，不向 parent cluster 或单一整体中心聚集。

## 13. Validator contract

Renderer 必须输出未按 region 裁剪的 per-segment `RenderedGlyphEvidence`：

```text
glyph_evidence_id
typesetting_block_id / text_segment_id
bubble_instance_id / revision
layout_plan_revision
region_id / revision / hash
coordinate_space
glyph_coverage_artifact_ref / hash
glyph_write_mask_artifact_ref / hash
expected/rendered glyph counts
missing_codepoints[]
render_manifest_hash
```

Validator 顺序固定：

1. identity/hash/revision/coordinate-space preflight；
2. segment assignment/exclusion/block/glyph reconciliation；
3. actual glyph 空间安全；
4. layout quality；
5. issue drafts 与 root attribution。

任何 preflight mismatch 直接 `validator_input_mismatch`，不得计算可被误读为通过的 overflow 指标，也不得回退 bbox/parent cluster。

令 `G` 为 actual glyph write mask，`R` 为 exact typesetting region：

```text
overflow_pixels      = |G \ R|
overflow_ratio       = overflow_pixels / max(|G|, 1)
minimum_inner_margin = min(distance_to_complement(R), pixel in G ∩ R)
boundary_touch       = any inner_distance <= profile.touch_margin_px
```

`|G| = 0` 是 missing/empty glyph blocker。confirmed hard touch 为 blocking；仅在 boundary uncertainty/profile 临界带内的接近可为 review。Validator还从 actual glyph/line evidence 重算 occupancy、字号、行首行尾、orphan、visual-center offset、contrast 和 missing glyph。

Immediate hard constraints：missing/duplicate/wrong-instance、missing glyph、empty glyph、actual overflow、confirmed boundary touch、不可读 low contrast。下一 calibration 冻结 occupancy、relative margin、center、orphan/line-break 数值；人工里程碑只评价整体自然度，不能替代自动安全 Gate。

## 14. QualityIssue taxonomy

| Issue | 默认 root component | 默认处理 |
|---|---|---|
| `segment_unassigned` | segment_assignment | blocking |
| `segment_missing` | block_construction 或更早 ledger root | blocking |
| `segment_rendered_multiple_times` | block_construction/rendering | blocking |
| `wrong_instance_assignment` | segment_assignment | blocking |
| `bubble_instance_merge_error` | visual_topology | blocking |
| `bubble_instance_split_error` | visual_topology | blocking |
| `ordinary_bubble_false_exclusion` | cleaning_eligibility | blocking |
| `cleaning_residue` | pixel_text_mask 或 cleaning_writeback | blocking |
| `protected_structure_damage` | safe_edit_region/writeback | blocking |
| `bubble_boundary_damage` | safe_edit_region/writeback | blocking |
| `wrong_instance_cleaning` | pixel_text_mask/safe_edit_region | blocking |
| `cleaning_outside_safe_edit_region` | cleaning_writeback | blocking |
| `wrong_instance_rendering` | typesetting_region/block_construction | blocking |
| `glyph_overflow` | layout，错误 region 时回溯 region | blocking |
| `glyph_boundary_touch` | layout | confirmed touch blocking；临界 uncertainty review |
| `occupancy_too_high` | layout | correction candidate；严重/二次失败 blocking |
| `font_size_too_large` / `font_size_too_small` | layout | correction candidate；不可读 blocking |
| `unnatural_line_break` | layout | correction candidate/review；影响可读性 blocking |
| `single_character_orphan_line` | layout | correction candidate/review |
| `visual_center_outlier` | layout | correction candidate/review；严重 blocking |
| `low_contrast` | layout/rendering | 不可读 blocking，否则 warning |
| `missing_glyph` | rendering | blocking |
| `validator_input_mismatch` | validator_binding | blocking |
| `visual_evidence_missing` / `visual_evidence_hash_mismatch` | evidence_binding | blocking |
| `unsupported_but_explainable_skip` | qualification/eligibility | local non-blocking exclusion |

QualityCheckService 产生 issue draft 和 root-stage attribution；WorkflowLoopEngine 才能持久化 decision 并决定 correction、warning、skip 或 block。

## 15. Blocking / warning / exclusion policy

| 处理类 | 定义 | 页面 readiness |
|---|---|---|
| `blocking` | supported scope 的完整性、安全性、实例归属或可复现性失败 | pure/warning readiness 均阻塞 |
| `warning` | 输出仍完整、安全、可读的有限缺陷 | profile允许时 warning-ready |
| `review` | 自动证据不足，不表示必须等产品用户逐块确认 | supported内容默认不通过；一次 correction 后仍 review 则 block |
| `supported_scope_exclusion` | 对象属于当前支持范围，但本次无法安全处理 | MVP-1 high-quality page 默认 blocking；不能 warning 掩盖 |
| `unsupported_but_explainable_skip` | 对象明确超出 profile，role/reason/evidence/source-preserved 完整 | 不阻塞其他 supported instances；页面最多 warning-ready |

普通对白/旁白的 missing、duplicate、wrong instance、明显 residue、人物/线稿/边界损坏、glyph overflow 和无解释 exclusion 一律 blocking。

局部 instance blocker 不会阻止同页其他实例继续计算和保存可复用结果；但 unresolved supported-scope blocker 仍阻止整页 MVP-1 high-quality acceptance/export。这不是 page-global rerun，也不是 warning 放行。

Pure `ready_for_export` 需要：全部 supported segment 唯一归属、清字/排版/验证完成；active output 与 active visual revision fresh；artifact完整；无 warning/review/exclusion/blocker。`ready_for_export_with_warnings` 还要求无 blocker/review，且 profile 显式允许 warning 和 unsupported skip。

## 16. 一次 local loop

保留 canonical `cleaning` / `typesetting` stage；使用 `root_component` 定位：

```text
cleaning:
  visual_topology
  instance_qualification
  segment_assignment
  cleaning_eligibility
  pixel_text_mask
  safe_edit_region
  cleaning_writeback

typesetting:
  typesetting_region
  block_construction
  layout
  rendering
  validator_binding
  visual_validation
```

流程：

```text
candidate ordinal 0
→ QualityCheck
→ WorkflowLoopEngine root attribution
→ at most one retry_upstream_stage
→ candidate/validation ordinal 1
→ pass / warning / unsupported skip / block
```

唯一 correction 必须跨崩溃 exactly-once。WorkflowLoopEngine 决定 retry 时，在一个短 `WorkflowDecisionTransaction` 中原子持久化：

```text
correction_chain_id
correction_ordinal = 1
budget_after = 0
target stage/component/scope
dependency snapshot
retry decision
ordinal-1 WorkflowAttempt reservation
```

恢复只能继续或幂等复用该 reservation。工具成功但 acceptance 前崩溃时，按 input fingerprint 与 registered artifact hash 重验/复用，不重新消费预算。ordinal 1 仍失败时原子持久化 block；issue code、root attribution 或进程重启不得创建 ordinal 2。用户主动修改 active upstream revision 可建立新 chain，但必须有新 dependency snapshot。

同页存在多个 blocker 时：若一个最上游 root 的 dependency closure 覆盖全部 blocker，选择该 root；若 roots 互不为祖先且一次修正无法同时解决，直接 block，不为每个 issue 各给一次 retry。

所有终态使用 `WorkflowDecisionTransaction`：accept 分支可更新 active pointers；block/review 分支仍原子保存 candidate refs、validation report、issues、decision、attempt terminal state、budget 和 freshness，但不更新 active output。

## 17. Stale propagation

| 变化 | stale 范围 | 不应无故 stale |
|---|---|---|
| cluster split/merge | affected instance/assignment、qualification、eligibility、mask、Cleaning、region、layout、render、validation | 其他独立 cluster |
| instance boundary revision | 本实例及共享边界受影响邻居的空间下游 | 无关实例 |
| segment reassignment | old/new instance eligibility 与全部下游 | OCR/Translation 内容 |
| OCR/译文内容变更 | Translation（若 OCR 变）、layout/render/validation | topology，除非几何也变 |
| eligibility/rule profile 变更 | 该实例 eligibility 与下游 | topology |
| text/protected/safe mask 变更 | Cleaning、typesetting dependency、render/validation | instance identity |
| cleaned artifact hash 变更 | layout/render/validation | topology/assignment |
| typesetting region 变更 | layout/render/validation | Cleaning |
| layout 变更 | render/validation | Cleaning/region |
| validator binding 修正 | validation only | render/glyph evidence |

每次局部 rerun 后必须重新执行 Page reconciliation。旧 revision 和失败证据 immutable 保留；active/freshness 由 acceptance transaction 更新。

## 18. ArtifactService 边界

ArtifactService 唯一负责：

- child mask/region/glyph/delta artifact 的安全写入、hash、登记、storage state、retention；
- candidate image、quality report、ledger/manifest、overlay 的正式 artifact 生命周期；
- presence/hash/dimension integrity 检查。

顺序：先登记 manifest 引用的 child artifacts，再生成/登记 immutable manifest，最后进入 WorkflowDecisionTransaction。

ArtifactService 不决定 qualification、eligibility、质量、active selection、retry 或 export。Overlay 是 `cache_rebuildable` 诊断证据，不得作为 geometry、mask 或 recovery truth。Active/open-issue/replay 所需 artifact 不得被 retention 清理。

## 19. Repository / persistence 边界

正式 Workflow 前 project.db 必须能够查询并原子约束以下逻辑事实：

- page visual contract revision header 与单一 active pointer；
- stable segment/cluster/instance identities 和 revision lineage；
- cluster membership；
- segment assignment 或 explicit exclusion；
- unique content owner refs；
- qualification/eligibility summary、result/evidence refs；
- dependency hashes、freshness；
- attempt、decision、correction chain、issue lifecycle；
- cleaned/typeset selected pointers 与 active visual revision 绑定。

这不要求每个 LayoutSlot、CleaningCandidate 或 glyph artifact 都有独立表；物理表拆分留给 schema review。禁止 generic EAV/typed-edge 作为核心关系主源，禁止 row-level active flags 与 Page active pointer重复表达 current。

Acceptance 使用 expected-state guards：旧 active visual revision、source hash、active OCR/Translation refs/hash、profile hash、相关 instance/segment revisions、artifact integrity、task/stage state。guard 失败则 abort、reload、redecide。

Recovery 加载 active revision、relations、attempts、decisions、issues、artifact metadata 和 profile snapshot；校验 manifest/DB identity/hash、artifact integrity、reconciliation 与 freshness。不得从 `Page.status`、latest timestamp、目录扫描或最终 PNG恢复 pass。

Reuse key 必须包含完整语义依赖；相同 bytes 但不同 instance/region revision 不能复用 validator pass。Reuse 仍生成 `reused_cached` attempt/decision evidence。

## 20. Migration decision

```text
MIGRATION_NOW = NO
MIGRATION_FOR_NEXT_BOUNDED_SPIKE = NO
MIGRATION_BEFORE_FORMAL_MVP1_WORKFLOW_INTEGRATION = YES
```

下一 bounded Spike 使用 run-local immutable JSON，不接 active pointer、跨重启 recovery、正式 export 或 UI edit。

满足任一条件即触发 schema review/migration：

1. visual result 将更新 active cleaned/typeset pointer；
2. 需要跨进程恢复 instance-local correction；
3. UI 需要查询/编辑 segment、instance、exclusion 或 issue；
4. export gate 依赖 visual contract；
5. bounded Spike 通过并进入正式 MVP-1 slice。

正式集成不能把 JSON 目录扫描包装成 Repository。当前设计冻结逻辑事实与门槛，不冻结 DDL、ORM 或 migration 文件。

## 21. HARNESS scenario validation

| # | 设计证据 | 预期 issue / correction | 恢复与 readiness |
|---:|---|---|---|
| 1 case-71 | 1 cluster→2 instance；每实例1 segment/region/mask/glyph | merge/wrong-instance blocking；局部 topology split | 新 page revision；两实例分别通过才 high-quality ready |
| 2 case-72 | 7 instance/8 segment；3 eligible/5 excluded；per-instance reasons | 无理由普通 exclusion blocking；eligibility rerun | 恢复 rules/features/evidence；不得误报 OCR miss |
| 3 N≥3 | cluster membership 1..N | 少分/多分 blocking；local topology | N 不固定；未受影响实例复用 |
| 4 单实例多列 | 多 segment，同一 instance，每段1 slot | 错拆 split error | order/assignment来自 ledger，不从图恢复 |
| 5 单实例两段 | 两 content owners、两 block/slot、保序 | missing/duplicate blocking | 两段均恰好一次 |
| 6 普通 E1 | qualification、assessment、mask、delta、residue、glyph 全链 | residue/damage/overflow 按 root 一次修正 | pointer仅在全部 evidence/freshness 通过后 export-effective |
| 7 unsupported SFX | explicit role/reason/evidence/source preserved | unsupported explainable skip | 其他实例继续；页面最多 warning-ready |
| 8 deliberate missing | expected ledger 无 block/glyph | `segment_missing` blocking | 不更新 active pointer；issue/report/decision可恢复 |
| 9 duplicate | 同 segment 两 active glyph relations | duplicate blocking | candidate保留，active不变 |
| 10 wrong instance | assignment=A，block/glyph=B | wrong-instance blocking | parent cluster 内也拒绝 |
| 11 overflow | unclipped glyph write mask vs exact region | `glyph_overflow`；一次 layout correction | ordinal1仍overflow则block |
| 12 wrong validator region | renderer=A，validator=parent/B | preflight mismatch；只重绑重验 | 复用 glyph artifact；correction ordinal不因重启重置 |
| 13 cluster高风险/成员安全 | per-instance eligibility，无 worst-risk 广播 | 安全实例可E1，高风险保持E2/E3 | 各自 revision可恢复 |
| 14 同气泡多group | 多 group/segment→同一 instance，多 slot | 错拆 blocking | LayoutSlot 不成为 instance |
| 15 多接触气泡误合并 | cluster 下独立 instance masks/boundaries | merge/assignment blocking | topology新revision，下游stale |

设计门禁结果：15/15 场景可由 identity、revision、artifact 和 issue 合同解释；deliberate negatives 均在自动合同层拒绝；没有场景要求 Batch、跨页或复杂 retry 才成立。

## 22. Rejected alternatives

1. 用一个 parent container + 多 LayoutSlot 表示接触气泡：无法独立清字和验证。
2. 每个 segment 自动成为一个 BubbleInstance：单实例多列/多段反例失败。
3. B1 non-empty region 直接作为 BubbleInstance/safe region：Goal 7 已有 WRONG_OR_LEAK。
4. cluster worst-risk 广播成员：重现 collateral exclusion。
5. 所有 E2/E3 升级 E1：破坏安全边界。
6. OCR bbox、coarse region 或 dilation 直接作为 Pixel Text Mask：像素语义错误。
7. `changed_outside=0` 等于 Cleaning 成功：case-40 已反证。
8. Renderer 先裁剪 glyph 再验证：系统性隐藏 overflow。
9. Validator 信任 Provider 自报指标：QualityCheck 必须从正式 artifact 重算。
10. 只保存最终 PNG/计数：无法发现 missing、duplicate、wrong instance 或 residue 根因。
11. bounded Spike 与正式 DB 同时维护可写关系主源：形成双重事实来源。
12. artifact registration 自动 active 或 latest timestamp 选 current：绕过 acceptance 与 recovery 不变量。
13. 每个 issue 一次 retry：形成变相无界 loop。
14. 默认把 REVIEW_REQUIRED 交用户逐块确认：把开发期 gate 误设成产品必经流程。
15. 现在设计完整 DDL/API/UI：合同尚需 bounded Spike 证伪，且任务明确禁止。

## 23. 风险与缓解

| 风险 | 缓解 |
|---|---|
| BubbleInstance qualification 仍依赖未验证算法 | 下一 bounded Spike 以 case-71/72 与 N≥3/单实例多段成对反例证伪 |
| TextBlock/TextSegment owner 未来 schema 选择错误 | 正式 migration 前强制 schema review；当前 contract只允许一个 immutable content owner |
| JSON/DB 双主 | 阶段切换明确；正式 DB 唯一，manifest只审计 |
| mask/region/hash 漂移 | dependency fingerprint + preflight mismatch blocking |
| residue detector 假阴性 | required-text/residue report、deliberate positive/negative、人工里程碑三层证据 |
| 阈值过拟合两页 | 只冻结字段/单位/版本；数值在独立 calibration 子集冻结 |
| 一次 correction 不足以处理多根因 | ancestor closure 规则；独立根因直接 block，避免无界 retry |
| 局部失败被误解为整页停止 | 其他实例继续计算/保存；仅页面 high-quality acceptance受 supported blocker影响 |
| artifact 数量增长 | 大 payload retention policy；active/open-issue/replay证据保留 |
| 人工评估渗入产品运行期 | 人工只作开发 calibration/里程碑；运行合同输出自动 pass/block/exclusion |

## 24. Implementation readiness

本设计已达到 **bounded Spike contract-ready**，未达到产品实现授权。

下一 bounded Spike 可以且只应：

1. 使用 schema-versioned `VisualContractSnapshot`；
2. 用 case-71 验证 cluster→2 instances，用单实例多段 control 防止过拆；
3. 加 N≥3 contact cluster；
4. 对 case-72 重放 7/8 eligibility ledger；
5. 生成 per-segment RequiredTextEvidence、residue 正反例；
6. 生成真实整段未裁剪 glyph evidence；
7. 拒绝 missing、duplicate、wrong-instance、overflow、touch、wrong-validator-region；
8. 验证一次 correction reservation/recovery 的合同数据，不接正式 Workflow；
9. 记录阶段耗时，但不以性能为门禁。

停止条件：任一 deliberate negative 被接受；需要 parent cluster/bbox/overlay 才能通过；segment/glyph 无法对账；residue evidence不可重放；第二次自动 correction 才能过；或必须扩展到 E2/E3/SFX/Batch 才能继续。

正式 Workflow 实现前还必须完成：purpose-specific schema review、migration、Repository/UoW/acceptance transaction 设计、正式 artifact types、QualityIssue codes/profile schema 和实现测试。此处不创建下一实现任务。

## 25. Open questions

非阻塞问题集中记录于 `final/open-questions.md`。当前无 blocking open question。关键后续决策包括：

- TextSegment 与现有 TextBlock 的最终 1:1/独立实体方案；
- 最小 purpose-specific 表拆分；
- topology split/merge identity matching 算法；
- mask/glyph canonical encoding 与 hash；
- residue、occupancy、margin、center、orphan、contrast 的 calibration 阈值；
- `simple_label` 是否进入 MVP-1 supported profile；
- retention TTL 与 cleaned-only preview 语义。

这些问题均不改变本设计已冻结的 identity、cardinality、source-of-truth、artifact、QualityIssue、一次 correction 与 migration phase boundary。
