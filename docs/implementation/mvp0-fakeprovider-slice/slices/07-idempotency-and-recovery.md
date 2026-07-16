# Slice 07：Idempotency and Recovery

## 1. 目标

规划 MVP-0 FakeProvider single-Page backend slice 的第一批幂等重跑与崩溃恢复验证。

本 slice 证明 workflow 可以复用未变化的 OCR / translation / cleaned / typeset outputs，在选定 crash 后恢复，处理 official-but-unselected artifacts，并在不只依赖 Page.status 或 timestamps 的情况下响应 missing active artifacts。

## 2. 为什么现在做这个 slice

Happy path 和 quality paths 已经创建 recovery 需要的 durable evidence。最后一个 MVP-0 后端规划 slice 会在接入任何真实 provider 或 UI 之前，验证这些 evidence 在 reruns 和 crashes 后是否足够，因为真实依赖会让 failures 代价更高。

决策：

- Idempotency 是 WorkflowLoopEngine / repository decision，不是 Provider Adapter decision。
- Reuse 通过 `WorkflowAttempt.status = reused_cached` 和 / 或 `WorkflowDecision.decision_type = reuse_cached_result` 可审计。
- Recovery 优先使用 committed results、active pointers、artifact metadata、decisions、attempts 和 dependency hashes。
- Official unselected artifacts 只是 evidence / reuse candidates，绝不按 latest timestamp 选择。
- ArtifactService 标记 missing / hash-invalid artifacts；WorkflowLoopEngine 决定 rebuild、warning、pause 或 block。

被拒绝的备选方案：

- 每次 unchanged Page 都重新运行 providers。
- 从 Page.status 推断 recovery success。
- 按 timestamp promote latest artifact / result。
- 在 recovery 中不经过正常 validation / acceptance replay，就把 raw provider temp output 解析成 accepted results。
- 让 ArtifactService 在 missing file detection 后决定 workflow outcome。

## 3. 来自先前设计的输入

