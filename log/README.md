# Development Session Log — 2026-07-09

> 本文件根据 Git 历史、测试结果和 Codex 阶段反馈重构。
> 本 Session 完成了 MVP-0 FakeProvider 单 Page 后端闭环，并建立了 Real Tool Spike 所需的本地样本与 GPU 工具环境。

## Session Metadata

* Started: 2026-07-09 11:40
* Ended: Real Tool Spike 本地环境验证完成后；精确结束时间未完整保留
* Log reconstruction date: 2026-07-10
* Phase:

  * MVP-0 FakeProvider 单 Page 后端垂直切片
  * Real Tool Spike 前置准备
* Main implementation branch at backend closure: `feat/slice-07-idempotency-recovery`
* Primary goals:

  1. 完成 Slice 01–07；
  2. 验证 persistence、artifact、workflow、quality、readiness、idempotency 和 recovery 闭环；
  3. 为 Detection + OCR Real Tool Spike 准备本地 synthetic 样本和 GPU 环境。

## Completed

### 1. Slice 01 — Foundation and Project Store

Commit:

* `fb98736 feat: add project store foundation`

Result:

* 建立 Python package 和测试骨架。
* 实现最小 `app.db` / `project.db` 初始化。
* 实现 Project identity、migration ledger 和 Project open gate。
* 使用真实临时 SQLite 文件完成验证。

Focused validation:

* `pytest tests/integration/test_project_store_init.py -q`
* Result: `11 passed`

### 2. Slice 02 — Repository and Unit of Work Core

Commit:

* `77aaa5d feat(slice-02): add repository unit of work core`

Result:

* 建立 Repository / Unit of Work 核心边界。
* 上层模块不直接获得 SQLite connection、cursor 或原始 SQL 接口。
* Provider 仍无 persistence 能力。

Focused validation:

* `pytest tests/integration/test_repository_uow_core.py -q`
* Result: `7 passed`

### 3. Slice 03 — ArtifactService and Import

Commit:

* `33b67d5 feat(slice-03): import pages through ArtifactService`

Result:

* 原图通过 ArtifactService 注册为正式 artifact。
* 原始文件不被覆盖。
* Page 通过 artifact id 引用原图。
* 文件 bytes 保留在 workspace，SQLite 只保存元数据。

Focused validation:

* `pytest tests/integration/test_import_and_artifactservice.py -q`
* Result: `7 passed`

### 4. Slice 04 — FakeProvider and StageExecutor

Commit:

* `2af6c10 feat: Implement FakeProvider and StageExecutor for workflow processing`

Result:

* FakeProvider 使用正式 Provider contract 返回 deterministic evidence。
* StageExecutor 执行单个 stage attempt。
* Provider 不访问数据库、不注册正式 artifact、不创建 QualityIssue、不决定 retry、fallback、skip 或 block。
* StageExecutor 不更新 active pointer，不创建 WorkflowDecision。

Focused validation:

* `pytest tests/integration/test_fakeprovider_stageexecutor.py -q`
* Result: `17 passed`

### 5. Slice 05 — WorkflowLoop Happy Path

Commit:

* `7a65230 feat(slice-05): add workflow loop happy path`

Result:

* 单 Project、单 Batch、单 Page happy path 可运行到 `ready_for_export`。
* WorkflowLoopEngine 负责 stage progression、acceptance 和 workflow decision。
* accepted result 和 artifact 通过 active pointer 成为当前有效输出。

Focused validation:

* `pytest tests/integration/test_workflow_happy_path.py -q`
* Result: `8 passed`

### 6. Slice 06 — Quality Issues and Readiness

Commit:

* `d177e67 feat(slice-06): add quality issues and readiness gates`

Result:

* invalid、partial、provider refusal、cleaning skip 和 typesetting overflow 可形成 QualityIssue。
* unresolved blocking QualityIssue 阻塞 normal export。
* warning readiness 由 ProcessingProfileSnapshot 控制。
* 本 Slice 只实现 `ready_for_export` 判断，不生成实际 export output。

Focused validation:

* `pytest tests/integration/test_quality_issues_and_readiness.py -q`
* Result: `9 passed`

### 7. Slice 07 — Idempotency and Recovery

Commit:

* `374d57e feat(slice-07): add idempotency and recovery`

Result:

* unchanged rerun 可以复用 OCR、Translation、Cleaning 和 Typesetting 结果。
* 复用行为通过 attempt 和 decision 留下审计证据。
* OCR acceptance 后发生中断时，可以从 Translation 阶段继续。
* 已注册但未被 acceptance 选中的 artifact 不会因时间较新而自动生效。
* missing active artifact 会被标记为 `missing`，再由 workflow 决定 rebuild、warning 或 block。
* recovery 不依赖单一 `Page.status`。

