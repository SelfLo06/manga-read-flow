# 150 Cleaning

Cleaning 只在已接受的页面、容器关联、文字 support、physical boundary 和 safe-edit 证据上生成候选 cleaned artifact；原图永不覆盖。Cleaner 不能决定 eligibility、skip 或 accept，所有写入范围与 provenance 由候选/检查账本解释。

当前主线处于 M1。受限 topology、pixel evidence、real cleaner 和局部页面切片证明了部分机制，但没有形成通用单页能力。最新 physical-boundary 诊断裁决：A1/A2/A5 当前均 NO_GO；g002/g004 为 `BLOCKED_PENDING_CAPABILITY`；本 Spike `ACTUAL_CLEANING=NOT_RUN`。

当前选择 protected/uncertainty fail-closed，不缩小 required 或扩大 safe 来制造通过。拒绝全局阈值放宽、按 case/坐标硬编码和把人工标签作为算法输入。风险、实验与检查分别见 [已知问题](150-10-known-problems.md)、[实验索引](150-20-experiments.md) 和 [CleaningCheck](150-40-cleaning-check.md)。
