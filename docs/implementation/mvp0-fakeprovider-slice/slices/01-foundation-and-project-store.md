# Slice 01：Foundation and Project Store

## 1. 目标

规划最小后端基础能力：初始化临时 `app.db`、创建 Project workspace、初始化每个 Project 独立的 `project.db`、验证 Project identity，并且只在 Project store 就绪后暴露 Project-scoped repositories。

本 slice 为后续所有 FakeProvider 工作建立可测试的 persistence shell。它不实现 workflow execution、ArtifactService import、provider calls、FastAPI routes、frontend code、真实 migrations 或 export output。

## 2. 为什么现在做这个 slice

后续所有 slices 都依赖已经验证的 `app.db + project.db` 边界。Repository、artifact、workflow、quality、idempotency 和 recovery 测试需要真实临时 SQLite files 和临时 workspace，才能验证架构边界。

决策：

- 使用一个全局 `app.db` 保存 Project registry 和 app migration ledger。
- 每个 Project 使用一个 `project.db` 保存 Project-owned content、workflow、quality、result、artifact 和 project migration data。
- 只有在 ProjectMetadata identity 和 migration readiness 通过后，才暴露 Project repositories。
- MVP-0 中 migration support 保持最小：baseline ledger 和 verification hooks，而不是生产级 Alembic topology。

被拒绝的备选方案：

- 所有 Projects 使用单一 SQLite database，因为它削弱 Project isolation 和 recovery。
- In-memory fake persistence，因为它无法验证 recovery、idempotency、migration ledgers 或 file / database consistency。
- 在 Project open verification 之前暴露 repositories，因为这会允许对不匹配或损坏的 project.db files 执行 mutation。

## 3. 来自先前设计的输入

- `AGENTS.md`：minimal-change mode、Project isolation、`app.db + project.db`、no image BLOBs、no unrelated files。
- `docs/SRS-v1.0.md`：Project、Batch、Page、task recovery、original image safety、SQLite plus filesystem。
- `docs/HLD.md`：local Web UI / FastAPI / backend architecture、SQLite / workspace storage、repository boundary。
- `docs/PROJECT-PLAN.md`：Phase 4 MVP-0 single Page backend vertical slice。
- `docs/design/data-model/final/data-model-dd-v0.1.md`：`app.db` 与 `project.db` 拆分、`ProjectMetadata`、migration ledgers。
- `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`：Project store gate、immediate app / project tables。
- `docs/design/persistence/final/migration-strategy-minimal.md`：independent migration lifecycles 和 Project open outcomes。
- `docs/implementation/mvp0-fakeprovider-slice/GOAL.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`

## 4. 实现期间允许修改的文件或目录

仅适用于未来实现任务：

- `pyproject.toml` 或等价的最小 Python project metadata，如果尚不存在。
- `src/manga_read_flow/**` 用于后端包基础，或届时已经存在的 backend package。
- `tests/integration/test_project_store_init.py`
- `tests/conftest.py`
- `tests/fixtures/**`，仅限小型非敏感 test fixtures。
- 仅当实现发现计划缺陷时，允许修改 `docs/implementation/mvp0-fakeprovider-slice/` 下的最小文档。

## 5. 禁止变更

- Production Web UI、Next.js、React 或 frontend files。
- FastAPI routes 或 API schemas。
- 真实 provider integrations。
- SQL DDL design documents、ORM model documentation 或 Alembic migration files，除非后续任务明确授权。
- `docs/design/**/final/` 下的先前最终设计文档。
- Export output、ZIP、manifest artifact 或 `ExportRecord`。
- Secrets、local config、logs、caches、build outputs、`.codex/`、`.claude/`、`.idea/` 或 generated scratch files。
- allowed implementation paths 之外的任何文件，除非用户在看到原因后明确批准。

## 6. 实现任务

1. 检查 branch 和 `git status --short`；如果存在 unrelated changes，停止。
2. 添加 persistence tests 所需的最小 backend package skeleton。
3. 添加 temporary workspace fixture，用于创建隔离目录和临时 SQLite file paths。
4. 实现足够的 app store initialization，用于创建或验证 `app.db` 和 app `schema_migrations` ledger。
5. 实现 Project creation / open scaffolding，用于创建 Project workspace 和 `project.db`。
6. 实现足够的 project store initialization，用于创建或验证 `project_metadata` 和 project `schema_migrations` ledger。
7. 将 `ready`、`identity_mismatch`、`database_missing` 和 `checksum_mismatch` 等显式 Project open outcomes 实现为 contract-level values 或 test-visible outcomes。
8. 确保只有当 open outcome 为 `ready` 时才返回 Project-scoped repository access。
9. 添加使用真实临时 SQLite files 的 integration tests。

