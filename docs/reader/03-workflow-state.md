# Phase 2B Workflow State：真实设计结果

本文给项目维护者看，解释 workflow 状态机阶段最终决定了什么底层行为。

## 源文件

- [../design/workflow-state/final/workflow-state-dd-v0.1.md](../design/workflow-state/final/workflow-state-dd-v0.1.md)
- [../design/workflow-state/final/state-vocabulary.md](../design/workflow-state/final/state-vocabulary.md)
- [../design/workflow-state/final/stage-transition-table.md](../design/workflow-state/final/stage-transition-table.md)
- [../design/workflow-state/final/decision-matrix.md](../design/workflow-state/final/decision-matrix.md)
- [../design/workflow-state/final/recovery-rules.md](../design/workflow-state/final/recovery-rules.md)
- [../design/workflow-state/final/stale-propagation-rules.md](../design/workflow-state/final/stale-propagation-rules.md)

## canonical stage 已经固定

MVP 单页 workflow 的阶段是：

```text
import
-> detection
-> ocr
-> translation
-> translation_check
-> cleaning
-> typesetting
-> export_check
```

注意：`export_check` 只是导出前条件检查 / readiness 逻辑，不等于实际导出文件。

实际 ExportRecord、ZIP、manifest 属于后续 export design。

## Page.status 不是恢复真相

设计明确禁止只靠 `Page.status` 恢复任务。

恢复要看：

- ProcessingTask；
- WorkflowAttempt；
- WorkflowDecision；
- ToolRunLog；
- active OCR / translation / cleaned / typeset pointers；
- result dependency hashes；
- ProcessingArtifact storage_state；
- QualityIssue；
- TextBlock stage statuses。

底层意义：

- `Page.status = processing` 只能说明摘要，不说明哪些结果已经提交。
- OCR 后崩溃时，系统应看到 active OCR pointer 已经提交，然后从 translation 继续，而不是重跑 OCR。
- artifact 已注册但未 active 时，不能按最新时间戳选它。

## WorkflowDecision 类型已经固定

WorkflowLoopEngine 可以做的决策是：

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

底层意义：

- retry/fallback/skip/warning/block 都必须有 WorkflowDecision 证据。
- Provider 不允许直接说“应该重试”或“应该跳过”。
- ArtifactService 不允许直接说“应该 rebuild/block”。
- QualityCheckService 不允许直接推进状态。

## ready_for_export 的条件

纯 `ready_for_export` 需要：

- active typeset artifact 存在；
- artifact 是官方注册 artifact；
- 文件存在且 hash 有效；
- upstream OCR / translation / cleaning / typesetting fresh；
- 没有 open blocking QualityIssue；
- 没有 unresolved warning/skip 状态影响纯 readiness。

`ready_for_export_with_warnings` 需要：

- 输出仍然可用；
- 没有 open blocker；
- warning/skip 可见；
- 当前 ProcessingProfileSnapshot 允许 warning export。

底层意义：

- cleaning skip 不能悄悄变成纯 ready。
- typesetting overflow 不能悄悄变成纯 ready。
- warning 是否允许不是全局当前设置说了算，而是这次任务的 profile snapshot 说了算。

## provider refusal 是一等状态路径

Provider 拒绝内容时，不是普通 crash，也不是自动绕过。

系统只能选择：

- fallback；
- pause/manual；
- allowed skip；
- warning path；
- block。

禁止：

- prompt laundering；
- policy bypass；
- same-provider evasion retry。

底层证据需要出现在：

- WorkflowAttempt；
- ToolRunLog；
- QualityIssue；
- WorkflowDecision。

## stale propagation 已经固定

用户编辑 OCR 后：

- 新建 OCRResult；
- 更新 active OCR pointer；
- translation / translation_check / typesetting 变 stale；
- Page translation context 变 stale；
- 旧 translation/typeset 可以保留用于 review，但不能 export-effective。

用户编辑 translation 后：

- 新建 TranslationResult；
- 更新 active translation pointer；
- translation_check / typesetting 变 stale；
- 不因为目标文本变化就让 Page translation context stale；
- 旧 typeset 可以保留用于预览/历史，但不能 export-effective。

底层意义：

- 用户改译文后必须重新 typeset，旧嵌字图不能当最终结果。
- 用户改 OCR 后必须重新翻译或明确处理 downstream。

## crash recovery 的行为

恢复规则：

- stale running task 先标 `interrupted`，再进入 `recovering`。
- running attempt 根据已有证据处理。
- 已提交 active pointer 的结果优先复用。
- 未提交的 provider temp/orphan 文件不自动变官方结果。
- 只有通过正常 validation/acceptance 才能变 active。
- crash retry 有上限。

典型例子：

```text
OCRResult + active_ocr_result_id 已提交
但进程在 translation 前崩溃
=> recovery 从 translation 继续，不重跑 OCR
```

## 这个阶段没有决定什么

Workflow State 没有定义：

- SQL DDL；
- Repository 方法；
- Provider DTO 具体字段；
- ArtifactService 目录布局；
- API / UI 行为；
- 实际导出文件结构。

这些由 Execution Contract、Persistence 或后续 API/Export/UI 设计负责。
