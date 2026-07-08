# Phase 2A Data Model：真实设计结果

本文给项目维护者看，解释数据模型阶段最终决定了什么底层结构。

## 源文件

- [../design/data-model/final/data-model-dd-v0.1.md](../design/data-model/final/data-model-dd-v0.1.md)
- [../design/data-model/final/schema-outline.md](../design/data-model/final/schema-outline.md)
- [../design/data-model/final/state-data-impact.md](../design/data-model/final/state-data-impact.md)
- [../design/data-model/final/open-questions.md](../design/data-model/final/open-questions.md)
- ADR 目录：[../design/data-model/adr/](../design/data-model/adr/)

## 最核心决定：app.db + project.db

系统不用一个全局大数据库装所有内容，而是分成：

```text
app.db
  只放全局 Project registry、非 secret 设置、provider/profile 模板、app migration ledger

每个 Project 一个 project.db
  放这个 Project 自己的 Batch、Page、TextBlock、OCR、翻译、workflow、artifact、quality、tool log
```

底层意义：

- Project 之间天然隔离。
- 一个 Project 坏了，不应该污染其他 Project。
- Project 可以被软删除、归档、恢复、迁移。
- 不需要跨数据库 foreign key，也不要求跨数据库事务。

## 内容层级已经固定

业务对象主干是：

```text
Project
-> Batch
-> Page
-> TextBlock
```

含义：

- Project 表示一部漫画或一个独立翻译任务集合。
- Batch 表示一次上传/一话/一组图片。
- Page 是一张漫画图。
- TextBlock 是页面里的一个文本区域。

检测阶段创建 TextBlock。OCR 和翻译都挂在 TextBlock 下面。

## 原图和处理结果都不是数据库 BLOB

所有图片、大 payload、raw provider response 都放 filesystem。SQLite 只存 metadata。

核心表是：

```text
ProcessingArtifact
```

它记录：

- artifact_id
- artifact_type
- owner_type / owner_id
- relative_path
- file_hash
- byte_size
- mime_type
- width / height
- workflow_attempt_id
- tool_run_id
- retention_class
- storage_state
- debug/sensitive flags

底层意义：

- 原图不会被覆盖。
- cleaned/typeset/export/debug 都是新 artifact。
- 文件丢了，不删除记录，而是把 `storage_state` 标为 `missing`。
- cleanup 只能改 artifact 状态，不能抹掉 workflow 解释能力。

## active pointer 是当前结果的唯一来源

系统不靠“最新一条 result”判断当前 OCR/翻译/图片输出。

当前有效结果通过 pointer 选择：

```text
TextBlock.active_ocr_result_id
TextBlock.active_translation_result_id
Page.original_artifact_id
Page.active_cleaned_artifact_id
Page.active_typeset_artifact_id
```

这解决几个底层问题：

- 用户编辑会创建新版本，但旧版本保留。
- provider 重试会创建新候选或新版本，但不会自动变当前。
- artifact 注册了，也不代表它就是 active output。
- recovery 不能靠时间戳捡“最新文件”。

## OCR 和翻译都是不可变版本

`OCRResult` 和 `TranslationResult` 不覆盖旧行。

规则：

- provider OCR 输出创建 OCRResult。
- 用户 OCR 编辑创建新的 OCRResult。
- Page 级翻译尝试可以为多个 TextBlock 创建 TranslationResult。
- 用户翻译编辑创建新的 TranslationResult。
- TranslationResult 必须记录它基于哪个 OCRResult / source_text_hash。
- TranslationResult 必须记录 glossary_version / glossary hash。

底层意义：

- 可以解释“这句译文来自哪个 OCR 文本、哪个术语表版本、哪个 provider attempt”。
- 用户编辑不会破坏历史。
- idempotency 可以根据 input hash / config hash / context hash 复用。

## workflow 证据表已经固定

核心证据表：

```text
ProcessingTask
WorkflowAttempt
WorkflowDecision
WorkflowDecisionIssue
ToolRunLog
QualityIssue
ProcessingProfileSnapshot
```

它们回答不同问题：

- ProcessingTask：用户或系统发起了什么任务。
- WorkflowAttempt：某个阶段对某个目标尝试过什么。
- ToolRunLog：具体 provider/tool 调用发生了什么。
- QualityIssue：发现了什么问题，是否 blocking。
- WorkflowDecision：WorkflowLoopEngine 为什么继续、重试、fallback、warning、block、finish。
- WorkflowDecisionIssue：某个 decision 是基于哪些 issues。
- ProcessingProfileSnapshot：这次任务用的策略快照是什么。

底层意义：

- 崩溃后能知道哪些 attempt 已经发生。
- provider refusal 不是丢在日志里，而是 attempt/log/issue/decision 都可查。
- export gate 可以查 open blocking QualityIssue。
- 用户可以理解为什么不能正常导出。

## ExportRecord 在数据模型里存在，但 MVP-0 当前不实现

Data Model 把 `ExportRecord` 列入 P0 概念，因为最终要记录成功、warning、blocked export attempt。

但当前 MVP-0 FakeProvider 后端切片只做到：

```text
ready_for_export
```

不做：

- 实际 export output；
- ZIP；
- manifest；
- ExportRecord 实现。

这个范围收窄来自后续 Persistence / MVP0 planning 的决策。

## 这个阶段留下的实现级开放点

Data Model 没有决定：

- 具体 SQL DDL；
- ORM 选型和 mapping；
- 具体字段约束名称；
- 具体 UUID/ULID/整数 ID 策略；
- artifact 目录布局；
- retention TTL；
- API DTO。

这些在 Persistence Readiness 和后续实现 slice 中继续收敛。
