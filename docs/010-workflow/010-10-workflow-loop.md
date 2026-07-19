# Workflow Loop

WorkflowService 接收用户意图并准备阶段上下文；StageExecutor 记录 attempt、调用 Provider Adapter、登记 artifact 并取得质量检查输入；QualityCheckService 返回 issue drafts；WorkflowLoopEngine 根据证据作唯一执行决定。

## 决策语义

| 决策 | 含义 |
| --- | --- |
| accept | 结果满足当前阶段合同，在同一语义事务中接受并推进 active pointer |
| retry | 在预算内以新的 attempt 重试；不覆盖失败证据 |
| fallback | 选择已声明替代 Provider/策略，并记录原因与来源 attempt |
| skip | 仅对允许跳过的实例/阶段使用；保留原内容和可解释 issue |
| block | 阻止依赖结果或导出继续接受，等待用户动作或能力变化 |

Provider refusal、异常和质量失败都是输入证据，不由 Adapter 自行选择 retry/fallback/skip/block。retry budget 按阶段/操作显式管理；崩溃 attempt 仍须保留元数据，恢复不得把未提交结果误认为 accepted。

## 接受与恢复

attempt artifact 可以先登记，但 active pointer 只在质量问题、execution decision 和接受结果能够一致提交时更新。重启后优先相信数据库中已提交的 result/decision/pointer，并用 hash 验证文件；存在 artifact 而无接受事务时应恢复、重试或清理，不能静默提升。

幂等键至少涵盖输入内容、依赖 active version、配置/Provider 版本与阶段语义。复用命中也需产生可解释的 attempt/decision 证据。

## 决策、替代、风险与验证

选择集中式 loop 是为了让失败行为可解释、可测试、可恢复。拒绝 Adapter 内部隐藏重试、调用方直接改 active pointer，以及“文件存在即成功”。风险包括预算重复消耗、并发接受丢失更新和 crash window。验证覆盖成功、质量失败、拒绝、预算耗尽、fallback、skip、block、接受事务中断、重启与重复请求。并发 TaskRunner 的具体锁策略仍待 M3 设计。
