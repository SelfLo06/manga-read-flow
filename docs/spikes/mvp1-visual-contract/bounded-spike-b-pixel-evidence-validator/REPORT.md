# MVP-1 Visual Contract Bounded Spike B — REPORT

## 当前裁决

```text
UNSAFE_REQUIRED_GATING = PASS
CONTROL_SET_ISOLATION = PASS
VISIBLE_GLYPH_SUPPORT_CANDIDATE = GENERATED_ONLY
REQUIRED_TEXT_EVIDENCE_VISUAL_COMPLETENESS = NOT_PROVEN
REAL_CLEANING_RESIDUE_CONTRACT = CHANGES_REQUIRED
CURRENT_SAMPLE_HUMAN_REVIEW = PASS
SPIKE_B = PASS_WITH_CHANGES / NOT_GO_FOR_REAL_CLEANING
```

此前“人工反馈中的 residue 合同缺陷已修正”的表述过头。准确结论是：**unsafe required
pixels 被错误纳入 Cleaning PASS 的问题已修正；完整可见字形的 RequiredTextEvidence 覆盖
仍未通过人工审查。**

## 冻结运行

```text
data/local/mvp1-visual-contract-spike-b-v0.1/run-v0.7/
```

- PixelEvidenceSnapshot content SHA-256：
  `f656e634c2f0c157f3810d6e7fb29f7d450ebd3fc7e7f6ee14105495932e212e`；
- Spike A snapshot、input lock、人工 FORM、source images、translation provenance、CJK font、
  Spike B module 与 evaluation oracle 均被 hash-lock；
- candidate snapshot 在读取 oracle 前冻结；overlay 不参与关系或 Validator 判定。

## 已修复：required / safe 分离

v0.2 把 `safe_edit` 直接当作 residue 所需文字域；v0.4 起，完整候选文字域与 safe-edit
分开。后者未覆盖前者的像素会明确得到 `required_text_not_safely_editable` /
`INCOMPLETE_REVIEW`，不得混入 clean-negative PASS：

| Segment | support candidate | safe 覆盖 | 不可安全编辑 | 状态 |
|---|---:|---:|---:|---|
| case-71 `g002/s02` | 10,079 | 10,056 | 23 | `INCOMPLETE_REVIEW` |
| case-72 `g002/s01` | 15,802 | 15,092 | 710 | `INCOMPLETE_REVIEW` |
| case-72 `g004/s01` | 13,133 | 13,063 | 70 | `INCOMPLETE_REVIEW` |

因此 clean-negative 只含安全完整覆盖候选：case-71 `g002/s01`（8,830 px）及 case-72
`g001/s01`、`g006/s01`（7,805 px）。此处的“完整覆盖”只指**当前 support candidate**，
不指完整人眼可辨字形。

## 仍未通过：完整可见字形支持域

v0.7 明确保存两个不同对象：

```text
text_core
  = bbox ∩ BubbleInstance ∩ (luminance <= 180)

visible_glyph_support_candidate
  = dilate(text_core, 2 px) ∩ BubbleInstance
```

紫色 overlay 是第二项。它能将浅色抗锯齿/描边邻域纳入受控 residue 反例：若只清深色
core、保留 220 luminance 的 halo，新的回归测试会得到 `cleaning_residue`。但 dilation
仍不是完整可见字形 GT，特别不能保证覆盖彩色高亮、远离深色 core 的描边或完整可辨识
字符结构。

因此下列命题**尚未成立**：

```text
safe_edit_covered_required_pixels == visible_support_candidate_pixels
⇒ 原文已不可辨认
```

此 run 不产生真实 Cleaner 输出；任何 current clean-negative PASS 都只能说明该受控白填充
覆盖了当前 support candidate，不能说明真实 Cleaning 成功。

## 其他通过的 Validator 合同

- case-71 两个接触 BubbleInstance 的 required/support、region binding 与 full-canvas glyph
  evidence 独立；没有使用 parent cluster；
- case-72 `g003` 保持 `REVIEW_ONLY_G003`。旧 instance-level 17.23% overlap ratio 不再
  作为整体 E3 的充分理由，但本轮不批准实际 Cleaning；
- deliberate residue、missing、duplicate、wrong-instance、overflow、boundary touch、
  wrong-validator-region 都被拒绝；正常 glyph control 无 issue；
- correction reservation 只允许 ordinal 0→1；重放幂等，第二次自动请求拒绝。

## 限制与下一修改要求

1. 在进入真实 Cleaning 验证前，RequiredTextEvidence 必须表示完整应消失的可见字形支持
   域：字芯、描边、抗锯齿、浅色边缘与可辨识彩色部分；
2. RequiredTextEvidence 与 SafeEditMask 保持独立；存在不可安全编辑 required 像素必须为
   `INCOMPLETE / REVIEW / BLOCK`；
3. residue 检查必须针对完整支持域或组件级/可辨识残留证据；人眼仍可读原文字形时，不能
   通过高质量 Cleaning Gate；
4. controlled white fill、固定 glyph control 都不是产品清字/排版质量证据；
5. migration、正式 Workflow、Provider、实际 Cleaning、UI/API、Batch 仍禁止。

## 最终人工审查

`run-v0.7/FORM.md` 已确认：

- case-71 的接触 BubbleInstance 仍维持 required/support/glyph evidence 隔离；
- `g003` 的 protected-overlap pixel evidence 可解释，且保持 review-only；
- halo residue、overflow 和 wrong-validator-region 的 deliberate controls 被正确拒绝；
- 当前固定样本未发现明确落在紫色 visible-support candidate 外的可辨原文字形；
- 当前 support 仍只是启发式候选，不能升格为正式完整字形事实来源。

最终裁决：

```text
Instance / revision binding = PASS
Unsafe-required gating = PASS
Controlled halo-residue regression = PASS
Current-sample visible-support human review = PASS
Real Cleaning residue completeness = CHANGES_REQUIRED
Overall = PASS_WITH_CHANGES
```

## 人工入口

填写：

```text
data/local/mvp1-visual-contract-spike-b-v0.1/run-v0.7/FORM.md
```

重点查看：`overlays/case-71-evidence.png`、`overlays/case-72-evidence.png`、
`pixel-evidence-snapshot.json`、`gate-matrix.json`。