## 7. 验证命令或测试目标

```bash
pytest tests/integration/test_project_store_init.py
```

## 8. 验收标准

- `app.db` 可以在临时 workspace 中初始化，并记录 app migration ledger。
- `project.db` 可以在 Project workspace 下初始化，并记录 project migration ledger。
- 打开 Project 时，`ProjectMetadata.project_id` 匹配 app Project registry id。
- Identity mismatch 或 missing project.db 会阻塞 repository exposure。
- Project repository access 只在 open outcome 为 `ready` 后可用。
- 不存在 UI / API / export code。
- SQLite 中不存储 image bytes 或 large payloads。

## 9. 需要测试的失败场景

- 打开一个 `project_metadata.project_id` 与 app registry 不同的 Project。
- 打开缺失 `project.db` 的 Project。
- 用 failed 或 incompatible migration ledger marker 打开。
- 在 readiness 前尝试获取 Project repositories。
- 创建第二个具有隔离 workspace 和 project.db 的 Project。

## 10. Commit 策略

如果任务 prompt 明确允许 commits，则在验证命令通过后，仅为本 slice 做一个小实现 commit。只 stage 本 slice 变更文件。不要 push。

如果由于 project scaffolding 有意尚不完整导致 validation 无法运行，停止并报告精确 blocker，不要提交部分 foundation。

## 11. 风险与范围陷阱

- 意外设计完整 migration framework，而不是最小 ledgers 和 open outcomes。
- 对已有 Project identity 静默重建 missing project.db。
- 选择与后续 backend structure 冲突的 package layout。缓解：优先使用 `src/manga_read_flow/**`，除非已经存在 backend package。
- 添加 FastAPI routes 或 UI 来“证明” Project creation。本 slice 只做后端 persistence。
- 将 identity 或 migration failures 隐藏在 tests 无法断言的 exceptions 后。

## 12. Codex 实现 prompt

```text
Goal:
实现 Slice 01，即 MVP-0 foundation 和 Project store initialization，用于临时 app.db / project.db 测试。

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/HLD.md
- docs/PROJECT-PLAN.md
- docs/design/data-model/final/data-model-dd-v0.1.md
- docs/design/persistence/final/persistence-readiness-dd-v0.1.md
- docs/design/persistence/final/migration-strategy-minimal.md
- docs/implementation/mvp0-fakeprovider-slice/GOAL.md
- docs/implementation/mvp0-fakeprovider-slice/HARNESS.md
- docs/implementation/mvp0-fakeprovider-slice/PLAN.md
- docs/implementation/mvp0-fakeprovider-slice/slices/01-foundation-and-project-store.md

Allowed files:
- pyproject.toml or equivalent minimal Python project metadata if absent
- src/manga_read_flow/**, or the existing backend package if one exists
- tests/integration/test_project_store_init.py
- tests/conftest.py
- tests/fixtures/**

Forbidden files:
- frontend/UI files
- FastAPI route files
- real provider integrations
- Alembic migrations, production SQL DDL, or ORM model documentation unless explicitly authorized
- docs/design/**/final/**
- export output, ZIP, manifest, or ExportRecord code
- secrets, logs, caches, build outputs, local config, .codex/, .claude/, .idea/

Implementation boundaries:
- Repository/DAO remains the only SQLite access entry.
- Project repositories are exposed only after Project identity and migration readiness are verified.
- Do not store image bytes or large payloads in SQLite.
- Do not add UI, API, real providers, or export output.

Validation command:
pytest tests/integration/test_project_store_init.py

Expected output:
- Temporary app.db initialization works.
- Temporary project.db initialization works.
- ProjectMetadata identity is verified.
- Repository access is blocked before readiness.
- Tests document success and failure paths.

Commit rule:
Do not commit unless the user explicitly allows commits for this implementation task. If commits are allowed, stage only the files changed for this slice and make one focused commit after validation passes.

Stop conditions:
- Unrelated dirty working tree exists.
- Implementing this slice requires UI, API routes, real providers, export output, or prior final design doc edits.
- Project open cannot be made test-visible without inventing a broad persistence framework.
- Validation command is unavailable or failing for an unrelated reason.
```
