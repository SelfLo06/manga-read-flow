# Physical Bubble Boundary Evidence and Correction Spike v0.1

状态：`STAGE_A_COMPLETE / NO_GO`；Stage B 已拒绝。

本 Spike 是 Slice 3 的独立、受限能力研究；不修改产品实现、Slice 3 acceptance、冻结 run、数据库或 active pointer。

唯一问题是：`dilate(text_core, 2)` 在真实物理气泡边界走廊中产生的 required support，能否以通用像素证据安全地区分为文字、真实边框或不可判定像素。

Stage A 仅产生 hash-locked mask/evidence、三个候选分类（A1/A2/A5）和维护者人工标注材料。A5 检验通用局部颜色／背景色差证据，不扩展到说话人归属或排版样式。它不运行 Cleaner，也不产生 Cleaning candidate。未知像素一律标记 `unresolved_uncertain`；`protected` 永远不可写。

冻结输入为 Slice 3 `case-72/run-v0.5` 的 g002/g004 source 与 evidence。控制样本在同一实现中仅作回归/abstain 评估；不得改变 g002/g004 的算法、参数或阈值。
