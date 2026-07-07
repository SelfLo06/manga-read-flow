# 系统概要设计说明书 HLD v0.1

版本：v0.1
状态：概要设计初稿
适用阶段：MVP / 单 Page 端到端闭环验证
目标读者：项目维护者本人、AI 编码代理、后续详细设计与实现阶段

---

## 1. 文档目的

本文档用于定义“漫画翻译与基础嵌字自动化工作流应用”的系统概要设计。

本文档承接 SRS v1.0 需求方向，重点回答以下问题：

1. 应用采用什么形态；
2. 系统如何分层和拆分模块；
3. Project / Batch / Page / TextBlock 等核心对象如何组织；
4. 一键处理流程如何自动执行；
5. Workflow Loop、Quality Gate、状态恢复、artifact 管理如何支撑无人值守处理；
6. OCR、翻译、清字、嵌字等外部工具如何通过 Provider Adapter 接入；
7. UI 如何支持一键处理、结果预览、质量报告和局部返工；
8. 错误、NSFW、云端 Provider、API key 和本地数据如何处理。

本文档不展开以下内容：

1. 具体数据库 DDL；
2. 具体 API schema；
3. 具体 Prompt 模板；
4. OCR、清字、嵌字算法细节；
5. 详细 UI 样式；
6. 具体模型版本和第三方工具参数；
7. 完整测试用例。

这些内容将在后续详细设计阶段分别展开。

---

## 2. 设计目标与非目标

### 2.1 设计目标

系统第一阶段目标是：

在真实 Project / Batch / Page 结构下，跑通单 Page 端到端自动化处理闭环。

理想路径为：

```text
创建 Project
→ 创建上传批次
→ 上传 1 页漫画图片
→ 选择 ProcessingProfile
→ 点击一键翻译
→ 系统无人值守执行检测、OCR、Page 级翻译、质量检查、自动重试、清字、嵌字
→ 生成 ready_for_export 结果
→ 用户可直接导出
```

人工 review 和局部返工是后处理能力，不是默认主流程的必经步骤。

### 2.2 最高优先级

MVP 第一阶段最高优先级：

```text
单 Project 内单 Page 的一键无人值守处理、结果预览、质量报告、局部修改、局部返工和导出。
```

### 2.3 可牺牲内容

MVP 阶段可以牺牲：

1. UI 美观程度；
2. 大批量整章处理体验；
3. 发布级清字和嵌字质量；
4. 复杂拟声词、花体字、艺术字；
5. 高级字体与复杂排版；
6. 多人协作；
7. 云端部署；
8. 专业汉化组流程；
9. 完整漫画阅读器；
10. 高级 Provider 编排界面。

### 2.4 非目标

MVP 阶段不提供：

1. 漫画资源搜索；
2. 漫画资源抓取；
3. 漫画资源下载；
4. 漫画资源分发；
5. 发布平台；
6. 多人协作；
7. 商业化云端批处理；
8. 专业汉化组级别精修；
9. 对第三方 Provider 内容策略的规避能力。

---

## 3. 应用形态与部署方式

### 3.1 MVP 应用形态

MVP 采用：

```text
CLI + 本地后端服务 + 本地 Web UI
```

具体形态：

1. CLI 用于启动本地服务和开发调试；
2. 本地 Web UI 用于主要用户操作；
3. 后端服务运行在本机；
4. OCR、清字、嵌字 worker 运行在本机；
5. SQLite 和 workspace 位于本地文件系统；
6. 翻译 Provider 支持 OpenAI-compatible API，可指向云端或本地兼容服务。

### 3.2 最终产品形态

最终目标是本地桌面应用。

桌面化阶段可将本地后端和 Web UI 包装为桌面应用，例如 Electron、Tauri 或其他桌面壳。

桌面壳只负责：

1. 启动本地服务；
2. 提供窗口；
3. 管理托盘或启动器；
4. 管理基础配置。

桌面壳不改变核心后端、worker、Provider Adapter、workspace 和数据库结构。

### 3.3 启动方式

MVP 阶段允许命令行启动。

目标产品阶段应支持双击启动器。

---

## 4. 总体架构

### 4.1 技术选型

后端：

```text
Python + FastAPI
```

前端：

```text
React + Next.js
```

任务执行：

