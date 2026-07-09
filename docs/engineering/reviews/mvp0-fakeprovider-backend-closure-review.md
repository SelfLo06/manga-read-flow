# MVP-0 FakeProvider Backend Closure Review

## 1. Review 结论

- 结论：PASS_WITH_DEFERRED_RISKS
- 是否允许进入下一阶段：允许进入下一阶段，建议优先进入 Real Tool Spike 前置准备，同时可启动 API/UI 前置设计的只读/设计工作。
- 阻塞项：无 Category A blocker；无必须在进入下一阶段前立即修复的架构边界违规。

本次 review 认为 Slice 01-07 后的 MVP-0 FakeProvider backend 仍保持核心架构边界。当前风险主要是文件规模和下一阶段真实 Provider/API 化前的接缝清理，不是已经破坏职责边界的阻塞问题。

## 2. Review 范围

- 分支：`feat/slice-07-idempotency-recovery`
- 最近提交：
  - `374d57e (HEAD -> feat/slice-07-idempotency-recovery) feat(slice-07): add idempotency and recovery`
  - `1627013 (main) Merge branch 'feat/slice-06-quality-issues-readiness'`
  - `d177e67 feat(slice-06): add quality issues and readiness gates`
  - `7a65230 feat(slice-05): add workflow loop happy path`
  - `2af6c10 feat: Implement FakeProvider and StageExecutor for workflow processing`
  - `33b67d5 feat(slice-03): import pages through ArtifactService`
  - `77aaa5d feat(slice-02): add repository unit of work core`
  - `fb98736 feat: add project store foundation`
- 工作区状态：开始 review 前 `git status --short --untracked-files=all` 无输出，工作区干净。
- 已检查模块：
  - `src/manga_read_flow/application/**`
  - `src/manga_read_flow/artifacts/**`
  - `src/manga_read_flow/domain/**`
  - `src/manga_read_flow/persistence/**`
  - `src/manga_read_flow/providers/**`
  - `src/manga_read_flow/quality/**`
  - `src/manga_read_flow/workflow/**`
  - 指定的 7 个 integration test 文件
- 未检查模块及原因：
  - API/UI/frontend/export output 模块：当前仓库范围内未实现，且本 review 明确禁止新增或评审实际 API/UI/export 实现。
  - `docs/design/**/final/**`：作为来源基线读取，不修改。

## 3. 验证结果

Focused tests：

| Command | Result |
| --- | --- |
| `pytest tests/integration/test_project_store_init.py -q` | `11 passed in 0.93s` |
| `pytest tests/integration/test_repository_uow_core.py -q` | `7 passed in 0.46s` |
| `pytest tests/integration/test_import_and_artifactservice.py -q` | `7 passed in 0.63s` |
| `pytest tests/integration/test_fakeprovider_stageexecutor.py -q` | `17 passed in 1.77s` |
| `pytest tests/integration/test_workflow_happy_path.py -q` | `8 passed in 1.20s` |
| `pytest tests/integration/test_quality_issues_and_readiness.py -q` | `9 passed in 2.03s` |
| `pytest tests/integration/test_idempotency_and_recovery.py -q` | `9 passed in 2.53s` |

Full suite：

| Command | Result |
| --- | --- |
| `pytest -q` | `68 passed in 12.61s` |

测试数量判断：focused tests 合计 68，完整 `pytest -q` 也是 68 passed，符合 Slice 07 后预期。

行数统计摘要：

| Area | Total |
| --- | ---: |
| `src/manga_read_flow/**/*.py` | 6947 |
| `tests/**/*.py` | 4162 |

Source line-count review triggers：

| File | Lines |
| --- | ---: |
| `src/manga_read_flow/workflow/engine.py` | 960 |
| `src/manga_read_flow/persistence/workflow_execution_repository.py` | 875 |
| `src/manga_read_flow/persistence/content_state_repository.py` | 830 |
| `src/manga_read_flow/persistence/acceptance_repository.py` | 782 |
| `src/manga_read_flow/persistence/project_store.py` | 662 |
| `src/manga_read_flow/workflow/reuse.py` | 462 |
| `src/manga_read_flow/artifacts/service.py` | 405 |

Test line-count review triggers：

