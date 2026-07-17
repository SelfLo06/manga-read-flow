# MVP-1 Visual Contract Bounded Spike A — HARNESS

## 候选生成与评价隔离

```text
Frozen inputs + frozen general policy
→ candidate snapshot
→ snapshot hash freeze
→ load evaluation oracle
→ automatic contract/oracle checks
→ human FORM review
```

候选生成阶段不得读取 `FIXTURE-ORACLE-v0.1.json`。

## 固定案例

| Case | 输入 | 预期关系 | 主要门禁 |
|---|---|---|---|
| case-71 | 真实接触气泡 | 1 contact cluster → 2 instances → 各 1 segment | 不得保留单一 parent instance |
| case-72 | 真实彩页 | 7 instances / 8 segments | 逐实例 eligibility；普通气泡假阴性可审查 |
| synthetic-contact-n3 | 3 个接触椭圆 | 1 cluster → 3 instances | N 不固定为 2 |
| synthetic-multi-column | 单椭圆、两列 | 1 instance → 2 segments | 不得过度拆分 |
| synthetic-two-paragraphs | 单椭圆、上下两段 | 1 instance → 2 segments | 不得过度拆分 |
| synthetic-mixed-risk | 两个接触实例、不同背景风险 | 同 cluster 内 risk 不同 | 禁止 worst-risk broadcast |

## Deliberate negatives

| Mutation | 必须被拒绝为 |
|---|---|
| deliberate merge | `EXPECTED_DIFFERENT_SEGMENTS_MERGED` |
| deliberate split | `EXPECTED_SAME_SEGMENTS_SPLIT` |
| deliberate unassigned | `SEGMENT_DISPOSITION_INVALID` |
| deliberate wrong-instance | `EXPECTED_ASSIGNMENT_MISMATCH` |

## 自动合同检查

1. 每个 active segment 恰好 assigned 或 explicitly excluded；
2. stable ID 不依赖输入列表或目录顺序；
3. cluster mask 等于各 instance mask 的无重叠并集；
4. instance relation、mask revision 和 eligibility evidence 的 ID/hash 同源；
5. E2/E3 均有非空 reason codes、rules、features、threshold version、evidence；
6. snapshot 声明自己是该 run 的唯一关系事实来源；
7. 禁止 `parent_bbox_mapping`、`directory_order_mapping`、`cluster_risk`；
8. oracle hash 被记录，但 oracle 不写入 snapshot relationship facts。

## 人工审查

人工只裁决真实图像中的语义拓扑与 eligibility 解释是否合理，不绘制 pixel-accurate GT。重点审查：

- case-71 两个 instance overlay；
- case-72 每个实例的历史风险、重放风险、触发规则和特征；
- 普通对白是否被无充分证据排除；
- synthetic 输出仅作为合同反例，不作为真实质量证据。

## 退出门禁

采用用户指定的十项门禁。自动检查通过但人工 FORM 未完成时，Gate 只能是 `PENDING_HUMAN_REVIEW`。
