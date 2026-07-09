# Slice 02：Repository and Unit of Work Core

## 1. 目标

规划 FakeProvider 后端切片所需的最小 repository contracts 和 Unit of Work 边界。

本 slice 创建 persistence access shape，用于 content state、result versions、workflow evidence、quality issues、artifact metadata、glossary versions 和 readiness queries，同时不向 workflow modules 暴露 SQLite、cursors、ORM sessions 或 table-shaped generic repositories。

## 2. 为什么现在做这个 slice

ArtifactService、StageExecutor、QualityCheckService integration、WorkflowLoopEngine acceptance、idempotency 和 recovery 都需要 repository boundaries，之后才能安全实现。本 slice 位于 import 和 provider execution 之前，以防后续 service 中滋生 ad hoc SQLite access。

决策：

- 实现命名 repository groups，而不是 generic `Repository<T>`。
- SQLite access 只通过 Repository / DAO。
- 为 lifecycle、import、attempt reservation、tool evidence、artifact metadata、acceptance 和 recovery repair 使用命名 Unit of Work operations。
- 为 StageExecutor 引入窄接口 `StageEvidenceWriter`。
- 在 happy path 使用 acceptance transaction 之前，先预留其形态。

被拒绝的备选方案：

- Generic CRUD repositories，因为它们泄漏 table shape，并诱导业务决策进入 persistence。
- 将 SQL sessions 或 connections 传入 WorkflowLoopEngine 或 StageExecutor。
- 允许 StageExecutor 写 active pointers、QualityIssues、WorkflowDecisions、retry budget 或 stage completion。

## 3. 来自先前设计的输入

- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/persistence/**`
- `src/manga_read_flow/domain/**`，用于 repository contracts 需要的最小 DTO / value objects。
- `src/manga_read_flow/workflow/**`，仅用于让 repository tests 能编译的 contract-facing DTOs。
- `tests/integration/test_repository_uow_core.py`
- `tests/conftest.py`
- `tests/fixtures/**`，仅限小型 persistence fixtures。

## 5. 禁止变更

- 访问 repositories 或 SQLite 的 Provider adapter code。
- 超出 `StageEvidenceWriter` 的 StageExecutor writes。
- WorkflowLoopEngine 完整 happy path 实现。
- ArtifactService file promotion 或 official artifact lifecycle 实现，除测试需要的 metadata contract stubs 外。
- UI / API / routes / frontend files。
- 真实 provider integrations、真实 prompt templates、export output、ZIP、manifest 或 `ExportRecord`。
- 大范围 schema redesign 或先前 final design doc edits。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 为以下内容添加 repository contract interfaces 或 concrete minimal modules：
   - ProjectIdentityRepository
   - ContentStateRepository
   - ResultVersionRepository
   - GlossaryRepository
   - WorkflowExecutionRepository
   - QualityIssueRepository
   - ArtifactMetadataRepository
   - ReadinessQueryRepository
3. 添加用于短事务的命名 Unit of Work helpers，并隐藏实现细节。
4. 添加 acceptance transaction placeholder，包含 expected-state guard inputs 和可见 conflict outcome。
5. 添加 `StageEvidenceWriter`，只包含 ToolRunLog 和窄 attempt evidence operations。
6. 添加测试，证明 workflow-facing code 可以使用 repository contracts，而不需要 SQL / session handles。
7. 添加测试，证明 provider code 没有 repository dependency。
8. 添加测试，证明 StageExecutor-facing evidence writes 不能更新 active pointers、QualityIssues、WorkflowDecisions 或 retry budget。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_repository_uow_core.py
```

## 8. 验收标准

- Repository contracts 向调用方隐藏 SQLite details。
- 没有 workflow-facing test 使用 SQL strings、ORM sessions、cursors 或 table-shaped row dictionaries。
- `StageEvidenceWriter` 只能创建 / 更新 ToolRunLog 和窄 attempt evidence。
- Provider adapter modules 没有 repository 或 SQLite dependency。
- Acceptance transaction shape 能表示 accepted results、active pointers、issue lifecycle、WorkflowDecision、retry budget、task progress、stage statuses 和 expected-state conflict。
- 不引入 generic `Repository<T>` 抽象。

## 9. 需要测试的失败场景

- Expected active pointer guard 失败，acceptance 返回 conflict / reload outcome。
- StageEvidenceWriter caller 尝试执行 forbidden write，而 API 不暴露该 capability。
- Provider adapter import path 无法触达 repository modules。
- Slice 01 中 verified Project context 之前仍阻塞 repository access。
- Attempt reservation 通过 expected task status / current stage guard 避免重复 runner claim。

## 10. Commit 策略

如果该实现任务明确允许 commits，则在 `pytest tests/integration/test_repository_uow_core.py` 通过后做一个小实现 commit。只 stage 本 slice 的 repository / UoW contract 和 test files。

## 11. 风险与范围陷阱

- 在 FakeProvider slice 需要之前构建完整 ORM layer 或 DDL suite。
- 为方便而向 WorkflowLoopEngine 暴露 sessions。
- 过早让 QualityCheckService 感知 persistence。
- 因 StageExecutor 靠近 provider execution 而给它 broad repository access。
- 将 conflict handling 隐藏成 generic exception，而不是 workflow-decision input。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 02，即 MVP-0 FakeProvider backend tests 所需的最小 repository 和 Unit of Work core。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/persistence-readiness-dd-v0.1.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/implementation/mvp0-fakeprovider-slice/slices/02-repository-and-uow-core.md

Allowed files:
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/workflow/** only for minimal contract DTOs
- tests/integration/test_repository_uow_core.py
- tests/conftest.py
- tests/fixtures/**

Forbidden files:
- Provider adapter code with repository or SQLite dependency
- StageExecutor code that writes active pointers, QualityIssues, WorkflowDecisions, retry budget, or stage completion
- UI/API/frontend files
- real providers or prompt templates
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- Repository / DAO is the only SQLite access entry.
- WorkflowLoopEngine-facing code must not need SQL/session objects.
- StageExecutor may use only StageEvidenceWriter for tool evidence.
- Provider adapters must receive no persistence dependency.
- Use named operations, not generic Repository<T>.

Validation command:
pytest tests/integration/test_repository_uow_core.py

Expected output:
- Minimal repository groups and UoW helpers exist.
- Acceptance transaction placeholder has expected-state guards.
- StageEvidenceWriter is narrow.
- Tests prove SQL/session details do not leak.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- A broad ORM/migration framework becomes necessary.
- Any provider adapter needs SQLite/repository access.
- StageExecutor needs active pointer, issue, decision, or retry writes.
- Validation command is unavailable or failing for unrelated reasons.
```