| File | Lines |
| --- | ---: |
| `tests/integration/test_workflow_happy_path.py` | 920 |
| `tests/integration/test_idempotency_and_recovery.py` | 883 |
| `tests/integration/test_fakeprovider_stageexecutor.py` | 792 |
| `tests/integration/test_quality_issues_and_readiness.py` | 622 |

只读 grep 检查摘要：

| Check | Summary |
| --- | --- |
| Direct SQL in workflow/application/providers/quality | 无输出。未发现这些层直接访问 SQLite/SQL。 |
| `QualityIssue` / `WorkflowDecision` in provider or `stage_executor.py` | 无输出。未发现 Provider 或 StageExecutor 创建 issue/decision 的信号。 |
| readiness/reuse/block keywords in provider/artifact/stage_executor | 命中主要是 `text_block` 字样、`ArtifactService` 的 `rebuildability_hint="non_rebuildable"`、StageExecutor 的 `text_block_ids`。未见 retry/fallback/readiness policy 漂移到这些模块。 |
| `latest` / `created_at DESC` / timestamp in workflow/persistence | `engine.py` 的 `latest_page` 是重新读取 Page snapshot，不是 timestamp selection；`content_state_repository.latest_text_block_versions` 返回 active pointers；`workflow_execution_repository` 用 `ORDER BY created_at, issue_id` 稳定列出 issues。未发现用 latest timestamp 选择 active result/artifact。 |
| Export/API/UI grep | `src` 无 `ExportRecord`、manifest、ZIP、`APIRouter`、`FastAPI` 命中；tests 只断言没有 export artifacts。 |

## 4. 架构边界总评

| Boundary | Status | 证据 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| Provider Adapter | PASS | `providers/fake.py` 只依赖 `domain.provider_contracts`，返回 `ProviderResult`/payload/temp refs；grep 未发现 persistence/ArtifactService/QualityIssue/WorkflowDecision。 | `FakeProvider` 模式表会继续增长；真实 Provider 前需要更正式 provider identity/config。 | 不立即重构；Real Tool Spike 前收窄 provider metadata/config 接缝。 |
| StageExecutor | PASS | `StageExecutor.execute()` 只 reserve attempt、调用 provider、写 ToolRun/Attempt evidence、经 ArtifactService 注册 stage temp outputs。public API 只有 `execute`。 | 它拥有 ArtifactService 调用，这符合 StageExecutor contract；后续不要让它接受 broad repositories。 | 保持窄 `AttemptRecorder`/`StageEvidenceWriter`。 |
| ArtifactService | PASS | `ArtifactService` 负责 original/stage output path、copy、hash、metadata registration、missing/hash validation、storage_state update。未见 readiness/retry/block 词义决策。 | `retention_class="stage_output"` 还不是最终设计词汇；cleanup/retention 前需收敛。 | P1 前定义或映射 retention vocabulary。 |
| QualityCheckService | PASS | `quality/__init__.py` repository-free，只返回 `QualityCheckReport`/`IssueDraft`。tests 验证调用前后 DB 计数不变。 | 文件放在 `__init__.py`，后续 taxonomy 增长时可读性会下降。 | 暂不拆；真实 taxonomy 增长时按 issue family 拆。 |
| WorkflowLoopEngine | RISK | 拥有 stage progression、quality acceptance、readiness、reuse orchestration；不直接 SQL，不绕过 StageExecutor，不用 timestamp 选择 active output。 | 960 行；接受逻辑分支较多。仍是合理 controller，但再加入 retry/fallback/real provider 后会逼近 God service 风险。 | 不立即重构；下一阶段只做 targeted provider/config 接缝，避免大重构 workflow。 |
| Repository / DAO | RISK | SQLite 只在 persistence 层；外部拿到 named repos/UoW，不暴露 raw connection/cursor/session。 | `content_state_repository.py` 和 `workflow_execution_repository.py` 已经多 repository class 同文件；schema bootstrap 与仓储在同文件，后续 migration 需要分清边界。 | P1/P2 观察，按 data responsibility 拆，不按行数拆。 |
| Domain DTOs | PASS | `domain/provider_contracts.py` 与 `domain/artifacts.py` 是无副作用 dataclass/Enum，不调用 provider/DB/FS。 | `ProviderRequest` 带 `Path attempt_temp_root` 是 provider temp boundary，不是 official artifact path。 | 真实 Provider 前保持 DTO 不泄漏 repository/artifact ids。 |
| Tests | PASS_WITH_DEFERRED_RISKS | 覆盖 Project store、UoW、ArtifactService/import、StageExecutor、happy path、quality/readiness、idempotency/recovery；断言 attempts/logs/decisions/issues/artifacts/pointers。 | 大测试文件使用 raw SQL 和 `_latest_decision()` timestamp helper 作观察；不是生产 active selection，但有测试脆性。 | 不立即拆；后续按主题新增文件，避免单文件继续无限增长。 |

