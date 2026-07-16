# Goal 5 — Routed Spatial Association Validation v0.1

状态：`FROZEN_FOR_IMPLEMENTATION`

## GOAL

验证 Goal 4 识别出的三类空间任务能否组成一个高精度、允许弃权且不依赖人工真值输入的分流架构：

```text
Detection / Grouping seeds + local image evidence
├─ strong container evidence → COARSE_CONTAINER_SEARCH
├─ valid compact text without container evidence → BOUNDED_SUPPORT
└─ invalid / conflicting / insufficient evidence → REGIONLESS_ABSTENTION
```

Goal 5 只回答该架构是否值得进入 Goal 6 的最小清字试验。它不生成 Pixel Text Mask，不执行 Cleaning，也不声称像素级分割准确率。

## 冻结决策

1. 保留 text-first association；不改写为通用 bubble detector。
2. 显式/接触气泡使用 B1-style seeded watershed 作为 coarse container search；B1 是强基线，不是生产实现。
3. 无气泡文字使用独立 bounded-support contract；不得把 support 声称为 container。
4. 无 seed、极端跨幅、复杂装饰/SFX 或证据冲突输出 regionless abstention。
5. same/different 只在证据 decisive 时确认；否则 `topology=uncertain`，不得进入 Goal 6。
6. OCR 字符串不进入 router；只用 fragment 位置、尺度、方向、分组、score 与局部图像证据。
7. 所有阈值只在四个 calibration crop 冻结；四个 evaluation crop 只运行一次，失败后不回调。
8. R0、Goal 4 calibration 与 Goal 4 R0 output 均不用于本轮调参或评分。

## 成功与裁决

唯一允许的裁决是：

- `GO_TO_GOAL6_MINIMAL_CLEANING_TRIAL`：8/8 route contract 正确、evaluation 4/4、无 false-low-risk、无错误确认 topology；
- `KEEP_AS_ASSOCIATION_SPIKE_ONLY`：安全弃权成立，但分流或空间 contract 证据不足；
- `NO_GO`：出现跨容器非弃权合并、错误 topology 确认、危险路由或 GT/数据泄漏。

正向裁决只授权规划 Goal 6 的人工审查最小试验，不授权自动清字、Provider 或 Workflow。

## 允许文件

```text
docs/spikes/cleaning/followups/text-seeded-container-association/goal5-routed-association/GOAL5-*.md
tools/spikes/text_seeded_container_association/routed_*.py
tests/unit/test_text_seeded_container_routed_*.py
data/local/text-seeded-container-association/goal5-routed-v0.1/**  # Git ignored
```

## 禁止文件与能力

- 不修改 `src/manga_read_flow/**`、SRS、HLD、PROJECT-PLAN、algorithm lock 或既有 REPORT/GATE；
- 不实现 Pixel Text Mask、safe edit region、fill、inpaint 或任何实际 Cleaning；
- 不使用 LaMa、Diffusion、ControlNet、FFT 网点重建、GrabCut、Active Contour、CRF；
- 不实现 CleanerProvider，不接入 Workflow、Repository、SQLite、ArtifactService；
- 不生成 benchmark manifest，不使用 `AUTO_ACCEPT`，不覆盖原图，不 push；
- 不以 asset ID、人工标签、OCR 字符串或 evaluator verdict 作为算法输入。

## 理由、拒绝方案与风险

选择显式 router，是因为 Goal 4 已证明统一 corrected P1 会把真实气泡退化成文字邻域 support，而 B1 又会在 free text/false seed 上扩散。拒绝继续把 B1、bounded support 和 abstention 包装成一个统一 mask 算法，也拒绝在 Goal 5 提前实现清字来“看效果”。

主要风险是：小样本阈值只记住画风；B1 basin 被分镜线误当容器；紧凑 SFX 被误送 container；大气泡因面积上限被弃权；same/different evidence 仍不足。所有风险优先转为 `REVIEW_REQUIRED/SKIP`，不得通过扩大 coverage 修复。

## 验证场景与开放项

必须覆盖 explicit same、explicit different、bounded support、regionless abstention 各一组 calibration 与一组 evaluation。开放项只有 Goal 6 的像素文字 Mask 与 safe edit region 生成方式；它们不在本 Goal 内回答。
