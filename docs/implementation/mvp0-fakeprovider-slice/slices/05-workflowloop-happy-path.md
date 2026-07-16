# Slice 05：WorkflowLoop Happy Path

## 1. 目标

规划第一个完整单 Page happy path：使用 deterministic FakeProvider evidence，从 imported Page 推进到 `ready_for_export`。

本 slice 引入 WorkflowLoopEngine orchestration、acceptance transactions、active pointer updates 和 export readiness checks，但不实现实际 export output。

## 2. 为什么现在做这个 slice

底层边界已经存在：Project store、repositories / UoW、ArtifactService import、FakeProvider 和 StageExecutor。系统现在可以验证核心端到端状态转移，证明架构能串起一个 Project、一个 Batch 和一个 Page。

决策：

- WorkflowLoopEngine 拥有 stage decisions 和 acceptance。
- Acceptance transaction 是唯一选择 active OCR、translation、cleaned 和 typeset outputs 的边界。
- `export_check` 在 scope 内；实际 export output 在 scope 外。
- ProcessingProfileSnapshot 为 FakeProvider deterministic bootstrap，且不包含 secrets。
- WorkflowAttempt、ToolRunLog、WorkflowDecision、ProcessingArtifact 和 profile snapshot evidence 必须可在 tests 中检查。

被拒绝的备选方案：

- 在 StageExecutor 中更新 active pointers。
- 按 timestamp 选择 latest result / artifact。
- 将 Page.status 当作 recovery truth 的来源。
- 创建 ExportRecord 或 export artifact 来证明 readiness。

## 3. 来自先前设计的输入

- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/workflow-state/final/state-vocabulary.md`
- `docs/design/workflow-state/final/stage-transition-table.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/execution-contract/final/stage-executor-contract.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/workflow/**`
- `src/manga_read_flow/application/**`，仅用于 task start / run use case。
- `src/manga_read_flow/persistence/**`，用于 acceptance、readiness、workflow、result、content、glossary 和 artifact metadata operations。
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**`，仅使用既有 FakeProvider modes，不添加真实 providers。
- `src/manga_read_flow/artifacts/**`，仅用于 stages 已要求的 artifact validation / registration calls。
- `tests/integration/test_workflow_happy_path.py`
- `tests/fixtures/**`

## 5. 禁止变更

- 实际 export output、ZIP、manifest artifact 或 `ExportRecord`。
- FastAPI routes、frontend UI 或 Web UI behavior。
- 真实 providers 或真实 prompt templates。
- 超出最小 no-blocker happy path 的 quality issue-heavy paths。
- 超出后续需要的 happy-path reuse hooks 的 idempotency / recovery breadth。
- WorkflowLoopEngine 直接访问 SQL 或 ORM session。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 为单个 imported Page 添加 ProcessingTask creation 和 deterministic ProcessingProfileSnapshot bootstrap。
3. 实现 WorkflowLoopEngine happy-path stage progression：
   - detection；
   - OCR；
   - translation；
   - translation_check，在 fake happy path 中作为 no-blocker pass；
   - cleaning；
   - typesetting；
   - export_check。
4. 使用 StageExecutor 处理 provider / tool evidence，使用 ArtifactService 登记 official artifact。
5. 实现 acceptance transactions，一起创建 TextBlocks、OCRResults、TranslationResults、active OCR / translation pointers、cleaned / typeset artifact pointers、WorkflowDecisions、retry budget / task progress 和 stage statuses。
6. 确保 active pointers 只由 acceptance 选择，绝不按 latest timestamp。
7. 实现 readiness query：没有 open blocking issues，且存在 present / hash-valid active typeset artifact。
8. 添加从 Project / Page import 到 `ready_for_export` 的 happy-path integration test。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_workflow_happy_path.py
```

## 8. 验收标准

- 一个 Project、一个 Batch 和一个 Page 跑完 fake detection、OCR、translation、cleaning、typesetting 和 `export_check`。
- TextBlocks 从 fake detection 创建。
- OCRResults 和 TranslationResults 是不可变版本，并通过 active pointers 选择。
- Page active cleaned 和 typeset artifact pointers 通过 acceptance 设置。
- WorkflowAttempt、ToolRunLog、WorkflowDecision、ProcessingArtifact 和 ProcessingProfileSnapshot evidence 存在。
- Page 到达 `ready_for_export`。
- 不需要 ExportRecord、output export artifact、ZIP 或 manifest。

## 9. 需要测试的失败场景

- 当 active pointer 或 stage status 并发变化时，acceptance guard 失败；loop reload 或报告 conflict，而不是静默覆盖。
- 缺少 active OCR pointer 会阻塞 translation acceptance。
- 缺少 active translation pointer 会阻塞 typesetting acceptance。
- Typeset artifact 已登记但未 accepted 时，保持 unselected，且不具备 readiness-effectiveness。
- 如果手动 seed open blocking issue query，会阻止 pure readiness。

## 10. Commit 策略

如果明确允许 commits，则在 `pytest tests/integration/test_workflow_happy_path.py` 通过后做一个聚焦实现 commit。只 stage happy path 所需的 workflow、repository、domain、artifact / provider touchpoints、fixtures 和 tests。

## 11. 风险与范围陷阱

- 实现 broad batch workflow，而不是一个 Page。
- 创建 export output 来满足 readiness。
- 以阻碍 Slice 06 quality paths 的方式将 translation_check 折叠进 translation。
- 让 Page.status 成为 recovery / readiness 的唯一事实。
- 在 expected-state transaction 之外接受 artifacts / results。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 05，即第一个完整 FakeProvider happy path：从一个 imported Page 到 ready_for_export。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/state-vocabulary.md
- docs/design/workflow-state/final/stage-transition-table.md
- docs/design/workflow-state/final/decision-matrix.md
- docs/design/execution-contract/final/stage-executor-contract.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/05-workflowloop-happy-path.md

Allowed files:
- src/manga_read_flow/workflow/**
- src/manga_read_flow/application/** for task start/run use case only
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for existing FakeProvider modes
- src/manga_read_flow/artifacts/** only for stage artifact calls
- tests/integration/test_workflow_happy_path.py
- tests/fixtures/**

Forbidden files:
- export output, ZIP, manifest, or ExportRecord code
- UI/API/frontend files
- real providers or real prompt templates
- docs/design/**/final/**

Implementation boundaries:
- WorkflowLoopEngine owns workflow decisions.
- StageExecutor must not update active pointers or create WorkflowDecision.
- QualityCheckService must not advance workflow state.
- ArtifactService must not decide retry, fallback, warning, block, or readiness.
- WorkflowLoopEngine must not depend directly on SQL or ORM session internals.
- Active result/artifact selection must use guarded active pointers, not timestamps.

Validation command:
pytest tests/integration/test_workflow_happy_path.py

Expected output:
- One imported Page reaches ready_for_export through deterministic FakeProvider.
- TextBlocks, OCRResults, TranslationResults, cleaned/typeset artifacts, attempts, logs, decisions, and profile snapshot are persisted.
- Active pointers are set only during acceptance.
- No actual export output exists.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires actual export output, UI/API routes, real providers, or prompt templates.
- WorkflowLoopEngine needs direct SQL/session access.
- Active output selection requires timestamp or Page.status-only logic.
- Validation command is unavailable or failing for unrelated reasons.
```
