# Plan

1. 已完成独立评审，记录 A1/A2 的 guard、abstain 与 scope 风险。
2. 已以只读 Stage A harness 重放 A0，并实现 A1/A2/A5；算法模块不读取 case/target/name/坐标。A5 使用统一的局部颜色距离与连通性，不使用颜色名称或人工颜色阈值。
3. 已生成 hash lock、component review materials 和 Stage A 人工 FORM。
4. 已在人工标注返回后完成通用 arm 评估；未满足零误分、完整文字覆盖、完整 boundary proof 与零 unresolved，裁决 `NO_GO`，不进入 Stage B。

拒绝的替代方案：缩小 required mask、扩大 safe mask、复用 Slice F virtual-boundary planner、按 g002/g004 调参或运行 Cleaner。它们不能提供 physical-boundary 的通用安全证据。
