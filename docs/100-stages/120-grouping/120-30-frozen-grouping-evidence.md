# FrozenGroupingEvidenceSnapshot Contract

## Scope

本文冻结 M1 单页 Grouping 到 Physical Boundary 的最小正式合同。它定义 snapshot 的 authoritative inputs、candidate/check/accept/current 语义、幂等、stale 和 exact downstream binding。

本文是设计合同。Slice 1A Detection dependency、Slice 1B snapshot candidate path、Slice 1C GroupingCheck/QualityIssue、Slice 1D Workflow/UoW acceptance/current selection，以及 Slice 1E stale/reuse/recovery 与 Physical Boundary exact input selector/binding 已实现。具体生产 Grouping producer、Physical Boundary 产品能力和 M1 capability 仍未实现。

## Non-goals

- 不实现具体生产 Grouping producer、自动 association 算法、BubbleInstance 最终领域模型或 Physical Boundary 产品能力。
- 不把 Detection/OCR bbox、bbox union、convex hull、最近距离、单阈值或实验 association 结果提升为权威 Grouping。
- 不实现 Physical Boundary、Cleaner、UI 或跨页语义。

## Current Repository Facts

当前仓库已有正式 `GroupingCandidateApplicationService`、纯 `GroupingProducer` port、canonical manifest/fingerprint、`project_grouping_candidate_v5` persistence，以及 Slice 1C 的 `CheckGroupingCandidateApplicationService`、oracle-free `GroupingCheck`、`project_grouping_check_v6` persistence 和正式 QualityIssue binding。Slice 1D 新增 `AcceptGroupingCandidateApplicationService`、`WorkflowLoopEngine.decide_grouping`、`AcceptanceRepository.accept_stage` Grouping branch、`project_grouping_acceptance_v7`、immutable acceptance/execution facts 和页面 current selector。没有默认或具体生产 Grouping producer，自动 post-OCR orchestration 未启用；实验 association/harness 仍只属于 run-local evidence。

Detection 的正式产品路径在成功的 Detection `AcceptanceCommand.accepted_text_blocks` 事务中插入或重新接受 `AcceptedTextBlock`，并原子创建 immutable `AcceptedDetectionEvidenceSet` metadata、exact member bindings 和独立 acceptance provenance。canonical manifest 经 ArtifactService 正式登记，Repository/UoW 按 exact `detection_dependency_id` 读取并校验 source、artifact/hash、membership 和 provenance；没有 Detection active pointer。`ContentStateRepository.create_text_block` 仍可为测试或基础设施直接创建 row，因此后续 Grouping 不得用“页面全部 `text_blocks`”重建 accepted membership。OCR 使用不可变 `ocr_results` 行、`version_number`、`ocr_result_id`、`geometry_hash`、`input_hash` 和 `text_blocks.active_ocr_result_id` 选择当前结果。

`000-10-architecture.md` 已区分阶段职责编号与 M1 runtime dependency order。当前产品代码没有 Grouping runtime stage；本文冻结的 final `FrozenGroupingEvidenceSnapshot` 只能在其 exact OCR dependencies 接受之后物化，阶段编号不要求它先于 OCR 执行。

`ProjectUnitOfWork` 已提供 candidate materialization、historical exact-read、Grouping check atomic commit 和正式 `accept_stage` facade；`GroupingSnapshotRepository` 只保存 immutable candidate、exact OCR dependencies 和 generation outcomes，`GroupingCheckRepository` 保存 immutable CheckResult、到正式 QualityIssue 的 relation 和每次 execution provenance。Slice 1D 沿现有 `AcceptanceRepository.accept_stage` / `ProjectUnitOfWork.accept_stage` 写入 WorkflowDecision、immutable acceptance/execution 和页面 pointer/version；candidate 与 CheckResult 行不被修改。

## Historical Read and Current Usability

Slice 1C 已分离两种职责：

