# Spike D 最终只读证据审查

## 审查范围

仅阅读 Spike A/B/C 冻结 REPORT/GATE、Spike D 设计、fixture oracle、harness、定向测试，以及
`data/local/mvp1-visual-contract-spike-d-v0.1/run-v0.5/` 的 snapshot、summary、FORM 和三张 comparison。
未修改实现、未运行新实验，也未将任何 control 当作真实 Cleaner 成功。

## 核验事实

| 项目 | 结果 | 证据 |
|---|---|---|
| 真实 Cleaner 样本 | 3 条，均为 `COMPLETE` | `case-71__g002__s01`、`case-72__g001__s01`、`case-72__g006__s01` |
| 合成 controls | 5/5 如预期 `BLOCK` | unchanged/core-only 触发 `cleaning_residue`；outside-safe 与 protected-change 触发结构损伤；wrong-background 触发 residue/background 问题 |
| 实际写回边界 | PASS | 三条记录的 `ActualChangedPixelMask` 与 cleaner candidate content hash 相同；changed 分别为 4530/4248/2532，`outside/protected/uncertainty/boundary = 0` |
| 残字 | PASS（固定样本） | 三条真实输出均为 `residue_candidate_pixels=0`；三张 comparison 的中间面板可见输出没有可辨日文；人工 FORM 三项均 PASS |
| 背景一致性 | PASS（固定样本） | background-difference 均为 0；seam delta 为 1.0/2.236/2.449，小于 12；人工未见白块、灰块或接缝 |
| Oracle 隔离 | PASS_WITH_LIMITS | input lock 记录只在 candidate snapshot 前读取 oracle hash、未读取 decision；实现于写 snapshot 后才解析 oracle 内容。hash 预读仍是需持续保留的审计限制。 |
| 字段语义 | PASS | `required_support`、`safe_edit`、`candidate`、`actual_changed` 与 `visible_support` 分别存储；PASS 记录不生成 QualityIssue draft；没有将 visible-support 冒充 `text_core`。 |

## 人工与自动结论一致性

`FORM.md` 明确说明 run-v0.5 与已审查的 run-v0.3 在三条真实候选的 source、各 mask、cleaned output、诊断 mask、comparison SHA 及自动 decision 上完全一致，因此人工审查被追溯复用于相同可视输出。其三个 segment 均为 PASS、Overall 为 `PASS_WITH_LIMITS`。这与 run-v0.5 的自动 PASS 不冲突。

## 风险与未关闭边界

1. `border_sampled_fill` 是单色局部中位数填充；当前背景一致性只在三条普通白/浅色、低风险样本上得到人工与数值共同支持。复杂纹理、渐变、网点、发光/阴影/艺术字或背景文字仍可能出现背景一致性 false negative。
2. visible-support 仍是 Spike C 的启发式候选；本审查仅确认这三条固定样本没有发现 support 外可辨残字，不能一般化为完整字形 GT。
3. 当前 seam 指标比较候选邻环与局部中位背景，能补足明显边缘接缝证据，但不能替代更复杂背景中的感知质量判断。
4. controls 只证明 Gate 能拒绝特定故障；它们不构成真实 Cleaner 成功样本。真实成功证据仅来自上述三条实际 `border_sampled_fill` 输出。

## Verdict

```text
FINAL_EVIDENCE_REVIEW = PASS_WITH_LIMITS
REAL_CLEANER_OUTPUT_ON_FROZEN_SCOPE = PASS
GO_FOR_SINGLE_PAGE_CLEANING_SLICE = ALLOWED_WITH_GUARDS
FULL_PAGE / BATCH / AUTO_ACCEPT / PRODUCT INTEGRATION = NOT_APPROVED
```

未发现会迫使本轮冻结为 `CHANGES_REQUIRED` 的残字 false negative、mask 外写回、protected/uncertainty 损伤、字段语义污染、oracle decision 泄漏或人工/自动 Gate 冲突。该结论严格限于三个冻结、普通白/浅色气泡和本轮单一 Cleaner，不能覆盖 Cleaning eligibility、页面覆盖率、复杂对象或产品级自动化。
