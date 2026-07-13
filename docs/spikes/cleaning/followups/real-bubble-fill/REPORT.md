# Real Bubble Fill Validation Follow-up — REPORT

## 1. Executive Summary

* Formal run ID：
* Git HEAD at input freeze：
* Fixture count：12
* Source pages：4 real pages
* Final verdict：
* P0 product decision：

核心结论：

```text
Fixture validity:
Mask validity:
Fill quality:
Restricted AUTO_FILL readiness:
```

---

## 2. Scope

本 follow-up 验证：

```text
真实对白气泡
+ glyph-level text mask
+ allowed_edit_mask
+ protected_mask
→ fixed / sampled fill
→ 严格安全与视觉检查
```

未验证：

* 自动文字 mask；
* 自动气泡内部检测；
* OpenCV inpaint；
* LaMa 或生成式修复；
* 正式 CleanerProvider；
* Workflow、ArtifactService、SQLite；
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
| Baseline tests |       |
| Focused tests  |       |
| Final tests    |       |

---

## 4. Frozen Inputs

| Item                        | Value |
| --------------------------- | ----- |
| Manifest SHA-256            |       |
| Fixture-set SHA-256         |       |
| Source-set SHA-256          |       |
| Text-mask-set SHA-256       |       |
| Allowed-mask-set SHA-256    |       |
| Protected-mask-set SHA-256  |       |
| Inputs changed after freeze |       |
| Source files unchanged      |       |

若正式 run 前后发生输入变化，在此记录：

```text
NONE
```

---

## 5. Fixture Inventory

| Fixture | Source | Class     | Scenario | Expected policy | Final policy |
| ------- | ------ | --------- | -------- | --------------- | ------------ |
|         |        | A / B / D |          |                 |              |

汇总：

| Category                | Required | Actual |
| ----------------------- | -------: | -----: |
| A — AUTO_FILL candidate |        8 |        |
| B — REVIEW_REQUIRED     |        2 |        |
| D — SKIP control        |        2 |        |
| Pages represented       |        4 |        |

---

## 6. Fixture Selection Evidence

页面候选编号图：

| Source page | Selection image |
| ----------- | --------------- |
| black1      |                 |
| black2      |                 |
| gura        |                 |
| gura_color  |                 |

选择约束检查：

| Check            | Result |
| ---------------- | ------ |
| 四张真实页均使用         |        |
| 单页 fixture 不超过 4 |        |
| 无重复气泡凑数量         |        |
| A 类未集中于单页        |        |
| B/D 风险场景明确       |        |

---

## 7. Mask Validity

每个 A/B fixture 必须具备：

```text
text_mask
allowed_edit_mask
protected_mask
```

### 汇总

| Check                             | Pass | Fail |
| --------------------------------- | ---: | ---: |
| 尺寸一致                              |      |      |
| text_mask 为 glyph-level           |      |      |
| text_mask 位于 allowed_edit 内       |      |      |
| text_mask 不触碰 protected           |      |      |
| allowed_edit 不触碰 protected        |      |      |
| 无矩形 mask                          |      |      |
| minimum protected distance >= 1px |      |      |

### 逐 Fixture

| Fixture | Mask review     | Mask-to-bbox ratio | Min protected distance | Notes |
| ------- | --------------- | -----------------: | ---------------------: | ----- |
|         | VALID / INVALID |                    |                        |       |

任何 `INVALID` fixture 不得进入正式 run。

---

## 8. Mask Review Images

每个 fixture 的四联图路径：

| Fixture | Source | Text-mask overlay | Allowed/protected overlay | Combined overlay |
| ------- | ------ | ----------------- | ------------------------- | ---------------- |
|         |        |                   |                           |                  |

至少展示四个代表性示例：

1. 普通白色气泡；
2. 真实竖排气泡；
3. 边界敏感气泡；
4. SKIP control。

---

## 9. Method Matrix

正式方法：

| Method              | Dilation |
| ------------------- | -------- |
| fixed_white         | 0 / 1    |
| border_sampled_fill | 0 / 1    |

规则：

* A/B 类生成候选；
* B 类最终策略不得自动变为 `AUTO_FILL`；
* D 类不生成正常 candidate。

---

## 10. Automated Safety Results

| Method              | Candidates | Errors | Median time | Max time |
| ------------------- | ---------: | -----: | ----------: | -------: |
| fixed_white         |            |        |             |          |
| border_sampled_fill |            |        |             |          |

安全门禁：

| Check                        | Required | Actual | Result |
| ---------------------------- | -------: | -----: | ------ |
| Source mutation              |        0 |        |        |
| Changed outside allowed-edit |        0 |        |        |
| Changed inside protected     |        0 |        |        |
| Size/mode mismatch           |        0 |        |        |
| Path violations              |        0 |        |        |
| Processing errors            |        0 |        |        |

自动指标不替代视觉评级。

---

## 11. Candidate Ratings

| Method                 | ACCEPTABLE | REVIEW | UNUSABLE |
| ---------------------- | ---------: | -----: | -------: |
| fixed_white d0         |            |        |          |
| fixed_white d1         |            |        |          |
| border_sampled_fill d0 |            |        |          |
| border_sampled_fill d1 |            |        |          |

所有 A/B candidate 必须有评级。

---

## 12. Per-Fixture Decision

| Fixture | Best candidate | Rating | Final policy | Reason |
| ------- | -------------- | ------ | ------------ | ------ |
|         |                |        |              |        |

