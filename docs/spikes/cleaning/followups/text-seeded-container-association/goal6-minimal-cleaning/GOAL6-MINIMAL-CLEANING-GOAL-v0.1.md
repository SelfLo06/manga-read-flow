# Goal 6 — Minimal Human-Reviewed Cleaning Trial v0.1

状态：`COMPLETED`（见 [`GOAL6-FINAL-REPORT-v0.1.md`](GOAL6-FINAL-REPORT-v0.1.md)）

校准状态：`REOPENED_FOR_TARGETED_SUPPLEMENT`。初始 `cal-51..54` 已证明 P1 只在单一普通气泡上可用，而不能支持全局 policy freeze；它们保留为失败/skip 证据，不进入最终 policy 选择计数。

补充校准结论：`P0_conservative` 已由 `cal-61` 与 `cal-62` 两个独立正例一致选定；二者均为 `residual=none`、`structure_damage=none`。`cal-65` 为上游将星光背景斜向装饰纹理误识别为文字/容器的 false positive，固定 `ALL_SKIP`，不计入清字 policy 统计。

## GOAL

验证 Goal 5 已冻结的 `coarse container / bounded support / regionless abstention` 路由，能否为**保守的像素级文字 Mask、safe edit region 与局部清字**提供足够输入证据。

Goal 6 只产出少量、人工审查的候选图和可审计门禁；不恢复自动清字，也不进入产品路径。

```text
Goal 5 frozen spatial input
  → local polarity-aware text-mask candidates
  → protected mask + safe edit region
  → E1 fixed/border-sampled fill candidate
  → 200% visual review / abstention
```

## Frozen intake

只能读取 [`../goal5-routed-association/GOAL5-GOAL6-INPUT-CONTRACT-v0.1.md`](../goal5-routed-association/GOAL5-GOAL6-INPUT-CONTRACT-v0.1.md) 指定的 Goal 5 evaluation output：

| Asset | Route | Goal 6 role |
| --- | --- | --- |
| case-51 | same, 1 coarse container | E1 candidate；同容器多组文字 |
| case-52 | different, 3 coarse containers | 独立容器 E1/E2 candidate；跨容器防护 |
| case-53 | 1 bounded support | free-text safety candidate；证据不足则不清字 |
| case-54 | regionless abstention | 必须保持原样的 skip control |

cal-51～54 只可用于开发 smoke/calibration，不进入最终效果结论。

在正式 evaluation 前，必须新增 6–8 个、与 Goal 5 evaluation/R0/Goal 4 source hash 隔离的 targeted calibration case：至少两个普通气泡正例、两个边界敏感例、两个负例及一到两个无气泡 SFX/有限 support 例。单一正例上的胜出不得冻结 policy。

## Frozen decisions

1. Goal 5 的 coarse container/support 仅是搜索和编辑上限，绝不是删除 mask。
2. Pixel Text Mask 固定为：seed polygon + polarity-aware local segmentation + seeded connected components + soft edge；OCR 字符串不得参与。
3. `text_mask_core`、`text_mask_soft`、`text_mask_uncertain_band` 必须分开；uncertain band 不得写入清字 mask。
4. `M_effective = text_mask_core ∩ M_safe`；若 core 触及 protected structure、超出 container/support、或有未解释高置信 fragment，必须 `SKIP`。
5. `different` topology 的每个 container 独立 mask、独立 safe region、独立 fill；不得跨容器聚合。
6. 仅 E1（浅色、低方差、文字远离保护边界）可生成 `fixed_white` 与 `border_sampled_fill` 两个候选，二者都仍标记 `REVIEW_REQUIRED`。
7. E2 只允许低半径 Telea 作为**比较候选**，不自动选择；E3 保持 `REVIEW_REQUIRED`，E4 与 regionless 保持 `SKIP`。
8. 任何实际修改只写入 Git 忽略的本地 spike output；原 crop/source 永不覆盖。

## 成功与裁决

允许的最终裁决：

