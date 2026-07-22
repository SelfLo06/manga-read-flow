# PhysicalBoundaryEvidence Contract

## Scope

本文冻结 M1 单页 Cleaning 在进入实现前所需的最小 Physical Boundary 合同。它是设计合同，不表示 producer、runtime Check、持久化表或 capability 已实现，也不表示 M1 gate 已通过。

Grouping 的 authoritative handoff、accepted/current 语义和 snapshot lifecycle 由 [FrozenGroupingEvidenceSnapshot Contract](../120-grouping/120-30-frozen-grouping-evidence.md) 冻结；本文只定义 Physical Boundary 如何消费该 exact snapshot。

Grouping 只拥有 text-group identity、membership、ordering、provenance、proposal evidence 和 unresolved relations；它不创建 BubbleInstance 或 physical container。Physical Boundary 拥有 physical instance candidates、bubble/panel/page-edge/contact/separator/unknown boundary evidence，并负责后续 physical binding。

当前真实仓库已有 Slice 1B immutable candidate persistence、Slice 1C GroupingCheckResult/正式 QualityIssue、Slice 1D immutable acceptance/current pointer，以及 Slice 1E immutable stale facts、`CLEAR_ON_STALE`、replacement/recovery 和正式 Physical Boundary Grouping-input selector/binding。Physical Boundary producer、revision、Check、acceptance 和 pointer 仍未实现。下文专属于 Physical Boundary 且带有 `proposed responsibility/name; not yet implemented` 的名称只表示允许的未来职责名称。

## Non-goals

- 不实现 Physical Boundary producer、boundary algorithm、Cleaner 或 Physical Boundary 数据库 migration。
- 不把 bbox、bbox union、ellipse、convex hull、矩形扩张、morphology contour 或 routed region 提升为权威 BubbleInstance。
- 不把实验 runner 当作产品入口，不扩大到 M2/M3 graph/domain redesign。

## Canonical Processing Path

```text
Immutable source image
+ FrozenGroupingEvidenceSnapshot
+ optional proposal evidence
→ Physical Boundary generation attempt

SUCCEEDED:
→ ArtifactService registers immutable candidate artifacts
→ create immutable PhysicalBoundaryEvidenceRevision
→ oracle-free PhysicalBoundaryCheck
→ immutable PhysicalBoundaryCheckResult + IssueDrafts
→ persist formal QualityIssues
→ WorkflowLoopEngine decision
→ UoW acceptance
→ active_physical_boundary_evidence_revision_id
→ VisualContractRevision binds exact accepted evidence revision
→ CleaningEligibility
→ existing Cleaning canonical path

ABSTAINED or FAILED:
→ persist attempt/result/evidence
→ do not create PhysicalBoundaryEvidenceRevision
→ WorkflowLoopEngine decides retry/fallback/review/block
```

现有下游必须保持：

```text
accepted VisualContractRevision
→ BubbleInstanceRevision
→ TextSegmentRevision
→ SegmentInstanceAssignment
→ CleaningEligibility
→ frozen pixel evidence artifacts
→ StageExecutor
→ Cleaner Provider
→ ArtifactService
→ Cleaning validation
→ QualityCheckService
→ WorkflowLoopEngine
→ UoW acceptance
→ active_cleaned_artifact_id
```

Physical Boundary 不得放入 Cleaner Provider、CleaningCheck、FullPageCleaningHarness 或 VisualContractRepository。

ArtifactService 只负责 artifact 生命周期：登记、路径、hash、media type、retention 和清理。它不接受结果、不决定 Workflow、不创建 QualityIssue，也不写 active pointer。Repository/DAO 独占 SQLite，UoW 定义接受事务。

## Authoritative Inputs

运行时 authoritative inputs 为：