```text
historical exact-read
→ 按 snapshot_id 读取 immutable candidate rows、stored OCR bindings 和 generation provenance
→ 不要求 stored OCR 仍是 active/current

current usability evaluation
→ 调用方显式指定当前适用 Detection evidence set 与 ProcessingProfileSnapshot
→ application selector 读取 stored member IDs 对应的 exact active OCR
→ 比较 source、Detection、OCR、Profile、producer/operation compatibility
→ mismatch 进入 GroupingCheck input fingerprint 并生成 blocking IssueDraft
```

历史 candidate、manifest identity 和 stored bindings 不因 current drift 被修改或隐藏。Slice 1E append immutable stale/supersession facts 并以 pointer/version CAS 执行 `CLEAR_ON_STALE`，不修改历史 candidate，也不自动 materialize replacement candidate。

当前 stale 处理并不全局统一：OCR/Translation reuse 通过 exact upstream IDs/hashes 拒绝旧结果，Visual Contract 拒绝重新激活 stale revision，而 FullPageCleaning 已实现 `mark_cleaning_facts_stale_and_clear_active_pointer_atomically`，以 expected pointer CAS 原子标记 stale 并清空 `active_cleaned_artifact_id`。总体架构把 active pointer 定义为当前有效结果，因此本文按默认规则选择 `CLEAR_ON_STALE`，不沿用隐式 retain-and-validate 作为 Grouping current 语义。

## Canonical Processing Path

```text
accepted Detection evidence-set identity/hash
+ accepted OCR evidence
+ immutable source image
+ ProcessingProfileSnapshot
→ Grouping generation attempt
→ immutable fragment/group manifest artifact
→ FrozenGroupingEvidenceSnapshot candidate
→ Grouping structural/quality Check
→ IssueDrafts
→ WorkflowLoopEngine decision
→ UoW acceptance
→ accepted/current Grouping snapshot selection
→ Physical Boundary attempt binds exact snapshot ID/hash/fingerprint
```

## Runtime Ordering and Responsibility Boundary

M1 runtime dependency order 冻结为：

```text
Import
→ Detection acceptance
→ OCR acceptance
→ final FrozenGroupingEvidenceSnapshot materialization
→ Physical Boundary
→ Translation / Cleaning downstream according to their dependencies
```

`120 Grouping` 与 `130 OCR` 的编号表示职责和文档归属，不强制 runtime 顺序。Detection 后、OCR 前可以产生 routing、association 或 pre-grouping proposal，但它不能创建 final snapshot、acceptance fact 或 `active_grouping_snapshot_id`；proposal 与 final snapshot 不一致时，以 final accepted/current snapshot 为唯一 authoritative Grouping。

Grouping 只表达 fragments、text groups、membership、M1 ordering、membership provenance、proposal/supporting evidence 和 unresolved relations。它不创建 BubbleInstance，不表达 bubble interior、visible bubble boundary、panel/page-edge/contact/separator、safe-edit、CleaningEligibility 或最终 physical layout slot。Physical Boundary 才从 exact accepted/current Grouping snapshot、immutable page image 和 optional proposals 产生 physical instance candidates 与 boundary/unknown evidence；它不得从 bbox/OCR 重建 group membership。

失败路径：

```text
Grouping attempt
→ ABSTAINED or FAILED
→ persist attempt/result/evidence
→ no accepted/current snapshot
→ WorkflowLoopEngine decides retry/fallback/skip/block
```

人工修改路径：

```text
accepted snapshot
→ human changes fragment/group membership
→ new immutable snapshot revision
→ Check → Workflow decision → UoW acceptance
→ page current pointer moves to new snapshot
→ dependent Physical Boundary and later stages become stale
```

## Authoritative Inputs

每个 candidate 必须绑定以下输入；大型内容通过 ArtifactService 保存，SQLite 只保存 metadata、relations 和 hash：

```text
project_id
page_id
source_artifact_id
source_sha256
coordinate_space

accepted_detection_dependency_id
accepted_detection_dependency_hash
accepted_ocr_dependency_ids
accepted_ocr_dependency_hash

profile_snapshot_id
grouping_producer_name
grouping_producer_version
grouping_producer_hash
grouping_operation_semantics_version
dependency_fingerprint
```

