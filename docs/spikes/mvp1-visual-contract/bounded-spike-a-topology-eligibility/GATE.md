# MVP-1 Visual Contract Bounded Spike A — GATE

## 当前状态

```text
GO_TO_SPIKE_B_WITH_GUARD
```

## 自动门禁

| # | 门禁 | 状态 |
|---:|---|---|
| 1 | 每个 active TextSegment 恰好 assigned 或 explicitly excluded | PASS |
| 2 | case-71 接触区域输出两个独立 BubbleInstance | PASS |
| 3 | N≥3 不被限制为二分 | PASS |
| 4 | 单气泡多段、多列不被错误拆分 | PASS |
| 5 | merge/split/unassigned/wrong-instance 全部被拒绝 | PASS |
| 6 | eligibility 逐实例判断，无 cluster worst-risk broadcast | PASS |
| 7 | E2/E3 evidence 完整 | PASS |
| 8 | case-72 普通气泡排除原因人工可审查 | PASS_WITH_CHANGES |
| 9 | snapshot 是 run 唯一关系事实来源 | PASS |
| 10 | 不依赖 parent bbox、目录顺序或隐藏映射 | PASS |

## 人工裁决

`FORM.md` 已确认以下内容：

1. case-71 的两个 instance 分隔与 segment 归属语义正确；
2. case-72 保持 7 instances / 8 segments；
3. `g002/s01` 的历史 E3 被判断为 eligibility 假阴性，而不是本轮过度激进；
4. `g005`、`g007` 的 abstention 原因可接受；`g003` 的原因虽可审查，但人工裁决为
   `FALSE_NEGATIVE`，不得被错误记作已接受的 E3；
5. 没有发现依赖 case ID 或样本专属规则的候选行为。

## 最终裁决与 guard

```text
MIGRATION = FORBIDDEN
FORMAL_WORKFLOW_INTEGRATION = FORBIDDEN
ACTUAL_CLEANING = FORBIDDEN
SPIKE_B = ALLOWED
```

本轮十项退出门禁均已满足：第 8 项要求“原因可以人工审查”，并不要求当前所有历史
E2/E3 已被批准。`g003` 的人工 `FALSE_NEGATIVE` 是有价值的反例，不是自动合同失败。

进入 Spike B 的唯一附加 guard：必须用 actual text-mask / safe-edit pixel evidence
验证 protected structure 风险；不得用 BubbleInstance 级 protected-overlap ratio 作为
`g003` 或同类普通气泡的最终整体 E3 决策，也不得在此之前执行实际 Cleaning。