```text
MVP 使用同进程 TaskRunner。
```

存储：

```text
SQLite + 本地文件系统 workspace
```

### 4.2 总体分层

系统分为以下层：

```text
Web UI
API Layer
Application Service
WorkflowService
WorkflowLoopEngine
QualityCheckService
TaskRunner
Provider Adapters
Repository / DAO
ArtifactService
ConfigService
Domain Model
```

### 4.3 架构原则

1. 前端不得直接访问数据库；
2. 前端不得直接调用 OCR、翻译、清字、嵌字工具；
3. FastAPI 是唯一业务后端；
4. 长任务不得直接在 API handler 中同步执行；
5. API 创建 ProcessingTask 后返回 task_id；
6. TaskRunner 后台执行任务；
7. WorkflowService 负责任务编排；
8. WorkflowLoopEngine 负责 loop 控制；
9. QualityCheckService 负责质量检查与问题归因；
10. Provider Adapter 只负责工具调用；
11. ArtifactService 统一管理文件型中间产物；
12. Repository / DAO 统一访问 SQLite。

---

## 5. 核心模块设计

### 5.1 Web UI

职责：

1. Project 列表；
2. 新建 Project；
3. 上传图片；
4. 选择 ProcessingProfile；
5. 启动一键处理；
6. 展示任务进度；
7. 展示结果预览；
8. 展示质量报告；
9. 支持人工 review；
10. 支持局部返工；
11. 支持导出。

### 5.2 API Layer

职责：

1. 提供 FastAPI 路由；
2. 处理请求参数校验；
3. 调用 Application Service；
4. 创建 ProcessingTask；
5. 查询任务状态；
6. 提供文件预览和导出接口；
7. 不直接执行 OCR、翻译、清字、嵌字长任务。

### 5.3 Application Service

职责：

1. Project 用例；
2. Batch 用例；
3. Page 用例；
4. Glossary 用例；
5. Profile 用例；
6. Export 用例；
7. 调用 WorkflowService 启动处理任务。

### 5.4 WorkflowService

职责：

1. 启动 Batch / Page 处理；
2. 管理 ProcessingTask；
3. 调用 WorkflowLoopEngine；
4. 提供暂停、取消、恢复能力；
5. 处理任务级别状态聚合；
6. 不直接实现工具调用逻辑。

### 5.5 WorkflowLoopEngine

WorkflowLoopEngine 是 WorkflowService 内部核心控制模块。

职责：

1. 按阶段推进工作流；
2. 调用对应 StageExecutor；
3. 调用 QualityCheckService；
4. 读取 ProcessingProfile；
5. 控制 retry budget；
6. 决定 continue / retry / fallback / skip / warning / block；
7. 防止无限循环；
8. 保存 WorkflowAttempt metadata；
9. 保存 WorkflowDecision；
10. 最终产出 ready_for_export、ready_for_export_with_warnings 或 blocked。

WorkflowLoopEngine 不负责：

1. 直接调用模型；
2. 直接判断翻译质量；
3. 直接保存 artifact；
4. 直接访问数据库底层；
5. 直接拼 Prompt；
6. 直接处理 UI 展示。

### 5.6 QualityCheckService

QualityCheckService 是独立质量检查模块。

按阶段拆分：

```text
ImportCheck
DetectionCheck
OCRCheck
TranslationCheck
CleaningCheck
TypesettingCheck
ExportCheck
```

职责：

1. 检查阶段输出是否可信；
2. 生成 QualityIssue；
3. 标记问题严重程度；
4. 判断问题是否 blocking；
5. 支持下游问题反向归因到上游阶段；
6. 给出 suggested_action。

QualityCheckService 不直接推进业务状态。状态推进由 WorkflowLoopEngine 和 WorkflowStateManager 完成。

### 5.7 TaskRunner

MVP 使用同进程 TaskRunner。

职责：

1. 后台执行 ProcessingTask；
2. 避免 API 请求阻塞；
3. 支持任务暂停；
4. 支持任务取消；
5. 支持重启后恢复；
6. 后续可替换为独立 worker 进程。

### 5.8 Provider Adapters

Provider Adapter 包括：

```text
DetectorProvider
OCRProvider
TranslationProvider
CleanerProvider
TypesetterProvider
```

