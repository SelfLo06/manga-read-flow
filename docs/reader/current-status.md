# 当前真实进度

本文是给项目维护者看的当前状态摘要，不是给 Codex 的任务文件。

## 一句话结论

项目已经完成需求、架构、MVP-0 前置详细设计和 FakeProvider 后端切片实施拆分；尚未开始写后端代码。

## 已完成到什么程度

已完成的不是“想法”，而是可落到实现边界的设计：

- 需求和范围已经定版：看 [../SRS-v1.0.md](../SRS-v1.0.md)。
- 系统总体架构已经定版：看 [../HLD.md](../HLD.md)。
- 数据库/文件系统/实体关系已经设计到可实现：看 [02-data-model.md](02-data-model.md)。
- workflow 状态机、retry、warning/block、恢复规则已经设计到可测试：看 [03-workflow-state.md](03-workflow-state.md)。
- Provider、ArtifactService、QualityCheckService、StageExecutor 的边界已经设计到可编码：看 [04-execution-contract.md](04-execution-contract.md)。
- Repository / DAO / Unit of Work / migration readiness 已经设计到可开第一刀：看 [05-persistence-readiness.md](05-persistence-readiness.md)。
- MVP-0 FakeProvider 后端切片已经拆好，但那是给 Codex 执行用：你看 [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md)，不要把 `PLAN.md` 当主阅读材料。

## 还没有开始什么

- 没有 Python 后端源码。
- 没有 FastAPI route。
- 没有 Next.js / React 前端。
- 没有真实 OCR、翻译、清字、嵌字 Provider。
- 没有实际导出图片、ZIP、manifest、ExportRecord。
- 没有 Web UI。
- 没有多页 Batch 处理。

## 当前下一步

下一步不是继续写大设计，也不是让你读 `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`。

真正下一步是让 Codex 执行：

```text
MVP-0 FakeProvider Slice 01: Foundation and Project Store
```

这一步完成后，项目才会开始出现真实后端代码和第一批集成测试。

## 当前阶段判断

| 区域 | 状态 |
| --- | --- |
| 需求 | 完成 |
| 架构 | 完成 |
| MVP-0 前置详细设计 | 完成 |
| MVP-0 实施拆分 | 完成 |
| 后端代码 | 未开始 |
| 前端代码 | 未开始 |
| 真实工具集成 | 未开始 |
| 导出功能 | 未开始 |

## 你现在该读什么

如果你只是了解项目：

1. [stage-results.md](stage-results.md)
2. [01-requirements-and-architecture.md](01-requirements-and-architecture.md)
3. [02-data-model.md](02-data-model.md)
4. [03-workflow-state.md](03-workflow-state.md)
5. [04-execution-contract.md](04-execution-contract.md)
6. [05-persistence-readiness.md](05-persistence-readiness.md)
7. [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md)
