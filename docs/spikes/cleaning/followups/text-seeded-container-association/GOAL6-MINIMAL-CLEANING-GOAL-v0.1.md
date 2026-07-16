# Goal 6 — Minimal Human-Reviewed Cleaning Trial v0.1

状态：`FROZEN_FOR_IMPLEMENTATION`

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

只能读取 `GOAL5-GOAL6-INPUT-CONTRACT-v0.1.md` 指定的 Goal 5 evaluation output：

| Asset | Route | Goal 6 role |
| --- | --- | --- |
| case-51 | same, 1 coarse container | E1 candidate；同容器多组文字 |
| case-52 | different, 3 coarse containers | 独立容器 E1/E2 candidate；跨容器防护 |
| case-53 | 1 bounded support | free-text safety candidate；证据不足则不清字 |
| case-54 | regionless abstention | 必须保持原样的 skip control |

cal-51～54 只可用于开发 smoke/calibration，不进入最终效果结论。

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

## 允许文件

```text
docs/spikes/cleaning/followups/text-seeded-container-association/GOAL6-*.md
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