职责：

1. 接收结构化输入；
2. 调用具体工具；
3. 返回结构化输出；
4. 标准化错误；
5. 返回 provider metadata。

Provider Adapter 不得：

1. 访问数据库；
2. 推进状态；
3. 决定重试；
4. 决定 fallback；
5. 决定跳过；
6. 注册正式 artifact；
7. 生成 QualityIssue。

### 5.9 ArtifactService

职责：

1. 生成 artifact 路径；
2. 保存文件；
3. 计算 hash；
4. 登记 artifact metadata；
5. 管理临时文件；
6. 管理失败 artifact；
7. 支持 debug artifact 持久化策略；
8. 支持 soft delete 和清理。

### 5.10 Repository / DAO

职责：

1. 封装 SQLite 访问；
2. 保存和查询 Project / Batch / Page / TextBlock；
3. 保存 OCRResult / TranslationResult；
4. 保存 Artifact；
5. 保存 ProcessingTask；
6. 保存 WorkflowAttempt；
7. 保存 WorkflowDecision；
8. 保存 QualityIssue；
9. 支持事务；
10. 支持 migration。

### 5.11 ConfigService

职责：

1. workspace 配置；
2. Provider 配置；
3. API key / base URL 配置；
4. ProcessingProfile 管理；
5. debug artifact 策略；
6. 字体路径；
7. 导出格式；
8. 默认语言配置。

---

## 6. 核心领域模型

### 6.1 领域对象总览

核心对象：

```text
Project
Batch
Page
TextBlock
OCRResult
TranslationResult
GlossaryTerm
GlossaryVersion
ProcessingTask
ProcessingProfile
WorkflowAttempt
WorkflowDecision
QualityIssue
ProcessingArtifact
ToolRunLog
ExportRecord
```

### 6.2 Project

Project 必须存在。

即使第一阶段只处理单页，也必须在 Project 下运行。

Project 职责：

1. 隔离不同漫画项目；
2. 保存默认源语言和目标语言；
3. 关联术语表；
4. 关联 Batch；
5. 关联 project.db；
6. 关联 workspace 项目目录。

### 6.3 Batch

Batch 必须存在。

第一阶段 Batch 可以只包含 1 个 Page。

UI 上可将 Batch 弱化为：

```text
上传批次
章节
```

但系统内部必须保留 Batch 对象。

### 6.4 Page

Page 必须属于 Batch。

Page 表示一张漫画图片。

Page 关联：

1. 原图 artifact；
2. TextBlock 列表；
3. 当前 active 清字图；
4. 当前 active 嵌字图；
5. 导出结果；
6. Page 级状态；
7. Page 级 QualityIssue 聚合。

### 6.5 TextBlock

TextBlock 在检测阶段创建。

TextBlock 表示页面中的一个文本区域。

TextBlock 至少包含：

1. bbox；
2. 文本方向；
3. reading_order；
4. 检测置信度；
5. 分阶段状态；
6. active OCRResult；
7. active TranslationResult；
8. 关联清字和嵌字 artifact；
9. QualityIssue 聚合。

### 6.6 OCRResult

一个 TextBlock 允许多个 OCRResult。

用户修改 OCR 时，不物理覆盖旧结果，而是创建新的 OCRResult，并将其标记为 active。

### 6.7 TranslationResult

一个 TextBlock 允许多个 TranslationResult。

用户修改译文时，不物理覆盖旧结果，而是创建新的 TranslationResult，并将其标记为 active。

TranslationResult 需要记录：

1. source_text；
2. translation_text；
3. provider；
4. model_id；
5. prompt_version；
6. glossary_version；
7. input_hash；
8. config_hash；
9. quality flags；
10. 是否 user_edited；
11. 是否 active。

### 6.8 GlossaryTerm 与 GlossaryVersion

GlossaryTerm 属于 Project。

术语表不全局共享。

Glossary 需要版本。

TranslationResult 应记录生成时使用的 glossary_version。

### 6.9 ProcessingProfile

ProcessingProfile 控制一键处理行为。

内置 profile：

```text
快速
平衡
严格
```

用户可创建自定义 profile。

ProcessingProfile 控制：