## 5. 模块职责地图

| Module / file | Current responsibility | Should own | Should not own | Observed drift | Cohesion judgment | Coupling judgment | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `application/import_page.py` | Import Page use case，调用 ArtifactService 和 import UoW。 | 用户本地文件导入用例协调。 | Provider call、workflow decision、export。 | 无。 | 高。 | 低。 | 保持。 |
| `application/process_page.py` | 创建 deterministic Fake profile snapshot、ProcessingTask，组装 StageExecutor/WorkflowLoopEngine。 | MVP-0 process_page application entry。 | 真实 provider config、API/UI、workflow policy。 | 对 `FakeProvider` 具体类型耦合。 | 中高。 | 中。 | Real Tool Spike 前收窄 provider interface。 |
| `artifacts/service.py` | Official artifact path/copy/hash/register/validate/missing state。 | Artifact lifecycle 和 integrity evidence。 | Active pointer selection、readiness/retry/block。 | 无阻塞漂移。 | 高。 | 低到中，依赖 artifact repository。 | 保持；P1 前收敛 retention vocabulary。 |
| `domain/provider_contracts.py` | Provider envelope/request/temp refs。 | Provider DTO。 | Persistence behavior、workflow decisions。 | 无。 | 高。 | 低。 | 保持。 |
| `domain/artifacts.py` | Artifact metadata/integrity DTO。 | Artifact DTO。 | Filesystem side effect。 | 无。 | 高。 | 低。 | 保持。 |
| `providers/fake.py` | Deterministic FakeProvider modes and temp PNG outputs。 | Fake provider evidence generation。 | DB、official artifact registration、QualityIssue、WorkflowDecision、cache/retry/readiness。 | 无边界漂移。 | 高，虽模式表偏长。 | 低。 | 保持；真实 Provider 前不要扩成 policy switchboard。 |
| `quality/__init__.py` | QualityCheckService、IssueDraft、minimal issue classification。 | Issue detection/classification/root attribution drafts。 | Persistence、state advancement、WorkflowDecision。 | 无。 | 中高。 | 低。 | 暂不拆；taxonomy 增长时迁出 `__init__.py`。 |
| `workflow/stage_executor.py` | One-stage execution, provider call, evidence recording, temp artifact promotion via ArtifactService。 | Stage evidence boundary。 | Active pointers、issues、decisions、retry/readiness/reuse。 | 无。 | 高。 | 中，依赖 ArtifactService 和 evidence writer。 | 保持。 |
| `workflow/engine.py` | Main loop controller、stage acceptance、quality handling、readiness/reuse orchestration。 | Workflow decisions and semantic acceptance coordination。 | SQL、provider direct bypass outside StageExecutor、artifact lifecycle implementation、quality classification internals。 | 无 Category A drift；规模接近上限。 | 中，按 stage 方法组织仍可读。 | 中高，依赖多个 repo/service。 | No immediate refactor；下一阶段严控新增政策分支。 |
| `workflow/reuse.py` | Reuse planning, stage dependency hash, reuse attempt/decision acceptance helper。 | Idempotency/reuse decisions owned by workflow。 | Provider cache decision、artifact lifecycle implementation。 | 直接持有 `provider` 对象读取 identity。 | 中高。 | 中。 | P1 前改为 provider metadata/config 输入。 |
| `workflow/readiness.py` | Export readiness decision from readiness snapshot and ArtifactService integrity report。 | Workflow readiness decision。 | Export output/manifest/ExportRecord。 | 无。 | 高。 | 中。 | 保持。 |
| `workflow/quality_acceptance.py` | Convert `IssueDraft` to persistence `IssueLifecycleChange`。 | Boundary mapping from quality drafts to acceptance command。 | Quality classification、decision policy。 | 无。 | 高，虽小但命名清楚。 | 低。 | 保持。 |
| `workflow/detection_outputs.py` | Normalize provider detection output into accepted TextBlock drafts。 | Detection output mapping。 | Provider call、DB writes、workflow decisions。 | 无。 | 高。 | 低。 | 保持。 |
| `workflow/stage_results.py` | Stage error code extraction and synthetic StageResult for blocked precondition。 | Tiny StageResult utilities. | Generic helpers bucket。 | 小文件但职责明确。 | 中高。 | 低。 | 保持，不扩成 utils。 |
| `persistence/project_store.py` | app.db/project.db init/open, migration ledger check, ProjectRepositories factory, identity repo。 | Project lifecycle and repository exposure gate。 | Workflow processing policy、provider calls。 | 无；但 schema/checksum 与 lifecycle 在同文件。 | 中高。 | 中。 | 保留；migration 设计前不要继续膨胀。 |
| `persistence/content_state_repository.py` | Content state, active result input/reuse queries, glossary empty version, schema。 | Content/page/textblock/result/glossary reads/writes for MVP-0。 | Workflow decisions、provider calls、artifact filesystem writes。 | 文件层面聚合了 Content/Result/Glossary。 | 中。 | 中。 | Watch item；需要时按 repository class 拆。 |
| `persistence/acceptance_repository.py` | Acceptance transaction semantic commit。 | Atomic persistence of accepted results, pointers, issues, decisions, statuses。 | Choosing decision_type/retry/readiness。 | 无 policy drift。 | 高，尽管 782 行。 | 中，内部复用 persistence loaders。 | 保持，不把一个 transaction 拆散。 |
| `persistence/workflow_execution_repository.py` | Task/profile/attempt, readiness query, StageEvidenceWriter, workflow schema。 | Workflow execution evidence and readiness query persistence。 | Provider calls、workflow outcome choice。 | 文件层面聚合较多，但类边界清楚。 | 中。 | 中。 | Watch item；新增 recovery scanner 前按 query family 拆。 |
| `persistence/artifact_metadata_repository.py` | `ProcessingArtifact` metadata insert/load/storage_state。 | Artifact metadata persistence。 | File operations、workflow decisions。 | 无。 | 高。 | 低。 | 保持。 |
| `persistence/repository_uow_core.py` | Re-export named repo DTOs and UoW wrapper。 | Composition boundary for ProjectUnitOfWork and public imports。 | Generic Repository framework。 | 无。 | 中。 | 中。 | 保持，避免继续变成 barrel with logic。 |
| Integration tests | Focused slice behavior and boundary assertions。 | Durable integration evidence。 | Real OCR/LLM/GPU/network, UI/API/export implementation。 | 无越界；存在大型文件和 timestamp observation helper。 | 中高，按 slice/主题内聚。 | 中。 | 暂不拆；后续新增场景开新文件。 |

