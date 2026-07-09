# Slice 06：Quality Issues and Readiness

## 1. 目标

规划带 issue 的 FakeProvider paths、最小 QualityCheckService behavior、provider refusal handling 和 readiness gating。

本 slice 证明 invalid / partial outputs、provider refusal、cleaning skip 和 typesetting overflow 会变成可见 workflow evidence，并且不能静默变成纯 `ready_for_export`。

## 2. 为什么现在做这个 slice

Happy path 已证明 loop 可以完成。下一个实现风险是 false readiness：如果 QualityIssue 和 WorkflowDecision evidence 没有接入 acceptance 与 readiness checks，partial translations、provider refusals、skipped cleaning 或 typesetting overflow 可能被隐藏。

决策：

- MVP-0 中 QualityCheckService 保持 repository-free，并返回 issue drafts / reports。
- WorkflowLoopEngine 在 acceptance 期间持久化 QualityIssues、WorkflowDecision 和 WorkflowDecisionIssue links。
- Provider refusal 是一等 evidence，不是 generic crash。
- Pure `ready_for_export` 会被 open blocking issues 和 unresolved skip / warning states 阻塞。
- Warning readiness 是显式状态；当 policy 允许时，它保持可见为 `ready_for_export_with_warnings`。

被拒绝的备选方案：

- Provider Adapter 创建 QualityIssues。
- QualityCheckService 推进 workflow state。
- 将 partial translation 视为 full success。
- 将 provider refusal 当成 same-provider retry / prompt evasion。
- 允许 warning state 静默变成 pure readiness。

## 3. 来自先前设计的输入

- `docs/design/execution-contract/final/quality-check-contract.md`
- `docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md`
- `docs/design/execution-contract/final/fakeprovider-readiness.md`
- `docs/design/workflow-state/final/decision-matrix.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/quality/**`
- `src/manga_read_flow/workflow/**`
- `src/manga_read_flow/persistence/**`，用于 issue、decision-issue、readiness 和 acceptance operations。
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**`，仅用于 deterministic FakeProvider issue modes。
- `tests/integration/test_quality_issues_and_readiness.py`
- `tests/fixtures/**`

## 5. 禁止变更

- Provider adapters 创建 QualityIssues 或决定 retry / fallback / skip / warning / block。
- QualityCheckService 更新 active pointers、stage status、task status、Page status 或 WorkflowDecision。
- 实际 export output、ZIP、manifest artifact 或 `ExportRecord`。
- Policy bypass / evasion behavior 或针对 refusal 的 prompt workarounds。
- 真实 provider integrations 或 prompt templates。
- UI / API / frontend files。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 为以下场景实现最小 QualityCheckService reports：
   - invalid translation；
   - partial translation / missing block；
   - provider refusal；
   - cleaning skip；
   - typesetting overflow。
3. 确保 reports 包含 issue drafts，字段包括 target scope、discovered stage、root stage、issue type、error code、severity、blocking flag、status、related attempt / tool / artifact / result refs，以及适用时的 suggested action keys。
4. 扩展 WorkflowLoopEngine acceptance，在 decisions 链接 issues 时持久化 QualityIssues 和 WorkflowDecisionIssue links。
5. 实现区分 pure readiness、warning readiness 和 block 的 readiness query。
6. 如果 Slice 04 尚未提供，添加 issue-bearing scenarios 所需 FakeProvider modes。
7. 为 invalid / partial translation、provider refusal、warning readiness 和 blocking readiness 添加 integration tests。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_quality_issues_and_readiness.py
```

## 8. 验收标准

- Invalid 或 partial translation 会创建持久化 QualityIssue evidence。
- Provider refusal 会创建 ToolRunLog、refused WorkflowAttempt、QualityIssue、WorkflowDecision 和 WorkflowDecisionIssue link。
- 不出现 policy bypass / evasion data。
- Open blocking QualityIssue 阻止纯 `ready_for_export`。
- Warning state 保持可见，并且只有 active ProcessingProfileSnapshot policy 允许时，才能变为 `ready_for_export_with_warnings`。
- QualityCheckService 不推进 workflow state。
- Provider Adapter 不创建 QualityIssues。

## 9. 需要测试的失败场景

- Invalid translation JSON 在 retry budget 耗尽后，按 policy 变为 block 或 pause。
- Partial translation 只在被 accepted 时持久化 valid block results，并为 missing / invalid blocks 创建 issues。
- Provider refusal 记录 `is_provider_refusal` evidence，且没有 same-provider evasion attempt。
- Cleaning skip 不能变为纯 `ready_for_export`。
- Typesetting overflow 按 severity / profile block 或 mark warning readiness。
- 手动 seed 到 readiness scope 的 blocking issue 阻止 pure readiness。

## 10. Commit 策略

如果明确允许 commits，则在 `pytest tests/integration/test_quality_issues_and_readiness.py` 通过后做一个聚焦实现 commit。只 stage 本 slice 的 quality、workflow、persistence、FakeProvider mode、fixture 和 test files。

## 11. 风险与范围陷阱

- 实现完整 quality taxonomy，而不是最小 MVP-0 issue modes。
- 将 user-facing UI copy 或 localization 纳入 backend readiness。
- 让 refusal handling 漂移成 prompt bypass behavior。
- 将 warnings 当成 success，同时不保留 issue visibility。
- 为 blocked readiness 创建 ExportRecord。本 slice 止步于 workflow readiness。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 06，即 MVP-0 的最小 QualityCheckService issue paths 和 readiness gating。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/decision-matrix.md
- docs/design/execution-contract/final/quality-check-contract.md
- docs/design/execution-contract/final/error-and-issue-taxonomy-minimal.md
- docs/design/execution-contract/final/fakeprovider-readiness.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/06-quality-issues-and-readiness.md

Allowed files:
- src/manga_read_flow/quality/**
- src/manga_read_flow/workflow/**
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for deterministic FakeProvider issue modes
- tests/integration/test_quality_issues_and_readiness.py
- tests/fixtures/**

Forbidden files:
- Provider adapters creating QualityIssues or making workflow decisions
- QualityCheckService advancing workflow state or active pointers
- export output, ZIP, manifest, or ExportRecord code
- real providers or prompt templates
- UI/API/frontend files
- docs/design/**/final/**

Implementation boundaries:
- QualityCheckService owns quality issue detection and root-stage attribution.
- QualityCheckService returns issue drafts/reports but does not persist workflow state.
- WorkflowLoopEngine owns retry/fallback/warning/block/readiness decisions.
- Provider refusal must be recorded as first-class evidence.
- No provider policy bypass or evasion behavior.

Validation command:
pytest tests/integration/test_quality_issues_and_readiness.py

Expected output:
- Invalid/partial translation, provider refusal, cleaning skip, and typesetting overflow are issue-bearing paths.
- WorkflowDecisionIssue links exist when decisions link persisted issues.
- Open blockers prevent pure ready_for_export.
- Warning readiness remains explicit and policy-controlled.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires actual export output, UI/API routes, real providers, or prompt templates.
- QualityCheckService needs repository writes or state advancement.
- Provider refusal handling requires bypass/evasion logic.
- Validation command is unavailable or failing for unrelated reasons.
```
