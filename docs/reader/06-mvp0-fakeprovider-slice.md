# Phase 3 / Phase 4 MVP-0 FakeProvider：真实结果

本文给项目维护者看，解释 MVP-0 FakeProvider 单页后端切片到底准备实现什么。它不是 Codex 执行计划。

## 源文件

给你看的入口：

- [../implementation/mvp0-fakeprovider-slice/README.md](../implementation/mvp0-fakeprovider-slice/README.md)
- [../implementation/mvp0-fakeprovider-slice/GOAL.md](../implementation/mvp0-fakeprovider-slice/GOAL.md)
- [../implementation/mvp0-fakeprovider-slice/open-questions.md](../implementation/mvp0-fakeprovider-slice/open-questions.md)

Codex 执行材料，不建议你主读：

- [../implementation/mvp0-fakeprovider-slice/PLAN.md](../implementation/mvp0-fakeprovider-slice/PLAN.md)
- [../implementation/mvp0-fakeprovider-slice/HARNESS.md](../implementation/mvp0-fakeprovider-slice/HARNESS.md)
- [../implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md](../implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md)
- [../implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md](../implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md)
- [../implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md](../implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md)
- [../implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md](../implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md)
- [../implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md](../implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md)
- [../implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md](../implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md)
- [../implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md](../implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md)

## 当前真实状态

已经完成：

- 实施切片拆分；
- validation command 规划；
- file boundary 规划；
- Codex prompt 规划；
- review；
- open questions 收敛。

还没有完成：

- 后端代码；
- SQLite schema；
- repository 实现；
- ArtifactService 实现；
- WorkflowLoopEngine 实现；
- FakeProvider 实现；
- 测试代码。

## MVP-0 目标到底是什么

目标是跑通：

```text
create Project
-> create Batch
-> import one Page
-> register original artifact
-> run deterministic FakeProvider workflow
-> create TextBlocks
-> create OCRResults
-> create TranslationResults
-> register cleaned and typeset artifacts
-> persist WorkflowAttempt, ToolRunLog, QualityIssue, WorkflowDecision
-> update active pointers
-> support idempotent rerun
-> support selected crash/recovery scenarios
-> reach ready_for_export or documented warning/block state
```

当前 MVP-0 停在：

```text
ready_for_export
```

不做：

- actual export image；
- ZIP；
- manifest；
- ExportRecord；
- FastAPI routes；
- Web UI；
- real OCR/LLM/cleaner/typesetter。

## 七个切片分别证明什么

| Slice | 证明什么 | 底层结果 |
| --- | --- | --- |
| 01 Foundation and Project Store | app.db/project.db/project identity 可以初始化和打开。 | 开始有 Python package、临时 SQLite、ProjectMetadata、migration ledger、Project open gate。 |
| 02 Repository and Unit of Work Core | Repository/UoW 边界可用。 | Workflow 不碰 SQL，StageExecutor 只有窄 StageEvidenceWriter，provider 没 persistence 能力。 |
| 03 ArtifactService and Import | 原图 import 和 official artifact 注册可用。 | 原图成为 ProcessingArtifact，Page 指向 original_artifact_id，图片 bytes 在 filesystem。 |
| 04 FakeProvider and StageExecutor | FakeProvider 通过真实契约执行一个 stage。 | ProviderResult、temp files、ToolRunLog、StageResult、ArtifactService 注册路径跑通。 |
| 05 WorkflowLoop Happy Path | 单页 happy path 到 ready_for_export。 | TextBlock/OCRResult/TranslationResult/cleaned/typeset active pointers 和 WorkflowDecision 全部落库。 |
| 06 Quality Issues and Readiness | issue-bearing path 可解释。 | invalid/partial/refusal/skip/overflow 产生 QualityIssue 和 warning/block readiness。 |
| 07 Idempotency and Recovery | 重跑和崩溃恢复可解释。 | 不重复 provider call；OCR 后崩溃可从 translation 继续；missing active artifact 进入 loop 决策。 |

## Slice 01 实现后会第一次出现什么

Slice 01 完成后，项目应首次出现：

- `pyproject.toml` 或等价 Python 项目元数据；
- `src/manga_read_flow/**` 或等价后端 package；
- `tests/integration/test_project_store_init.py`；
- 临时 `app.db` 初始化；
- 临时 `project.db` 初始化；
- ProjectMetadata identity verification；
- Project repository exposure gate。

但仍不会出现：

- workflow execution；
- ArtifactService import；
- provider calls；
- FastAPI route；
- frontend；
- export output。

## 为什么先 FakeProvider

真实 OCR/LLM/清字/嵌字工具有太多不确定性：

- 失败；
- 超时；
- 输出 schema 不稳定；
- provider refusal；
- partial output；
- 文件生成失败；
- 本地依赖缺失。

如果先接真实工具，很难判断 bug 是架构问题还是工具问题。

FakeProvider 先证明：

- workflow 决策能跑；
- artifact 生命周期能跑；
- quality issue 能跑；
- active pointer acceptance 能跑；
- crash recovery 能跑；
- idempotency 能跑。

## 你不需要主读 PLAN 的原因

`PLAN.md` 是给 Codex 的执行编排：

- 它描述要产出哪些 slice 文件；
- 它规定每个 slice 的文件边界；
- 它包含 Codex prompt；
- 它给出 validation command；
- 它强调 stop conditions。

你真正需要知道的是：

- 当前代码还没开始；
- 下一步是 Slice 01；
- MVP-0 只证明后端单页到 `ready_for_export`；
- 后续再做真实工具、API、Web UI 和 export。
