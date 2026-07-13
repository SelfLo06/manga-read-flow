# Cleaning Real Tool Spike — REPORT

## 1. Executive Summary

* Run ID：
* Git HEAD：
* Fixture count：
* Source set：existing `local_samples`
* OpenCV version：
* Final verdict：

核心结论：

```text
Solid fill:
OpenCV inpaint:
Skip / review boundary:
Formal CleanerProvider readiness:
```

---

## 2. Scope

本轮验证：

```text
source image
+ frozen oracle mask
→ fill / OpenCV inpaint / skip
→ cleaned candidate
```

未验证：

* 自动 mask 生成；
* LaMa 或生成式修复；
* 正式 CleanerProvider；
* Workflow、ArtifactService 或数据库接入；
* Typesetting；
* API / UI。

---

## 3. Environment

| Item           | Value |
| -------------- | ----- |
| OS             |       |
| Python         |       |
| OpenCV         |       |
| Pillow         |       |
| NumPy          |       |
| CPU            |       |
| GPU used       | NO    |
| Baseline tests |       |
| Final tests    |       |

---

## 4. Frozen Inputs

| Item                       | Value |
| -------------------------- | ----- |
| Manifest SHA-256           |       |
| Fixture set SHA-256        |       |
| Mask set SHA-256           |       |
| Source files unchanged     |       |
| Masks changed after freeze |       |

偏差：

```text
NONE
```

---

## 5. Fixture Inventory

| Fixture | Source | Scenario | Expected policy | Mask readiness |
| ------- | ------ | -------- | --------------- | -------------- |
|         |        |          |                 |                |

汇总：

| Category                | Count |
| ----------------------- | ----: |
| AUTO_FILL candidate     |       |
| AUTO_INPAINT candidate  |       |
| REVIEW / SKIP candidate |       |
| Synthetic               |       |
| Real                    |       |

---

## 6. Mask Validation

| Check                                | Result |
| ------------------------------------ | ------ |
| Source / mask dimensions equal       |        |
| Binary mask conversion deterministic |        |
| Mask within region bbox              |        |
| Source hash unchanged                |        |
| Mask hashes frozen                   |        |
| Invalid masks                        |        |

Mask 制作方式只属于 fixture preparation，不计入自动 mask 能力。

---

## 7. Method Matrix

### Fill

| Method              | Dilation |
| ------------------- | -------- |
| fixed_white         | 0 / 1    |
| border_sampled_fill | 0 / 1    |

### Inpaint

| Method        | Radius    | Dilation  |
| ------------- | --------- | --------- |
| Telea         | 2 / 3 / 5 | 0 / 1 / 2 |
| Navier-Stokes | 2 / 3 / 5 | 0 / 1 / 2 |

Skip fixtures 不生成可接受 candidate。

---

## 8. Automated Results

| Method              | Candidates | Errors | Median time | Max outside-mask change |
| ------------------- | ---------: | -----: | ----------: | ----------------------: |
| fixed_white         |            |        |             |                         |
| border_sampled_fill |            |        |             |                         |
| Telea               |            |        |             |                         |
| Navier-Stokes       |            |        |             |                         |

异常：

* 路径越界：
* 尺寸变化：
* source 修改：
* processing error：

---

## 9. Visual Review

| Method              | ACCEPTABLE | REVIEW | UNUSABLE |
| ------------------- | ---------: | -----: | -------: |
| fixed_white         |            |        |          |
| border_sampled_fill |            |        |          |
| Telea               |            |        |          |
| Navier-Stokes       |            |        |          |

只读 reviewer：

* Reviewer：
* 是否修改代码、mask 或结果：NO
* Review evidence：contact sheets / candidate files

---

## 10. Per-Fixture Decision

| Fixture | Best candidate | Rating | Final policy | Reason |
| ------- | -------------- | ------ | ------------ | ------ |
|         |                |        |              |        |

Policy：

```text
AUTO_FILL
AUTO_INPAINT
REVIEW_REQUIRED
SKIP
```

---

## 11. Failure Taxonomy

| Failure                        | Count | Representative fixtures |
| ------------------------------ | ----: | ----------------------- |
| text_residue                   |       |                         |
| mask_undercoverage             |       |                         |
| mask_overcoverage              |       |                         |
| bubble_border_damage           |       |                         |
| line_art_damage                |       |                         |
| character_detail_damage        |       |                         |
| texture_smear                  |       |                         |
| color_discontinuity            |       |                         |
| gradient_break                 |       |                         |
| blur_artifact                  |       |                         |
| outside_mask_change            |       |                         |
| unsupported_complex_background |       |                         |
| unsafe_to_clean                |       |                         |
| invalid_mask                   |       |                         |
| processing_error               |       |                         |

---

## 12. Scenario Conclusions

### White / light bubble

```text
Recommended method:
Required conditions:
Known failures:
```

### Narration box

```text
Recommended method:
Required conditions:
Known failures:
```

### Simple texture or gradient

```text
Recommended method:
Required conditions:
Known failures:
```

### Line art or character overlap

```text
Recommended policy:
Reason:
```

### Artistic text / sound effects

```text
Recommended policy:
Reason:
```

---

## 13. Minimum Cleaning Policy

```text
IF background is light and low-variance
AND mask is separated from border and important line art
THEN AUTO_FILL

ELSE IF background contains simple continuous texture
AND mask is small
AND no important character detail is covered
THEN AUTO_INPAINT

ELSE
REVIEW_REQUIRED or SKIP
```

任何明显边框、线稿或人物细节破坏均不得自动接受。

---

## 14. Harness Gates

| Gate                            | Requirement                                     | Actual | Result |
| ------------------------------- | ----------------------------------------------- | ------ | ------ |
| Light bubble fill               | >= 80% acceptable                               |        |        |
| Inpaint value                   | Majority acceptable/review and better than fill |        |        |
| Dangerous fixtures              | 0 silently auto-accepted                        |        |        |
| Severe damage accepted          | 0                                               |        |        |
| Source files unchanged          | Required                                        |        |        |
| Outside-mask destructive change | 0                                               |        |        |
| Reproducible outputs            | Required                                        |        |        |

---

## 15. Final Verdict

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

理由：

---

## 16. Formal Integration Conditions

正式 CleanerProvider 设计前需要：

* 明确 `CleanerInput` 中的 source artifact 和 mask reference；
* Provider 只生成临时 cleaned output；
* ArtifactService 负责正式登记；
* QualityCheckService 分类 residue、border damage 和 unsafe cleaning；
* WorkflowLoopEngine 决定 retry、fallback、warning 或 skip；
* 复杂区域允许显式跳过；
* 原图永不覆盖；
* output method、radius、mask hash 和 source hash 进入 provenance。

---

## 17. Limitations

* oracle mask 不代表自动 mask 能力；
* fixture 数量有限；
* visual review 具有主观性；
* 未验证 LaMa；
* 未验证正式 Page 级性能；
* 未验证 Typesetting 后视觉效果。

---

## 18. Recommended Next Step

只选择一个：

```text
进入 Typesetting Real Tool Spike
进入 Mask Generation Follow-up
进入 LaMa Necessity Spike
补充 Cleaning 样本
停止 Cleaning 自动化方案
```
