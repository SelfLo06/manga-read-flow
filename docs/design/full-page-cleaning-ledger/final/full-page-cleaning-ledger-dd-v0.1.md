# 整页清字台账／持久化／验收事务详细设计 v0.1

## 1. 目的、范围与阻塞项

本设计为 MVP-1 Full-page Cleaning Closure 建立可恢复的持久化合同。当前 `SinglePageCleaningService` 仅允许恰好一个 E1，page-level result 无法表达全页 inventory、逐 segment disposition、成员组合、页验证或 durable correction budget；`page_scope_complete` 只是调用方布尔值。因此当前局部 Slice E/F 不能升级为整页 acceptance。

本设计只覆盖单页 Cleaning ledger/persistence/acceptance。它不实现 Cleaner、BubbleInstance 算法、Typesetting、OCR/Translation、API/UI、Batch 或双页 Closure。

## 2. 来源与冻结事实

权威输入：`AGENTS.md`、SRS、HLD、PROJECT-PLAN、Data Model/Workflow State/Execution Contract/Persistence Readiness/MVP-1 Visual Contract final、Spike B/C/D/E/F REPORT/GATE 与 case-71/Slice F FORM。若历史文本中 g002/s02 unsafe 数量为 6，与 hash-lock artifact 冲突；本设计采用 Slice F 的实际 23。

- case-71：6 segment；g002/s01、g002/s02 已有局部 PASS/新 revision evidence，其他四个没有完整 ledger，必须 `MISSING_REQUIRED_EVIDENCE`，不能伪造 E1。
- case-72：g002 unsafe=710，g004 unsafe=70，g003 review/E3；g005/g007/s01/g007/s02 无完整 ledger。所有目标仍须逐项可解释。
- Slice E/F 已证明 Provider candidate、ArtifactService promotion、Repository/UoW、QCS draft、decision transaction、原图不覆盖和局部 correction 的边界；这些结论不被本设计削弱。

## 3. 术语与模型

`PageCleaningRun` 是一次 page + frozen visual contract + source hash + profile/config 的完整清字尝试聚合，**不是** WorkflowAttempt，也不是旧 `cleaning_result_records`。它拥有 immutable inventory、result/disposition/candidate/validation/reservation 的关系及生命周期 `planned → inventory_frozen → executing → validating → candidate_ready → accepted|blocked|stale|abandoned_after_crash`。

`CleaningInventoryItem` 是 frozen visual revision 内每个 active TextSegmentRevision 的唯一输入条目；保存 assignment/instance、target class、eligibility、support policy、fingerprint 与证据。`SegmentCleaningDisposition` 是独立 immutable ledger row，而非 inventory 字段；一项仅一条 current final，通过 supersession 替换旧结论。

`InstanceCleaningResult` 是一个 BubbleInstance revision 的 provider candidate、正式 artifact、actual write 和独立 validator observation。`CombinedCleaningCandidate` 从同一 original 确定性重放 accepted members；一个 run 可有 0..N immutable candidate/validation revisions，但至多一个 accepted candidate。未通过的 candidate 仍可 official-but-unselected。

## 4. 输入清单、处置结论与支持范围

冻结 inventory 的短 UoW 从 active visual contract 创建所有 segment 条目，之后不可增删。每个终态 item 恰有一个 current final disposition：

```text
CLEANED_PASS
BLOCKED_UNSAFE_REQUIRED / BLOCKED_RESIDUE / BLOCKED_PROTECTED_CONFLICT
BLOCKED_BOUNDARY_DAMAGE / BLOCKED_INSTANCE_OVERLAP / BLOCKED_WRONG_INSTANCE_WRITE
INCOMPLETE_REVIEW
UNSUPPORTED_E2 / UNSUPPORTED_E3 / UNSUPPORTED_FREE_TEXT / UNSUPPORTED_SFX
EXCLUDED_NON_TEXT / MISSING_REQUIRED_EVIDENCE / CONTRACT_INVALID
```

disposition 由 WorkflowLoopEngine 决策、Repository 以命名操作保存；其 row 保存 reason、root stage、blocking-at-decision、policy/fingerprint、evidence 与 issue/result/member refs。普通对白/旁白的 missing、E2/E3 或 unsafe 默认 blocking；只有 profile 明示范围外、source preserved 且 evidence 完整的 SFX/free text/non-text 可见且非阻塞。TextBlock cleaning status 只是 ledger 投影，不能反推 ledger。

