# MVP-1 整页清字台账／持久化／验收事务 v0.1

## 目标

冻结最小的、可恢复且可审计的全页 Cleaning 持久化合同。它必须使系统仅凭 project.db 与正式 ArtifactService artifact 回答：页面目标清单、逐 segment 最终处置、逐实例像素证据、组合候选成员、全页验证、一次 correction 预算、问题生命周期及 active cleaned artifact 是否可接受。

## 范围

- Page-scoped Cleaning run、inventory、instance result、disposition、combined membership、page validation、correction reservation、issue/acceptance/stale/recovery 合同；
- schema outline、migration 决策、Repository/UoW 命名操作、HARNESS 与实现切片。

## 非范围

不实现产品代码、migration、测试、Cleaner/validator 算法、API、UI、Typesetting、Batch 或 case-71/72 Closure。不得修改既有 frozen run、Spike 报告、Gate 或 Form。

## 固定输入

- case-71 有 6 个 segment；`g002/s01`、`g002/s02` 已有通过的局部 pixel ledger；其余四项没有完整 ledger，不能伪造 E1。
- case-72 已有 `g001/g002/g003/g004/g006` 的部分 pixel evidence；`g002` unsafe=710、`g004` unsafe=70、`g003` review/E3；`g005/g007/s01/g007/s02` 没有完整 ledger。
- Slice E/F 的 Provider→ArtifactService→Repository/UoW→QualityCheck→decision 边界和原图不可覆盖结论保持有效。

## 硬不变量

1. 每个冻结 inventory target 在 run 终态恰有一个 current final disposition。
2. `Page.active_cleaned_artifact_id` 只能经全页 acceptance transaction 更新。
3. 页面完成、成员关系、预算和 blocking 状态均可由 durable facts 重建；不得由 Page.status、时间戳、目录扫描、manifest 或调用方布尔值推断。
4. 大型 mask/pixel payload 为 ArtifactService artifact；SQLite 保存可查询的 identity、关系、hash、数值摘要和状态。
5. Provider、ArtifactService、QualityCheckService、WorkflowLoopEngine、Repository 的既有责任边界不变。

## 允许文件

仅 `docs/design/full-page-cleaning-ledger/**`；proposal/review 为设计过程文件，final 为实现前基线。

## 退出条件

HARNESS 与独立审查确认：全页完成可重建、disposition 唯一、成员可重放、页级验证可拒绝缺失/重复/overlap/wrong-write、预算可恢复、acceptance 原子、迁移明确，且没有未解决的 blocking 设计问题。