- `docs/design/workflow-state/final/recovery-rules.md`
- `docs/design/workflow-state/final/stale-propagation-rules.md`
- `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
- `docs/design/persistence/final/repository-contract-minimal.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`
- `docs/design/data-model/final/data-model-dd-v0.1.md`
- `docs/design/execution-contract/final/artifact-service-contract.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/workflow/**`
- 如创建单独 recovery module，则可修改 `src/manga_read_flow/recovery/**`。
- `src/manga_read_flow/persistence/**`，用于 recovery snapshots、reuse lookups、task claim / repair 和 guarded acceptance。
- `src/manga_read_flow/artifacts/**`，用于 missing / hash validation state updates。
- `src/manga_read_flow/domain/**`
- `src/manga_read_flow/providers/**`，仅用于 FakeProvider call-count / test modes。
- `tests/integration/test_idempotency_and_recovery.py`
- `tests/fixtures/**`

## 5. 禁止变更

- 真实 provider integrations 或 prompt templates。
- Batch-scale workflow broadening。
- UI / API / frontend routes。
- Export output、ZIP、manifest 或 `ExportRecord`。
- Timestamp-selected active outputs。
- Page.status-only recovery logic。
- ArtifactService retry / fallback / warning / block / readiness decisions。
- Provider Adapter cache decisions。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 使用 dependency keys 和 artifact validation，为 OCR、translation、cleaned artifacts 和 typeset artifacts 添加 repository reuse lookups。
3. 添加可审计 reuse decision / attempt persistence。
4. 添加 rerun unchanged Page integration test，证明没有重复 provider calls，也没有重复 active result rows。
5. 添加 OCR acceptance 后 crash simulation；recovery 从 translation 继续且不重跑 OCR。
6. 添加 artifact registration 后、acceptance 前 crash simulation；official unselected artifact 保持 unselected，且不会按 timestamp 选择。
7. 添加 missing active artifact 场景；ArtifactService 标记 `storage_state = missing`。
8. 根据 evidence 和 policy 添加 WorkflowLoopEngine recovery decisions：rebuild、warning、pause 或 block。
9. 添加 recovery repair tests，使用 tasks、attempts、decisions、active pointers、dependency hashes、artifacts、issues 和 TextBlock statuses，而不是只用 Page.status。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_idempotency_and_recovery.py
```

## 8. 验收标准

- Unchanged rerun 避免对可复用 OCR、translation、cleaning 和 typesetting outputs 进行重复 provider calls。
- Reuse 通过 attempt 或 decision evidence 可审计。
- 不创建重复 active result rows。
- OCR acceptance 后 crash 可以从 translation 继续，且不重跑 OCR。
- Registered-but-unselected artifact 不会按 latest timestamp 被选中。
- Missing active artifact 变为 `storage_state = missing`。
- WorkflowLoopEngine 在 missing artifact evidence 后决定 rebuild / warning / pause / block。
- Recovery 不只依赖 Page.status。

## 9. 需要测试的失败场景

- Compatible dependency hashes 下，unchanged Page rerun。
- Dependency hash 变化后 rerun 不应复用 stale result。
- OCRResult 和 active OCR pointer committed 后 crash。
- Typeset artifact registration 后、active pointer acceptance 前 crash。
- Missing active cleaned 或 typeset artifact。
- Recovery 期间存在 open blocking issue，阻止 pure readiness。
- Locked translation 没有 explicit override 时，不会被 reuse 替换。

## 10. Commit 策略

如果明确允许 commits，则在 `pytest tests/integration/test_idempotency_and_recovery.py` 通过后做一个聚焦实现 commit。只 stage 本 slice 的 workflow / recovery、persistence、artifact、FakeProvider test support、fixture 和 test files。

## 11. 风险与范围陷阱

- 扩展到 full batch recovery，而不是一个 Page。
- 将 failed / refused attempts 当作 reusable successes。
- 因 dependency keys 太小而过度复用 stale results。
- 因缺少 artifact validation 而复用不足。
- 未经正常 ArtifactService registration 和 acceptance 就 promote temp / orphan files。
- 添加 cleanup scheduler 或 export records 来解释 missing artifacts。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 07，即 MVP-0 single-Page FakeProvider backend slice 的 idempotency 和 crash recovery validation。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/workflow-state/final/workflow-state-dd-v0.1.md
- docs/design/workflow-state/final/recovery-rules.md
- docs/design/workflow-state/final/stale-propagation-rules.md
- docs/design/persistence/final/repository-contract-minimal.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/design/execution-contract/final/artifact-service-contract.md
- docs/implementation/mvp0-fakeprovider-slice/slices/07-idempotency-and-recovery.md

Allowed files:
- src/manga_read_flow/workflow/**
- src/manga_read_flow/recovery/** if needed
- src/manga_read_flow/persistence/**
- src/manga_read_flow/artifacts/**
- src/manga_read_flow/domain/**
- src/manga_read_flow/providers/** only for FakeProvider test support
- tests/integration/test_idempotency_and_recovery.py
- tests/fixtures/**

Forbidden files:
- real providers or prompt templates
- Batch-scale workflow broadening
- UI/API/frontend files
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- Recovery must not rely only on Page.status.
- Active result/artifact selection must not use latest timestamp.
- Provider Adapter must not decide cache reuse.
- ArtifactService marks storage state but does not decide rebuild, warning, pause, block, or readiness.
- WorkflowLoopEngine owns reuse and recovery decisions.

Validation command:
pytest tests/integration/test_idempotency_and_recovery.py

Expected output:
- Unchanged reruns reuse results/artifacts audibly.
- Crash after OCR acceptance resumes from translation.
- Official unselected artifacts remain unselected unless accepted.
- Missing active artifact is marked missing and loop decision is persisted.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires real providers, UI/API routes, export output, or batch-scale workflow.
- Recovery needs Page.status-only or timestamp-based active selection.
- ArtifactService needs workflow decision authority.
- Validation command is unavailable or failing for unrelated reasons.
```
