# MVP-1 Visual Contract Bounded Spike A — PLAN

状态：`COMPLETE`

## Phase 0：冻结输入

- 核对 Visual Contract commit；
- 验证 S1、provenance、Goal 5 lock、Goal 6 evidence 和真实图片 hash；
- 冻结通用 policy 与 evaluation oracle hash。

## Phase 1：先写反例合同

- synthetic N≥3；
- 单气泡多列、两段；
- mixed-risk cluster；
- merge/split/unassigned/wrong-instance mutation；
- 顺序无关 stable ID 测试。

## Phase 2：实现候选 snapshot

- segment marker competition；
- widest-path saddle ratio 作为 same-container 证据；
- same 关系连通分量形成实例；
- 逐实例 Mask、disposition、qualification、eligibility；
- canonical JSON hash 与 artifact hash。

## Phase 3：真实输入运行

- case-71/72；
- synthetic fixtures；
- 自动合同与 oracle 检查；
- overlay 和 FORM。

## Phase 4：收口

- 人工反馈已纳入 REPORT/GATE；
- 结论：`GO_TO_SPIKE_B_WITH_GUARD`；
- `case-72__g003__s01` 冻结为 Pixel Evidence / safe-edit 级 protected-overlap
  反例，禁止依据本轮 instance-level ratio 进入实际 Cleaning；
- 任一负例误收或样本专属规则触发 `NO_GO`；
- 本轮不提交实现，除非维护者另行授权。
