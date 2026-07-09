# Slice 04：FakeProvider and StageExecutor

## 1. 目标

规划 detection、OCR、translation、cleaning 和 typesetting 的 deterministic FakeProvider contracts 与 StageExecutor evidence boundary。

本 slice 证明 provider-style stage execution 可以在不访问 SQLite、不直接登记 official artifacts、不创建 QualityIssues、不更新 active pointers、不创建 WorkflowDecisions 的情况下，生成 deterministic outputs 和 failures。

## 2. 为什么现在做这个 slice

Project store、repositories、UoW 和 ArtifactService 边界已经可用。下一个风险是 provider execution 周围的边界漂移。本 slice 在 WorkflowLoopEngine 开始根据 evidence 做决策之前，隔离 provider calls 和 stage evidence。

决策：

- FakeProvider 使用真实 provider result envelope：`success`、`partial_success`、`failure`、`refusal` 和 `invalid_output`。
- FakeProvider modes 是 deterministic，并通过 task / profile / test configuration 让测试可见，而不是隐藏在 process globals 中。
- Providers 只能在 attempt temp root 下写 temp outputs。
- StageExecutor 只通过 `StageEvidenceWriter` 记录 sanitized tool evidence。
- Provider output 之后通过 ArtifactService 执行 official artifact registration，但 active pointer selection 在这里仍被禁止。

被拒绝的备选方案：

- Providers 返回 OCRResult、TranslationResult、QualityIssue、WorkflowDecision 或 artifact ids。
- StageExecutor 执行 retry / fallback / skip / warning / block 逻辑。
- 在 SQLite write transactions 内执行 provider calls。
- 在 FakeProvider validation 之前接入真实 OCR / LLM / cleaner / typesetter integrations。

## 3. 来自先前设计的输入

- `docs/design/execution-contract/final/provider-adapter-contract.md`
- `docs/design/execution-contract/final/stage-executor-contract.md`
- `docs/design/execution-contract/final/fakeprovider-readiness.md`
- `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/providers/**`
- `src/manga_read_flow/workflow/stage_executor*`
- `src/manga_read_flow/workflow/stages/**`
- `src/manga_read_flow/artifacts/**`，仅用于 stage outputs 需要的 temp-to-official registration calls。
- `src/manga_read_flow/persistence/**`，仅用于 `StageEvidenceWriter` support。
- `src/manga_read_flow/domain/**`，用于 provider / stage DTOs。
- `tests/integration/test_fakeprovider_stageexecutor.py`
- `tests/fixtures/**`

## 5. 禁止变更

- WorkflowLoopEngine final decision logic。
- Active OCR / translation / cleaned / typeset pointer updates。
- QualityIssue creation 或 lifecycle persistence。
- WorkflowDecision creation。
- Retry、fallback、skip、warning、pause、block 或 readiness decisions。
- 真实 provider integrations、真实 translation prompt templates、cloud calls 或 local OCR / model calls。
- UI / API / frontend / export code。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 定义最小 provider input / output DTOs 和 `ProviderResult` envelope。
3. 实现 FakeProvider modes：
   - deterministic detection success；
   - deterministic OCR success；
   - deterministic translation success；
   - invalid translation output；
   - partial translation output；
   - provider refusal；
   - cleaning skip or success；
   - typesetting overflow or success。