1. 检查严格程度；
2. OCR retry budget；
3. Translation retry budget；
4. Translation reviewer round；
5. Shorten translation retry budget；
6. Cleaning retry budget；
7. Typesetting retry budget；
8. 是否启用 LLM reviewer；
9. 是否允许 warning 导出；
10. 是否自动导出；
11. 是否自动跳过复杂区域；
12. 是否在 blocking 错误时暂停。

### 6.10 WorkflowAttempt

WorkflowAttempt 记录每一轮 loop 尝试。

所有 attempt metadata 必须保存。

attempt payload artifact 可按策略保存。

### 6.11 WorkflowDecision

WorkflowDecision 记录 WorkflowLoopEngine 为什么做出某个决策。

decision_type 包括：

```text
continue
retry_same_stage
fallback_provider
retry_upstream_stage
skip_target
mark_warning
block
finish_ready_for_export
finish_ready_for_export_with_warnings
```

### 6.12 QualityIssue

QualityIssue 记录质量问题和问题归因。

核心字段概念：

```text
discovered_stage
root_stage
issue_type
severity
is_blocking
target_type
target_id
message
suggested_action
status
```

severity：

```text
info
warning
error
blocking
```

---

## 7. Workflow Loop 与 Quality Gate 设计

### 7.1 核心原则

系统主流程不是一次性线性流水线。

错误设计：

```text
检测 → OCR → 翻译 → 清字 → 嵌字 → 导出
```

正确设计：

```text
阶段执行
→ 质量检查
→ 自动修复 / 重试 / fallback / 跳过 / warning / block
→ 继续推进
```

### 7.2 Loop 目标

Workflow Loop 的目标：

```text
减少人工参与，使一键处理尽可能自动产出可导出结果。
```

非目标：

```text
自动保证发布级汉化质量。
```

### 7.3 Loop 控制

WorkflowLoopEngine 根据以下输入做决策：

1. 当前阶段；
2. 阶段输出；
3. QualityIssue；
4. ProcessingProfile；
5. retry budget；
6. attempt history；
7. Provider 可用性；
8. artifact 状态；
9. TextBlock / Page 状态。

### 7.4 阶段级 Loop

阶段 loop 示例：

```text
Detection
→ DetectionCheck
→ retry / mark needs_manual_textblock / skip complex region

OCR
→ OCRCheck
→ retry OCR / fallback OCR / manual_source_needed

Translation
→ TranslationCheck
→ retry page / retry selected blocks / shorten translation / needs_review

Cleaning
→ CleaningCheck
→ retry / skip cleaning / mark complex background

Typesetting
→ TypesettingCheck
→ shrink font / shorten translation / warning / block

Export
→ ExportCheck
→ regenerate / block / export_with_warnings
```

### 7.5 Loop 预算

loop 必须有限。

预算由 ProcessingProfile 控制。

预算耗尽后：

1. 非 blocking 问题进入 ready_for_export_with_warnings；
2. blocking 问题进入 blocked；
3. 不允许无限循环。

---

## 8. 主处理流程

### 8.1 一键处理入口

用户上传图片后，系统不立刻处理。

用户进入处理配置页，选择或确认 ProcessingProfile 后点击“一键翻译”。

### 8.2 主流程

```text
Create Project
→ Create Batch
→ Import Page
→ ImportCheck
→ User clicks Start Processing
→ Create ProcessingTask
→ WorkflowLoopEngine starts
→ Detect TextBlocks
→ DetectionCheck
→ OCR TextBlocks
→ OCRCheck
→ Build PageTranslationContext
→ Page-level Translation
→ TranslationCheck
→ Auto retry / selected retry / shorten if needed
→ Cleaning
→ CleaningCheck
→ Typesetting
→ TypesettingCheck
→ ExportCheck precondition
→ ready_for_export / ready_for_export_with_warnings / blocked
```

### 8.3 Page 级翻译

翻译调用粒度：

```text
Page
```

翻译存储粒度：

```text
TextBlock
```

Page 级翻译输入：

1. Page 内所有 TextBlock；
2. reading_order；
3. OCR 文本；
4. Project glossary；
5. glossary_version；
6. 当前上下文；
7. 已确认译文；
8. style goal；
9. ProcessingProfile。

LLM 返回结构化 JSON。

系统再将译文写入每个 TextBlock 的 TranslationResult。

