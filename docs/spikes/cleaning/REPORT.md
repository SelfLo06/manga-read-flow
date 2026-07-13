# Cleaning Real Tool Spike — REPORT

## 1. Executive Summary

* Formal Run ID：`20260713T071318Z-a1af2b`
* Git HEAD at input freeze：`f39c0c24ca8198a99281aad424c87f87958ca599`
* Fixture count：10（4 fill、3 inpaint、3 review/skip；4 个 real）
* Source set：existing `local_samples`
* OpenCV：`5.0.0`
* Final verdict：`FURTHER_SPIKE`

核心结论：

```text
Solid fill: GO for strictly bounded white / near-white bubble and narration interiors.
OpenCV inpaint: one low-radius Telea label case is acceptable, but it did not show a repeatable advantage over the fill baseline.
Skip / review boundary: GO; decorative text, complex texture, line art, and non-dialogue overlays were never auto-accepted.
Formal CleanerProvider readiness: not ready for a general inpaint path; a restricted solid-fill path has sufficient spike evidence.
```

首个正式尝试 `20260713T070911Z-863d77` 在 contact sheet 中发现部分矩形 mask 的文字边缘覆盖不足，未用于 verdict。其原始输出保持在 `local_samples/spike_outputs/cleaning/`，原 mask 保存在 `local_samples/cleaning/masks_history/c680252b2e0c/`。修正 mask 后重新冻结并产生本报告使用的 run。

---

## 2. Scope

本轮只验证：

```text
source image + frozen oracle mask
→ fixed/border fill 或 OpenCV Telea/Navier-Stokes
→ local cleaned candidate + metrics + visual review
```

未验证自动 mask 生成、LaMa、生成式修复、正式 CleanerProvider、Workflow、ArtifactService、SQLite、API/UI、Typesetting 或网络服务。所有 source 均只读，候选仅写入 Spike 输出目录。

---

## 3. Environment

| Item | Value |
| --- | --- |
| OS | Linux 6.18.33.2-microsoft-standard-WSL2 x86_64 |
| Python | 3.13.12 |
| OpenCV | 5.0.0 |
| Pillow | 12.2.0 |
| NumPy | 2.4.6 |
| CPU | AMD Ryzen 9 7945HX with Radeon Graphics |
| GPU used | NO |
| Baseline tests | `127 passed` |
| Focused tests | `9 passed` |
| Final tests | 交付前 `pytest -q`：`136 passed in 31.38s`；formal run 期间未使用测试或网络依赖 provider |

---

## 4. Frozen Inputs

| Item | Value |
| --- | --- |
| Manifest SHA-256 | `31c7c35c9607217464bf758fad8a2c4b54f0115dfb31bd181d7ac4a74ad0d23c` |
| Fixture set SHA-256 | `c1167333d490114afb46696f910a242da44eb5de7c8ed34d98f7c2231177226c` |
| Mask set SHA-256 | `4f52d80be2a7686aa43931eb0e88c63115e8df86be544c77b6eea13bfdf6c812` |
| Mask semantics | white = remove; black = preserve |
| Source files unchanged | YES; verify rechecked all frozen source hashes |
| Masks changed after final freeze | NO |
| Invalid masks | 0 |

`manifest.json` records every source and mask SHA-256. `validate` confirms dimensions, binary conversion, region containment, policy distribution, path containment, and the required real-sample count before `run`.

---

## 5. Fixture Inventory

