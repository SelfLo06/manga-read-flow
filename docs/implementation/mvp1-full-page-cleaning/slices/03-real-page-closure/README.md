# Slice 3——case-71 收口与 case-72 泛化

**状态：`IN_PROGRESS`；目前暂停在受控的 Physical Bubble Boundary Spike。**

## 范围

对 case-71 运行正式整页 Cleaning workflow 并记录人工 Gate，然后使用完全相同的 contract 和 configuration 处理 case-72，并单独记录人工 Gate。禁止增加 case-specific schema、threshold 或特殊逻辑。

截至 Correction Checkpoint A：case-71 已完成原子 acceptance；case-72 的 ledger 与安全 block 正确，但泛化质量尚不可接受。g003 已由旧 instance-level E3 广播修正为 pixel-level `REVIEW`；g002/g004 仍因真实物理 bubble boundary capability blocker 阻塞。详见 [Checkpoint REPORT](REPORT.md)、[当前 Gate](GATE.md)、[case-72 诊断](../../diagnostics/case-72-generalization-diagnosis-v0.1.md) 与 [Physical Boundary Spike 交接](../../diagnostics/physical-bubble-boundary-spike-handoff-v0.1.md)。

## 退出 Gate

两个页面必须分别由 Slice 1/2 的持久合同裁决为 accepted 或 blocked。只有两个 Gate 都完成后，combined code-health review 才能覆盖 Spike E、Slice F 和三个整页 Slice。

当前不授权 Combined Code Health Review 或 Typesetting。只有独立 Physical Bubble Boundary Spike 的 Gate 为 `GO` 后，才能返回本 Slice 继续 case-72 集成、人工 Gate 和最终提交。