- immutable source image artifact、`source_artifact_id`、source SHA-256；
- page coordinate space、完整页面尺寸和变换；
- accepted/current `FrozenGroupingEvidenceSnapshot`，以及它所 exact-bind 的 AcceptedDetectionEvidenceSet ID/hash 与 OCR result IDs/hashes；
- `ProcessingProfileSnapshot` 及 settings hash；
- producer name、version、implementation hash；
- 由 revision、artifact、配置和 producer identity 组成的 dependency fingerprint。

Detection/OCR bbox、text geometry、routed association、gradient、color、watershed 和 morphology 只能作为 optional proposal/supporting evidence，不能成为 direct authoritative input、重建 text groups，或单独成为 BubbleInstance、visible boundary、page truncation、panel boundary、contact separator 的 source of truth。

## FrozenGroupingEvidenceSnapshot

### Current fact

当前仓库已有正式 immutable `FrozenGroupingEvidenceSnapshot` candidate、canonical manifest/fingerprint、exact Detection/OCR/Profile/source/producer bindings、GroupingCheckResult、正式 QualityIssue、immutable Grouping acceptance fact 和 `page_grouping_state.active_grouping_snapshot_id`。candidate 与 CheckResult 本身均不构成 accepted/current；Slice 1D selector 会 exact-read pointer/acceptance/snapshot 并检查当前 dependency facts。实验 association/harness 结果仍是 run-local evidence，不能作为产品 source of truth。

### Implemented candidate contract

`FrozenGroupingEvidenceSnapshot` candidate persistence、accepted/current selection、stale propagation 与正式 Physical Boundary exact input selector/binding 已实现。selector 只准备 exact input，不代表 Physical Boundary product 已实现。

最低 metadata：

```text
snapshot_id
project_id
page_id
source_artifact_id
source_sha256
coordinate_space
detection_dependency_id
detection_dependency_hash
ocr_dependency_ids
ocr_dependency_hash
fragment_group_manifest_artifact_id
fragment_group_manifest_sha256
producer_version
profile_snapshot_id
dependency_fingerprint
created_at
```

manifest artifact 保存 fragment membership、text-group membership、fragment geometry、provenance 和 assignment 关系；SQLite 只保存 metadata、relations 和 hash，不保存大型 JSON/geometry payload。

任何 Detection evidence set、OCR revision、人工 Grouping edit、source hash、配置或 producer identity 变化都会通过 `CLEAR_ON_STALE` 使旧 Grouping pointer 清空。stale snapshot 不能生成或接受新的 Physical Boundary revision。

## Generation Outcome and PhysicalBoundaryEvidenceRevision

Physical Boundary generation attempt 的结果属于 WorkflowAttempt、stage result 或等价执行账本：

```text
SUCCEEDED | ABSTAINED | FAILED
```

- `SUCCEEDED`：producer 产生结构合法、可登记的 candidate artifacts；
- `ABSTAINED`：producer 根据证据主动不生成 candidate；
- `FAILED`：producer 异常或无法完成执行。

`ABSTAINED` 和 `FAILED` 不创建 `PhysicalBoundaryEvidenceRevision`。attempt/result/evidence 必须保留，WorkflowLoopEngine 决定 retry、fallback、review 或 block；不得伪造空 revision 或空 graph artifact。

`PhysicalBoundaryEvidenceRevision`：`proposed responsibility/name; not yet implemented`。

它只在存在真实、结构合法、可追踪的 candidate artifacts 时创建，是不可变 candidate revision，最低字段为：

```text
evidence_revision_id
project_id
page_id
source_artifact_id
source_sha256
coordinate_space
grouping_snapshot_id
grouping_snapshot_manifest_sha256
grouping_dependency_fingerprint
profile_snapshot_id
producer_name
producer_version
producer_hash
dependency_fingerprint
graph_artifact_id
graph_artifact_sha256
mask_manifest_artifact_id
mask_manifest_sha256
provenance_artifact_id
provenance_artifact_sha256
candidate_disposition
created_at
```