### 8.4 单块重翻

单块重翻不能裸翻。

单块重翻应携带：

1. 整页 OCR 文本；
2. 整页已有译文；
3. Project glossary；
4. reading_order；
5. 当前目标 TextBlock ID。

模型只重写目标 TextBlock。

### 8.5 人工 review

人工 review 是后处理能力。

默认一键流程不要求用户逐块 review。

用户可在以下情况下进入 review：

1. 主动提高质量；
2. 修复 warning；
3. 处理 blocked；
4. 修改 OCR；
5. 修改译文；
6. 接受 warning；
7. 跳过 TextBlock；
8. 局部重翻；
9. 局部重嵌字。

---

## 9. 状态机设计

### 9.1 Batch 状态

```text
created
imported
queued
processing
auto_checking
auto_retrying
paused
cancelled
reviewing
partially_failed
failed
ready_for_export
ready_for_export_with_warnings
completed
exported
blocked
```

### 9.2 Page 状态

```text
uploaded
detecting
detected
ocr_processing
ocr_done
translating
translated
translation_checking
cleaning
cleaned
typesetting
typeset_done
auto_checking
auto_retrying
reviewing
partially_failed
ready_for_export
ready_for_export_with_warnings
completed_with_warnings
failed
skipped
exported
blocked
```

### 9.3 TextBlock 分阶段状态

TextBlock 不采用单一 status，而采用分阶段状态：

```text
detection_status
ocr_status
translation_status
translation_check_status
cleaning_status
typesetting_status
review_status
```

阶段状态：

```text
pending
running
done
failed
skipped
needs_review
stale
locked
```

### 9.4 paused 与 cancelled

paused：

```text
用户手动暂停或系统可恢复暂停。
任务可继续。
已完成结果保留。
```

cancelled：

```text
用户主动取消。
任务不自动继续。
已完成结果、artifact、日志和状态保留。
如需继续，应创建新 ProcessingTask 或手动选择从当前结果重新开始。
```

### 9.5 skipped 规则

TextBlock skipped 不等于 failed。

Page 存在 skipped block 时：

1. 可以进入 ready_for_export_with_warnings；
2. 不应进入纯 ready_for_export；
3. 质量报告必须显示 skipped block。

### 9.6 stale 规则

用户修改 OCR 后：

```text
当前 TextBlock:
translation_status = stale
translation_check_status = stale
typesetting_status = stale
review_status = needs_review

Page:
translation_context_stale = true
needs_review = true
```

用户修改译文后：

```text
当前 TextBlock:
typesetting_status = stale
review_status = needs_review

Page:
has_stale_blocks = true
needs_review = true
```

用户修改 TextBlock 区域后：

```text
cleaning_status = stale
typesetting_status = stale
```

### 9.7 重启恢复

应用重启后，Workflow 根据以下信息恢复：

1. ProcessingTask；
2. TextBlock 分阶段状态；
3. WorkflowAttempt；
4. WorkflowDecision；
5. Artifact；
6. QualityIssue；
7. active result 指针。

恢复不能只看 Page status。

### 9.8 避免重复调用

避免重复调用 OCR / LLM 依赖：

```text
input_hash
config_hash
provider
model_id
prompt_version
glossary_version
artifact_hash
active result status
```

Provider Adapter 不负责缓存判断。

WorkflowService / WorkflowLoopEngine 负责决策是否执行。

Repository 和 ArtifactService 负责查询可复用结果。

---

## 10. 存储与 Artifact 设计

### 10.1 数据库结构

系统采用：

```text
app.db + project.db
```

app.db 保存全局数据。

project.db 保存单 Project 内数据。

### 10.2 app.db 职责

```text
projects
global_settings
provider_configs
processing_profiles
recent_projects
workspace_config
schema_migrations
```

### 10.3 project.db 职责

```text
batches
pages
text_blocks
ocr_results
translation_results
glossary_terms
glossary_versions
processing_tasks
workflow_attempts
workflow_decisions
quality_issues
processing_artifacts
tool_run_logs
exports
schema_migrations
```

### 10.4 Workspace

workspace 由用户第一次启动时选择。

若用户未选择，系统提供默认路径，例如：

```text
~/MangaTranslator/workspace
```

目录结构：

