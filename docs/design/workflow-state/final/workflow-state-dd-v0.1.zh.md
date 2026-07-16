# Workflow State 详细设计 v0.1

## 1. 设计目标

定义一个面向 MVP 单 Page 的 Workflow State / Workflow Loop 设计，使其可用 FakeProvider 实现、可在崩溃后恢复、可通过 attempts / decisions / issues / artifacts 审计，并且足够小，适合本地漫画翻译工作流。

该设计优先优化普通读者可用性、有界自动化、原图安全，以及清晰的职责分离。

workflow-state 设计不新增漫画搜索、抓取、下载、分发、发布、Provider 策略绕过或规避 Provider 策略的行为。

## 2. 来源文档

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- `docs/design/workflow-state/GOAL.md`
- `docs/design/workflow-state/HARNESS.md`
- `docs/design/workflow-state/PLAN.md`
- 所有 `docs/design/workflow-state/proposals/*.md`
- 所有 `docs/design/workflow-state/reviews/*.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/data-model/final/schema-outline.md`
- `docs/design/data-model/final/state-data-impact.md`
- `docs/design/data-model/final/open-questions.md`

未发现阻塞性冲突。主要词汇漂移在本文中收敛：TextBlock 完成态为 `done`，ProcessingTask 成功终态为 `succeeded` / `succeeded_with_warnings`，workflow 使用 `export_check` 表示就绪性检查，而 export records 仍归 export 设计负责。

## 3. MVP workflow 阶段

规范阶段：

```text
import -> detection -> ocr -> translation -> translation_check -> cleaning -> typesetting -> export_check
```

`export_check` 是 workflow 前置条件 / 就绪性逻辑。实际单页 / 批次 / ZIP export records、输出 artifacts 和 manifests 仍由 export 设计负责。

## 4. 状态词汇

规范值见 `state-vocabulary.md`。

摘要：

- ProcessingTask：`queued`、`running`、`pausing`、`paused`、`cancelling`、`cancelled`、`interrupted`、`recovering`、`succeeded`、`succeeded_with_warnings`、`blocked`、`failed`。
- WorkflowAttempt：`planned`、`running`、`succeeded`、`failed`、`refused`、`cancelled`、`skipped`、`reused_cached`、`interrupted`、`abandoned_after_crash`。
- Page：持久化的可修复聚合状态：`uploaded`、`queued`、`processing`、`paused`、`cancelled`、`interrupted`、`recovering`、`needs_review`、`partially_failed`、`blocked`、`ready_for_export`、`ready_for_export_with_warnings`、`exported`、`deleted`。
- TextBlock stage：`pending`、`running`、`done`、`failed`、`skipped`、`needs_review`、`stale`、`blocked`。

Page status 永远不是恢复事实来源。恢复使用 tasks、attempts、decisions、active pointers、result dependency hashes、artifacts、ToolRunLogs、QualityIssues 和 TextBlock stage statuses。

## 5. 合法与非法状态转移

见 `stage-transition-table.md`。

重要非法转移：

- cancelled task 自动恢复；
- blocked task 在没有证据变化或显式 resume 的情况下恢复；
- terminal attempts 被重新打开；
- 必需上游状态为 stale / failed / blocked 时，下游 stage 变为 `done`；
- OCR / translation 在没有 active pointer 的情况下为 `done`，显式 skipped / non-text target 除外；
- stale output 未经 validation / rerun / reuse 就变为 export-effective；
- 自动 workflow 替换 locked translation；
- 存在 skipped TextBlocks 时进入纯 `ready_for_export`；
- 存在 open blocking issues 时通过正常 export / readiness。

## 6. WorkflowDecision 与 loop 策略

见 `decision-matrix.md`。

Decision types：

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

retry budget 由持久化 retry decision 消耗。Attempts 会记录 budget 前后状态以供审计。`abandoned_after_crash` 本身不消耗普通 retry budget；自动恢复 retry 由 snapshot 或 task policy 中的 crash retry ceiling 限制。