| Fixture | Source | Scenario | Expected policy | Final policy |
| --- | --- | --- | --- | --- |
| fill-white-bubble-01 | synthetic_01 | 白色横排气泡 | AUTO_FILL | AUTO_FILL |
| fill-white-bubble-02 | synthetic_01 | 白色横排气泡 | AUTO_FILL | AUTO_FILL |
| fill-narration-box-01 | synthetic_02 | 白色旁白框 | AUTO_FILL | AUTO_FILL |
| fill-real-black2-vertical-01 | real/black2 | 白色竖排气泡 | AUTO_FILL | AUTO_FILL |
| inpaint-gray-label-01 | synthetic_04 | 灰色平面 label | AUTO_INPAINT | AUTO_INPAINT（仅 Telea r2/d0） |
| inpaint-warm-label-02 | synthetic_04 | 暖色渐变 label | AUTO_INPAINT | REVIEW_REQUIRED |
| inpaint-striped-background-03 | synthetic_04 | 重复条纹与白线 | AUTO_INPAINT | REVIEW_REQUIRED |
| skip-real-black1-title-01 | real/black1 | 线稿上的大装饰文字 | SKIP | SKIP |
| skip-real-gura-color-sfx-02 | real/gura_color | 复杂纹理上的拟声词 | SKIP | SKIP |
| review-real-gura-camera-overlay-03 | real/gura | 面板线稿上的 camera overlay | REVIEW_REQUIRED | REVIEW_REQUIRED |

| Category | Count |
| --- | ---: |
| AUTO_FILL candidate | 4 |
| AUTO_INPAINT candidate | 3 |
| REVIEW / SKIP candidate | 3 |
| Synthetic | 6 |
| Real | 4 |

---

## 6. Method Matrix and Automated Results

正式候选矩阵：

* AUTO_FILL：`fixed_white`、`border_sampled_fill`，dilation `0 / 1`。
* AUTO_INPAINT：Telea、Navier-Stokes，radius `2 / 3 / 5`，dilation `0 / 1 / 2`。
* inpaint fixture 另有两个 dilation-0 fill comparison-only baseline；3 个危险 fixture 不生成正式可接受 candidate，只生成 source/mask debug comparison。

共生成 76 个候选：16 个正式 fill、54 个正式 inpaint、6 个 comparison-only fill。每个候选记录 source/mask/output hash、耗时、mask 像素数、mask 内外变化数、mask 外比例与边界变化比例。

| Method | Candidates | Errors | Median time | Max outside-mask change |
| --- | ---: | ---: | ---: | ---: |
| fixed_white | 11 | 0 | 1.512ms | 0 |
| border_sampled_fill | 11 | 0 | 3.029ms | 0 |
| Telea | 27 | 0 | 17.834ms | 0 |
| Navier-Stokes | 27 | 0 | 14.106ms | 0 |

所有候选 `changed_outside_mask = 0`、`outside_mask_change_ratio = 0`、`boundary_change_ratio = 0`。这只证明本轮 OpenCV 调用没有在给定处理 mask 外改变像素；不替代视觉质量判断。

---

## 7. Visual Review and Ratings

人工视觉 review 使用正式 run 的 `comparisons/<fixture>.png` contact sheets 与 candidate PNG；评级写入 `local_samples/cleaning/ratings/ratings.csv`，每项都覆盖 `ACCEPTABLE`、`REVIEW` 或 `UNUSABLE`。

| Method | ACCEPTABLE | REVIEW | UNUSABLE |
| --- | ---: | ---: | ---: |
| fixed_white | 8 | 1 | 2 |
| border_sampled_fill | 9 | 1 | 1 |
| Telea | 1 | 14 | 12 |
| Navier-Stokes | 0 | 15 | 12 |

评价依据是文字残留、边框/线稿/人物细节、颜色断层、渐变、纹理涂抹和后续嵌字可用性。自动指标未单独决定任何 rating。

独立 reviewer：见第 15 节；reviewer 只读，未修改代码、mask、评分或结果。

---

## 8. Per-Fixture Decision