- `GO_TO_EXPANDED_CLEANING_VALIDATION`：全部输入/安全门禁通过；case-54 严格跳过；0 次跨容器或 protected 修改；至少两个独立 E1 region 的人工评级为 `ACCEPTABLE`，且没有可辨认文字残留或结构性伤害。
- `KEEP_AS_MINIMAL_MANUAL_REVIEW_SPIKE`：安全限制与弃权正确，但清字质量或样本不足以扩展。
- `NO_GO`：出现跨容器修改、protected structure 损伤、非 regionless case 被强制处理、case-54 被修改、source/hash 泄漏，或需要扩大区域才能掩盖失败。

无论结果如何，Goal 6 都不产生 `AUTO_ACCEPT`，不授权 CleanerProvider、Workflow、Repository、SQLite、ArtifactService 或产品集成。

## 已授权的整页人工演示扩展

在 policy 已冻结后，允许仅以用户指定的 `local_samples/real/black2.webp` 与
`local_samples/real/gura_color.webp` 进行一次整页候选可视化。该扩展的目的只是让
维护者观察多区域组合时的实际效果，**不是** Goal 6 的独立 evaluation，也不得改变
上述成功裁决、P0 参数、Goal 5 router 或 S1。

- 每张源图先复制到 Git 忽略的本地输入包并记录 SHA-256；原图绝不覆盖。
- 只对重新运行的 S1、冻结 Goal 5 router 与 P0 mask 均通过的局部 context 生成候选；
  `E3`、regionless、uncertain 与未分配 fragment 保持原像素。
- 输出必须分为 `E1-only`（仅 border-sampled fill）与 `E2-comparison`（E2 Telea r=2
  的人工比较层）；后者不是自动选择结果。两者都标记 `REVIEW_REQUIRED`。
- 必须证明总改动完全位于各 context 的 `M_effective` 并且不同 container 的 mask 不相交。
- 整页图的人工观感不得回写为 calibration/evaluation 分数，也不得据此修改 lock。

## 允许文件

```text
docs/spikes/cleaning/followups/text-seeded-container-association/goal6-minimal-cleaning/GOAL6-*.md
tools/spikes/text_seeded_container_association/goal6_*.py
tests/unit/test_text_seeded_container_goal6_*.py
data/local/text-seeded-container-association/goal6-minimal-cleaning-v0.1/**  # Git ignored
```

## 禁止项

- 不修改 `src/manga_read_flow/**`、SRS、HLD、PROJECT-PLAN、algorithm lock、Goal 5 frozen docs/output；
- 不使用 LaMa、Diffusion、ControlNet、FFT 网点重建、GrabCut、Active Contour、CRF；
- 不使用通用 inpainting；Telea 仅按本 GOAL 的 E2 comparison 限制使用；
- 不使用 `AUTO_ACCEPT`、benchmark manifest、Provider/Workflow/数据库集成；
- 不把 asset ID、人工标签、reviewer verdict 或 OCR 字符串输入算法；
- 不在 Goal 6 evaluation 后回改 Goal 5 router、阈值、ROI、S1 或本 Goal 的 calibration lock。

## 理由、拒绝方案与风险

Goal 5 证明“在哪里尝试”具有最小证据，不证明“哪些像素可以擦”。因此本轮把 mask 与 fill 分离验证，并把 fill 限制为已有证据支持的浅色局部基线。拒绝把整个 container 清白、把 bounded support 伪装成气泡、以通用 inpainting 修复纹理、以及用效果图代替安全证据。

主要风险包括：seed 漏掉笔画、阈值吞入边框/头发、coarse container 边界本身不精确、anti-aliasing 残字、白填充造成结构损伤，以及 free text 与人物线条粘连。所有此类风险优先 `REVIEW_REQUIRED/SKIP`。

## 验证与开放项

必须验证 hash/provenance、mask 位于输入空间域内、protected overlap=0、different-container 隔离、case-54 不变、输出可重复、200% 人工审查与候选质量表。

开放项仅限后续扩大验证的样本规模、mask 置信度标定与更复杂背景的重建方法；它们不在本 Goal 内解决。