```text
workspace/
  app.db
  config/
    providers.local.json
    profiles.local.json
  projects/
    {project_id}/
      project.db
      originals/
      pages/
        page_0001/
          detection/
          crops/
          ocr/
          translation/
          masks/
          cleaned/
          typeset/
          export/
          quality/
          attempts/
          logs/
      exports/
      trash/
```

### 10.5 图片与大文件

图片和大文件不进入 SQLite。

SQLite 只保存：

1. file_path；
2. file_hash；
3. artifact_type；
4. project_id；
5. batch_id；
6. page_id；
7. text_block_id；
8. source_step；
9. tool_run_id；
10. created_at。

### 10.6 Artifact 保存策略

必存 artifact：

1. original image；
2. active cleaned image；
3. active typeset image；
4. export image / zip；
5. mask；
6. quality report；
7. failed attempt artifact。

可选持久保存：

1. crop image；
2. raw OCR output；
3. raw LLM request；
4. raw LLM response；
5. detection visualization；
6. successful attempt payload；
7. debug log bundle。

临时 artifact：

1. 可重建 crop；
2. 临时 preview；
3. 成功 attempt 的大型 payload。

### 10.7 WorkflowAttempt 保存策略

所有 WorkflowAttempt metadata 必须保存。

attempt payload artifact 策略：

1. 失败 attempt 默认保存；
2. 成功 attempt 默认不持久保存 raw payload；
3. debug 模式全部保存；
4. 严格模式可保存更多 payload。

### 10.8 删除策略

删除 Project 采用 soft delete / 回收站机制。

永久删除需要二次确认。

---

## 11. Provider Adapter 设计

### 11.1 Provider 类型

系统定义以下 Provider 接口：

```text
DetectorProvider
OCRProvider
TranslationProvider
CleanerProvider
TypesetterProvider
```

### 11.2 DetectorProvider

职责：

```text
输入 Page 原图；
输出 TextBlock 候选区域、bbox、方向、置信度、reading_order 候选。
```

Detector 不负责 OCR 文本识别。

### 11.3 OCRProvider

职责：

```text
输入 TextBlock crop 或 bbox；
输出 OCR 文本、置信度、方向信息、原始输出 metadata。
```

OCRProvider 不创建 TextBlock。

### 11.4 TranslationProvider

MVP 只实现 OpenAI-compatible Provider。

接口保持抽象，避免 OpenAI-compatible 请求格式污染 Workflow 层。

职责：

```text
输入 PageTranslationContext；
输出 PageTranslationOutput。
```

### 11.5 CleanerProvider

允许多个实现：

1. simple white fill；
2. OpenCV inpaint；
3. LaMa；
4. 后续其他 inpainting 工具。

MVP 可以先实现简单方案，但接口必须允许替换。

### 11.6 TypesetterProvider

MVP 阶段自研实现，使用 Pillow / PIL。

职责：

1. 中文文本绘制；
2. 自动换行；
3. 字号自适应；
4. 溢出检测；
5. 最小字号限制；
6. 结果图生成。

虽然 MVP 只有一个实现，但仍通过 TypesetterProvider 接口接入。

### 11.7 Provider 错误类型

标准错误类型：

```text
provider_unavailable
provider_timeout
provider_refusal
invalid_input
invalid_output
model_error
dependency_missing
file_io_error
unsupported_content
unknown_error
```

Provider Adapter 识别错误。

WorkflowLoopEngine 决策如何处理错误。

### 11.8 Provider 文件边界

Provider Adapter 不负责正式 artifact 生命周期。

允许：

```text
Provider 使用临时文件。
```

禁止：

```text
Provider 自己决定 artifact 路径；
Provider 自己写入 workspace 正式目录；
Provider 自己登记数据库；
Provider 自己决定文件清理策略。
```

正式 artifact 由 ArtifactService 管理。

---

## 12. UI 与交互概要设计

### 12.1 首页

首页展示：

1. 最近 Project；
2. 新建 Project；
3. 打开 Project；
4. 设置入口。

### 12.2 创建 Project

必填：

1. Project 名称；
2. 源语言；
3. 目标语言；
4. 默认 ProcessingProfile。

可选：

1. 自定义 Project 存储位置；
2. 初始术语表导入。