Provider refusal 默认走 fallback、pause / manual、允许 skip、有效 warning path 或 block。该设计不提供任何策略绕过或规避逻辑。

## 7. 导出就绪性

正常就绪要求：

- active typeset artifact 存在，且为 official、present、hash-valid；
- 必需上游 OCR / translation / cleaning / typesetting 状态是 fresh；
- export scope 内不存在 open blocking QualityIssue；
- 对于纯就绪性，不得残留 skipped / warning 状态。

warning 就绪要求满足所有正常 freshness / artifact 条件，并且：

- 没有 open blockers；
- unresolved warnings / skips 保持可见；
- `ProcessingProfileSnapshot.allow_warning_export = true`。

全 skipped Page 不能进入纯 `ready_for_export`。只有当存在可用输出且 snapshot 允许 warning export 时，才能进入 `ready_for_export_with_warnings`；否则 pause 或 block。

## 8. 最小 ProcessingProfileSnapshot 策略字段

loop 只消费最小不可变策略：

- snapshot identity 与 settings hash；
- 各 stage retry budgets；
- crash recovery retry ceiling；
- fallback policy 与脱敏后的 provider / config refs；
- provider refusal policy；
- warning export policy；
- auto-skip allowlist；
- pause / block policy；
- quality strictness reference；
- artifact / debug retention hints。

Snapshots 不得包含 secrets。

## 9. 边界

Provider Adapter：

- 调用工具并返回结构化 outputs / errors / provider metadata；
- 可以使用临时文件；
- 不得访问 SQLite、登记 official artifacts、创建 QualityIssues、决定 retry / fallback / skip / warning / pause / cancel / block、决定 cache reuse，或执行策略规避。

ArtifactService：

- 是唯一 official artifact lifecycle 入口；
- 拥有 path generation、atomic write / promotion、hash、metadata registration、storage state、retention、cleanup、trash 和 missing checks；
- 不决定 workflow reuse / retry / rebuild / warn / block。

QualityCheckService：

- 检查 outputs / errors / artifacts / result metadata；
- 创建并分类 QualityIssues、severity / blocking、discovered stage、root stage、suggested action；
- 不推进 workflow state，也不决定 workflow outcomes。

Repository / DAO：

- 是唯一 SQLite 访问入口；
- 持久化 tasks、attempts、decisions、issues、artifacts、result versions、active pointers 和 stage statuses；
- 精确 methods / DDL / ORM 后置。

StageExecutor：

- 从 durable context 执行单个 stage；
- 根据 repository reads 和 ArtifactService lookups 构建 inputs；
- 调用 Provider Adapters 或 local tools；
- 向 loop 返回 stage output / standardized failure；
- 不做最终 workflow decisions，不在已接受 loop decisions 之外修改 active pointers，不在 provider calls 期间持有 write transactions，也不绕过 ArtifactService。

## 10. 崩溃恢复与幂等重跑

见 `recovery-rules.md`。

恢复：

- 将 stale running tasks 标记为 `interrupted`，再标记为 `recovering`；
- 根据 durable evidence 协调 running attempts；
- 优先使用已提交 results / artifacts 和 active pointers；
- 将未知 in-flight attempts 标记为 `abandoned_after_crash`；
- 仅在有限 budget / policy 内 retry；
- MVP 中不直接解析 raw provider output 成 accepted results，除非重放正常 validation / acceptance；
- 在 evidence reconciliation 后修复 Page aggregate status。

幂等重跑通过 `reuse_cached_result` 复用当前或历史匹配结果，并避免重复 active results。

## 11. stale 传播

见 `stale-propagation-rules.md`。

OCR edit：

- 创建新的 OCRResult 和 active OCR pointer；
- 将 translation、translation_check 和 typesetting 标记为 stale；
- 将 Page translation context 标记为 stale；
- 保留旧 translation / typeset pointers 供 review 使用，但不具备 export-effectiveness。

Translation edit：

