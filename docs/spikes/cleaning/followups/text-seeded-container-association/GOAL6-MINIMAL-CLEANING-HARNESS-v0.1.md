# Goal 6 — Minimal Human-Reviewed Cleaning Harness v0.1

状态：`FROZEN_FOR_IMPLEMENTATION`

## 1. Data and provenance

- 读取 Goal 5 `case-51..54` source crop、S1 input、calibration lock 与 routed result；所有 hash 必须匹配 Goal 5 matrix。
- `case-51..53` 是唯一主试验候选；`case-54` 是不可编辑的 abstention control。
- `cal-51..54` 可以在 calibration 阶段产生局部 mask/fill preview，但不得计入 Goal 6 正式质量结论。
- 所有 Goal 6 运行首先验证 source/crop hash；运行后再次验证。输出目录已存在则失败，禁止覆盖/重跑正式 evaluation。

## 2. Required artifacts per case

```text
source.png                         # 只读副本/引用
goal5-spatial-overlay.png          # seed + container/support
text-mask-overlay.png              # core / soft / uncertain 三层
safe-region-overlay.png            # protected + M_safe + M_effective
candidate-fixed-white.png          # 仅适用 E1
candidate-border-sampled.png       # 仅适用 E1
candidate-telea-r2.png             # 仅 E2 comparison
comparison.png                     # source / overlays / candidate / 200% zoom
result.json                         # hashes、route、risk、decision、metrics
```

`SKIP` case 不生成 candidate image；仅生成 source、overlay 与 skip reason。

## 3. Pixel-mask contract

每个 upstream fragment 必须处于以下之一：`assigned_core`、`assigned_soft`、`uncertain`、`unassigned_with_reason`。不允许 silent drop。

```text
M_text_core ⊆ M_context
M_text_soft ⊆ M_context
M_uncertain ⊆ M_context
M_effective = M_text_core ∩ M_safe
M_effective ∩ M_protected = ∅
```

其中 `M_context` 是对应 coarse container 或 bounded support；`M_protected` 至少含 context contour band、不同容器边界带、强结构边缘与不确定带。

对 `different` topology，所有 context、mask、safe region、candidate 均按 container 分区；任意两个分区的 effective mask 交集必须为 0。

## 4. Risk and reconstruction contract

| Risk | Conditions | Permitted output |
| --- | --- | --- |
| E1 | 浅色、低方差、core 远离 protected | `fixed_white` + `border_sampled_fill` comparison，均为 REVIEW_REQUIRED |
| E2 | 靠近边界但未触 protected | `Telea r=2` comparison only，REVIEW_REQUIRED |
| E3 | 网点/渐变/线稿或人物结构粘连 | 不清字，REVIEW_REQUIRED |
| E4 | SFX/装饰字/复杂 free text | SKIP |
| regionless | 无有效空间输入 | SKIP |

任何对保护区域、context 之外或不同 container 的像素变化都是 hard failure。候选图不能因视觉较好而覆盖该失败。

## 5. Calibration and one-shot evaluation

1. 先在 `cal-51..54` 运行预声明、有限的 mask 参数候选；评价只用几何安全 contract、seed trace 与人工 calibration review，不读取 `case-*` 标签或输出。
2. calibration 选出单一 policy 并冻结：polarity 规则、core/soft 阈值、component 尺度带、context erosion、protected edge band、E1 variance 与 border-distance 门槛。
3. 以 lock 的实现 hash 与参数对 `case-51..54` 运行一次；之后不允许改参数、mask、risk 分类或 fill 选择。
4. 运行完成后由人工只读 review 评价候选，填写 `ACCEPTABLE / REVIEW / UNUSABLE / SKIP` 与理由；reviewer 不改代码或输出。

## 6. Metrics and gates

| Metric | Gate |
| --- | ---: |
| source / S1 / Goal 5 hash integrity | all PASS |
| mask/context containment | 100% |
| protected overlap | 0 pixels |
| cross-container effective-mask or pixel-change overlap | 0 pixels |
| case-54 masks / changed pixels | 0 / 0 |
| unexplained high-confidence fragment | 0 |
| evaluation rerun / post-run tuning | 0 / 0 |
| E1 visual `ACCEPTABLE` regions | at least 2 for expansion verdict |
| severe non-text / border / character damage accepted | 0 |
| readable residual text in `ACCEPTABLE` candidate | 0 |
| all outputs marked AUTO_ACCEPT | 0 |

不存在 pixel-ground-truth 时，不报告 pixel precision、recall、IoU 或 boundary F1。人工审查只针对可见残字、边框、线稿、人物/背景损伤与可用性。

## 7. Stop conditions

立即停止并只保存失败证据的条件：hash 不符、GT/asset-ID 泄漏、source 改变、context 外编辑、protected overlap、跨容器修改、case-54 被处理、silent fragment drop、evaluation 后调参、需要禁止模型或产品集成才能继续。

## 8. Reviewer form

每个 candidate 在 100% 与 200% 下填写：

| Field | Allowed value |
| --- | --- |
| text residue | none / minor / readable |
| bubble border damage | none / minor / severe |
| line-art or character damage | none / minor / severe |
| background discontinuity | none / minor / severe |
| overall | ACCEPTABLE / REVIEW / UNUSABLE / SKIP |
| evidence | 简短自由文本 |

`ACCEPTABLE` 只能在 residue=none 且所有结构损伤=none/minor 时填写；任何 severe 或 readable residue 至少为 `REVIEW`。