workspace 默认继承全局设置。

### 12.3 上传与处理配置

上传图片后进入处理配置页。

处理配置页允许：

1. 查看待处理页面；
2. 选择 ProcessingProfile；
3. 展开高级设置；
4. 启动一键翻译。

### 12.4 一键处理前配置

默认使用上次配置。

用户可展开修改：

1. 处理模式；
2. 检查严格度；
3. retry budget；
4. 是否启用 LLM reviewer；
5. 是否允许 warning 导出；
6. 是否自动导出；
7. debug artifact 策略。

### 12.5 处理过程 UI

默认显示：

1. 当前阶段；
2. 当前页；
3. 总体进度；
4. warning 数量；
5. error 数量；
6. 是否可导出。

可展开查看：

1. 实时日志；
2. Page 状态；
3. TextBlock 状态；
4. QualityIssue；
5. WorkflowAttempt；
6. Provider 调用记录。

non-blocking warning 不打断处理。

blocking 错误按 ProcessingProfile 处理。

### 12.6 处理完成页

显示：

1. 结果预览；
2. 导出按钮；
3. 质量报告摘要；
4. warning / error 列表；
5. 进入人工 review 入口；
6. 重新处理入口。

### 12.7 质量报告

质量报告按 Page / TextBlock 分组展示。

支持在图片上叠加 issue 标记。

issue 显示：

1. 问题类型；
2. 严重程度；
3. 发现阶段；
4. 疑似根因阶段；
5. 建议动作；
6. 是否阻塞导出。

### 12.8 人工 Review 页面

P0 能力：

1. 原图 / 结果图切换或对照；
2. TextBlock 框叠加；
3. 查看 OCR；
4. 查看译文；
5. 修改 OCR；
6. 修改译文；
7. 重新翻译当前 TextBlock；
8. 重新嵌字当前 TextBlock；
9. 跳过 TextBlock；
10. 接受 warning。

P1 能力：

1. 重新清字当前 TextBlock；
2. 手动调整 TextBlock 框；
3. 手动调整字体大小；
4. 手动换行；
5. 手动选择清字方式；
6. 查看完整 WorkflowAttempt。

### 12.9 高级设置页

MVP 高级设置包括：

1. Provider / API key；
2. OpenAI-compatible base URL；
3. 默认模型；
4. workspace；
5. ProcessingProfile；
6. debug artifact 保存策略；
7. 字体路径；
8. 导出格式。

---

## 13. 错误处理、合规与边界

### 13.1 错误分类

系统使用统一 ErrorCode / IssueType。

覆盖：

1. import；
2. detection；
3. OCR；
4. translation；
5. cleaning；
6. typesetting；
7. export；
8. filesystem；
9. database；
10. provider；
11. config；
12. workflow。

### 13.2 用户错误与内部错误分离

用户界面显示：

1. 可理解错误原因；
2. 影响范围；
3. 建议动作。

内部日志保存：

1. stack trace；
2. provider response metadata；
3. tool run 信息；
4. attempt 信息；
5. config hash；
6. input hash。

API key 不得进入日志。

### 13.3 API key 错误

API key 缺失或无效时：

1. 相关 Provider 标记 unavailable；
2. 若无 fallback，则依赖该 Provider 的阶段 blocked；
3. UI 提示配置 API key 或切换 Provider。

不是整个系统因缺少云端 API key 而不可用。

### 13.4 Provider 拒绝

云端 LLM Provider 拒绝处理内容时：

1. Provider Adapter 返回 provider_refusal；
2. WorkflowLoopEngine 根据 ProcessingProfile 决定 fallback、warning、skip 或 blocked；
3. 不将 provider_refusal 当作普通崩溃处理。

### 13.5 NSFW 边界

系统允许用户处理本地持有内容。

系统不承诺第三方 API 一定处理 NSFW 或敏感内容。

系统不主动绕过第三方 API 内容策略。

用户可自行配置本地或云端 OpenAI-compatible Provider。

系统不提供规避第三方策略的 Prompt、对抗逻辑或绕过机制。

### 13.6 资源边界

系统不提供：

1. 漫画资源搜索；
2. 漫画资源抓取；
3. 漫画资源下载；
4. 漫画资源分发；
5. 发布平台。

### 13.7 原图安全

