# 总体架构

## 系统上下文

应用采用本地 Web UI、Python/FastAPI 后端、React/Next.js 前端、SQLite 与本地文件工作区。MVP 的本地 TaskRunner 与 FastAPI 后端同进程运行，不引入外部任务队列；当前仓库主要实现后端架构证明和单页 Cleaning 基础，API 与 Web UI 尚未形成产品入口。

线性处理为 Import → Detection → Grouping → OCR → Translation → Cleaning → Typesetting → Export，Review/Edit、Workflow Loop、Quality、Retry/Recovery、Reuse/Staleness 横跨各阶段。编号是文档信息架构，不重命名或扩展现有运行时状态机。

## 固定模块边界

- WorkflowService 编排用户用例；WorkflowLoopEngine 独占 accept/retry/fallback/skip/block 决策。
- QualityCheckService 检测质量问题并归因根阶段，不执行 Provider 或管理 artifact。
- Provider Adapter 只适配外部工具，不访问数据库、不拥有 artifact 生命周期、不决定重试或跳过。
- ArtifactService 独占路径、hash、登记、保留与清理；外部路径必须防止 traversal。
- Repository/DAO 独占 SQLite；Unit of Work 定义事务边界。
- UI 通过后端用例访问能力，不直接调用底层工具。

## 数据与持久化边界

全局配置使用 `app.db`，每个 Project 使用独立 `project.db` 和 workspace。图片 payload 保存在文件系统，SQLite 仅保存元数据、关系、状态与 hash。原图永不覆盖；GlossaryTerm 属于 Project，变更形成 `glossary_version`；OCRResult 和 TranslationResult 版本化，用户编辑创建新版本。

当前有效 OCR、翻译、cleaned image 和 typeset image 由 active pointer 选择，P0 不维护第二套 active flag。ProcessingProfile 的实际运行配置保存为版本化 ProcessingProfileSnapshot。每次 WorkflowAttempt 都持久化；失败 artifact 默认保留，成功的大 payload 可按 retention policy 清理。API key 不进入 project.db 或日志。

## 关键语义

“产生结果”与“接受结果”分离：只有质量检查和 loop decision 完成后的事务才能推进 active pointer。active pointer 是当前有效结果的主事实源；恢复以已提交的 attempt、result、decision、pointer 和 artifact hash 为准，不能只依赖 `Page.status`。相同输入、配置与依赖版本应支持幂等复用。Provider refusal 记录为结构化结果，由 loop 决定 fallback、warning 或 blocked。

## 决策、替代与风险

采用 SQLite 元数据 + filesystem payload，而非图片 BLOB，可控制数据库体积和 artifact 生命周期；采用显式状态机和决策账本，而非隐藏全局状态，可解释恢复。拒绝 Provider 直写数据库、UI 直调工具和各结果表独立 active flag，这些方案会破坏边界与原子接受语义。

风险包括文件/数据库不一致、并发接受冲突、stale 传播遗漏和 debug artifact 泄露内容。验证需覆盖崩溃恢复、重复请求、部分 artifact、软删除、清理、拒绝和导出阻断。FastAPI/Next.js 具体部署形态、后台任务隔离与打包方式仍属后续设计。