## 6. 是否存在“为了限制代码长度而乱拆”

结论：no。

合理职责拆分：

- `workflow/reuse.py`：承载 idempotency/reuse planning 和 reuse acceptance helper，是 Slice 07 稳定职责，不是单纯降行数。
- `workflow/readiness.py`：承载 export_check readiness decision，避免 `engine.py` 继续塞入 readiness query interpretation。
- `workflow/quality_acceptance.py`：承载 QualityCheck draft 到 acceptance command 的边界映射，避免 QualityCheckService 持有 persistence DTO。
- `workflow/detection_outputs.py`：承载 detection payload normalization，避免 detection provider payload parsing散在 engine 内。
- `workflow/stage_results.py`：小但职责明确，目前不是 generic `utils.py`。

可疑拆分：

- 暂未发现明显为了压行数而制造的垃圾桶模块。
- `stage_results.py` 很小，但命名和调用点都清楚；不建议因为小就合并。

大但应暂时保留的文件：

- `persistence/acceptance_repository.py`：同一 acceptance transaction 的信息局部性比拆文件更重要。
- `workflow/engine.py`：当前是 workflow controller，不直接 SQL，不绕过 StageExecutor；应作为 watch item，不建议立即拆。
- `tests/integration/test_workflow_happy_path.py`、`test_idempotency_and_recovery.py`：场景内聚，拆分收益暂低于信息局部性。

小但职责不清的文件：

- 未发现。

## 7. 文件大小与内聚性审查