4. 实现 StageExecutor：reserve / use stage context，在 SQLite write transactions 之外调用 provider，normalize result / failure / refusal，并且只通过 `StageEvidenceWriter` 持久化 sanitized tool evidence。
5. 对 cleaning / typesetting success，确保 temp file outputs 可以通过 ArtifactService 登记为 official 但 unselected artifacts。
6. 添加测试，证明没有 provider 接收 repository、SQLite 或 official artifact registration access。
7. 添加测试，证明 StageExecutor 不创建 WorkflowDecision，也不写 active pointer。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_fakeprovider_stageexecutor.py
```

## 8. 验收标准

- FakeProvider 为 detection、OCR、translation、cleaning 和 typesetting 生成 deterministic success outputs。
- FakeProvider 生成 deterministic invalid translation 和 refusal outputs。
- StageExecutor 只通过 `StageEvidenceWriter` 记录 sanitized ToolRunLog / attempt evidence。
- Provider call 不持有 SQLite write transaction。
- Temp outputs 在 ArtifactService registration 前不是 official artifacts。
- 本 slice 中登记的 official artifacts 只是 unselected evidence。
- StageExecutor 不更新 active pointers、QualityIssues、WorkflowDecisions、retry budgets 或 readiness state。

## 9. 需要测试的失败场景

- Provider refusal 创建 refused ProviderResult 和 sanitized tool evidence，但尚不创建 QualityIssue 或 WorkflowDecision。
- Invalid translation output 被捕获为 provider / stage evidence，不选择 active translation。
- Cleaning skip 返回为后续 QualityCheck / loop decision 的 evidence。
- Typesetting overflow 返回 preview / evidence，但不产生 readiness。
- Artifact registration failure 作为 stage evidence 返回给 loop，而不是隐藏成 provider success。
- Provider call 尝试访问 repository / SQLite，测试证明不存在这种 dependency。

## 10. Commit 策略

如果明确允许 commits，则在 `pytest tests/integration/test_fakeprovider_stageexecutor.py` 通过后做一个聚焦实现 commit。只 stage 本 slice 的 provider、StageExecutor、evidence-writer support、fixtures 和 tests。

## 11. 风险与范围陷阱

- 将 StageExecutor 变成隐藏的 WorkflowLoopEngine。
- 让 provider failure modes 包含 policy bypass 或 evasion behavior。
- 允许 providers 写 official workspace paths。
- 因为 artifact 最新就把 registered artifact 当作 active。
- 在 deterministic FakeProvider evidence 被证明之前添加真实 provider clients。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 04，即 deterministic FakeProvider modes 和 StageExecutor evidence boundary。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/execution-contract/final/provider-adapter-contract.md
- docs/design/execution-contract/final/stage-executor-contract.md
- docs/design/execution-contract/final/fakeprovider-readiness.md
- docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/implementation/mvp0-fakeprovider-slice/slices/04-fakeprovider-and-stageexecutor.md

Allowed files:
- src/manga_read_flow/providers/**
- src/manga_read_flow/workflow/stage_executor*
- src/manga_read_flow/workflow/stages/**
- src/manga_read_flow/artifacts/** only for temp output registration calls
- src/manga_read_flow/persistence/** only for StageEvidenceWriter support
- src/manga_read_flow/domain/**
- tests/integration/test_fakeprovider_stageexecutor.py
- tests/fixtures/**

Forbidden files:
- WorkflowLoopEngine decision implementation
- active pointer update code
- QualityIssue lifecycle code
- WorkflowDecision creation code
- real provider clients or real prompt templates
- UI/API/frontend/export files
- docs/design/**/final/**

Implementation boundaries:
- Provider Adapter must not access SQLite.
- Provider Adapter must not register official artifacts.
- Provider Adapter must not create QualityIssues.
- Provider Adapter must not decide retry, fallback, skip, warning, block, or readiness.
- StageExecutor must not update active pointers or create WorkflowDecision.
- StageExecutor uses StageEvidenceWriter only for tool evidence.
- Provider calls must not hold SQLite write transactions.

Validation command:
pytest tests/integration/test_fakeprovider_stageexecutor.py

Expected output:
- Deterministic FakeProvider success, invalid, partial, refusal, skip, and overflow modes exist.
- StageExecutor records only evidence.
- Temp outputs can become official unselected artifacts through ArtifactService.
- Tests prove provider and stage boundaries.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- A real provider, cloud call, local OCR/model call, or real prompt template becomes necessary.
- Provider or StageExecutor needs forbidden persistence/decision authority.
- Validation command is unavailable or failing for unrelated reasons.
```
