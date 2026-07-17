# 当前真实进度

本文是给项目维护者看的当前状态摘要，不是 Codex 的任务文件。文档层级和正式入口见 [../README.md](../README.md)。

## 一句话结论

M0“架构机制验证”已完成；项目目前处于 MVP-1“高质量单页视觉闭环”的验证阶段。系统尚未达到可交付的完整单页中文漫画结果。

## 已确认的阶段事实

- M0 已证明 WorkflowLoopEngine、Provider Adapter、ArtifactService、Repository/DAO、QualityIssue、active pointer 与恢复/幂等基础能够形成后端机制闭环。
- MVP-1 的 Visual Contract 已形成详细设计：见 [../design/mvp1-visual-contract/](../design/mvp1-visual-contract/)。
- 已完成一组受限的 topology、pixel evidence、visible glyph support、real cleaner 与单页清字纵向切片 Spike；正式证据在 [../spikes/mvp1-visual-contract/](../spikes/mvp1-visual-contract/)。
- 最新的 Spike E 只证明 case-71 内一个允许的 E1 文本段可以局部清除且写回范围受控；同簇另一段因 safe-edit 边界不足而进入阻塞复核。它不是整页清字成功，也不是产品级自动清字结论。
- OCR、翻译、气泡实例拓扑、清字资格、清字、嵌字与视觉验证仍需收敛为高质量单页闭环；复杂 SFX、艺术字和复杂背景文字可继续明确排除。

## 当前阶段边界

MVP-1 的目标是：在声明支持的常规对白气泡/旁白框范围内，对一张真实漫画页得到完整、干净、舒适、可直接阅读的中文结果。当前优先级是输入/实例拓扑、safe edit、清字和嵌字的视觉正确性，而不是批处理吞吐量或整章自动化。

局部人工审查、冻结输入和表单只用于开发期验证；它们不等同于产品运行时必须人工参与。遇到证据不足的区域，系统应保留原图、记录 QualityIssue，并允许页面其余可处理区域继续完成。

## 维护者应读什么

1. 项目范围与当前路线：[../SRS-v1.0.md](../SRS-v1.0.md)、[../HLD.md](../HLD.md)、[../PROJECT-PLAN.md](../PROJECT-PLAN.md)。
2. 当前 MVP-1 设计：[../design/mvp1-visual-contract/GOAL.md](../design/mvp1-visual-contract/GOAL.md) 与 `final/`。
3. 当前实验裁决：[../spikes/mvp1-visual-contract/](../spikes/mvp1-visual-contract/)。
4. 需要恢复全局上下文时：[../handoffs/project-realignment-after-goal7/HANDOFF.md](../handoffs/project-realignment-after-goal7/HANDOFF.md)。

“下一步具体做哪一个 Goal”应由当前项目级基线、最新 Gate 和一次新的设计裁决共同决定；本导读不替代该裁决。
