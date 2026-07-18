# Stage A Harness

## A0 基线

读取冻结 `visible` 为旧 required support，读取 `safe`、`protected`、`uncertainty`、`instance` 与 source bytes；不重写这些输入。必须复现 g002 `15,802/15,092/710` 与 g004 `13,133/13,063/70`。

## 候选

| Arm | 方法 | 硬 guard | abstain |
| --- | --- | --- | --- |
| A1 | text-seeded constrained support：从深色 core 沿旧 required support 的局部连通组件传播 | 不跨 `protected`；不跨检测出的边界 ridge；不越过 instance | 无 core ownership、接触 barrier 或局部外观不一致时为 `unresolved_uncertain` |
| A2 | boundary-aware geodesic support：以 gradient/edge ridge 和 protected 为硬 barrier，计算 core 到旧 support 的有界可达性 | protected 是不可穿越 barrier；ridge 是不可穿越 barrier | 任何分歧、ridge 不连续或到种子路径不唯一时为 `unresolved_uncertain` |
| A5 | color-aware text-seeded support：从高置信 seed 以局部 Lab 文字／气泡背景色差与笔画连通性扩张 | 不跨 `protected` 或 physical ridge；颜色只参与统一距离证据，不参与颜色名称分支 | 背景样本不足、色差/连通性矛盾、跨 ridge 或多候选冲突时为 `unresolved_uncertain` |

二者都不允许把 `protected` 改为 safe，也不允许把不确定像素写成可清除文字。每个旧 required 像素必须在 `required_text`、`proven_non_text_boundary`、`unresolved_uncertain`、`evidence_error` 中恰有一个分类；在没有人工或可证明证据前，本 harness 不产生 `proven_non_text_boundary`。

## 输出与人工 Gate

每个 unsafe component 输出 original crop、nearest-neighbor 放大 crop、core/required/safe/protected/uncertainty、gradient/ridge、component 与 A1/A2 overlay、统计和输入 hash。生成 `FORM-stage-a.md` 后立即暂停，不能由 agent 填写。

A5 同时输出 seed/background 的 Lab 统计、色差分布和色族审计标签。深蓝、橙色、抗锯齿边缘的 precision/recall 在没有维护者像素标签前必须明确标为 `PENDING_HUMAN_LABELS`，不得以颜色启发式自行填写。控制必须覆盖同气泡多颜色、浅色文字和彩色边框；色族标签只用于报告，不能影响阈值或算法路径。