Focused validation:

* `pytest tests/integration/test_idempotency_and_recovery.py -q`
* Result: `9 passed`

## Code Health Gate

新增：

* `docs/engineering/code-health-gate.md`
* `docs/prompt-patterns/implementation/code-health-review-pass.md`

Purpose:

* 在功能验证后检查 architecture boundary drift、responsibility drift、coupling、testability 和文件增长。
* 只允许当前 Slice 范围内的局部安全修复。
* Category A blocker 或架构边界违规未解决时，不允许进入提交或阶段关闭。

## MVP-0 Backend Closure Review

Review document:

* `docs/engineering/reviews/mvp0-fakeprovider-backend-closure-review.md`

Closure review commit:

* `aca74c7 feat(review): 添加 MVP-0 FakeProvider 后端关闭审查文档`

Conclusion:

* `PASS_WITH_DEFERRED_RISKS`
* 无 Category A blocker。
* 无必须在进入下一阶段前修复的架构边界违规。
* 允许进入 Real Tool Spike 前置工作。

Full validation:

* `pytest -q`
* Result: `68 passed`

Deferred risks:

* Provider concrete identity/config coupling。
* Migration/bootstrap 边界需要在真实用户数据和 API/UI 前继续设计。
* Artifact retention vocabulary 尚未完全收敛。
* WorkflowLoopEngine 和部分 Repository 文件需要防止后续继续无边界增长。

## Provider Identity Seam

Commit:

* `6cdcf9e refactor(provider): add provider identity seam`

Result:

* 从 application、workflow 和 reuse 逻辑中收窄对 `FakeProvider` 具体类型的依赖。
* Provider identity / metadata 可以作为窄契约传递。
* 为 Real Tool Spike 替换 FakeProvider 提供接缝。
* 本次没有引入真实 Provider，也没有改变 workflow policy ownership。

## Synthetic Sample Preparation

### Local files created

写过本地生成脚本：

* `tools/generate_synthetic_samples.py`

写过最小测试：

* `tests/unit/test_generate_synthetic_samples.py`

生成 manifest：

* `tests/fixtures/synthetic/manifest.json`

生成四张 WebP 样本：

* `synthetic_01_clean_dialogue.webp`
* `synthetic_02_narration_boxes.webp`
* `synthetic_03_small_bubble_overflow.webp`
* `synthetic_04_complex_background_skip.webp`

### Scenario coverage

样本覆盖：

* 清晰对白气泡；
* 矩形旁白框；
* 小气泡长文本和 overflow risk；
* 复杂背景、弱对比、倾斜文本和 skip risk；
* 横排文本；
* 竖排文本；
* 倾斜文本；
* `dialogue_bubble`；
* `narration_box`；
* `difficult_text`；
* `detection`；
* `ocr`；
* `overflow_risk`；
* `skip_risk`。

### Validation

Focused validation:

* `pytest tests/unit/test_generate_synthetic_samples.py -q`
* Result: passed

Full validation:

* `pytest -q`
* Result: passed

### Repository boundary

后来按要求将以下路径加入 `.gitignore`：

* `tools/generate_synthetic_samples.py`
* `tests/unit/test_generate_synthetic_samples.py`
* `tests/fixtures/synthetic/`

这些文件继续保留在本地，但不纳入版本追踪。

当时 Git 可见的相关工作区状态为：

```text
M .gitignore
```

因此必须区分：

* synthetic 脚本、测试、图片和 manifest：本地存在、已验证、被 Git 忽略；
* `.gitignore`：仓库可见的待提交变更；
* synthetic 文件：不是仓库正式测试资产或产品代码。

## Real Tool Local Environment

### Conda environment

创建本地 Conda 环境：

```text
manga-read-flow
```

该环境用于 Real Tool Spike，不属于应用运行时或正式交付环境基线。

### GPU and library verification

已确认：

* PyTorch CUDA: OK
* Paddle GPU: OK
* manga-ocr CUDA initialization: OK
* PaddleOCR GPU initialization: OK
* Pillow WebP support: OK
* OpenCV import/runtime: OK

Result:

* 当前机器具备执行 Detection + OCR GPU Spike 的基本运行条件。
* PaddleOCR 可以初始化 GPU detection/OCR 组件。
* manga-ocr 可以初始化 CUDA 推理路径。
* synthetic WebP 样本可以被 Pillow 和 OpenCV 读取。

### Dependency conflict

`pip check` 发现 `nvidia-*` 包存在精确版本依赖冲突。

Current assessment:

* 当前环境可用于短期、隔离的技术 Spike。
* 当前环境不应直接作为产品集成、持续开发或可复现交付环境。
* 尚未形成稳定的 lockfile、Conda environment 文件或其他可复现环境定义。