| Fixture | Best candidate | Rating | Final policy | Reason |
| --- | --- | --- | --- | --- |
| fill-white-bubble-01 | fixed_white d1 | ACCEPTABLE | AUTO_FILL | 文字已清除，边框保持，底色一致。 |
| fill-white-bubble-02 | fixed_white d0 | ACCEPTABLE | AUTO_FILL | 仅有不影响阅读的抗锯齿像素。 |
| fill-narration-box-01 | fixed_white d0 | ACCEPTABLE | AUTO_FILL | 双边框未被触及。 |
| fill-real-black2-vertical-01 | fixed_white d0 | ACCEPTABLE | AUTO_FILL | 真实竖排气泡文字清除完整。 |
| inpaint-gray-label-01 | Telea r2/d0 | ACCEPTABLE | AUTO_INPAINT | 保持灰色 label 局部连续性。 |
| inpaint-warm-label-02 | Navier-Stokes r2/d0 | REVIEW | REVIEW_REQUIRED | 文字已清除，但渐变连续性减弱。 |
| inpaint-striped-background-03 | Navier-Stokes r2/d0 | UNUSABLE | REVIEW_REQUIRED | 重复纹理和白线产生明显涂抹。 |
| skip-real-black1-title-01 | — | REVIEW | SKIP | 大装饰文字与线稿共存，未生成正式 candidate。 |
| skip-real-gura-color-sfx-02 | — | REVIEW | SKIP | 拟声词叠加屋瓦与色彩纹理，未生成正式 candidate。 |
| review-real-gura-camera-overlay-03 | — | REVIEW | REVIEW_REQUIRED | 非对白 overlay 与面板线稿重叠，未生成正式 candidate。 |

---

## 9. Failure Taxonomy

| Failure | Count | Representative fixtures |
| --- | ---: | --- |
| blur_artifact | 37 | gray label 高半径、warm label inpaint |
| color_discontinuity | 3 | warm label fixed white、striped fill baselines |
| gradient_break | 20 | warm label，尤其 dilation 2 |
| line_art_damage | 20 | striped background fill/inpaint |
| texture_smear | 18 | striped background Telea / Navier-Stokes |
| unsafe_to_clean | 23 | striped background 与三项 risk fixture |
| text_residue | 0 in final run | 最终 frozen mask 已覆盖影响阅读的原文 |
| bubble_border_damage | 0 accepted | fill fixture 均保持边框 |
| character_detail_damage | 0 accepted | 风险样本未进入算法接受路径 |
| outside_mask_change | 0 | 全部候选 |
| processing_error | 0 | 全部候选 |

高半径或 dilation 2 的同类失败按 candidate 计数，而不是独立页面缺陷数；不能把这些计数解释为真实漫画发生率。

---

## 10. Scenario Conclusions and Minimum Policy

### White / light bubble and narration box

```text
Recommended method: fixed_white (dilation 0; use dilation 1 only when oracle mask has anti-aliasing residue)
Required conditions: low-variance light interior; mask has a visible margin from bubble/narration border and important line art.
Known failures: do not use if the mask reaches the border or spans character/line-art detail.
```

### Simple label / gradient

```text
Recommended method: Telea radius 2, dilation 0 only for a small, flat gray label validated by review evidence.
Required conditions: small mask; no line art crossing it; preview/rating evidence for the profile.
Known failures: warm gradient labels degrade to REVIEW; fixed white causes an obvious discontinuity.
```

### Repeating texture, line art, character overlap, artistic text

```text
Recommended policy: REVIEW_REQUIRED or SKIP.
Reason: OpenCV fills/inpaint smear the repeated texture or erase line structure; artistic SFX and non-dialogue overlay are not MVP automatic cleaning targets.
```

Minimum policy:

```text
IF interior is light and low-variance
AND mask is separated from border and important line art
THEN AUTO_FILL

ELSE IF profile is explicitly validated as a small flat label
AND Telea radius=2, dilation=0 passes the same visual gate
THEN AUTO_INPAINT

ELSE REVIEW_REQUIRED or SKIP
```

---

## 11. Harness Gates

