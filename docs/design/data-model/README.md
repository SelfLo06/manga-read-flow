# 数据模型详细设计

本目录包含数据模型详细设计包。

范围：
- Project / Batch / Page / TextBlock ownership model
- app.db / project.db 数据拆分
- OCR 与 translation result 版本化
- Active pointer 规则
- Artifact metadata 与 retention 边界
- WorkflowAttempt、WorkflowDecision、ToolRunLog 和 QualityIssue 的持久化需求
- ProcessingProfileSnapshot 与 export gate 数据支持
- Soft delete / trash 行为和重启恢复数据支持

主要最终产物：
- `final/data-model-dd-v0.1.md`
- `final/schema-outline.md`
- `final/state-data-impact.md`
- `final/erd.mmd`
- `final/open-questions.md`
- `adr/` 下的 ADR

本目录仅包含设计文档。

这里不应包含生产代码、SQL DDL、SQLAlchemy models、migrations、FastAPI routes、前端实现、真实 provider integrations 或真实 translation prompt templates。