Potential future separation:

* `manga-read-flow-torch`

  * manga-ocr
  * PyTorch
  * 对应 CUDA / `nvidia-*` 依赖

* `manga-read-flow-paddle`

  * PaddleOCR
  * PaddlePaddle GPU
  * 对应 CUDA / `nvidia-*` 依赖

该拆分目前是环境风险缓解建议，不是已经接受的产品架构决策。应先通过 Spike 观察两个工具是否确实需要长期共存，再决定是否固化为双环境方案。

## Durable Decisions

* MVP-0 FakeProvider 后端闭环已完成，不回头重写既有架构。
* Real Tool Spike 前只做必要的 Provider 接缝清理。
* synthetic sample 作为本地实验输入，不进入 Git 历史。
* 当前 Conda 环境只用于隔离 Spike，不作为产品环境基线。
* 真实 Detection 和 OCR 必须先通过独立实验验证，再设计生产 Provider 集成。
* Spike 不直接修改 workflow、persistence、ArtifactService 或 QualityIssue 机制。
* API、UI、实际 export output、Batch 和 P1/P2 功能仍未进入实现范围。

正式事实来源：

* 七个 Slice 文档；
* 产品代码和集成测试；
* Closure Review；
* Git commits；
* 后续独立 Real Tool Spike 报告。

## Validation Summary

| Validation                             | Result                                     |
| -------------------------------------- | ------------------------------------------ |
| Project store                          | 11 passed                                  |
| Repository / UoW                       | 7 passed                                   |
| ArtifactService / import               | 7 passed                                   |
| FakeProvider / StageExecutor           | 17 passed                                  |
| Workflow happy path                    | 8 passed                                   |
| Quality / readiness                    | 9 passed                                   |
| Idempotency / recovery                 | 9 passed                                   |
| Full suite at backend closure          | 68 passed                                  |
| Synthetic generator focused test       | passed                                     |
| Full suite after synthetic preparation | passed                                     |
| PyTorch CUDA initialization            | passed                                     |
| Paddle GPU initialization              | passed                                     |
| manga-ocr CUDA initialization          | passed                                     |
| PaddleOCR GPU initialization           | passed                                     |
| Pillow WebP                            | passed                                     |
| OpenCV                                 | passed                                     |
| `pip check`                            | failed due to `nvidia-*` version conflicts |
| Category A blockers                    | none                                       |
| Architecture boundary blockers         | none                                       |

## Open Items

* [ ] 创建独立 Detection + OCR Spike 任务。
* [ ] 使用 PaddleOCR detection 在 synthetic 图片上生成 bbox。
* [ ] 将检测 bbox 与 manifest region 做基础匹配。
* [ ] 对 bbox crop 使用 manga-ocr。
* [ ] 记录识别文本、bbox、耗时、GPU 使用和失败类型。
* [ ] 分类漏检、误检、竖排问题、小气泡问题、弱对比问题和复杂背景误识别。
* [ ] 形成 Spike 报告和 Go / No-Go / Further Spike 结论。
* [ ] 根据 Spike 结果决定是否拆分 Torch 和 Paddle 环境。
* [ ] 在进入生产集成前建立可复现依赖定义。
* [ ] 在 API/UI 或真实用户数据前明确 migration/bootstrap boundary。
* [ ] 在 cleanup/retention 实现前收敛 artifact retention vocabulary。
* [ ] 暂不实现实际 export output、ZIP、manifest 或 `ExportRecord`。

## Handoff

* Backend closure status: `PASS_WITH_DEFERRED_RISKS`
* Provider identity seam: completed
* Synthetic samples: local-only, validated, ignored by Git
* Conda environment: `manga-read-flow`
* GPU tool status: usable for isolated Spike
* Environment health: `pip check` has unresolved `nvidia-*` version conflicts
* Repository-visible local change at environment handoff:

```text
M .gitignore
```

* Next concrete task: 独立 Detection + OCR Real Tool Spike
* Recommended execution form:

  * temporary script；
  * notebook；
  * isolated CLI；
  * 不进入产品 `src/` 路径。
* Required inputs:

  * local synthetic samples；
  * manifest；
  * PaddleOCR；
  * manga-ocr；
  * GPU environment；
  * Spike-specific acceptance criteria。
* Required outputs:

  * per-sample detection result；
  * per-region OCR result；
  * timing and resource evidence；
  * failure taxonomy；
  * environment issues；
  * Go / No-Go / Further Spike decision。
* Stop condition:

  * 如果实验需要修改正式 workflow、provider、persistence、ArtifactService 或 quality contract，应停止 Spike 并先形成设计变更；
  * 不得把临时实验代码直接并入产品实现路径。
