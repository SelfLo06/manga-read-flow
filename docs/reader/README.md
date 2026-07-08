# 项目维护者阅读入口

这个目录是给人看的中文导读，不是给 Codex 或其他 AI agent 执行任务用的。

这里的文件只解释“每个阶段已经做出了什么设计结果，以及这些结果意味着底层会怎么实现”。它们不是新的权威设计，也不替代源文件。每份解读都会列出对应源文件链接。

## 你应该先看什么

1. [current-status.md](current-status.md)  
   看项目现在真实停在哪里，下一步是什么。

2. [stage-results.md](stage-results.md)  
   看每个阶段最终结果是什么，以及该看哪份中文解读。

3. 按阶段看底层设计结果：
   - [01-requirements-and-architecture.md](01-requirements-and-architecture.md)
   - [02-data-model.md](02-data-model.md)
   - [03-workflow-state.md](03-workflow-state.md)
   - [04-execution-contract.md](04-execution-contract.md)
   - [05-persistence-readiness.md](05-persistence-readiness.md)
   - [06-mvp0-fakeprovider-slice.md](06-mvp0-fakeprovider-slice.md)

## 不建议作为你的主阅读入口

这些文件主要给 Codex / agent / 具体实施任务使用：

- `docs/design/**/PLAN.md`
- `docs/design/**/GOAL.md`
- `docs/design/**/HARNESS.md`
- `docs/design/**/proposals/*.md`
- `docs/design/**/reviews/*.md`
- `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`
- `docs/implementation/mvp0-fakeprovider-slice/GOAL.md`
- `docs/implementation/mvp0-fakeprovider-slice/HARNESS.md`
- `docs/implementation/mvp0-fakeprovider-slice/slices/*.md`
- `docs/implementation/mvp0-fakeprovider-slice/checklists/*.md`

这些是“执行者材料”和“设计过程证据”。你只在需要追溯某个决定、验证某个 agent 是否按约束工作时再看。

## 真正的权威源文件

如果你要查原始设计，请看：

- [../SRS-v1.0.md](../SRS-v1.0.md)
- [../HLD.md](../HLD.md)
- [../PROJECT-PLAN.md](../PROJECT-PLAN.md)
- [../design/data-model/final/data-model-dd-v0.1.md](../design/data-model/final/data-model-dd-v0.1.md)
- [../design/workflow-state/final/workflow-state-dd-v0.1.md](../design/workflow-state/final/workflow-state-dd-v0.1.md)
- [../design/execution-contract/final/execution-contract-dd-v0.1.md](../design/execution-contract/final/execution-contract-dd-v0.1.md)
- [../design/persistence/final/persistence-readiness-dd-v0.1.md](../design/persistence/final/persistence-readiness-dd-v0.1.md)

## 当前一句话

项目已经完成需求、架构、MVP-0 前置详细设计和 FakeProvider 后端切片拆分；还没有开始写后端代码。