`accepted_detection_dependency_id` 必须引用下述 immutable `AcceptedDetectionEvidenceSet`，不能引用临时查询、单个 row、文件路径、时间戳或实验 run。

### AcceptedDetectionEvidenceSet

`AcceptedDetectionEvidenceSet` 已由 Slice 1A 按 Persistence `Option 2` 实现：Detection 接受事务在提交 exact accepted members、WorkflowDecision 和 attempt facts 的同一 UoW 中写入 `accepted_detection_evidence_sets`、`accepted_detection_evidence_members` 和 `detection_evidence_acceptance_provenance`；不新增 Detection active pointer。历史 Detection rows 不做推测性 backfill，必须经正式 Detection acceptance/replay 才能形成该依赖。

最低 metadata：

```text
detection_dependency_id
project_id
page_id
source_artifact_id
source_sha256
coordinate_space
canonical_member_count
canonical_manifest_sha256
schema_version
created_at
```

accepted membership 只能来自同一个成功 Detection acceptance transaction 中的 exact `AcceptanceCommand.accepted_text_blocks`。提交后对应 `text_blocks` 必须为 `detection_status = done`，并具有 non-null geometry/hash 和 provider provenance；candidate、rejected、stale、直接 `create_text_block` helper row，以及没有该 evidence-set acceptance binding 的 row 都不是成员。Grouping repository 不得在事后查询页面全部 `text_blocks` 来猜测 membership。

canonical semantic manifest 使用版本 `accepted-detection-evidence-set.v1`，顶层绑定 schema version、project/page、source artifact ID/hash、coordinate space、影响 Detection 结果的 configuration identity，以及稳定的 provider/tool implementation provenance；set-level implementation binding 统一适用于全部 members。每个 member 至少包含：

```text
text_block_id
project_id
page_id
reading_order
bbox
polygon
geometry_hash
coordinate_space
detection_provider
detection_confidence
detection_status
```

member 按 `(project_id, page_id, text_block_id)` 的持久化 UTF-8 byte sequence 升序排列；数据库返回顺序、row insertion order 和 reading order 不决定 canonical ordering，重复 stable identity 是合同错误。canonical serialization 为 schema-versioned UTF-8 JSON：object key 按 UTF-8 byte sequence 升序、member array 使用上述顺序、无多余空白、只接受有限 JSON number 并使用最短 round-trip decimal；时间戳、文件路径、mtime 和数据库 row order 不进入 semantic bytes。

semantic bytes 明确排除 WorkflowAttempt ID、WorkflowDecision ID、acceptance record/transaction ID、accepted/created timestamp、provider execution reference、临时 run ID、文件路径、mtime 和数据库 insertion order；这些 execution/acceptance provenance 不改变 Detection evidence 内容。

`canonical_manifest_sha256 = SHA-256(canonical UTF-8 bytes)`；`detection_dependency_hash` 等于该值，`detection_dependency_id = detection-set-v1:<canonical_manifest_sha256>`。相同 accepted members、source binding、stable provider/tool implementation 和 configuration 必须得到相同 ID/hash；member、geometry、reading order、stable provider/tool implementation、Detection configuration、source binding 或 coordinate space 变化必须改变 hash。相同 semantic evidence 即使由不同 retry/replay attempt、decision 或 acceptance timestamp 接受，也复用相同 dependency ID/hash。record 可经 ArtifactService 保存 canonical manifest，但 metadata record 与 acceptance binding 才是正式 identity，临时 JSON 文件本身不是 source of truth。

execution/acceptance provenance 通过独立 immutable record 保存，至少包含 `workflow_attempt_id`、`workflow_decision_id`、acceptance identity、`accepted_at`，以及与 stable implementation identity 不同的 provider execution reference。一次 semantic set 可以关联多个 provenance records；不得更新 semantic evidence-set row 覆盖历史 provenance。

OCR 输入必须引用 exact active `ocr_result_id` 集合及对应 text/geometry hashes。manifest 包含 text-group identity、membership provenance 和 M1 ordering metadata，因此 OCR 只有文本变化而 geometry 不变时也会使依赖该结果的 Grouping snapshot stale。