- 创建新的 TranslationResult 和 active translation pointer；
- 将 translation_check 和 typesetting 标记为 stale；
- 不仅因为目标译文变更就将 Page translation context 标记为 stale；
- 保留旧 typeset pointer 供 preview / history 使用，但不具备 export-effectiveness。

OCR / translation 文本编辑后，cleaning 默认不 stale。

## 12. 场景回放

| Scenario | Result | Replay summary |
| --- | --- | --- |
| H01 happy path | PASS | Stages continue to `export_check`; active OCR / translation / cleaned / typeset pointers set; final `finish_ready_for_export`. |
| F01 OCR fails once then succeeds | PASS | Failed attempt persists; `retry_same_stage` consumes OCR budget; retry sets active OCR and continues. |
| F02 invalid translation JSON then retry succeeds | PASS | Invalid attempt / issue recorded; retry consumes translation budget; valid retry creates TranslationResults. |
| F03 partial Page translation | PASS | Valid block translations persist; missing / invalid blocks get issues; profile chooses retry / warning / pause / block. |
| F04 provider refusal | PASS | Attempt `refused`; ToolRunLog / QualityIssue / Decision persisted; fallback / manual / skip / warn / block only, no bypass. |
| F05 cleaning skips complex background | PASS | Cleaning `skipped`; warning issue; Page may become warning-ready, never pure ready. |
| F06 typesetting overflow | PASS | Preview may be retained; decision retry-upstream / warning / pause / block; export readiness follows issue / profile. |
| S01 OCR edit after translation | PASS | New OCR active; downstream stale; old translation / typeset not export-effective. |
| S02 translation edit after typesetting | PASS | New translation active; check / typesetting stale; rerender needed before readiness. |
| R01 crash after OCR before translation | PASS | OCR result reused; task recovers and resumes at translation; OCR not rerun. |
| R02 crash during provider call | PASS | Running attempt abandoned unless durable evidence exists; retry bounded by crash / stage policy. |
| R03 missing artifact during recovery | PASS | ArtifactService marks missing; loop rebuilds / retries / warns / blocks; original never overwritten. |
| E01 normal export with blocker | PASS | `export_check` blocks; export design records blocked attempt; no normal output artifact. |
| E02 warning export allowed | PASS | `allow_warning_export = true` permits warning readiness / export; issues remain auditable. |
| E03 warning export not allowed | PASS | Warning-only output blocks / rejects export readiness with profile rationale. |
| T01 pause then resume | PASS | Task pauses at safe boundary; resume recomputes from durable state without discarding results. |
| T02 cancel then new task | PASS | Cancelled task terminal; new task may reuse valid outputs. |
| I01 rerun completed Page unchanged | PASS | Reuse decisions avoid duplicate provider calls and active results. |
| I02 rerun after OCR edit | PASS | Edited OCR remains active; stale translation / typeset regenerated or blocked until handled. |

## 13. ADR 清单

- `docs/design/workflow-state/adr/0001-canonical-workflow-vocabulary.md`
- `docs/design/workflow-state/adr/0002-retry-budget-and-crash-attempts.md`
- `docs/design/workflow-state/adr/0003-export-check-and-warning-readiness.md`
- `docs/design/workflow-state/adr/0004-recovery-committed-results-first.md`

## 14. 被拒绝的备选方案

| Alternative | Reason rejected |
| --- | --- |
| Generic BPM / workflow engine | 对 MVP 单 Page 本地 workflow 来说过重。 |
| Page.status as recovery truth | 违反恢复不变量，无法解释 active pointer / artifact 漂移。 |
| Provider Adapter decides retry / fallback / skip | 违反架构边界，并使恢复不透明。 |
| QualityCheckService advances workflow state | 拆分决策所有权并削弱可审计性。 |
| Store images / large payloads in SQLite | 违反数据模型和 workspace artifact 设计。 |
| Active flags on result rows | 数据模型基线规定 active pointers 是唯一 P0 active source。 |
| `completed` stage status | 替换为规范 `done`。 |
| `locked` stage status | 替换为 lock pointer / metadata。 |
