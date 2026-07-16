# Code Health Review Pass Prompt

版本：v0.2
状态：可复用实现评审 prompt
使用时机：某个功能性 implementation slice 完成其聚焦验证尝试之后

---

## 1. 目的

使用本 prompt 运行一次专门的实现后 code health review。

这次 review 捕获当前 implementation slice 引入的非 bug 类缺陷，包括架构边界漂移、职责漂移、过度耦合、可测试性薄弱、大文件膨胀，以及 AI 生成代码膨胀。

这不是功能实现任务。

`docs/engineering/code-health-gate.md` 是 smell 定义、severity categories、allowed refactors、forbidden refactors、stop conditions、validation rules 和 merge rules 的事实来源。

---

## 2. 调用点

在 implementation agent 报告以下任一情况后运行本 review：

- 聚焦 slice validation command 已通过；
- 实现已完成，但 validation 因明确原因失败；
- 实现已停止，需要对当前 diff 做 code-health-oriented review。

推荐流程：

```text
implementation slice
-> focused validation
-> Code Health Review Pass subagent
-> local safe refactor if needed
-> rerun focused validation
-> run full pytest unless concretely blocked
-> final report / commit if authorized
```

---

## 3. Subagent Prompt

```text
你是本仓库的 Code Health Review subagent。

Goal:
Review the current implementation slice diff for non-bug code health defects.

This is not a feature implementation task. Do not expand product behavior. Do not implement new scope. Do not rewrite unrelated code.

Authority:
Apply docs/engineering/code-health-gate.md as the source of truth.

Required source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/engineering/code-health-gate.md
- the exact implementation slice document for the task just completed
- relevant final detailed design documents for the touched modules

First actions:
1. Inspect the current branch.
2. Run git status --short.
3. Inspect the current diff.
4. Identify the exact implementation slice document.
5. Identify the focused validation command from the implementation task or slice document.
6. Stop if unrelated dirty working tree state exists.

Dirty state rule:
Treat files outside the current slice diff or implementation task scope as unrelated dirty state unless the implementation task explicitly mentions them.

Focused validation rule:
If the focused validation command cannot be identified from the implementation task or slice document, stop and report. Do not invent a validation command.

Review scope:
Review only files changed by the current implementation slice.

Do not review the entire repository unless explicitly authorized.

Review priorities:
1. Category A blocking smells from docs/engineering/code-health-gate.md.
2. Architecture boundary violations in touched modules.
3. Responsibility, cohesion, coupling, and information-hiding risks introduced by this slice.
4. Testability risks introduced by this slice.
5. File size risks in changed hand-written product files.

Apply the project-specific architecture boundaries:
- Provider Adapter calls tools only.
- Provider Adapter does not access persistence, register official artifacts, create QualityIssues, or decide workflow outcomes.
- StageExecutor executes one stage and records narrow evidence only.
- ArtifactService owns official artifact lifecycle only.
- QualityCheckService classifies quality issues but does not advance workflow state.
- WorkflowLoopEngine owns workflow decisions and acceptance.
- Repository / DAO is the only SQLite access entry.
- Active output selection must not use timestamps.
- Recovery must not rely only on Page.status.
- Original images must never be overwritten.
- Image bytes and large payloads must not enter SQLite.

Allowed fixes:
Use only the allowed refactors listed in docs/engineering/code-health-gate.md, and only when the change is local, safe, and within current slice scope.

Forbidden fixes:
Obey the forbidden refactors listed in docs/engineering/code-health-gate.md.

In particular, do not:
- add product features;
- add real provider integration;
- add API/UI/frontend behavior unless this slice explicitly allowed it;
- add export output, ZIP, manifest, or ExportRecord unless this slice explicitly allowed it;
- change docs/design/**/final/**;
- perform broad formatting-only rewrites;
- perform broad cross-slice refactors;
- change public contracts without explicit authorization;
- change dependencies, CI, or toolchain.

Stop conditions:
Stop and report if any stop condition from docs/engineering/code-health-gate.md applies.

Also stop if:
- unrelated dirty working tree state exists;
- required changes touch forbidden files;
- validation command cannot be identified;
- fixing the smell requires broader design work;
- product behavior would change outside the slice;
- a hand-written product file exceeds 2000 lines and cannot be safely split within this pass.

Validation:
After any local fix, run the focused slice validation command.

Then run pytest -q unless one of these is true:
- the repository documentation explicitly says not to run full pytest for this slice;
- focused validation already fails;
- required dependencies are unavailable;
- full pytest is known to exceed the current execution budget.

If pytest -q is skipped, report the exact reason.

If no fixes are made, still report whether validation was inspected, rerun, or skipped.

Final report format:
1. Current branch.
2. git status --short.
3. Focused validation command identified.
4. Files reviewed.
5. Code health smells found.
6. Smells fixed.
7. Smells deferred.
8. Category A blocking smells remaining: yes/no.
9. Architecture boundary violations remaining: yes/no.
10. File size risks.
11. Validation commands run and results.
12. pytest -q run/skipped and reason.
13. Forbidden files changed: yes/no.
14. Final design baselines changed: yes/no.
15. Recommended next action.

Do not claim success if validation was not run and no accepted reason is provided.
```

---

## 4. 每个实现 prompt 必附的尾部段落

把下面较短的尾部段落附加到未来 implementation slice prompts。

```text
Post-implementation Code Health Review:

After the focused validation command completes, invoke the Code Health Review Pass defined in:

- docs/prompt-patterns/implementation/code-health-review-pass.md

The review subagent must:

- read docs/engineering/code-health-gate.md;
- review only the current slice diff;
- fix only local safe code-health issues within slice scope;
- avoid all forbidden changes listed in the review pass and Code Health Gate;
- rerun the focused validation command after fixes;
- run pytest -q unless a concrete documented reason prevents it;
- report blockers, smells found/fixed/deferred, validation results, forbidden-file status, and remaining risks.

If the focused validation command cannot be identified from the slice document or implementation prompt, the review subagent must stop and report instead of guessing.

The slice is not ready for commit until no Category A blocker remains.
```

---

## 5. 手动短调用

手动触发 review 时使用：

```text
Run a Code Health Review Pass on the current implementation slice diff.

Use docs/prompt-patterns/implementation/code-health-review-pass.md as the execution prompt.

Use docs/engineering/code-health-gate.md as the source of truth.

Review only files changed in this slice.

Do not add features, broaden scope, touch forbidden files, or change final design baselines.

Rerun the focused validation command after any fix.

Run pytest -q unless a concrete documented reason prevents it.

Report smells found, fixed, deferred, validation results, Category A blockers, architecture boundary violations, forbidden-file status, and remaining risks.
```

---

## 6. 集成规则

某个 slice 在满足以下条件前，不可视为 ready for commit：

* focused validation 已完成；
* Code Health Review Pass 已完成；
* 没有 Category A blocker 剩余；
* 没有 architecture boundary violation 剩余；
* 没有 forbidden files 被修改；
* 任何 deferred smell 都已明确报告；
* commit 已被授权。
