# 实现切片任务 Pattern

这是一个面向 MVP-0 implementation slice tasks 的轻量可复用模式。

它基于 `docs/implementation/mvp0-fakeprovider-slice/slices/` 下的 Slice 01-07 文档。它不得把某个 slice 扩大到超出对应 slice document 的范围。

## 适用场景

- MVP-0 backend implementation slices
- 有清晰文件边界的小型垂直实现任务
- 必须以测试、命令输出和 diff review 收尾的 Codex tasks

不要用它生成新的产品路线图、详细设计基线或真实 Codex prompt，除非正在准备执行某个具体 slice。

## 目标

用一到两段说明精确 slice objective。

包含：

- 这个 slice 证明什么；
- 为什么现在做；
- 它有意不实现什么；
- 它支持的产品阶段。

## 来源文档

只列出 slice 需要的文档。

典型来源：

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- 相关最终详细设计；
- 相关 MVP-0 implementation package files；
- 精确 slice document。

避免添加过宽来源清单，以免诱导 agent 重新打开已经收敛的设计决策。

## 允许文件

列出实现可以修改的精确文件或目录。

清单应足够窄，使 diff 能快速 review。显式包含 tests 和 fixtures。

## 禁止文件

列出实现不得触碰的文件和类别。

典型禁止范围：

- 无关 source code；
- UI / API / frontend files，除非 slice 处理它们；
- 使用 FakeProvider 的 slice 中的真实 providers；
- export output、ZIP、manifest 或 `ExportRecord`，除非 slice 处理 export；
- `docs/design/**/final/**`；
- secrets、logs、caches、build outputs、local config 和 AI runtime files。

## 实现边界

说明 slice 必须保持的架构规则。

示例：

- Repository / DAO 是唯一 SQLite 访问入口。
- Provider adapters 不得访问 SQLite。
- Provider adapters 不得登记 official artifacts。
- StageExecutor 不得更新 active pointers 或创建 WorkflowDecision。
- ArtifactService 不得决定 retry、fallback、warning、block 或 readiness。
- WorkflowLoopEngine 拥有 workflow decisions。
- Active output selection 不得使用 timestamps 或仅依赖 Page.status。

## 验证命令

提供一个聚焦命令，通常是 pytest target：

```bash
pytest tests/integration/test_<slice_name>.py
```

如果需要多个命令，解释原因。在早期 slice 工作中，优先使用聚焦 integration tests，而不是宽泛 full-suite runs。

## 预期输出

描述实现后的可观察结果：

- 应存在的 files 或 modules；
- 应通过的 behavior；
- 持久化或暴露的 evidence；
- 覆盖的 failure paths；
- 仍然有意缺席的内容。

## Commit 规则

默认规则：

```text
Do not commit unless explicitly allowed.
```

如果允许 commits，要求验证通过后做一个聚焦 slice commit。只 stage slice 允许的文件。

## 停止条件

遇到以下情况停止并报告：

- 存在 unrelated dirty working tree；
- slice 需要 forbidden files；
- slice 需要更广泛的设计决策；
- validation 无法因无关原因运行；
- 实现 slice 会要求 UI、API、真实 providers、export output 或 slice 外的 batch-scale behavior；
- 某个 architecture invariant 会被违反。

## 最终报告要求

最终报告应包含：

- files changed；
- what was implemented；
- tests or commands run；
- pass / fail result；
- what was skipped and why；
- risks that remain；
- 确认 forbidden files 和 final design baselines 未被修改。

如果未执行 validation，不要声称成功。

## 实现任务的 Harness 原则

- 实现的真实 harness 不是 prompt text；而是 tests、commands、diffs、file boundaries 和可 review evidence。
- 每个实现任务都应让 Codex 报告改了什么、运行了什么、通过了什么、跳过了什么、风险在哪里。
- 优先 pytest 和聚焦 integration tests，而不是新的自定义 harness runtime。
- 不要为本项目构建自定义 agent loop 或类似 Superpowers 的框架。
- 只有当重复失败证明有必要时，才添加 repo-side scripts 或 checkers。

## 最小可复用骨架

```text
Goal:
Implement <slice id and name>.

This slice proves <specific behavior>. It does not implement <explicit non-goals>.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- <relevant final design docs>
- <exact slice document>

Allowed files:
- <narrow source paths>
- <test file>
- <fixtures if needed>

Forbidden files:
- <unrelated product areas>
- docs/design/**/final/**
- secrets, logs, caches, build outputs, local config, AI runtime files

Implementation boundaries:
- <architecture invariant 1>
- <architecture invariant 2>
- <slice-specific boundary>

Validation command:
pytest <focused test target>

Expected output:
- <observable success>
- <failure path coverage>
- <intentionally absent scope>

Commit rule:
Do not commit unless explicitly allowed. If allowed, make one focused slice commit after validation passes and stage only allowed files.

Stop conditions:
- Unrelated dirty working tree exists.
- <forbidden dependency or scope expansion appears>
- Validation command is unavailable or failing for unrelated reasons.

Final report:
- files changed
- implementation summary
- validation run and result
- skipped validation, if any
- risks
- confirmation that no forbidden files or final design baselines changed
```

## Scope Guard

本 pattern 只是把现有 slice document 转换成真实 task prompt 的外壳。

它不得增加 slice document 之外的能力。如果 slice document 说 “ready_for_export only”，生成的 prompt 就不得要求实际 export output。如果 slice document 说 FakeProvider only，生成的 prompt 就不得要求真实 provider integration。
