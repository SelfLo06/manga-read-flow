# Goal 7 — Local Association Routing Correction

状态：`FROZEN_FOR_PHASE_A`

## GOAL

修正已确认的 page-global association 粒度错误，使普通文字 group 在整页环境中独立进入
局部 association；异常 seed、uncertain topology 或资源超限只能影响所属 local cluster，
不得使整页其他 group 失去资格。

固定方向：

```text
Page
└── local group / local cluster
    ├── false / oversized seed → local abstention
    ├── free text              → bounded support candidate
    └── container-bearing      → bounded local B1 candidate
```

本 Goal 保留 text-first、局部多源竞争、same/different/uncertain topology、free-text
support 与 first-class abstention。它不重新选择 Cleaning 方向。

## 三阶段

1. Phase A：复用 40 页 frozen S1，只做 clustering、local routing、local topology 与资源预算；
2. Phase B：在人审冻结的小样本上运行 bounded local B1，生成真实 source/seed/ROI/coarse
   region contact sheet；
3. Phase C：实现和参数冻结后，对同一 40 页 S1 单次复放，只评估 association coverage、
   route correctness、资源稳定性和 coarse container 可见性。

## 非目标

- 不运行 Pixel Text Mask、safe edit region、E1/E2、Telea 或实际 Cleaning；
- 不重跑 Detection/Grouping；
- 不进入 `src/manga_read_flow/**`、CleanerProvider 或 Workflow；
- 不使用 LaMa、Diffusion、ControlNet、FFT、C++ 重写或 `AUTO_ACCEPT`；
- 不生成 benchmark manifest；不 commit/push。

## 允许文件

```text
docs/spikes/cleaning/followups/text-seeded-container-association/goal7-local-routing/**
tools/spikes/text_seeded_container_association/goal7_local_routing.py
tests/unit/test_text_seeded_container_goal7_local_routing.py
data/local/text-seeded-container-association/goal7-local-routing-v0.1/**
docs/spikes/cleaning/CLEANING-HANDOFF.md
docs/spikes/cleaning/CLEANING-DESIGN-RATIONALE.md
docs/spikes/cleaning/algorithm-lock-v0.1.md
```

## 决策、理由与拒绝方案

- 决策：page-global association 和 full-page B1 被最新 40 页证据拒绝；local cluster 是唯一
  允许继续验证的粒度。
- 理由：33/40 页被全页联合几何误杀；任意 uncertain pair 可阻塞整页；full-page B1 可
  OOM 到约 14GB。
- 拒绝：只提高 0.85/0.65 阈值、继续 whole-page route、仅加速/C++、或用更强 inpaint
  掩盖覆盖率失败。

## 开放项

- local clustering 是否会把相邻不同气泡连成一个 cluster；
- bounded local B1 是否能看见普通对白 coarse container；
- local topology 是否能保留接触气泡，同时不拆同气泡多列文字；
- 在资源预算内能达到多少可审查 coverage。