Detection/OCR bbox、routed association、bbox union、convex hull、距离规则和其他几何计算只能作为 manifest 中的 proposal/supporting evidence；它们不能自动成为 text-group membership、container、BubbleInstance 或 Physical Boundary source of truth。Physical Boundary 不得从这些弱输入重新构造 Grouping。

## Snapshot and Manifest Contract

`FrozenGroupingEvidenceSnapshot` candidate metadata 与 exact OCR dependency bindings 已由 Slice 1B 实现；Slice 1C 已实现 CheckResult 与 QualityIssue；Slice 1D 已实现独立 immutable acceptance fact 和 `page_grouping_state` current selection。candidate 与 CheckResult 本身仍不等于 accepted/current。

最低 immutable metadata：

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
manifest_artifact_id
manifest_artifact_sha256
profile_snapshot_id
producer_name
producer_version
producer_hash
operation_semantics_version
dependency_fingerprint
candidate_disposition
created_at
```

人工 revision 还必须保留 `parent_snapshot_id` 和 edit provenance；这些字段属于 immutable metadata/provenance，不是可变状态。

`coordinate_space` 必须绑定 source pixel dimensions、origin 和必要 transform。`candidate_disposition` 只能是 `PRODUCED` 或 `INCOMPLETE`；它不能写入 `ACCEPTED`、`STALE`、`RETRY` 或 `BLOCKED`，这些语义分别属于 acceptance/current facts、dependency evaluation、WorkflowDecision 和 QualityIssue。

manifest artifact 至少表达：

- fragment identities、geometry references 和 provenance；
- text-group identities、fragment-to-group membership；
- M1 所需的 group ordering metadata；
- proposal/supporting evidence references；
- unresolved 或 abstained relations。

snapshot、manifest 和 provenance 均不可变。修改 membership、geometry interpretation 或人工 assignment 必须创建新 snapshot revision；旧 snapshot 不覆盖、不删除。

snapshot 不直接表达 Physical Boundary，不直接创建 BubbleInstance，也不静默强制归组。无法安全归组的关系必须显式标记为 unresolved，并由 Check 产生对应 IssueDraft。

## Generation Outcome

Grouping generation attempt 属于 WorkflowAttempt、stage result 或等价执行账本，结果为：

```text
SUCCEEDED | ABSTAINED | FAILED
```

- `SUCCEEDED`：生成可登记、结构合法且 provenance 完整的 candidate manifest。
- `ABSTAINED`：证据不足，主动不生成 candidate。
- `FAILED`：执行异常或无法完成。

`ABSTAINED` 和 `FAILED` 必须保留 attempt/result/evidence，但不创建 `FrozenGroupingEvidenceSnapshot` row，也不创建 accepted/current snapshot。结构不完整但 manifest 合法的 candidate 可以创建 snapshot candidate，并通过 blocking IssueDraft 表达不完整性；不能伪造空 snapshot。

## Runtime Grouping Check

`GroupingCheck` 已由 Slice 1C 实现，并通过现有 `QualityCheckService.check_grouping` 承载。它只消费 application use case 构造的 immutable candidate、manifest integrity evidence 与 current-usability facts，返回 `GroupingCheckEvaluation(check_result, findings, issue_drafts)`；不访问 Repository 或 ArtifactService，也不承担 Workflow 决策。

runtime Check 至少校验：

- source/project/page binding、artifact/hash 和 coordinate space；
- Detection/OCR dependency identity、hash 和 stale 状态；
- manifest schema、fragment identity 完整性和 membership 引用有效性；
- 不兼容的重复 membership；
- provenance、producer/profile identity 和 dependency fingerprint；
- unresolved relation 是否显式表达；
- snapshot 是否包含 Physical Boundary 伪事实。

immutable `GroupingCheckResult` 已保存 `check_result_id`、project/page/snapshot binding、check name/version、input fingerprint、candidate manifest/dependency hashes、结构化 metrics、finding codes、`grouping-check-evidence.v1` artifact ID/hash 和 `completed_at`。`input_fingerprint` 覆盖 candidate identity、check name/version、manifest integrity、current source/Detection/OCR/Profile identities、producer/operation compatibility 和 runtime config hash，不覆盖 result ID、completed time、DB order 或临时路径。

IssueDraft 经现有 `IssueLifecycleChange` 路径写入 `quality_issues`，`root_stage = grouping`，并通过 `applies_to_result_id` 与 immutable `grouping_check_result_issues` relation 绑定 CheckResult。重复 exact Check 复用 CheckResult、evidence artifact 和 dedupe-identical QualityIssue，同时在 `grouping_check_executions` 追加 execution provenance。CheckResult、issue relation 和 execution 表均由 immutable triggers 保护；QualityIssue 后续仍使用既有 lifecycle 解决或接受 warning。

Check 只输出 immutable check facts、metrics、evidence 和 IssueDrafts。它不得调用 producer、修改 snapshot、升级 proposal、生成 Physical Boundary、读取 benchmark oracle、接受 candidate、更新 current pointer 或决定 retry/fallback/skip/block。

算法质量阈值若需实验验证，必须由 offline evaluator 单独处理，不得混入 runtime structural Check。

## QualityIssue and Workflow Decision

IssueDraft 经正式 QualityIssue persistence 保存；`QualityCheckService` 负责检测和 root-stage attribution，`WorkflowLoopEngine` 独占：

```text
accept | retry | fallback | skip | block
```

Check 通过不等于自动接受。unresolved blocking QualityIssue 时，WorkflowLoopEngine 不得 accept，current pointer 不得推进。

## Acceptance Transaction

Grouping 接受必须复用现有 `ProjectUnitOfWork.accept_stage` / `AcceptanceRepository.accept_stage` 扩展点。最小原子事务包含：

```text
Grouping Check completed
+ IssueDrafts persisted as QualityIssues
+ WorkflowDecision persisted
+ accepted snapshot fact persisted
+ page current-selection fact persisted
+ attempt terminal status and task/stage progress persisted
```

accepted fact 已由独立 immutable `grouping_snapshot_acceptances` 表达，关联 snapshot、CheckResult、WorkflowDecision、attempt/execution、accepted manifest/fingerprint 和 accepted time；`grouping_acceptance_executions` 保留首次接受与 exact replay provenance。candidate row 不进入 `accepted` 状态机。

candidate artifact 可以先经 ArtifactService 登记；artifact 存在不等于 accepted。crash 后只有 artifact、candidate 或 attempt 而没有完整 acceptance transaction 时，不得自动提升为 accepted/current。

并发接受必须复用现有 expected-state/pointer CAS 语义；冲突返回 reload/retry 结果，不覆盖其他 revision。

## Current Selection and Stale Policy: OPTION_A + CLEAR_ON_STALE

采用页面级 Grouping active pointer，作为唯一 current-selection 机制：

```text
page_grouping_state
- project_id
- page_id
- active_grouping_snapshot_id
- version
- updated_at
```

`page_grouping_state`、`active_grouping_snapshot_id` 和 pointer `version` 已由 Slice 1D 实现，并由 `AcceptanceRepository.accept_stage` / `ProjectUnitOfWork.accept_stage` 在 Grouping 接受事务中维护。candidate、accepted 和 current 仍是不同事实：candidate 由 producer 产生，accepted 由 Check + QualityIssue + WorkflowDecision + UoW transaction 形成，current 由页面 pointer 唯一选择。

pointer 只允许引用已存在且未 stale 的 accepted fact；`active pointer = current usable accepted snapshot`。接受、替换和清空事务必须同时 CAS expected `active_grouping_snapshot_id` 与 `page_grouping_state.version`，成功后递增 version。不得同时维护第二套 `is_active`、accepted flag、retain-and-validate selector 或文件级 current 规则。UI、recovery 和后续 stage 只把该页面 pointer 当 current selection；dependency validation 是 fail-closed integrity guard，不会把另一个 snapshot 提升为隐式 current。

Slice 1D 实现首次建立 pointer、已有 NULL state 的 CAS 和 exact replay；Slice 1E 已实现不同 snapshot replacement 的旧 acceptance superseded fact 与 A→B pointer CAS。仓库当前不存在真实 exact-bound Physical Boundary state，因此没有需同步清空的下游 pointer，也没有为未来阶段创建影子状态表。

## Idempotency and Reuse

Grouping operation 的幂等 key 至少覆盖：

```text
source_sha256
detection_dependency_id/hash
ocr_dependency_ids/hash
profile_snapshot_id/settings_hash
grouping_producer_name/version/hash
operation_semantics_version
human_edit_revision, if present
```

完全相同依赖可以复用 existing immutable snapshot。复用仍须产生可解释的 attempt/decision 证据；不得以 manifest 文件存在性判断成功。artifact/hash 不一致或 snapshot stale 时不得复用为当前输入，也不得重新接受旧 snapshot。

## Staleness

以下变化必须使 Grouping snapshot stale：

```text
new accepted Detection dependency
→ append Grouping stale/supersession fact
→ clear active_grouping_snapshot_id with pointer/version CAS
→ Physical Boundary / Visual Contract / Cleaning / Typesetting / Export stale