原图永不覆盖。

所有清字、嵌字和导出结果都作为新 artifact 保存。

### 13.8 导出前检查

导出前必须检查 unresolved blocking issue。

存在 unresolved blocking issue 时，禁止正常导出。

warning 是否允许导出由 ProcessingProfile 决定。

高级操作可允许强制导出当前可生成结果，但必须标记为 forced_export / incomplete_export，并显示 blocking issue 摘要。

### 13.9 本地数据与云端 Provider

本地 Project 数据默认不上传。

只有用户启用云端 Provider 时，相关 OCR 文本、术语表和上下文才会发送给第三方服务。

系统必须提示用户该事实。

### 13.10 Debug Artifact 提示

debug artifact 可能包含：

1. 原图；
2. OCR 文本；
3. 译文；
4. LLM request；
5. LLM response；
6. 错误上下文。

系统需要在开启 debug 持久保存时提示用户。

---

## 14. MVP 技术路线

### 14.1 后端

```text
Python
FastAPI
SQLite
Alembic
Pydantic
```

### 14.2 前端

```text
React
Next.js
```

### 14.3 图像处理

```text
Pillow / PIL
OpenCV
```

### 14.4 OCR 与检测

DetectorProvider 与 OCRProvider 保持抽象。

MVP 可先接入开源检测/OCR 工具。

### 14.5 翻译

MVP 实现：

```text
OpenAI-compatible TranslationProvider
```

### 14.6 清字

MVP 支持：

1. simple fill；
2. OpenCV inpaint；
3. 后续可扩展 LaMa。

### 14.7 嵌字

MVP 自研 TypesetterProvider。

能力：

1. 中文字体绘制；
2. 自动换行；
3. 字号自适应；
4. 溢出检测；
5. 最小字号限制；
6. 横排中文嵌字。

---

## 15. MVP 验收标准

MVP 第一阶段成功标准：

1. 用户可以创建 Project；
2. 用户可以创建上传批次；
3. 用户可以上传 1 张漫画图片；
4. 系统可以创建 Page；
5. 系统可以检测 TextBlock；
6. 系统可以 OCR；
7. 系统可以按 Page 级上下文翻译；
8. 系统可以执行 TranslationCheck；
9. 系统可以自动重试或标记 warning；
10. 系统可以清字；
11. 系统可以嵌字；
12. 系统可以生成结果预览；
13. 系统可以生成质量报告；
14. 系统可以在无 blocking issue 时进入 ready_for_export；
15. 用户可以导出结果；
16. 用户可以修改 OCR；
17. 用户可以修改译文；
18. 用户可以重新翻译单个 TextBlock；
19. 用户可以重新嵌字单个 TextBlock；
20. 系统可以保存状态并在重启后恢复；
21. 系统不会覆盖原图；
22. 系统不会因为单个 non-blocking warning 中断一键处理。

---

## 16. 后续详细设计任务

HLD 完成后，应进入以下详细设计：

1. 数据模型详细设计；
2. 状态机详细设计；
3. WorkflowLoopEngine 详细设计；
4. QualityIssue / QualityCheckService 详细设计；
5. Provider Adapter 接口设计；
6. TranslationProvider Prompt 与 JSON schema 设计；
7. ProcessingProfile schema 设计；
8. ArtifactService 详细设计；
9. API 设计；
10. UI 页面结构与交互流设计；
11. 错误码与 IssueType 设计；
12. 本地配置与 API key 管理设计；
13. MVP 实现任务拆分；
14. 测试用例设计。

---

## 17. 当前设计结论摘要

本系统的核心不是线性工具链，而是一个本地运行的、可恢复的、以 Workflow Loop 驱动的漫画翻译自动化工作流。

核心架构判断：

```text
本地 Web UI + FastAPI 后端 + 同进程 TaskRunner
+ SQLite / filesystem
+ WorkflowLoopEngine
+ QualityCheckService
+ Provider Adapter
+ ArtifactService
```

核心产品判断：

```text
一键处理默认无人值守。
人工 review 是后处理。
warning 不默认阻塞。
blocking 必须阻塞正常导出。
翻译使用 Page 级上下文调用。
结果按 TextBlock 存储。
所有关键中间结果可追踪、可恢复、可局部返工。
```