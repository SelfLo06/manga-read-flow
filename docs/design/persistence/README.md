# 持久化就绪性设计

本目录包含 Goal 3：持久化就绪性设计。

范围：
- 最小 repository / DAO 设计就绪性
- app.db / project.db migration strategy
- Unit of Work / transaction boundary 指导
- FakeProvider single-Page backend vertical slice 的最小持久化支持
- Recovery、idempotency、active pointer、artifact、issue、attempt 和 decision 持久化就绪性

本目录仅包含设计文档。

这里不应包含生产代码、SQL DDL、SQLAlchemy models、Alembic migrations、FastAPI routes、前端实现、真实 provider integrations 或真实 translation prompt templates。