| File | Line count | Size band | Cohesion | Reason to keep / split | Priority |
| --- | ---: | --- | --- | --- | --- |
| `src/manga_read_flow/workflow/engine.py` | 960 | 700-1000 | 中 | Workflow controller 职责仍成立；不要为降行数拆。后续 retry/fallback/real provider 增长时按 policy family 提取。 | Watch / P1 |
| `src/manga_read_flow/persistence/workflow_execution_repository.py` | 875 | 700-1000 | 中 | Task/profile/attempt/readiness/stage evidence 都属 workflow execution persistence；类边界清楚。新增 recovery scanner 前可拆。 | Watch / P1-P2 |
| `src/manga_read_flow/persistence/content_state_repository.py` | 830 | 700-1000 | 中 | ContentState/ResultVersion/Glossary 三类在同文件；当前可接受，未来可按 repository class 拆。 | Watch / P1-P2 |
| `src/manga_read_flow/persistence/acceptance_repository.py` | 782 | 700-1000 | 高 | 一个 semantic commit transaction，拆散会破坏信息局部性。 | Keep |
| `src/manga_read_flow/persistence/project_store.py` | 662 | 400-700 | 中高 | Project lifecycle/open gate/schema bootstrap 内聚；migration 体系前观察。 | Keep / Watch |
| `src/manga_read_flow/workflow/reuse.py` | 462 | 400-700 | 中高 | Idempotency/reuse 职责稳定。 | Keep |
| `src/manga_read_flow/artifacts/service.py` | 405 | 400-700 | 高 | Artifact lifecycle 职责清晰。 | Keep |
| `src/manga_read_flow/providers/fake.py` | 388 | <=400 | 高 | Fake modes 内聚。 | Keep |
| `src/manga_read_flow/quality/__init__.py` | 353 | <=400 | 中高 | MVP taxonomy 可接受；后续不宜继续塞入 `__init__.py`。 | Watch |
| `src/manga_read_flow/workflow/stage_executor.py` | 273 | <=400 | 高 | One-stage evidence boundary 清晰。 | Keep |
| `tests/integration/test_workflow_happy_path.py` | 920 | 700-1000 | 中高 | Happy path + acceptance/readiness guards 内聚。 | Keep |
| `tests/integration/test_idempotency_and_recovery.py` | 883 | 700-1000 | 中高 | Idempotency/recovery 主题内聚。 | Keep |
| `tests/integration/test_fakeprovider_stageexecutor.py` | 792 | 700-1000 | 中高 | Provider/StageExecutor boundary 主题内聚。 | Keep |
| `tests/integration/test_quality_issues_and_readiness.py` | 622 | 400-700 | 高 | Quality/readiness 主题内聚。 | Keep |

## 8. 模块功能分布混乱检查

| 功能链路 | 当前分布 | 分布是否合理 | 重复 source of truth | Misplaced logic | 建议 |
| --- | --- | --- | --- | --- | --- |
| project open / repository readiness | `project_store.AppStore`, `ProjectOpenResult.repositories()`, `ProjectIdentityRepository` | 合理。Project open gate 暴露 repos 前验证 identity/migration。 | 无。 | 无。 | 保持；migration 后续单独设计。 |
| import / original artifact | `ImportPageService` -> `ArtifactService.register_original_image()` -> `ArtifactMetadataRepository` + import UoW | 合理。Artifact 先 official register，再 Page pointer commit；失败路径有 evidence。 | Page 只存 artifact id，不存路径 truth。 | 无。 | 保持。 |
| stage execution | `WorkflowLoopEngine._execute_stage()` -> `StageExecutor.execute()` -> Provider -> StageEvidenceWriter/ArtifactService | 合理。Provider call 不在 SQL write transaction 内，StageExecutor 不做最终 decision。 | 无。 | 无。 | 保持 narrow recorder/writer。 |
| provider result evidence | `ProviderResult` -> `StageResult` -> ToolRunLog/WorkflowAttempt | 合理。Evidence 先持久化，acceptance 后决策。 | 无。 | 无。 | 保持。 |
| workflow acceptance | `WorkflowLoopEngine` builds `AcceptanceCommand`; `AcceptanceRepository` commits | 合理。决策在 engine，持久化在 repository。 | 无。 | 无。 | 不拆散 acceptance transaction。 |
| active pointer selection | Engine/reuse/readiness 决定是否接受；`AcceptanceRepository` 更新 pointers | 合理。未发现 latest timestamp selection。 | 无独立 active flags。 | 无。 | 保持 guarded expected state。 |
| quality issue acceptance | QualityCheckService drafts -> `quality_acceptance` -> engine command -> acceptance repository | 合理。QualityCheckService repository-free。 | 无。 | 无。 | 保持 mapping module 小而专。 |
| readiness | `ReadinessQueryRepository` loads counts/snapshot flag；`workflow/readiness.py` 决策；ArtifactService validates active artifact | 合理。query 和 decision 分离。 | Page status 不是唯一 truth。 | 无。 | 保持；后续 ExportRecord 仍不塞入 readiness。 |
| reuse / idempotency | `workflow/reuse.py` + result/artifact repositories + ArtifactService validation | 合理。Provider 不决定 cache reuse。 | 无。 | `WorkflowReuseService` 直接持有 provider 对象是 P1 接缝风险。 | 改成 provider metadata 输入。 |
| recovery | MVP-0 通过 durable state seed、active pointers、attempts、artifacts、issues 跑恢复场景 | 当前 MVP 合理。还不是完整 TaskRunner stale scan/recovery module。 | 未只依赖 Page.status。 | 无 Category A。 | Web/worker 前设计 recovery scanner。 |
| missing artifact handling | ArtifactService marks `missing`; reuse/readiness/engine 决定 rebuild/block | 合理。ArtifactService 不决定 workflow outcome。 | 无。 | 无。 | 保持。 |