`CLEANED_PASS` 只有同时指向 fresh validated result、accepted combined member 和完整 instance evidence 时才合法；不得仅因 provider 成功或 artifact 已登记而成立。

## 5. 逐实例证据与组合证据

每个 result 绑定 stable/revision instance、覆盖的 inventory targets、source hash、visual dependency fingerprint、provider attempt/config/profile。它引用 candidate、actual-changed、required support、safe edit、protected、uncertainty、visible support、residue、boundary damage、background difference 与 validator evidence artifacts，并保存可查询的像素计数、overlap、residue 和判定摘要。

组合规则固定：每个 member 均基于同一 original；从 original 复制各自 `ActualChangedPixelMask` 内的像素，不在前一 candidate 上串行 inpaint。canonical member key 只用于确定性重放，不以 mtime/目录决定。页验证重新计算：inventory completeness、unique disposition、member-to-target missing/duplicate、pairwise actual overlap、wrong-instance write、outside-safe/protected/uncertainty/boundary/residue、combined delta=member union、source/combined hash 与全部 fingerprint freshness。任何一项失败拒绝 acceptance。

## 6. 修正、问题、过期与恢复

一次自动 correction 的预算属于 immutable `CorrectionChain`（page + affected target scope + source/target fingerprint + policy/config），不是 page counter 或 per-issue 计数。WorkflowLoopEngine 在外部调用前以短 UoW `reserve_or_replay_correction` 保存 ordinal=1、idempotency key、reserved attempt/decision、budget_after=0；同 key 返回同 reservation，新的同-chain key 被 `reject_second_automatic_correction`。状态统一为 `reserved/executing/completed/abandoned_after_crash/rejected_second/stale`。Validator/Provider 不消费预算。

QualityCheckService 只返回 drafts；WorkflowLoopEngine 在 decision/acceptance UoW 保存 issue lifecycle `open → corrected → resolved`，或 `superseded/stale/reopened/accepted_warning`。专用关系表连接 issue 与 run、inventory、result、candidate、validation、reservation、decision，不能把 ids 塞入 JSON。旧 g002/s02 unsafe issue 保留历史，通过 relation 记录 corrected/resolved 或 superseded。

任何 source hash、visual/instance revision、shared-boundary 邻居、mask/config/profile dependency 或 artifact integrity 变化都会使相关 result、disposition、candidate、validation stale。guarded stale/repair UoW 必须清空 `Page.active_cleaned_artifact_id`；历史仅由 immutable run/artifact relations 读取。translation 文字单独变化通常不 stale Cleaning；OCR 也只有改变 geometry/segment identity 时 stale。

恢复：promotion 前崩溃只留下 attempt/temp/orphan，不能提升；promotion 后崩溃留下 official unselected candidate，可重验；部分 result 可按 exact fingerprint 复用；acceptance 失败整体回滚；同 task/key 重放返回相同 logical facts；artifact missing/hash mismatch 建立 blocker，不能以 Page.status 伪装成功。

## 7. 事实源与责任边界

| 事实 | 唯一 source | 禁止替代 |
|---|---|---|
| 当前有效 cleaned output | `Page.active_cleaned_artifact_id` | newest file/run/status |
| 页面尝试 | PageCleaningRun | WorkflowAttempt/Page.status |
| target inventory | immutable inventory items | caller list/manifest |
| segment final conclusion | current disposition ledger | TextBlock/issue summary |
| instance pixel result | result ledger + official artifacts | overlay/debug folder |
| combined members | normalized member relation | directory/timestamp |
| page conclusion | accepted page validation | `page_scope_complete` |
| correction consumption | reservation chain | memory/retry JSON |
| blockers | current unresolved blocking issues + validation/dispositions | Page.status |
| bytes/hash/path | ProcessingArtifact / ArtifactService | manifest |

Provider only produces temp candidate. ArtifactService only promotes/registers/integrity-checks. Validator/QCS compute facts/drafts. WorkflowLoopEngine owns policy and correction decisions. Repository/UoW persists named commands; it does not decide algorithmic quality. No SQLite write transaction spans provider, artifact computation, composition or validation.

## 8. Repository／UoW 与验收

