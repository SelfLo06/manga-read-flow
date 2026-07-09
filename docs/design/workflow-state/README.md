# Workflow State / Workflow Loop 详细设计

本目录包含 Goal 1 的 Workflow-State Core Design 设计包。

本设计包定义 MVP workflow 如何跨阶段推进，如何做出 retry / fallback / skip / warning / block 决策，stale state 如何传播，以及中断或崩溃后如何恢复。

本目录仅包含设计文档。不得包含实现代码、SQL DDL、ORM mappings、API routes、UI components 或真实 Provider integration。