| Gate | Requirement | Actual | Result |
| --- | --- | --- | --- |
| Light bubble fill | >=80% acceptable | 4/4 ACCEPTABLE | PASS |
| Inpaint support | majority ACCEPTABLE or REVIEW | 2/3 (1 ACCEPTABLE, 1 REVIEW) | PASS |
| Inpaint value | also better than fill baseline | no strict rating improvement over comparison fill baseline | FAIL |
| Dangerous fixtures | 0 silently auto-accepted | 3/3 kept REVIEW_REQUIRED or SKIP | PASS |
| Severe damage accepted | 0 | 0（按 `bubble_border_damage`、`line_art_damage`、`character_detail_damage`、`unsafe_to_clean` 人工 taxonomy 统计） | PASS |
| Source files unchanged | required | verify PASS | PASS |
| Outside-mask destructive change | 0 | 0 candidates | PASS |
| Reproducible outputs | required | manifest/mask/source/output hashes recorded | PASS |

---

## 12. Final Verdict

```text
FURTHER_SPIKE
```

理由：oracle mask 下的普通白色/浅色气泡和旁白框通过了 fill 门槛，危险样本也被明确阻止自动接受。但 inpaint 虽有 2/3 可评样本，却没有对 fill comparison-only baseline 显示严格的、可重复的质量优势；条纹/线稿区域稳定不可用。因此不能把 OpenCV inpaint 作为通用 P0 自动路径。

推荐下一步：`补充 Cleaning 样本`，专门增加不含边框/线稿穿越的小面积真实渐变和简单纹理区域，并预先定义可审计的 fill baseline 对照。LaMa 是否必要应在该证据仍不足后另开专项 Spike，本轮不引入。

---

## 13. Formal Integration Conditions

进入正式 CleanerProvider 设计前至少需要：

* P0 仅允许上述 `AUTO_FILL` 判定，inpaint 继续 gated；
* `CleanerInput` 明确 source artifact、oracle/detected mask reference、method、radius、dilation；
* Provider 只生成临时 cleaned output，不访问数据库、不登记正式 artifact、不决定 retry；
* ArtifactService 负责 hash、正式登记、保留和 cleanup；
* QualityCheckService 负责 residue、border damage、line-art damage、unsafe cleaning 分类；
* WorkflowLoopEngine 按 ProcessingProfileSnapshot 决定 retry、fallback、warning、review 或 skip，且有界；
* source 原图永不覆盖；method、radius、dilation、source hash、mask hash、output hash 进入 provenance；
* 一切高风险区域默认 `REVIEW_REQUIRED` 或 `SKIP`。

---

## 14. Limitations

* oracle mask 不能证明自动 mask 生成的精度；
* 10 个 region 是小样本；同一 synthetic 页面提供了 3 个 inpaint fixture；
* 视觉评级有主观性，不能替代真人漫画编辑审校；
* 处理时间只代表本机 region-level OpenCV 调用，不代表 Page/Bath 或正式 artifact 性能；
* 未验证 LaMa、生成式修复、人物/复杂背景重绘或 Typesetting 后效果；
* 运行前发现的 mask undercoverage 已通过新 freeze/run 隔离，说明正式流程必须把 mask review 置于算法 run 之前。

---

## 15. Independent Reviewer

* Reviewer：只读独立审查完成；正式 run 的证据支持 `FURTHER_SPIKE`。
* Review mode：只读；不得修改代码、fixture、mask、ratings 或 output。
* Review evidence：final manifest、freeze history、formal `results.json` / `summary.json`、ratings.csv、contact sheets。
* Review conclusion：10 个 fixture 的分类、freeze 的 source/mask/output hash、76 条 ratings 覆盖、method 统计与报告一致；3 个危险 fixture 都无 candidate，未自动接受。三个 inpaint fixture 对应 formal/baseline 最佳评级为 A/A、R/R、U/U，因此没有严格优于 fill baseline，`FURTHER_SPIKE` 正确。
* Review limitation：样本较小，3 个 inpaint fixture 复用同一 synthetic 页面；mask 外指标基于 dilation 后的处理 mask，并非原始 oracle mask 外绝对零变化。