## 9. Category A blockers

No Category A blockers found.

## 10. Non-blocking smells

### P0-before-next-phase

无。当前没有必须在下一阶段前阻塞处理的 smell。

### P1-before-real-tool-integration

| smell | evidence | risk | recommended action | whether code change is required |
| --- | --- | --- | --- | --- |
| Provider concrete coupling | `ProcessPageService`、`WorkflowLoopEngine`、`WorkflowReuseService` 类型/构造使用 `FakeProvider`，reuse 直接读 provider object 的 `provider_name/model_id`。 | 真实 Provider Spike 时可能把 provider config/identity 与 FakeProvider 实例耦死。 | 引入窄 provider metadata/config DTO 或 Protocol 输入，不引入真实 provider client。 | yes |
| Migration/bootstrap 边界尚未产品化 | `project_store.py` 直接初始化 schema、baseline checksum 与 Project open gate。 | API/UI 或真实用户数据出现后，测试式 bootstrap 可能被误认为生产 migration/backfill 策略。 | 做 migration/backfill design 或最小 migration module 边界，不改 final baselines。 | design first |
| Artifact retention vocabulary 未完全收敛 | `ArtifactService.register_stage_output()` 默认 `retention_class="stage_output"`，设计基线列的是 `active_result`、`successful_payload`、`cache_rebuildable` 等。 | cleanup/retention/export 前可能出现语义不明 artifact state。 | 定义 MVP-0 到 P1 的 retention_class 映射并补 focused tests。 | likely yes |

### P2-before-web-mvp

| smell | evidence | risk | recommended action | whether code change is required |
| --- | --- | --- | --- | --- |
| 大 repository 文件继续增长风险 | `content_state_repository.py` 830 行，`workflow_execution_repository.py` 875 行。 | API/read models/recovery scanner 加入后可能变成 persistence bucket。 | 仅在新增职责前按 stable repository class 拆分，例如 result-version/readiness/stage-evidence。 | maybe |
| 测试 helper 使用 timestamp 观察 latest decision | `_latest_decision()` 在 quality/recovery tests 用 `ORDER BY created_at DESC`。 | 这不是生产 active selection，但未来并发/同秒时间可能让测试脆。 | 对最终 decision 优先断言 `ProcessPageResult`、stage-specific decision 或 deterministic IDs。 | yes |
| `quality/__init__.py` 继续承载 taxonomy 风险 | 当前 353 行仍可接受。 | issue taxonomy 增长后 `__init__.py` 变成模块桶。 | 新增 taxonomy 时拆到 `quality/service.py`、`quality/issues.py` 等明确模块。 | maybe |

### Backlog

| smell | evidence | risk | recommended action | whether code change is required |
| --- | --- | --- | --- | --- |
| `workflow/engine.py` 接近 1000 行 | 960 行，但职责仍是 workflow controller。 | 后续 retry/fallback/provider replacement 会增加复杂度。 | 先不拆；当新增真实 retry/fallback 时按 stable policy object 提取。 | maybe |
| Test source-inspection assertions 较脆 | 多处 `inspect.getsource()` 检查边界关键词。 | 重命名或注释可能误伤；不过对 MVP boundary 有价值。 | 后续补更行为化的边界 tests。 | maybe |

