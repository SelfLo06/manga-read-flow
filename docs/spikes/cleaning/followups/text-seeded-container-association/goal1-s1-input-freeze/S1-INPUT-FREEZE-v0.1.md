# Text-Seeded Container Association — S1 Input Freeze v0.1

日期：2026-07-15
状态：`FROZEN_FOR_MINIMAL_R0_SPIKE`

## 1. 决策

最终 S1 不拼接历史 run 与五个新资产的结果，而是对六个 blind R0 crop 运行一条新的、统一的 Detection + Grouping chain。

历史 chain：

```text
Detection/OCR  20260710T091753Z-0676c2 / cold
Grouping       20260710T142823Z-b08c9c / cold
```

其既有输出 hash 仍可验证，Grouping runner 也可追踪到当前相同代码；但历史 Detection runner 当时位于 Git ignored 路径，没有可验证的提交版本，且只覆盖六个新 R0 中的 `black2`。因此它只保留为历史证据，不作为最终六例 S1 base，也不把新结果称为该 run 的同版本 extension。

## 2. Blind input contract

S1 runner 只接受：

```text
blind asset_id
relative image path under images/
image SHA-256
width / height
```

明确拒绝 semantic label、container count、same/different label、overlay path 或其他 evaluator 字段。运行时不读取 Annotator A overlay、Annotator B 表单、coordinator key 或 R0 verdict。

OCR 字符串本轮不作为 S1 输入；detector fragment 的 `ocr_text` 为空。Detector parser 当前不输出 score，因此 `score = null` 被记录为已知输入限制，不得在 Goal 2 中伪造。

## 3. Frozen R0 S1 run

| 项 | 冻结值 |
| --- | --- |
| Run ID | `20260715T075811Z-3e9711` |
| Results SHA-256 | `33f1061aac43e5b4ca4b86d66c8aec262d19eb33151a965aaf81e656d406da0a` |
| Input spec SHA-256 | `95d7d627eefb2b8d7c119364c6e362528848399e5b06a6de7f3c28a1bd7995e7` |
| Freeze runner SHA-256 | `0553b1e7a825d0662344db542fa341cd3b0e556013141502064c32fe6513d15b` |
| Detection module SHA-256 | `e13cee052d549127a3da312b8716d4bcffb5de0efeea1ee5e2f5fe56a4ed6676` |
| Detector | `paddleocr._models.text_detection.TextDetection` / `PP-OCRv6_medium_det` |
| Grouping module SHA-256 | `833cb77047cd340f1012a9841b1b1431f55408ef60f05a65b7e080cd02ef8ce0` |
| Grouping parameters | `orientation_ratio=1.25`; `projection_overlap_ratio=0.15`; `gap_relative_limit=0.35`; `gap_min_px=16` |
| Source hashes unchanged | `true` |

本地结果：

```text
data/local/text-seeded-container-association/r0-final-blind-v0.3/
  S1-INPUT-SPEC.local.json
  s1-runs/20260715T075811Z-3e9711/results.json
```

## 4. 六例覆盖

| Blind case | R0 role（evaluator-only mapping） | Fragments | Groups | 冻结状态 |
| --- | --- | ---: | ---: | --- |
| `case-01` | not-text false seed | 1 | 1 | FROZEN；真实 S1 false seed 被保留，不人工删除。 |
| `case-02` | free text | 1 | 1 | FROZEN |
| `case-03` | broken/occluded boundary | 6 | 4 | FROZEN；extra/邻接局部内容必须可追踪。 |
| `case-04` | textured decorative risk | 4 | 3 | FROZEN；不得把 extra group 静默删除。 |
| `case-05` | same-container multicol | 8 | 2 | FROZEN；一个额外 uncertain horizontal group 必须保留。 |
| `case-06` | contact different-containers | 5 | 2 | FROZEN |

连续三次使用相同输入、Detector 与 Grouping 得到完全相同的 normalized fragments/groups；最终只冻结最后一次、且 runner hash 与当前代码一致的 run。

## 5. Minimal calibration isolation

只冻结两个未进入 R0、且由维护者在候选表中明确选为 backup 的 crop：

| Blind ID | 用途 | Crop SHA-256 | S1 evidence |
| --- | --- | --- | --- |
| `cal-01` | different-container | `e667c122b80be14fed36f929b333a9a0772ceb2a60b6ffd91d5cdb565d1ac208` | 5 fragments / 3 groups；只使用两个完整目标 group。 |
| `cal-02` | same-container multicol | `06938a37a30f1daaf5ceddabf35689868c34695b64dcc380f6c586c4b3dec405` | 4 fragments / 2 groups；只使用中央容器内三个目标 fragments。 |

Calibration S1：

| 项 | 冻结值 |
| --- | --- |
| Run ID | `20260715T075556Z-7bb156` |
| Results SHA-256 | `195230ecd63191d64621b251b9c1adbc9c6efd6b3366cdfab5bf4438f066a621` |
| Input spec SHA-256 | `9162a4314f5b2d71c5bdf80e89a90d02b23852f7d0df2ca85452ae9833074d99` |
| Freeze runner SHA-256 | `0553b1e7a825d0662344db542fa341cd3b0e556013141502064c32fe6513d15b` |

Goal 1 不生成 pair、不计算 scorer、不选择阈值。Goal 2 必须先冻结 conservative initial-group 规则，再从 evaluator-only coarse scope 内生成 pair。若无法形成明确 separation，所有 pair 保持 `uncertain`；禁止使用 R0 选择或修正阈值。

## 6. Current minimal-Spike metrics

R0 允许：

- 分类与容器数量；
- same/different topology；
- false merge / false split；
- 是否跨容器泄漏；
- 是否正确 abstain；
- 相对 Annotator A coarse reference 的定性或宽容差判断。

R0 禁止：

- pixel-accurate segmentation accuracy；
- 严格 IoU 或 boundary F1；
- 双人 boundary agreement；
- 已冻结的 uncertainty-band 数值。

## 7. Goal 1 gate

```text
R0 blind assets present             PASS (6/6)
R0 S1 fragments/groups present      PASS (6/6)
Source hashes unchanged             PASS
Evaluator labels absent from input  PASS
Runner/model/grouping provenance     PASS
Calibration isolated from R0        PASS
Calibration thresholds selected     NOT RUN (Goal 2 only)
```

Goal 1 input verdict：`PASS_TO_GOAL_2`。

这不表示 association 算法有效，也不表示可以进入 pixel mask、safe edit region 或 Cleaning。