new accepted OCR text or geometry dependency
→ append Grouping stale/supersession fact
→ clear active_grouping_snapshot_id with pointer/version CAS
→ downstream stale

accepted human Grouping snapshot revision
→ atomically switch active_grouping_snapshot_id to the new accepted snapshot
→ previous Physical Boundary exact binding stale
→ clear affected downstream active pointers
→ Visual Contract / Cleaning / Typesetting / Export stale
```

采用唯一 `CLEAR_ON_STALE` 裁决。接受新的 Detection evidence set、OCR revision、适用 profile revision 或其他 Grouping authoritative dependency 的应用/UoW 路径负责触发 stale；上游 acceptance、immutable stale/supersession fact、Grouping pointer 清空、受影响下游 stale facts/pointer 清空必须在同一语义事务中提交。历史 snapshot、check、acceptance、attempt 和 artifact 不修改、不删除。

事务以当前 upstream expected revision、expected `active_grouping_snapshot_id`、`page_grouping_state.version` 以及受影响下游 expected pointer/version 做 CAS。任一冲突或数据库失败时整体回滚并返回 reload/retry，不允许已接受新 OCR 但仍把旧 Grouping 暴露为 current usable。

恢复从已提交 upstream acceptance、stale facts 和 pointers 开始。若旧版本或中断实现遗留“pointer 存在但 dependency mismatch”，recovery 与 Physical Boundary input selector 必须 fail closed，不返回该 snapshot、不启动新 attempt，并通过同一 CAS stale-repair transaction 追加 stale fact 和清空 pointer；修复失败继续 reload/block，不采用 `RETAIN_AND_VALIDATE`。

Translation-only stale 规则不在本合同范围内。

## Human Grouping Edit

人工 review/edit 不修改既有 snapshot。它读取 accepted/current snapshot，创建新的 immutable manifest 和 snapshot revision，保留 `parent_snapshot_id`、editor/action provenance、new dependency fingerprint，然后重新经过 Check、QualityIssue、WorkflowDecision 和 UoW acceptance。

旧 snapshot 及其历史 Physical Boundary attempt 保留。新 revision 接受事务以旧 Grouping pointer/version 做 CAS，原子写入新 acceptance、切换 pointer、追加旧 dependency supersession/stale facts，并清空受影响的 Physical Boundary、Visual Contract、Cleaning、Typesetting 和 Export current pointers；事务失败时旧 current 与全部下游保持原状。

## Physical Boundary Exact Binding

每个 Physical Boundary generation attempt、candidate revision 和 provenance 必须保存：

```text
grouping_snapshot_id
grouping_snapshot_manifest_sha256
grouping_dependency_fingerprint
```

Physical Boundary 只能消费非空 `active_grouping_snapshot_id` 所选、accepted 且 dependency-valid 的 exact revision。pointer 已清空、snapshot stale 或 dependency mismatch 时必须产生 blocking input failure，不得启动 producer。它不能读取页面“当前文件”、只记录 group IDs、在恢复时重新解析另一个 snapshot，或从 Detection/OCR 弱证据重建 Grouping。

页面 current pointer 后续变化不改变历史 attempt 的输入；新的 attempt 必须重新绑定新的 snapshot。下游 Visual Contract 也必须保存 exact Physical Boundary revision binding。

## Failure and Recovery

| Condition | Required result |
| --- | --- |
| source artifact missing/hash mismatch | blocking IssueDraft |
| Detection/OCR dependency missing or stale | blocking IssueDraft |
| accepted Detection set cannot be uniquely identified | STOP_DESIGN_GAP before implementation |
| Detection canonical manifest/hash mismatch | blocking IssueDraft |
| active pointer target stale or dependency-mismatched | clear/repair pointer; not usable by Physical Boundary |
| upstream accepted but stale transaction incomplete | recovery fail-closes and repairs; old Grouping is not current usable |
| pre-OCR proposal exists | supporting evidence only |
| proposal differs from final snapshot | final accepted/current snapshot is authoritative |
| Grouping manifest contains physical boundary facts | blocking contract violation |
| Physical Boundary reconstructs groups from bbox/OCR | forbidden bypass |
| manifest missing/hash mismatch | blocking IssueDraft |
| invalid fragment identity or membership | blocking IssueDraft |
| incompatible duplicate membership | blocking IssueDraft |
| incomplete provenance or coordinate space | blocking IssueDraft |
| unresolved relation | explicit unresolved evidence plus blocking/review IssueDraft |
| producer abstains | no accepted/current snapshot |
| producer fails | failed attempt; no accepted/current snapshot |
| unresolved blocking issue | Workflow cannot accept |
| current-selection CAS conflict | UoW returns conflict/reload result |

恢复从已提交的 upstream acceptance、attempt、snapshot/check facts、QualityIssue、WorkflowDecision、stale facts 和 page pointer 开始。孤儿 artifact 不得自动成为 current；由正式 recovery/retention 规则处理。

## Future Implementation Slices

| Slice | 正式入口 | Source of truth | Allowed extension point | 直接下游 | 最低集成证据 |
| --- | --- | --- | --- | --- | --- |
| A. Detection evidence-set + Grouping manifest serialization | Detection acceptance → Grouping application use case | immutable AcceptedDetectionEvidenceSet + text-group manifest | Slice 1A Detection set 与 Slice 1B Grouping canonical serializer/application entry 已实现 | snapshot metadata repository、GroupingCheck | exact accepted members 和 OCR results 得到 canonical ID/hash；不得查询全部 text_blocks |
| B. Snapshot metadata repository | `ProjectUnitOfWork` | Detection set、immutable candidate metadata、exact OCR bindings | Slice 1B Repository/UoW schema、Slice 1C historical-read separation 与 Slice 1D immutable acceptance metadata 已实现 | Check、acceptance、recovery | immutable insert、project isolation、duplicate replay、artifact/hash 对账；OCR drift 后仍可历史读取 |
| C. Runtime structural Check + QualityIssue | `CheckGroupingCandidateApplicationService` → `QualityCheckService.check_grouping` | immutable `GroupingCheckResult` + existing QualityIssue lifecycle | Slice 1C IssueDraft/QualityCheck/UoW extension 已实现 | Slice 1D acceptance application | source/hash、membership、provenance、unresolved 和 current dependency drift；原子 CheckResult/Issue/execution；无自动 acceptance |
| D. Workflow/UoW acceptance + current selection | `AcceptGroupingCandidateApplicationService` → `WorkflowLoopEngine.decide_grouping` → UoW | WorkflowDecision + immutable acceptance fact + `page_grouping_state` | Slice 1D `AcceptanceRepository.accept_stage` Grouping branch 已实现 | Physical Boundary input selector | blocker 禁止接受；事务中断无 pointer；pointer CAS 冲突可重载；replacement fail closed |
| E. Stale/reuse/idempotency | upstream acceptance + workflow reuse/recovery path | dependency fingerprint + exact dependency identities + stale facts | existing CAS/UoW stale patterns | Physical Boundary、Visual Contract | `CLEAR_ON_STALE` 原子清空；相同依赖复用；Detection/OCR/edit 变化使下游 stale |
| F. Physical Boundary exact binding | Physical Boundary application use case | attempt/revision provenance 中的 snapshot ID、manifest hash、fingerprint | Physical Boundary repository/UoW contract | Visual Contract preparation | current pointer 后变不改历史输入；stale/mismatch 阻止新 attempt |
| G. Formal application-entry integration test | 产品 Grouping 应用入口 | UoW 选出的 accepted/current snapshot | 正式 orchestration 测试入口 | Physical Boundary attempt | 从 accepted Detection/OCR 到 exact binding 的真实调用链；不得只测 helper |

## Migration and Rollback

Slice 1A migration 已新增 immutable AcceptedDetectionEvidenceSet metadata/member binding/provenance；Slice 1B migration 已新增 immutable Grouping candidate metadata、exact OCR bindings 与 generation outcome provenance；Slice 1C `project_grouping_check_v6` 已新增 immutable CheckResult/Issue relations/executions。Slice 1D `project_grouping_acceptance_v7` 新增 acceptance/current selection；Slice 1E `project_grouping_stale_v8` 新增 immutable `grouping_snapshot_stale_facts`，旧项目升级不回填推测性 stale facts，也不新增 Physical Boundary 状态表。

实现回滚时停止新的 Grouping application entry 和 pointer 写入，保留已登记 metadata、artifacts、attempts 和 decisions 供恢复/审计；不得删除受保护数据或把旧实验输出提升为替代 source of truth。schema 迁移和回滚验证至少覆盖空 pointer、重复 migration、旧项目打开、CAS 冲突、孤儿 artifact 和 downgrade 后不误接受。

## Forbidden Bypasses

- 新建平行 generator、shadow pipeline 或未经授权 fallback。
- 将 routed-association runner、benchmark 或 debug artifact 产品化。
- 从 bbox union、最近距离、convex hull 或单 case 启发式生成权威 group。
- 让 ArtifactService 接受 snapshot、创建 QualityIssue 或更新 current pointer。
- 让 Grouping Check 决定 Workflow 或更新 pointer。
- 创建第二套 active/current 机制。
- 修改历史 snapshot 或通过文件存在性判断 accepted。
- 在测试中手工拼装产品不会产生的 accepted snapshot。
- 把 Physical Boundary 回填为 Grouping source of truth。

## Open Questions

- Grouping stale/supersession facts、Detection/OCR acceptance 原子 pointer clearing、recovery repair、replacement 与 Physical Boundary exact selector/binding 已由 Slice 1E 实现；Profile/source mutation path 当前不存在，因此未接入推测性触发器。
- Visual Contract 对 exact Physical Boundary revision 的 schema migration 仍属后续设计。
- schema/check/operation version 的具体命名可在对应实现 slice 中确定，但不得改变本文冻结的职责和 source-of-truth 语义。

## Status

```text
Grouping snapshot contract: ACCEPTED
Grouping/Physical Boundary responsibility boundary: ACCEPTED
Detection dependency identity contract: ACCEPTED
Detection formal handoff Slice 1A: IMPLEMENTED
Grouping stale/current-selection semantics: ACCEPTED
Runtime dependency order: ACCEPTED
Ready for implementation planning: YES
Ready for implementation: YES, subject to implementation Preflight
Grouping product implementation overall: PARTIAL
FrozenGroupingEvidenceSnapshot candidate path: IMPLEMENTED
GroupingCheck / QualityIssue Slice 1C: IMPLEMENTED
Workflow acceptance / active pointer Slice 1D: IMPLEMENTED
Stale / reuse / exact Physical Boundary binding Slice 1E: IMPLEMENTED
Grouping algorithm capability: NOT VALIDATED
Production Grouping algorithm: NOT IMPLEMENTED / NOT VALIDATED
Physical Boundary: NOT IMPLEMENTED
M1 closed: NO
```