允许的最终 policy：

```text
AUTO_FILL
REVIEW_REQUIRED
SKIP
```

---

## 13. Image Results

### Per-Fixture Comparisons

每个 A/B fixture 必须提供：

```text
comparisons/<fixture_id>.png
```

| Fixture | Comparison image | Best candidate | Rating |
| ------- | ---------------- | -------------- | ------ |
|         |                  |                |        |

### Accepted Gallery

```text
accepted-gallery/index.png
```

应包含：

* source crop；
* best cleaned result；
* 200% detail；
* method 与 dilation；
* fixture ID。

### Review Gallery

```text
review-gallery/index.png
```

必须直接标明：

* 色差；
* 抗锯齿残留；
* 边界距离不足；
* 不规则气泡；
* 其他 review 原因。

### Rejected Gallery

```text
rejected-gallery/index.png
```

必须包含：

* 明显矩形填充；
* 边框或尾巴损伤；
* 文字残留；
* 过度填充；
* D 类 SKIP control；
* 其他不可接受结果。

---

## 14. Representative Successes

至少给出两项 200% 局部放大成功例。

### Success 1

* Fixture：
* Method：
* Dilation：
* Image：
* Why acceptable：

### Success 2

* Fixture：
* Method：
* Dilation：
* Image：
* Why acceptable：

---

## 15. Representative Failures

至少给出两项 200% 局部放大失败例。

### Failure 1

* Fixture：
* Method：
* Failure tags：
* Image：
* Why unusable：

### Failure 2

* Fixture：
* Method：
* Failure tags：
* Image：
* Why unusable：

---

## 16. Failure Taxonomy

| Failure                  | Count | Representative fixtures |
| ------------------------ | ----: | ----------------------- |
| text_residue             |       |                         |
| rectangular_fill         |       |                         |
| fill_edge_visible        |       |                         |
| color_mismatch           |       |                         |
| anti_aliasing_residue    |       |                         |
| bubble_border_damage     |       |                         |
| bubble_tail_damage       |       |                         |
| line_art_damage          |       |                         |
| overfill                 |       |                         |
| changed_inside_protected |       |                         |
| changed_outside_allowed  |       |                         |
| invalid_mask             |       |                         |
| processing_error         |       |                         |

Candidate 级计数不得解释为真实漫画发生率。

---

## 17. Independent Review

* Reviewer：
* Review mode：read-only
* Reviewed evidence：

  * source crop；
  * 三层 mask overlay；
  * raw candidate；
  * difference overlay；
  * 200% zoom。

Reviewer 结论：

```text
Mask validity:
Rating consistency:
Severe damage missed:
Verdict support:
```

评级冲突：

| Fixture | Original rating | Reviewer rating | Final rating | Reason |
| ------- | --------------- | --------------- | ------------ | ------ |
|         |                 |                 |              |        |

发生冲突时采用更严格评级。

---

## 18. Harness Gates

| Gate                      | Requirement | Actual | Result |
| ------------------------- | ----------- | ------ | ------ |
| A-class acceptable        | >= 7/8      |        |        |
| A-class protected damage  | 0/8         |        |        |
| A-class rectangular fill  | 0/8         |        |        |
| B-class auto-accepted     | 0/2         |        |        |
| D-class normal candidates | 0/2         |        |        |
| Changed inside protected  | 0           |        |        |
| Changed outside allowed   | 0           |        |        |
| Severe damage accepted    | 0           |        |        |
| Invalid fixture admitted  | 0           |        |        |
| Source mutation           | 0           |        |        |

---

## 19. Final Verdict

选择一个：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

理由：

---

## 20. P0 Product Decision

### 当 Verdict 为 CONDITIONAL_GO

仅允许：

```text
低方差白色或浅色气泡内部
+ 已通过审核的 glyph-level mask
+ 明确 allowed-edit 区域
+ protected-region safety gate
→ restricted AUTO_FILL
```

继续禁止：

```text
边界敏感气泡自动接受
纹理和渐变区域自动修复
人物或线稿重叠区域清字
艺术字和拟声词清字
OpenCV inpaint 默认启用
```

### 当 Verdict 为 FURTHER_SPIKE / NO_GO

```text
Restricted AUTO_FILL remains disabled.
```

---

## 21. Formal Integration Conditions

进入 CleanerProvider 设计前必须满足：

* `CleanerInput` 明确 source、text mask、allowed-edit 和 protected references；
* Provider 只返回临时输出；
* Provider 不访问数据库或决定接受策略；
* ArtifactService 负责正式 artifact 生命周期；
* QualityCheckService 检查 protected-region damage、residue 和 overfill；
* WorkflowLoopEngine 决定 warning、review、skip 或 block；
* 所有 mask/source/method 参数进入 provenance；
* 原图永不覆盖；
* 自动接受仅限本实验支持的 A 类 profile。

---

## 22. Limitations

至少记录：

* fixture 数量有限；
* mask 为人工制作；
* 未验证自动 mask；
* 未验证所有漫画风格；
* 未验证 Typesetting 后效果；
* 视觉审查仍带主观性；
* 真实 P0 使用中的 A/B 分类仍需实现。

---

## 23. Recommended Next Step

只选择一个：

```text
进入 Typesetting Real Tool Spike
进入 Mask Generation Follow-up
补充 Real Bubble Fill 样本
停止自动 Cleaning
```
