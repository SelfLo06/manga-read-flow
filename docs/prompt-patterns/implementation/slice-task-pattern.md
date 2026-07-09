# 实现切片任务 Pattern

版本：v0.2  
状态：可复用 implementation slice prompt pattern  
适用阶段：MVP-0 / FakeProvider backend slices / 后续小型垂直实现任务

---

## 1. 目的

本 pattern 用于编写具体的 implementation slice prompt。

它的目标是让 Codex / coding agent 在清晰边界内完成一个小型、可验证、可回滚的实现切片，并以测试、diff review、Code Health Review 和最终报告收尾。

本 pattern 不是产品路线图、详细设计模板，也不是通用大 prompt。它只用于准备某个具体实现任务。

---

## 2. 适用场景

适用于：

- MVP-0 backend implementation slices；
- 有明确 slice document 的垂直实现任务；
- 有清晰允许文件、禁止文件和验证命令的任务；
- 需要 Codex 输出可审查 diff、测试结果和风险报告的任务；
- 功能实现后需要进行 Code Health Review 的任务。

不适用于：

- 新产品路线图；
- 新详细设计基线；
- 大型架构重构；
- 真实工具 Spike；
- UI / API / Export 等尚未完成前置设计的任务；
- 无明确验证命令的探索性编码。

---

## 3. 编写原则

每个实现 prompt 必须做到：

- 目标窄；
- 文件边界窄；
- 验证命令明确；
- 禁止事项明确；
- 架构不变量明确；
- 不允许 agent 自行扩大范围；
- 不允许 agent 猜测缺失设计；
- 不允许 agent 在未授权时 commit；
- 实现后必须触发 Code Health Review。

不要把所有项目文档都塞进 source documents。只列出当前 slice 必须读取的文档，避免诱导 agent 重新打开已经收敛的设计决策。

---

## 4. Prompt 必备结构

每个实现 prompt 建议包含以下部分：

```text
Goal
Source documents
Allowed files
Forbidden files
Implementation boundaries
Validation command
Expected output
Commit rule
Stop conditions
Post-implementation Code Health Review
Final report
````

---

## 5. Goal

用一到两段说明本 slice 的目标。

必须说明：

* 这个 slice 要证明什么；
* 为什么现在做；
* 它支持哪个产品阶段；
* 它有意不实现什么。

示例：

```text
Goal:
Implement Slice 03: ArtifactService and one-Page import.

This slice proves that original image bytes are stored in the Project workspace, SQLite stores only artifact metadata, and Page import is valid only after original artifact metadata and Page.original_artifact_id are committed together.