## 11. 建议的后续任务

### Task title

Provider metadata seam before Real Tool Spike

- Goal：把 `FakeProvider` 具体类型依赖收窄为 `StageProvider`/provider metadata/config 输入，让 Real Tool Spike 可替换 provider 而不改 workflow policy。
- Allowed files：`src/manga_read_flow/application/process_page.py`、`src/manga_read_flow/workflow/engine.py`、`src/manga_read_flow/workflow/reuse.py`、必要的 provider contract/tests。
- Forbidden files：real provider client、prompt templates、API/UI/export、`docs/design/**/final/**`。
- Validation：`pytest tests/integration/test_fakeprovider_stageexecutor.py -q`、`pytest tests/integration/test_workflow_happy_path.py -q`、`pytest tests/integration/test_idempotency_and_recovery.py -q`、`pytest -q`。
- Why now / why later：Real Tool Spike 前做；现在不阻塞 closure，因为 FakeProvider backend 已通过。

### Task title

Minimal migration/bootstrap boundary design

- Goal：明确当前 schema bootstrap/checksum 与未来 production migration/backfill 的边界，防止 API/UI 后把测试式初始化当成长期迁移方案。
- Allowed files：`docs/design/migration/` 或 `docs/engineering/` 下新文档。
- Forbidden files：`docs/design/**/final/**`、`src/**`、`tests/**`。
- Validation：设计文档需覆盖 app.db/project.db 独立迁移、Project open outcomes、checksum/backfill、rollback/blocked open 场景。
- Why now / why later：API/UI 或真实用户数据前需要；不必在 Real Tool Spike 的第一步前阻塞。

### Task title

Artifact retention vocabulary alignment

- Goal：把 `stage_output` 等实现词汇映射到设计中的 retention classes，确认 active result、failed payload、cache rebuildable 的清理边界。
- Allowed files：`src/manga_read_flow/artifacts/**`、`src/manga_read_flow/workflow/stage_executor.py`、相关 artifact tests。
- Forbidden files：workflow decision 重构、export output、cleanup scheduler、real provider。
- Validation：`pytest tests/integration/test_import_and_artifactservice.py -q`、`pytest tests/integration/test_fakeprovider_stageexecutor.py -q`、`pytest tests/integration/test_idempotency_and_recovery.py -q`。
- Why now / why later：真实工具可能产生更大 artifacts 前处理；不影响当前 closure。

## 12. 是否建议立即重构

结论：No immediate refactor needed。

理由：

- 没有 Provider DB access、Provider official artifact registration、StageExecutor decision/active pointer write、QualityCheck persistence、Workflow direct SQL、timestamp active selection 等 Category A 违规。
- 大文件主要是职责自然聚合：`AcceptanceRepository` 是单一 semantic commit；`WorkflowLoopEngine` 是 workflow controller；测试文件按 slice/场景内聚。
- 现在若按行数拆 `engine.py` 或 acceptance transaction，反而会破坏 information locality。

需要后续 targeted cleanup，但这些是进入真实 Provider/API/UI 前的接缝任务，不是立即阻塞的行数修正。

## 13. 下一阶段建议

选择：Real Tool Spike 前置准备。

理由：

- FakeProvider backend 的 architecture validation 已经通过：68 tests green，ready/warning/block/reuse/recovery evidence 都可验证。
- 当前 deferred risks 最接近 Real Tool Spike：provider identity/config 接缝、retention vocabulary、schema/bootstrap 边界。
- API/UI 前置设计可以并行做，但不应先让 UI 直接绑定 FakeProvider-only process service 或绕开 WorkflowLoopEngine/ArtifactService。

建议顺序：

1. Provider metadata seam before Real Tool Spike。
2. Real Tool Spike 最小设计/验证计划。
3. API/UI 前置设计，明确只调用 ApplicationService/API，不直接碰 repositories/tools。

## 14. 最终状态

- forbidden files changed：no
- final design baselines changed：no
- source code changed：no
- tests changed：no
- report file changed：yes
- commit status：未 commit
- push status：未 push
