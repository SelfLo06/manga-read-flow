# Slice 03：ArtifactService and Import

## 1. 目标

规划单个 Page 的 original image import 和 official artifact registration。

本 slice 证明 filesystem / artifact metadata 边界：original bytes 位于 Project workspace，SQLite 只保存 metadata，并且只有当 original artifact pointer 与 Batch / Page rows 一起 commit 时，Page import state 才有效。

## 2. 为什么现在做这个 slice

Project store 和 repository / UoW 边界就绪后，系统可以安全登记 official artifacts 并创建 Page import state。FakeProvider stages 需要 original artifact 作为 durable input，recovery 也需要在任何 workflow processing 开始前拥有 artifact metadata。

决策：

- MVP-0 中 import 实现为 ApplicationService / import use case，而不是 WorkflowLoopEngine stage。
- ArtifactService 是唯一 official artifact lifecycle 入口。
- Artifact paths 使用 project-relative。
- Original images 是 permanent originals，永不覆盖。
- Import acceptance 通过 repository / UoW 提交 Page original pointer 和 content state。

被拒绝的备选方案：

- Provider 或 workflow code 直接写 official workspace paths。
- Page rows 存 authoritative file paths，而不是 artifact ids。
- 将 original image bytes 存入 SQLite。
- 在 original artifact metadata 和 pointer 一起 commit 前，就把 Page 视为 imported。

## 3. 来自先前设计的输入

- `docs/design/data-model/final/data-model-dd-v0.1.md`：ProcessingArtifact metadata、Page original pointer、artifact states。
- `docs/design/execution-contract/final/artifact-service-contract.md`
- `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
- `docs/design/persistence/final/unit-of-work-and-transactions.md`：import transaction。
- `docs/design/persistence/final/fakeprovider-persistence-readiness.md`：mandatory original artifact。
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `src/manga_read_flow/artifacts/**`
- `src/manga_read_flow/application/**`，仅用于 import use case。
- `src/manga_read_flow/persistence/**`，用于 import 所需 artifact metadata 和 content state repository operations。
- `src/manga_read_flow/domain/**`，用于 artifact / page DTOs。
- `tests/integration/test_import_and_artifactservice.py`
- `tests/fixtures/**`，用于 tiny fake image fixture。

## 5. 禁止变更

- WorkflowLoopEngine stage implementation。
- Provider adapters writing official artifacts。
- Export artifacts、ZIP、manifest 或 `ExportRecord`。
- SQLite 中的 image BLOB storage。
- 覆盖 original files。
- 超出 import / missing detection 最小状态的 cleanup scheduler 或完整 retention policy。
- UI / API upload routes。
- 真实 provider integrations。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 添加 ArtifactService path boundary checks，防止 path traversal，并确保 files 位于 Project workspace 下。
3. 添加 original artifact registration，包含 project-relative path、hash、byte size、MIME / type metadata、可行时的 dimensions、retention class 和 safety flags。
4. 添加 import use case：校验本地 image fixture、调用 ArtifactService，并提交 Batch / Page import state 与 `Page.original_artifact_id`。
5. 添加 missing / corrupt artifact detection 支持，作为后续 recovery 所需的 metadata state update 或 service report。
6. 添加测试，证明 bytes 保留在 filesystem，SQLite 只保存 metadata。
7. 添加测试，证明 rerun 或 duplicate filename import 不会覆盖 original artifact。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_import_and_artifactservice.py
```

## 8. 验收标准

- Original image 通过 ArtifactService 被复制或存储到 Project workspace。
- `processing_artifacts` metadata 持久化 project-relative path、hash、size、type、retention 和 `storage_state = present`。
- Page 指向 `original_artifact_id`。
- Original image bytes 保留在 filesystem，不存入 SQLite。
- Original image 永不覆盖；duplicate names 通过 deterministic 或 unique path handling 变安全。
- 删除或损坏 artifact 后，可以在后续检测为 missing / hash mismatch，且不由 WorkflowLoopEngine 决定 outcome。

## 9. 需要测试的失败场景

- Import path traversal attempt。
- Unsupported file extension 或 MIME / type。
- 同一 Project 中 duplicate original filename。
- Original artifact file 在 registration 后被删除。
- 文件损坏后的 hash mismatch。
- Artifact registration 后 import transaction 失败；artifact 保持 official，但 Page 在 pointer commit 前不视为 imported。

## 10. Commit 策略

如果明确允许 commits，则在 `pytest tests/integration/test_import_and_artifactservice.py` 通过后做一个聚焦实现 commit。只 stage 本 slice 的 ArtifactService、import use case、repository additions、fixtures 和 tests。

## 11. 风险与范围陷阱

- 构建完整 upload / API behavior，而不是 backend import use case。
- 添加 artifact paths 时顺手实现 export output。
- 让 ArtifactService 对 missing files 决定 workflow rebuild、warning、pause 或 block。它只应报告 artifact state。
- 使用 absolute paths 作为 domain truth。metadata 中使用 project-relative artifact paths。
- 在 active outputs 存在前添加 cleanup scheduler complexity。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 03，即 MVP-0 的 ArtifactService original registration 和 one-Page import。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/execution-contract/final/artifact-service-contract.md
- docs/design/execution-contract/final/execution-contract-dd-v0.1.md
- docs/design/persistence/final/unit-of-work-and-transactions.md
- docs/design/persistence/final/fakeprovider-persistence-readiness.md
- docs/implementation/mvp0-fakeprovider-slice/slices/03-artifactservice-and-import.md

Allowed files:
- src/manga_read_flow/artifacts/**
- src/manga_read_flow/application/** for import use case only
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- tests/integration/test_import_and_artifactservice.py
- tests/fixtures/**

Forbidden files:
- WorkflowLoopEngine full stage implementation
- Provider adapters writing official artifacts
- UI/API/frontend files
- real providers
- export output, ZIP, manifest, or ExportRecord code
- docs/design/**/final/**

Implementation boundaries:
- ArtifactService owns official artifact path, hash, registration, retention metadata, and missing detection.
- ArtifactService does not decide retry, fallback, warning, block, or readiness.
- Repository/DAO remains the only SQLite access entry.
- Original images are never overwritten.
- No image bytes or large payloads in SQLite.

Validation command:
pytest tests/integration/test_import_and_artifactservice.py

Expected output:
- One Page can be imported through backend service code.
- Original artifact metadata is persisted.
- Page original artifact pointer is set.
- Filesystem bytes and SQLite metadata remain separated.
- Missing/corrupt artifact can be detected as artifact evidence.

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementation requires UI/API upload routes.
- Implementation requires export output.
- ArtifactService starts making workflow decisions.
- Provider adapter needs official artifact registration authority.
- Validation command is unavailable or failing for unrelated reasons.
```