命名操作：`create_or_replay_page_cleaning_run`、`freeze_cleaning_inventory`、`append_instance_cleaning_result`、`record_or_supersede_segment_disposition`、`create_combined_candidate_with_members`、`append_page_cleaning_validation`、`reserve_or_replay_correction`、`reject_second_automatic_correction`、`persist_issue_lifecycle`、`load_page_cleaning_recovery_ledger`、`mark_cleaning_facts_stale_by_dependency`、`validate_active_cleaned_pointer_eligibility`、`accept_page_cleaning_atomically`。

acceptance predicate：run completed and inventory frozen; all targets have exactly one current disposition; all supported required targets `CLEANED_PASS`; only policy-allowed targets unsupported; no unresolved current-run blocking issue; selected page validation passes; combined artifact is official/present/hash-valid; source hash equals active original; member revisions/fingerprints fresh; correction reservations auditable; expected visual/pointer/task/attempt guards pass.

在同一 acceptance UoW 原子更新：accepted candidate/member/run/validation relation、issue lifecycle、WorkflowDecision及 links、TextBlock/Page summary、task/attempt/progress/budget、以及 active pointer。任何 guard/write 失败全部 rollback；block/review 也以短 UoW 保存证据/issue/decision，但绝不更新 pointer。

## 9. 迁移、case 映射与实施顺序

逻辑 schema 采用 `project_full_page_cleaning_ledger_v3`；无 semantic backfill，旧 Spike E/F 只读 legacy evidence，old project 迁移失败即 workflow blocked，无 auto downgrade。物理实施分为不可变的 foundation record `project_full_page_cleaning_ledger_v3` 与 completion record `project_full_page_cleaning_acceptance_v3`，二者共同构成完整 v3；`project_metadata.project_schema_version` 仍保持 v3。详见 [migration decision](migration-decision.md)、[migration staging amendment v0.1.1](migration-staging-amendment-v0.1.1.md) 与 [schema outline](schema-outline.md)。

case-71 在新 ledger 中为 6 inventory；两个 g002 `CLEANED_PASS` 可记录，其余四项为 blocking `MISSING_REQUIRED_EVIDENCE`，所以不能 pointer accept。case-72 明确表达 710/70 unsafe、g003 review 和缺失项，禁止静默丢弃或强制 E1。

实现 slices：1) v3 schema/migration upgrade tests；2) repositories/UoW + run/inventory/disposition；3) durable correction reservation；4) per-instance result/issue relations；5) combined membership；6) page validator ledger；7) atomic acceptance/stale recovery；8) case-71 Closure；9) case-72 generalization；最后 combined code-health review。每 Slice 仅触及相应 persistence/application/tests，先写 focused tests；本 Goal 不授权实现。

## 10. 验证清单、拒绝项、风险与就绪条件

[HARNESS](../HARNESS.md) 的 30 项覆盖双页事实、缺失/重复、overlap/cross-write、stale、hash、reservation、崩溃、migration、unsupported、CAS guard 与原图。拒绝宽表、JSON-only manifest、WorkflowAttempt 代替 run、Page.status/boolean completion、event sourcing/CQRS、Batch/UI/Typesetting 扩张。

主要风险：新 schema 与现有 issue relation 的 mapping、multi-segment instance attribution、migration tests 和 stale pointer consumers。前两项保留为非阻塞实现问题（见 [open questions](open-questions.md)）；所有当前 blocker 已有明确模型/约束。实现就绪结论：`PASS_WITH_OPEN_QUESTIONS`，仅表示可进入小 Slice schema/repository 实现，不表示 case-71/72 Closure 已恢复或 Cleaning 产品已可用。

## 11. 必需内容覆盖

| 必需项 | 本文位置 |
|---:|---|
| 1 目的与范围；2 当前 blocker；3 来源文档；4 术语；5 page run；6 inventory；7 disposition | §§1–4 |
| 8 instance result；9 combined membership；10 page validator；11 correction；12 issue lifecycle | §§5–6 |
| 13 source of truth；14 ArtifactService；15 Repository/UoW；16 acceptance；17 active pointer gate | §§7–8 |
| 18 stale；19 recovery；20 idempotency；21 migration；22 backward compatibility | §§6、9与 migration decision |
| 23 case-71；24 case-72；25 HARNESS；26 rejected alternatives；27 risks | §§2、9–10与 HARNESS |
| 28 implementation slices；29 implementation readiness；30 open questions | §§9–10与 open questions |
