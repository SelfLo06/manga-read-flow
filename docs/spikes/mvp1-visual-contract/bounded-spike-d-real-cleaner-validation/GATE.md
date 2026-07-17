# Spike D Gate — Real Cleaner Output Validation

## 冻结输入

- Spike A/B/C 的冻结 REPORT、GATE 与 run；
- `run-v0.5` 的 candidate snapshot、summary、comparisons 与人工 FORM；
- `FIXTURE-ORACLE-v0.1.json`；
- 独立只读审计 `reviews/final-evidence-review.md`。

## 判定表

| 门禁 | 结果 | 证据 |
|---|---|---|
| 五个 deliberate failures 均被拒绝 | PASS | 5/5 controls 为预期 BLOCK |
| 至少一个真实 Cleaner 输出通过 | PASS | 3/3 固定真实 segment PASS |
| 原文字形不可辨 | PASS_WITH_LIMITS | residue=0 且 FORM 三项 PASS |
| ActualChanged 不越出 safe-edit | PASS | 3/3 outside-safe=0 |
| protected / uncertainty / boundary 无修改 | PASS | 3/3 为 0 |
| 背景无明显块、缝或字形拓扑 | PASS_WITH_LIMITS | difference=0，seam Δ<12，人工确认 |
| Validator 与人工一致 | PASS | FORM 与自动 3/3 PASS |
| Spike A/B/C 定向回归不退化 | PASS | 32 targeted tests passed |
| synthetic control 未被当作真实成功 | PASS | run summary 和独立审计均隔离记录 |

## 正式裁决

```text
SPIKE_D = PASS_WITH_LIMITS
ALLOW = GO_FOR_SINGLE_PAGE_CLEANING_SLICE
NOT_ALLOWED = FULL_PAGE_CLEANING, BATCH, AUTO_ACCEPT, PRODUCT INTEGRATION
```

允许下一阶段只在单页 vertical slice 中使用此能力，且必须保持实例级绑定、complete/safe 条件、输出验证和可回退的原图。任何复杂背景、非普通气泡、未 complete support 或新的 residue/structure/background false negative 都必须回到 `CHANGES_REQUIRED`，而不是扩大策略。
