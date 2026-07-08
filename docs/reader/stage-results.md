# 阶段成果总览

本文只记录每个阶段的真实结果。它不是执行计划，也不是给 AI agent 的任务说明。

## 总览表

| 阶段 | 当前结果 | 你应该看的中文结果 |
| --- | --- | --- |
| Phase 0 项目治理 | 已建立协作规则、边界、不变量和提交规则。 | 本文件 + [../../AGENTS.md](../../AGENTS.md) |
| Phase 1 需求与架构基线 | 已形成 SRS v1.0 和 HLD v0.2；当前 HLD v0.2 已提升为 `docs/HLD.md`。 | [01-requirements-and-architecture.md](01-requirements-and-architecture.md) |
| Phase 2 核心详细设计 | MVP-0 前置详细设计已完成：Data Model、Workflow State、Execution Contract、Persistence Readiness。 | [02-data-model.md](02-data-model.md)、[03-workflow-state.md](03-workflow-state.md)、[04-execution-contract.md](04-execution-contract.md)、[05-persistence-readiness.md](05-persistence-readiness.md) |
| Phase 3 架构验证与工具 Spike | FakeProvider 架构验证已有实施切片；真实工具 Spike 尚未启动。 | [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md) |
| Phase 4 MVP-0 单页后端切片 | 已完成实施拆分；代码还没开始。 | [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md) |
| Phase 5 MVP-1 单页 Web 闭环 | 未启动。 | 暂无真实结果，只看 [../PROJECT-PLAN.md](../PROJECT-PLAN.md) 的路线图即可。 |
| Phase 6 MVP-2 Batch / Recovery / Review / Export | 未启动。 | 暂无真实结果，只看 [../PROJECT-PLAN.md](../PROJECT-PLAN.md) 的路线图即可。 |
| Phase 7 稳定化测试 | 未启动。 | 暂无真实结果。 |
| Phase 8 本地交付 / 桌面化准备 | 未启动。 | 暂无真实结果。 |
| Phase 9 P1/P2 演化 | 未启动。 | 暂无真实结果。 |

## Phase 0：项目治理的结果

真实结果：

- Agent 必须先读需求和架构基线。
- 默认最小变更，不做无关重构。
- Provider Adapter、ArtifactService、WorkflowLoopEngine、QualityCheckService、Repository / DAO 的职责边界被固定。
- 明确禁止把图片 BLOB 放进 SQLite、覆盖原图、让 Provider 碰数据库、泄漏 API key。

源文件：

- [../../AGENTS.md](../../AGENTS.md)

## Phase 1：需求与架构基线的结果

真实结果：

- 产品目标确定为“本地个人阅读辅助工具”，不是发布级汉化生产系统。
- 第一阶段目标是日语到简体中文。
- 系统边界固定：不搜索、不抓取、不下载、不分发漫画资源。
- 技术形态固定为本地 Web UI + FastAPI 后端 + SQLite + filesystem + 本地 TaskRunner。
- 核心模块固定为 WorkflowLoopEngine、QualityCheckService、Provider Adapter、ArtifactService、Repository / DAO。

中文解读：

- [01-requirements-and-architecture.md](01-requirements-and-architecture.md)

源文件：

- [../SRS-v1.0.md](../SRS-v1.0.md)
- [../HLD.md](../HLD.md)

## Phase 2：核心详细设计的结果

真实结果：

- Data Model 决定系统用 `app.db + 每个 Project 一个 project.db`。
- Workflow State 决定从 `import` 到 `export_check` 的阶段、状态、retry、warning/block、恢复规则。
- Execution Contract 决定 Provider、Artifact、Quality、StageExecutor 之间怎么交换证据，谁不能越界。
- Persistence Readiness 决定 Repository / DAO、Unit of Work、migration 和 recovery 怎么落地。

中文解读：

- [02-data-model.md](02-data-model.md)
- [03-workflow-state.md](03-workflow-state.md)
- [04-execution-contract.md](04-execution-contract.md)
- [05-persistence-readiness.md](05-persistence-readiness.md)

源文件：

- [../design/data-model/final/data-model-dd-v0.1.md](../design/data-model/final/data-model-dd-v0.1.md)
- [../design/workflow-state/final/workflow-state-dd-v0.1.md](../design/workflow-state/final/workflow-state-dd-v0.1.md)
- [../design/execution-contract/final/execution-contract-dd-v0.1.md](../design/execution-contract/final/execution-contract-dd-v0.1.md)
- [../design/persistence/final/persistence-readiness-dd-v0.1.md](../design/persistence/final/persistence-readiness-dd-v0.1.md)

## Phase 3 / Phase 4：MVP-0 FakeProvider 的结果

真实结果：

- 还没有后端代码。
- 但已经把第一个后端实现拆成 7 个小切片。
- 当前 MVP-0 只证明单 Project / 单 Batch / 单 Page 可以经过 FakeProvider 跑到 `ready_for_export`。
- 实际导出图片、ZIP、manifest、ExportRecord 不在当前 MVP-0 切片里。

中文解读：

- [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md)

源文件：

- [../implementation/mvp0-fakeprovider-slice/README.md](../implementation/mvp0-fakeprovider-slice/README.md)
- [../implementation/mvp0-fakeprovider-slice/GOAL.md](../implementation/mvp0-fakeprovider-slice/GOAL.md)
- [../implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md](../implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md)

注意：`PLAN.md`、`HARNESS.md`、`slices/*.md` 是 Codex 执行材料，不是你日常了解项目的主阅读材料。