`candidate_disposition` 只能是 `PRODUCED` 或 `INCOMPLETE`。`INCOMPLETE` 仍必须有合法 graph、artifact 和 provenance，可由 runtime Check 产生 blocking IssueDraft。不得使用 `ABSTAINED`、`FAILED`、`ACCEPTED`、`BLOCKED`、`RETRY`、`FALLBACK` 或 `SKIP`；前两者属于 generation attempt，后五者属于 WorkflowDecision、QualityIssue 和 active pointer 语义。

## Evidence Graph Semantics

graph 必须分别表达 bubble interior candidate、visible bubble boundary、panel boundary、page truncation 及方向、contact region、inferred/virtual/latent separator、unknown/ambiguity、text-group-to-instance candidate relation 和 derived masks。

每项 evidence 标记：

```text
OBSERVED | INFERRED | VIRTUAL | UNKNOWN | DERIVED
```

derived mask 不是独立的物理真相；`UNKNOWN` 不得进入 authorized/safe-edit 区域；oracle 不得进入 graph、产品 provenance 或 producer input。

## Runtime PhysicalBoundaryCheck

`PhysicalBoundaryCheck`：`proposed responsibility/name; not yet implemented`。

输入：immutable evidence revision、source binding、frozen Grouping snapshot、ProcessingProfileSnapshot、candidate artifact manifest 和 dependency fingerprint。

`PhysicalBoundaryCheckResult`：`proposed responsibility/name; not yet implemented`，最低字段为：

```text
check_result_id
evidence_revision_id
check_name
check_version
input_fingerprint
metrics_json
evidence_artifact_id
evidence_artifact_sha256
completed_at
```

`PhysicalBoundaryCheckResult` 只保存 immutable check facts、metrics 和 evidence。runtime Check 的运行时返回值为 `PhysicalBoundaryCheckEvaluation`（`proposed responsibility/name; not yet implemented`，包含 `check_result` + `issue_drafts`）；`IssueDraft` 不写入 CheckResult row。

runtime Check 只能校验 source/artifact/hash、revision dependency、provenance、coordinate space、graph/mask 一致性、text-support/boundary 冲突、unknown 授权、impossible topology、page truncation、contact 和 separator 自洽性，并返回 `PhysicalBoundaryCheckEvaluation`。IssueDraft 经 UoW/QualityIssue persistence 保存为正式 QualityIssue；如需保存原始 findings，只能写入 immutable evidence/findings artifact，不能替代 QualityIssue lifecycle。

runtime Check 不得读取 oracle、计算 benchmark confusion matrix、接受 candidate、返回 accept/block recommendation、决定 retry/fallback/skip/block、更新 active pointer、创建 VisualContractRevision、调用 Cleaner 或修补 candidate。

```text
PhysicalBoundaryCheck → metrics/evidence/IssueDrafts
WorkflowLoopEngine → accept/retry/fallback/skip/block
```

## Experimental Benchmark Evaluator

`PhysicalBoundaryBenchmarkEvaluator`：`proposed responsibility/name; not yet implemented`，只能位于 `tools/experiments/150-cleaning/`，不得成为 runtime dependency。

它接收 frozen candidate artifacts/hash、frozen oracle manifest/hash、evaluator version 和 frozen config，输出 confusion matrix、precision/recall/IoU、bubble split/merge、text-group assignment、page truncation/direction、panel/bubble confusion、false-positive count 和实验 verdict。

Evaluator 不创建正式 QualityIssue，不接受 revision，不更新 active pointer，不创建 Visual Contract，不调用 Cleaner，不修改项目状态文档，也不自动授权 Stage B。controls verdict 属于实验/project decision，不等同于 runtime Check 结果。

## Persistence

`PhysicalBoundaryEvidenceRepository`：`proposed responsibility/name; not yet implemented`，只负责 SQLite metadata/relations/hash，不生成 evidence。

最小未来 metadata 表：

```text
physical_boundary_evidence_revisions
physical_boundary_check_results
page_physical_boundary_evidence_state
```

