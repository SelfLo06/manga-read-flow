# Execution Contract 详细设计 v0.1

## 1. 设计目标

本设计定义下一里程碑中 Provider Adapters、ArtifactService、QualityCheckService、StageExecutor 与 WorkflowLoopEngine 之间的 MVP execution contracts：

```text
FakeProvider single-Page backend vertical slice
```

目标：

- 保持 SRS、HLD、data-model 和 workflow-state 设计固定的架构边界。
- 在没有真实 OCR、LLM、清字或嵌字工具的情况下，使一个 Page 可以执行。
- 让 provider outputs、official artifacts、quality issues、workflow decisions 和 active pointer acceptance 能够分别解释。
- 支持重启恢复、幂等重跑、局部失败、Provider 拒绝、missing artifact 检测，以及 warning / blocking export readiness。
- 只保持文档化、最小化设计。本文不定义 SQL DDL、ORM、API、前端、真实 Provider 集成或真实 prompt template。

## 2. 来源文档

已阅读并综合：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/execution-contract/GOAL.md`
- `docs/design/execution-contract/HARNESS.md`
- `docs/design/execution-contract/PLAN.md`
- 所有 `docs/design/execution-contract/proposals/*.md`
- 所有 `docs/design/execution-contract/reviews/*.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/stage-transition-table.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`

未发现阻塞性冲突。`docs/HLD.md` 现在是当前 HLD v0.2 基线。最终设计遵循 `docs/HLD.md`，并在较旧 SRS / HLD 示例使用更宽泛词汇时，以更新的 data-model 和 workflow-state final 文档为准。

## 3. 最终文档地图

| Document | Owns |
| --- | --- |
| `provider-adapter-contract.md` | Provider result envelope、error envelope、metadata / capability metadata，以及五个 stage-specific provider contracts。 |
| `artifact-service-contract.md` | Official artifact lifecycle、artifact type / storage / retention vocabulary、temp promotion、missing detection 和 cleanup boundary。 |
| `quality-check-contract.md` | QualityCheckService input / output、issue drafts、attribution、severity / blocking、message / action keys 和 boundary rules。 |
| `stage-executor-contract.md` | StageExecutor context / result contracts、execution sequence、transaction boundaries，以及 WorkflowLoopEngine decision input。 |
| `error-and-issue-taxonomy-minimal.md` | 最小 error、issue、severity、root-stage、message 和 suggested-action vocabulary。 |
| `fakeprovider-readiness.md` | 必需 FakeProvider / FakeQuality modes、fixtures 和 HARNESS scenario replay。 |
| `open-questions.md` | 非阻塞 open questions 和 deferred decisions。 |

## 4. 跨模块决策

| Decision | Final choice |
| --- | --- |
| Provider envelope | 使用 `ProviderResult`，其中 `outcome = success | partial_success | failure | refusal | invalid_output`。 |
| Provider errors | 将标准化 `error` 嵌套在 `ProviderResult` 中；区分粗粒度 `kind` 和 stage-specific `code`。 |
| Provider refusal | 作为一等 `outcome = refusal`，包含 `is_provider_refusal = true`、refused attempt / log evidence、`provider_refusal` issue、`root_stage = provider_policy`。 |
| Provider temp files | Providers 只能返回 attempt temp root 下的 temp refs。它们绝不返回 official artifact ids 或 official paths。 |
| Official artifacts | ArtifactService promotion 加已提交 metadata 共同构成 official artifact。Artifact registration 不选择 active pointers。 |
| Quality issue persistence | MVP-0 中，QualityCheckService 返回带 issue drafts 和 lifecycle suggestions 的 `QualityCheckReport`；WorkflowLoopEngine 在 decision / acceptance transaction 中持久化 issue updates。 |
| Candidate results | StageExecutor 返回 result drafts / candidates。被接受的 OCR / TranslationResult rows 由 WorkflowLoopEngine acceptance 持久化。如果后续实现更早持久化 candidates，它们必须保持为未选中的历史 candidates。 |
| Acceptance transaction | WorkflowLoopEngine 协调一个 repository transaction，持久化 WorkflowDecision、issue lifecycle updates、accepted result rows、active pointers、retry budget after 和 stage statuses。 |
| Redaction | 在 ToolRunLog、保留 payload artifacts、QualityIssue drafts、WorkflowDecision rationale 或 debug summaries 持久化前，必须运行中心化 sanitization step。精确 helper / module 名称后置。 |
| FakeProvider modes | Fake modes 必须 deterministic，并通过 profile snapshot 或 task test config 复制到 sanitized attempt / tool metadata 中，做到持久且测试可见。隐藏的进程全局变量不足够。 |

## 5. 强不变量

| Invariant | Preserved by |
| --- | --- |
| Provider Adapter 只调用工具并返回结构化 outputs / errors / provider metadata。 | Provider contract。 |
| Provider Adapter 不访问 SQLite、不登记 official artifacts、不创建 QualityIssues、不决定 retry / fallback / skip / warning / pause / cancel / block。 | Provider 和 StageExecutor contracts。 |
| ArtifactService 是唯一 official artifact lifecycle 入口。 | Artifact contract。 |
| ArtifactService 不决定 workflow retry / fallback / warning / block / readiness。 | Artifact 和 StageExecutor contracts。 |
| Repository / DAO 是唯一 SQLite 访问入口。 | StageExecutor transaction guidance；所有 services 使用 repository boundaries。 |
| WorkflowLoopEngine 拥有 workflow decisions。 | StageExecutor output 仅作为 evidence。 |
| QualityCheckService 检查 outputs 并分类 issues，但不推进 workflow state，也不更新 active pointers。 | Quality contract。 |
| StageExecutor 执行单个 stage，但不做最终 workflow decisions。 | StageExecutor contract。 |
| 原图永不覆盖。 | Artifact lifecycle 和 import rule。 |
| 图片文件和大型 payloads 不存入 SQLite。 | Artifact retention / safety rules。 |
| Active pointers 仍是当前 OCR、translation、cleaned image 和 typeset image 的事实来源。 | Data-model alignment 和 acceptance transaction。 |
| Provider refusal 是一等 workflow path，不是 crash。 | Provider / quality / stage contracts 和 ADR 0001。 |
| 不允许 provider policy bypass 或 evasion logic。 | Provider refusal、suggested-action 和 redaction rules。 |
| FakeProvider 不需要真实 OCR、LLM、cleaning 或 typesetting tools。 | FakeProvider readiness。 |

## 6. WorkflowLoopEngine 决策输入

WorkflowLoopEngine 根据以下内容决策：

- 来自 StageExecutor 的 `StageResult` evidence。
- `ProviderResult` outcome、error / refusal evidence 和 provider metadata。
- 来自 ArtifactService 的 artifact registration 或 integrity reports。
- `QualityCheckReport` issue drafts、summary counts、severity / blocking、root / discovered stage 和 suggested action keys。
- 当前 task state、attempt history、retry budgets、fallback visited state，以及 cancellation / pause requests。
- `ProcessingProfileSnapshot` policy，包括 quality strictness、retry / fallback / refusal policy、warning export policy、auto-skip allowlist 和 retention / debug hints。
- Active pointers、result dependency hashes、artifact storage states、TextBlock stage statuses 和 Page aggregate state。

WorkflowLoopEngine 只能决定规范 workflow-state decisions：

```text
continue
reuse_cached_result
retry_same_stage
fallback_provider
retry_upstream_stage
skip_target
mark_warning
pause_for_user
block
finish_ready_for_export
finish_ready_for_export_with_warnings
cancel
```

## 7. 事务边界摘要

| Boundary | Rule |
| --- | --- |
| Before provider call | 在短事务中持久化 running WorkflowAttempt。允许可选 running ToolRunLog。 |
| Provider call | 不持有 SQLite write transaction。Provider 只能使用提供的 input refs 和 attempt temp root。 |
| Provider return | StageExecutor 规范化 provider output / error / refusal，并通过 Repository 记录 sanitized tool evidence。 |
| Artifact registration | ArtifactService 在短事务中 promote / register official artifacts。Registered artifacts 是 official 但 unselected。 |
| Quality check | QualityCheckService 返回 report / drafts；它不推进 workflow state。 |
| Workflow acceptance | WorkflowLoopEngine 将 decision、issue lifecycle、accepted results、active pointers、retry budget after 和 statuses 一起持久化。 |

## 8. HARNESS 场景回放

详细场景回放见 `fakeprovider-readiness.md`。摘要：

| HARNESS area | Result | Notes |
| --- | --- | --- |
| Provider Adapter P01-P05 | PASS | Success、timeout / failure、refusal、invalid output 和 partial translation 均由 `ProviderResult` 覆盖。 |
| ArtifactService A01-A05 | PASS | Original registration、temp promotion、failed evidence、missing artifact 和 cleanup boundary 均被覆盖。 |
| QualityCheckService Q01-Q06 | PASS | Empty OCR、invalid translation、missing block、refusal、cleaning skip 和 overflow 映射为 deterministic issue drafts。 |
| StageExecutor S01-S05 | PASS | One-stage sequence、provider failure、registration failure、blocking issue 和 warning issue 均为 evidence-only paths。 |
| FakeProvider F01-F07 | PASS | 必需 fake modes 和 fixture artifacts 覆盖 happy path、retry、invalid JSON、refusal、skip、overflow 和 missing artifact setup。 |
| Boundary failure checks | PASS | 没有最终 contract 赋予 provider、artifact、quality 或 stage executor workflow ownership。 |

## 9. 被拒绝的备选方案

| Alternative | Reason rejected |
| --- | --- |
| Provider returns domain rows such as OCRResult or TranslationResult. | 将工具耦合到 persistence、versioning、active pointers 和 workflow decisions。 |
| Provider writes official workspace files or registers artifacts. | 违反 ArtifactService 对 path、hash、retention、storage state 和 cleanup 的所有权。 |
| Provider creates QualityIssues or returns `should_retry` / `should_skip`. | 违反 QualityCheckService 和 WorkflowLoopEngine 所有权。 |
| Artifact registration automatically updates active pointers. | 跳过 quality / workflow acceptance，可能让坏输出变为 export-effective。 |
| QualityCheckService persists workflow state or returns WorkflowDecision. | 拆分决策所有权并削弱恢复审计能力。 |
| StageExecutor performs retry / fallback / skip / block logic. | 会把它变成隐藏的 WorkflowLoopEngine。 |
| Recovery promotes orphan temp files by default. | 绕过正常 artifact registration、quality classification 和 workflow acceptance。 |
| Store image bytes or raw provider payloads in SQLite. | 违反 data-model invariants，并增加 privacy / storage 风险。 |
| Treat provider refusal as generic failure. | 丢失策略语义，并可能造成不安全的同 Provider retry。 |
| Implement real OCR / LLM / cleaning / typesetting for Goal 2. | 会用工具行为掩盖 contract 缺陷，并阻塞 FakeProvider validation。 |

## 10. 风险与缓解

| Risk | Mitigation |
| --- | --- |
| Boundary drift from hints into decisions. | Provider retry hints、artifact rebuildability hints 和 quality suggested actions 明确都是非约束性 evidence。 |
| Partial success becomes ambiguous. | `partial_success` 要求有效 target payloads 加显式 missing / invalid target evidence；active pointer acceptance 仍归 loop 所有。 |
| Artifact DB / filesystem drift. | ArtifactService 校验 hash / path 并标记 `missing`；WorkflowLoopEngine 决定 rebuild / pause / block。 |
| Registered but unselected artifacts confuse recovery. | Official unselected artifacts 只作为 audit / reuse candidates，绝不按 timestamp 变为 export-effective。 |
| Quality issue persistence races active pointer updates. | MVP-0 在 WorkflowLoopEngine acceptance transaction 中持久化 issue lifecycle updates。 |
| Provider refusal hidden inside malformed output. | Adapter 可返回 `invalid_output`；QualityCheck 仅在可从 sanitized evidence 自信判断时分类 refusal。 |
| Debug / failed payloads leak secrets. | 中心化 sanitization、safety flags、无 raw secrets，failed / debug retention 只作为 filesystem artifacts。 |
| Fake modes hide real integration complexity. | FakeProvider 使用真实 envelope 和 artifact boundary；real-provider spike 是后续 validation step。 |

## 11. ADR 清单

- `docs/design/execution-contract/adr/0001-provider-result-envelope-and-refusal.md`
- `docs/design/execution-contract/adr/0002-artifact-promotion-and-unselected-official-artifacts.md`
- `docs/design/execution-contract/adr/0003-qualitycheck-issue-drafts-and-acceptance-transaction.md`
- `docs/design/execution-contract/adr/0004-stageexecutor-evidence-boundary.md`
- `docs/design/execution-contract/adr/0005-fakeprovider-deterministic-modes.md`
- `docs/design/execution-contract/adr/0006-redaction-sanitization-boundary.md`

## 12. 未决问题

见 `open-questions.md`。所有列出问题对最终综合和 FakeProvider single-Page backend vertical slice 规划都不是阻塞项。

## 13. 延后到后续设计阶段的决策

- 精确 SQL DDL、ORM models、migrations、indexes 和 repository method names。
- 精确 FastAPI routes、request / response DTOs 和 frontend behavior。
- 精确 provider prompt templates 和 real provider JSON schemas。
- 精确 artifact directory layout、temp naming、fsync mechanics、cleanup scheduler 和 retention TTLs。
- 精确 fast / balanced / strict ProcessingProfile defaults。
- 精确 API key storage implementation 和 OS secret store integration。
- 完整 export design、ZIP manifest schema 和 forced / incomplete export behavior。
- 完整 UI message localization 和 quality report rendering。
- 真实 OCR、translation、cleaning 和 typesetting tool integration details。
