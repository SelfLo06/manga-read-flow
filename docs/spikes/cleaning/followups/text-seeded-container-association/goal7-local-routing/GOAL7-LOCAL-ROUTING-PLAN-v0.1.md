# Goal 7 — Local Association Routing Plan

状态：`PHASE_A_IN_PROGRESS`

## Phase A — 静态局部路由重构

1. 锁定 frozen S1/hash；
2. 将 page groups 转为 local group views；
3. 仅连接空间邻近、尺度相容且不会形成大范围链式扩张的 mutual-neighbor group；
4. 每个 local cluster 独立计算 geometry/topology/ROI/resource budget；
5. 输出 40 页 matrix、cluster crop/overlay 与人工选择表；
6. 不运行 B1。

## Phase B — 小样本 bounded local B1

1. 读取已填写人工表，冻结 Phase B cluster IDs；
2. 先写资源预算与局部不连带回归测试；
3. 在 L1 local ROI 运行带 queue/runtime budget 的 B1；
4. 超限只标记当前 cluster abstain；
5. 生成至少 12 个真实可见诊断 panel/contact sheet；
6. 人工确认普通对白 coarse container 是否可见。

## Phase C — 一次性 40 页复放

1. 冻结 clustering、ROI、topology 与资源参数；
2. 对 frozen S1 单次运行；
3. 不再调参；
4. 只计算 coverage、route、资源稳定性与可见性门禁；
5. 输出 GO / NO-GO；不运行 Cleaning。

## 文档回写

完成后更新 Handoff、Design Rationale 和 Algorithm Lock：

```text
page-global association = rejected
local group/cluster routing = required
full-page B1 = rejected
bounded local B1 = candidate pending Goal 7 gate
Pixel Text Mask = blocked pending local association coverage
```

## 验证场景

- 普通多气泡页：每个局部 group 保留独立候选；
- `case-10` oversized SFX：只局部 abstain；
- `case-26` 单 uncertain pair：不影响不相干 cluster；
- `case-38` 多 uncertain pair：只相关 cluster unresolved；
- blank page：0 cluster 是有效结果；
- 运行中任一 ROI 超预算：该 ROI abstain，其余 ROI 继续。