大型 graph、mask manifest 和 provenance 必须经 ArtifactService 注册为 immutable artifacts；本任务不创建 migration。

candidate revision 和 check result 都是 immutable rows。不得通过更新同一 revision row 实现 `candidate → checked → accepted` 可变状态机。页面状态建议为：

```text
page_physical_boundary_evidence_state
- project_id
- page_id
- active_physical_boundary_evidence_revision_id
- version or updated_at
```

## Active Pointer

candidate 永远不能直接成为 active。只有 WorkflowLoopEngine 形成 decision，并由同一 UoW acceptance transaction 原子写入 acceptance facts、QualityIssue lifecycle、WorkflowDecision 和 active pointer 时，pointer 才能前进。当前 `AcceptanceRepository` 已支持 Slice 1D 的 Grouping acceptance 与 `page_grouping_state` pointer；`active_physical_boundary_evidence_revision_id` 及其 UoW/repository extension 仍未实现。

Physical Boundary 不拥有或推导 Grouping current pointer。Slice 1E selector 已实现为正式 application boundary，只读取非空 `active_grouping_snapshot_id` 所选、accepted、not-stale、dependency/artifact-valid 且无 blocker 的 snapshot，并返回包含 acceptance/check/snapshot、manifest、source、Detection、exact OCR、Profile 和 producer/operation 的 immutable binding。pointer 已清空或 mismatch 时结构化 fail closed，不启动 producer，也不从 Detection/OCR 重建 groups。

## Workflow Acceptance

PhysicalBoundaryCheck 只产生 issues。WorkflowLoopEngine 依据 issue、attempt、retry budget 和依赖决定 `accept | retry | fallback | skip | block`。Workflow decision 和 QualityIssue 独立持久化；check 通过不等于自动接受。

accepted、blocked、stale 是由 immutable revision、check result、issues、decision 和 pointer 推导的概念结果，不写回 candidate disposition。

未解决的 blocking QualityIssue 时，WorkflowLoopEngine 不得接受该 revision；UoW 不得推进 `active_physical_boundary_evidence_revision_id`，Visual Contract preparation 也不得消费该 revision。Check 只生成 IssueDraft，不直接返回或执行 block。

## Visual Contract Binding

Visual Contract preparation 只能消费 active/accepted Physical Boundary revision，并保存 exact `evidence_revision_id` 及 dependency/hash binding。当前 `visual_contract_revisions` 只有 source artifact 和 `input_hash`，无法表达 exact Physical Boundary revision；未来最小 schema change 应增加该 binding，本任务不实现 migration。

`VisualContractRepository` 只验证和持久化 binding，不生成 Physical Boundary。CleaningEligibility 只能在 binding 成立后创建；Physical Boundary pointer 与 Visual Contract pointer 属于两个阶段。

## Staleness and Reuse

source artifact/hash、Grouping snapshot、Detection/OCR dependencies、ProcessingProfileSnapshot、producer version/hash、graph/mask/provenance hash 或相关人工 edit revision 变化时，旧 evidence stale。Grouping dependency 变化的同一 UoW stale transaction 必须清空 active Grouping pointer，并以 CAS 清空受影响的 `active_physical_boundary_evidence_revision_id` 及更下游 pointers；历史 evidence/acceptance/attempt 保留。事务冲突整体回滚；recovery 遇到 stale exact binding 时 fail closed 并执行 CAS repair，不得暴露旧 revision 为 current usable。stale evidence 不得复用、重新接受或用于创建新的 CleaningEligibility。

## Fail-closed Semantics

