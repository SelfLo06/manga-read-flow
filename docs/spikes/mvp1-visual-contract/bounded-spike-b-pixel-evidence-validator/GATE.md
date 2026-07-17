# MVP-1 Visual Contract Bounded Spike B — GATE

## 当前状态

```text
PASS_WITH_CHANGES — NOT_GO_FOR_REAL_CLEANING
```

| # | 门禁 | 状态 |
|---:|---|---|
| B1 | 每个被测 segment 有 text core 与 visible-support candidate 证据 | PASS |
| B2 | clean-negative / deliberate-residue-positive 分别通过 / 拒绝（仅 candidate 完整覆盖的 control） | PASS |
| B3 | support candidate 与 SafeEditMask 分离；不安全 candidate 明确 `INCOMPLETE_REVIEW` | PASS |
| B4 | ActualChangedPixelMask 可重算且 mismatch 不可静默通过 | PASS |
| B5 | `g003` 输出 pixel-level protected / uncertainty / safe-edit evidence，保持 review-only | PASS |
| B6 | 每个被测 segment 有 full-canvas、未裁剪 glyph evidence | PASS |
| B7 | missing / duplicate / wrong-instance / overflow / touch / wrong-region 均拒绝 | PASS |
| B8 | renderer/validator binding mismatch 在空间检查前阻塞 | PASS |
| B9 | correction reservation 一次、重放幂等、第二次拒绝 | PASS |
| B10 | 完整可见字形支持域的人工作为独立审查（固定样本） | PASS_WITH_LIMITS |

## 不得误读的通过项

`B2=PASS` 只意味着：在当前 `visible_glyph_support_candidate` 内，受控 positive residue
被拒绝。它不意味着该 candidate 等于完整可辨字形，更不意味着真实 Cleaning 通过。

人工确认当前固定样本未发现明确落在 support candidate 外的可辨原文；但这不能一般化到
不同分辨率、字号、粗描边、发光/阴影、压缩噪声或复杂彩色文字。B10 不得被解释为真实
Cleaner residue contract 的 GO。

## 人工审查条件

`FORM.md` 应确认：

1. case-71 接触 instance 的 evidence 未重新合并；
2. `g003` 的 pixel evidence 可解释且未伪称能实际清字；
3. `INCOMPLETE_REVIEW` segment 未被当作 Cleaning PASS；
4. control 的紫色 visible-support candidate 是否覆盖每个完整可辨原文字形；
5. residue/overflow/wrong-validator-region 均被拒绝；
6. 结论不升级为 Cleaning 或 Typesetting 产品可用。

## 最终裁决

```text
SPIKE_B_PIXEL_VALIDATOR_CONTRACT = PASS_WITH_CHANGES
REAL_CLEANING_RESIDUE_COMPLETENESS = CHANGES_REQUIRED
ACTUAL_CLEANING = NOT_GO
```

本轮所有 deliberate evidence gate 均成立，但仅覆盖 controlled white-fill 与固定样本的
visible-support candidate。任何下一步都必须先重新定义/验证完整可见字形 RequiredTextEvidence，
再讨论真实 Cleaner 输出、背景一致性或结构损伤；不得把当前局部 control 可视化当作产品图。

## 禁止事项

```text
MIGRATION = FORBIDDEN
FORMAL_WORKFLOW_INTEGRATION = FORBIDDEN
PROVIDER_INTEGRATION = FORBIDDEN
ACTUAL_CLEANING = FORBIDDEN
PRODUCT_TYPESETTING = FORBIDDEN
```