This slice does not implement WorkflowLoopEngine, provider execution, API upload routes, export output, ZIP, manifest, or frontend behavior.
```

---

## 6. Source Documents

只列当前任务需要的文档。

典型来源：

```text
Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- relevant final detailed design documents
- exact implementation slice document
- docs/engineering/code-health-gate.md
- docs/prompt-patterns/implementation/code-health-review-pass.md
```

规则：

* 必须包含精确 slice document；
* 必须包含被触碰模块相关的最终详细设计；
* 不要加入无关设计文档；
* 如果 source documents 之间冲突，agent 必须停止并报告；
* 不得修改 `docs/design/**/final/**`，除非任务明确授权。

---

## 7. Allowed Files

列出允许修改的精确文件或目录。

要求：

* 足够窄；
* 显式包含测试文件；
* 显式包含 fixtures，如果需要；
* 不要使用过宽范围，例如整个 `src/**`，除非 slice 本身就是基础脚手架。

示例：

```text
Allowed files:
- src/manga_read_flow/artifacts/**
- src/manga_read_flow/application/** for import use case only
- src/manga_read_flow/persistence/**
- src/manga_read_flow/domain/**
- tests/integration/test_import_and_artifactservice.py
- tests/fixtures/**
```

---

## 8. Forbidden Files

列出不得触碰的文件和类别。

典型禁止范围：

```text
Forbidden files:
- unrelated source code
- UI / API / frontend files unless explicitly in scope
- real provider integrations during FakeProvider slices
- export output, ZIP, manifest, or ExportRecord unless explicitly in scope
- docs/design/**/final/**
- secrets, logs, caches, build outputs, local config, AI runtime files
- dependency files unless explicitly authorized
```

规则：

* 如果实现必须触碰 forbidden files，停止并报告；
* 不得为了“顺手修复”修改无关区域；
* 不得修改最终设计基线来适配实现。

---

## 9. Implementation Boundaries

列出本 slice 必须保持的架构不变量。

常用边界：

```text
Implementation boundaries:
- Repository / DAO is the only SQLite access boundary.
- Provider Adapter must not access SQLite, repositories, sessions, or cursors.
- Provider Adapter must not register official artifacts.
- Provider Adapter must not create QualityIssue or WorkflowDecision.
- StageExecutor must not update active pointers.
- StageExecutor must not own retry, fallback, skip, warning, block, pause, cancel, or readiness decisions.
- ArtifactService owns official artifact lifecycle only.
- ArtifactService must not decide workflow outcomes.
- QualityCheckService must not advance workflow state.
- WorkflowLoopEngine owns workflow decisions and acceptance.
- Active output selection must not use timestamps.
- Recovery must not rely only on Page.status.
- Original images must never be overwritten.
- Image bytes and large payloads must not enter SQLite.
```

每个具体 prompt 应保留与当前 slice 直接相关的不变量，不必每次复制全部。

---

## 10. Validation Command

提供明确、可执行的聚焦验证命令。

示例：

```bash
pytest tests/integration/test_import_and_artifactservice.py
```

规则：

* 早期 implementation slices 优先使用 focused integration test；
* 如果需要多个命令，说明原因；
* 不要用宽泛 full-suite run 替代 focused validation；
* 如果验证命令无法运行，agent 必须报告具体 blocker；
* 如果无法识别验证命令，Code Health Review subagent 不得猜测。

---

## 11. Expected Output

描述实现后的可观察结果。

应包含：

* 新增或修改的核心模块；
* 应通过的行为；
* 持久化或暴露的 evidence；
* 需要覆盖的失败路径；
* 明确仍然不做的内容。

示例：

```text
Expected output:
- Original image is copied or stored under the Project workspace.
- processing_artifacts stores project-relative metadata only.
- Page.original_artifact_id is committed with Page import state.
- Image bytes are not stored in SQLite.
- Duplicate original filenames do not overwrite existing originals.
- No WorkflowLoopEngine, provider execution, API route, export output, ZIP, or frontend behavior is added.
```

---

## 12. Commit Rule

默认规则：

```text
Do not commit unless explicitly allowed.
```

如果允许 commit：

```text
If commit is explicitly allowed:
- run the focused validation command first;
- run Code Health Review Pass;
- rerun focused validation after any code-health fix;
- run pytest -q unless concretely blocked;
- stage only allowed files;
- make one focused slice commit;
- do not push.
```

---

## 13. Stop Conditions

遇到以下情况必须停止并报告：

```text
Stop conditions:
- unrelated dirty working tree exists;
- required source documents are missing;
- source documents conflict on a blocking decision;
- implementation requires forbidden files;
- implementation requires broader design decisions;
- validation command is unavailable or cannot be identified;
- validation fails for unrelated environment reasons;
- slice would require UI, API, real providers, export output, ZIP, manifest, or batch-scale behavior outside scope;
- an architecture invariant would be violated;
- fixing a discovered issue requires a refactor task rather than local slice work.
```

不要绕过 stop condition 继续实现。

---

## 14. Post-implementation Code Health Review

每个 implementation slice prompt 都必须在结尾要求运行 Code Health Review。

执行入口：

```text
docs/prompt-patterns/implementation/code-health-review-pass.md
```

规则：

```text
After the focused validation command completes, invoke the Code Health Review Pass subagent.

The subagent must:
- read docs/engineering/code-health-gate.md;
- review only the current slice diff;
- fix only local safe code-health issues within slice scope;
- avoid feature expansion, forbidden files, and final design baseline changes;
- rerun the focused validation command after fixes;
- run pytest -q unless a concrete documented reason prevents it;
- report blockers, smells found/fixed/deferred, validation results, forbidden-file status, and remaining risks.

If the focused validation command cannot be identified from the slice document or implementation prompt, the subagent must stop and report instead of guessing.

The slice is not commit-ready until Code Health Review Pass is complete and no Category A blocker remains.
```

不要在本 pattern 中复制 `code-health-gate.md` 的完整检查清单。`code-health-gate.md` 是规则源；本 pattern 只负责把 review 接入实现流程。

---

## 15. Final Report

最终报告必须包含：

```text
Final report:
- current branch
- files changed
- implementation summary
- focused validation command and result
- pytest -q result, or exact skip reason
- Code Health Review Pass result
- smells found
- smells fixed
- smells deferred
- Category A blockers remaining: yes/no
- architecture boundary violations remaining: yes/no
- risks remaining
- confirmation that no forbidden files changed
- confirmation that no final design baselines changed
- commit status
- recommended next action
```

如果 validation 未运行，不得声称实现成功。

如果 Code Health Review 未运行，不得声称 slice commit-ready。

---

## 16. Harness Principles

实现任务的真实 harness 不是 prompt 本身，而是：

* tests；
* commands；
* diffs；
* file boundaries；
* persisted evidence；
* final report；
* code health review result。

规则：

* 优先使用 pytest 和 focused integration tests；
* 不要为本项目构建自定义 agent loop runtime；
* 不要为了一个 slice 引入重型检查框架；
* 只有重复失败证明必要时，才添加 repo-side scripts 或 checkers；
* FakeProvider slices 不应依赖真实 OCR、LLM、network、GPU 或云端服务。

---

## 17. 最小可复用骨架

```text
目标：
实现 <slice id and name>。

本 slice 用于证明 <specific behavior>。
本 slice 不实现 <explicit non-goals>。

来源文档：
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- <相关最终详细设计文档>
- <精确 slice document>
- docs/engineering/code-health-gate.md
- docs/prompt-patterns/implementation/code-health-review-pass.md

允许文件：
- <窄范围 source paths>
- <聚焦测试文件>
- <fixtures，如需要>

禁止文件：
- <无关产品区域>
- UI / API / frontend files，除非本 slice 明确包含
- real provider integrations，除非本 slice 明确包含
- export output、ZIP、manifest 或 ExportRecord，除非本 slice 明确包含
- docs/design/**/final/**
- secrets、logs、caches、build outputs、local config、AI runtime files

实现边界：
- <architecture invariant 1>
- <architecture invariant 2>
- <slice-specific boundary>

验证命令：
pytest <focused test target>

预期输出：
- <可观察成功结果>
- <持久化或可审查 evidence>
- <覆盖的 failure path>
- <明确不包含的 scope>

Commit 规则：
除非用户明确允许，否则不要 commit。
如果允许 commit，必须在聚焦验证、Code Health Review Pass 和必要重跑通过后，只做一个聚焦 slice commit。

停止条件：
- 存在 unrelated dirty working tree。
- 必需来源文档缺失或存在阻塞性冲突。
- 实现需要 forbidden files。
- 出现 forbidden dependency 或 scope expansion。
- 验证命令不可用或无法识别。
- 某个 architecture invariant 会被违反。
- 修复问题需要独立 refactor task，而不是当前 slice 内局部修改。

实现后的 Code Health Review：
聚焦验证命令完成后，调用 Code Health Review Pass subagent：

- docs/prompt-patterns/implementation/code-health-review-pass.md

该 subagent 必须读取：

- docs/engineering/code-health-gate.md

该 subagent 只审查当前 slice diff，只修复当前 slice 范围内的局部安全问题，不扩大功能范围，不触碰 forbidden files，不修改最终设计基线。

如果进行了修复，必须重新运行聚焦验证命令。

除非有明确且可报告的原因阻止，否则运行：

pytest -q

最终报告：
- current branch
- files changed
- implementation summary
- focused validation command and result
- pytest -q result or exact skip reason
- Code Health Review Pass result
- smells found
- smells fixed
- smells deferred
- Category A blockers remaining: yes/no
- architecture boundary violations remaining: yes/no
- risks
- confirmation that no forbidden files changed
- confirmation that no final design baselines changed
- commit status
- recommended next action