| Condition | Required result |
| --- | --- |
| Grouping snapshot missing/stale | blocking IssueDraft |
| source/candidate artifact missing | blocking IssueDraft |
| source/artifact hash mismatch | blocking IssueDraft |
| provenance incomplete | blocking IssueDraft |
| coordinate space inconsistent | blocking IssueDraft |
| unknown enters authorized/safe-edit region | blocking IssueDraft |
| text support crosses boundary | blocking IssueDraft |
| panel/bubble conflict | blocking IssueDraft |
| page truncation unresolved | blocking IssueDraft；recommended action: review |
| touching/contact separator unresolved | blocking IssueDraft；recommended action: review；不得自动 merge |
| unknown physical boundary affects authorization | blocking IssueDraft |
| separator resolved and graph internally consistent | no blocker for this condition |
| impossible graph topology | blocking IssueDraft |
| producer exception | failed attempt evidence；由 Workflow 决定下一步 |
| oracle benchmark passes but runtime provenance fails | 不接受 |
| no candidate | ABSTAINED/FAILED attempt；不创建 EvidenceRevision；由 Workflow 决定下一步 |

## Control-case Contract Walkthrough

### page_edge_bubble_001

合同必须表达：

```text
bubble interior candidate
+ visible bubble boundary
+ page_truncated:left
+ unknown outside page
```

页面边缘不能编码成闭合 visible contour。缺少 `page_truncated:left` 时，PhysicalBoundaryCheck 必须产生 blocking IssueDraft，recommended action 为 review；Check 不直接决定 block。未解决的 blocking issue 使 WorkflowLoopEngine 不得 accept，pointer 不得推进，Visual Contract 不得消费该 revision。benchmark evaluator 只能离线报告失败。

### black2_touching_bubbles_001

合同必须表达：

```text
two candidate instances
+ distinct text-group ownership
+ contact region
+ inferred/latent separator
+ unresolved state if separator evidence is insufficient
```

coarse connected region 不得自动导致 merge；separator 不足时 PhysicalBoundaryCheck 必须产生 blocking IssueDraft，recommended action 为 review。最终 retry、fallback、review 或 block 由 WorkflowLoopEngine 决定；在 issue 解决前不能 accept、推进 pointer 或创建可消费该 revision 的 Visual Contract。

## Validation Requirements

未来实现必须证明：

```text
FrozenGroupingEvidenceSnapshot
→ PhysicalBoundary producer
→ immutable candidate artifact/revision
→ oracle-free runtime Check
→ IssueDraft
→ Workflow/UoW acceptance
→ active_physical_boundary_evidence_revision_id
→ VisualContract preparation
→ CleaningEligibility
```

测试不得手工拼装最终 Visual Contract 绕过 producer、Check 和 acceptance；至少覆盖 missing/stale snapshot、hash mismatch、provenance、page-edge、touching bubbles、unknown authorization、重复执行和接受冲突。

## Forbidden Bypasses

- 新建平行 generator、shadow pipeline 或未经授权 fallback。
- 将实验 runner 当作产品入口。
- 从弱几何、morphology 或 routed region 生成权威 BubbleInstance。
- 从 required text support 反推物理容器。
- 在 VisualContractRepository、FullPageCleaningHarness、Cleaner Provider 或 CleaningCheck 中生成 Physical Boundary。
- 让 runtime Check 读取 oracle 或决定 Workflow。
- 建立第二套可变 stage 状态机。
- 让测试绕过正式入口手工构造最终 Visual Contract。
- 扩大到 M2/M3 graph/domain redesign。

## Open Questions

- `FrozenGroupingEvidenceSnapshot` candidate application 与 metadata repository、AcceptedDetectionEvidenceSet 和 exact OCR dependency binding 已实现；生产 Grouping producer 尚未实现。
- Grouping acceptance/current pointer 与 Slice 1E stale/reuse/recovery、Physical Boundary exact input selector 已实现；Physical Boundary product pipeline 仍属于后续工作。
- `page_physical_boundary_evidence_state` 的具体 schema 尚未实现；其 expected pointer/version CAS、Grouping stale 后原子清空和 recovery fail-closed 语义已经冻结。
- Visual Contract exact evidence binding 的列名和 stale propagation 需要 migration 设计。
- runtime Check structural thresholds 与 benchmark controls 的 project gate 仍需维护者冻结。
