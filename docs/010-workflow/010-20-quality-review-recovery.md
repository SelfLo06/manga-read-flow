# Quality、Review 与 Recovery

## Check 通用合同

每个阶段 Check 接收版本化输入、候选输出、artifact metadata 与必要 provenance，返回结构化 issue drafts；不得直接调用 Provider、修改 active pointer 或清理文件。Issue 至少包含稳定类型、严重度、根阶段、受影响对象、证据和建议动作。

QualityCheckService 负责检测与 root-stage attribution；WorkflowLoopEngine 负责依据 issue 和预算作执行决定。阶段 Check 归属产生该质量约束的阶段，例如 CleaningCheck 为 150，TypesettingCheck 为 160，ExportCheck 为 170。

## Review、Edit 与 stale propagation

人工 Review 可以确认、否决或修正候选，但不能伪造算法证据。OCR/译文编辑创建新版本；旧版本和 attempt 保留。依赖图将下游关联、Cleaning、Typesetting 与 Export 标记 stale，随后只重算受影响对象。active pointer 是当前有效版本的唯一选择机制。

以上是目标合同，不表示完整产品路径已经实现。当前 Grouping replacement、immutable stale facts、pointer CAS 和 recovery repair 较完整；普通 OCR/Translation edit application entry 尚未实现或未由正式入口证明，OCR/Translation replacement 后完整、原子的下游 pointer 清理也尚未证明。后续实现必须通过正式 application entry、同一 UoW acceptance/stale transaction 和 recovery 测试关闭该偏离，不能靠 UI 直写 Repository 或完整 rerun 掩盖中间状态。

## Recovery 与 export readiness

恢复从已提交数据库状态出发，校验 artifact 路径/hash，识别运行中断、部分写入和未接受候选。失败 attempt artifact 默认保留；清理只由 ArtifactService 按 retention policy 执行。

ExportCheck 必须阻止缺失 active 结果、未解决的 blocking QualityIssue、stale 依赖或 artifact 不一致，不能进入正常导出。是否允许 warning 导出由该次运行的版本化 ProcessingProfileSnapshot 决定，允许时仍须写入 manifest；skip 必须保留原内容并可解释，不能把正文静默删除。

## 决策、替代、风险与验证

将检测、决定、持久化接受分开，可避免单个 validator 成为隐式流程引擎。拒绝独立 active flags、编辑原记录、仅靠文件时间判断新旧，以及恢复时自动接受孤儿 artifact。风险是 issue 归因错误、传播遗漏、清理过早和 warning 过宽。验证覆盖编辑链、局部返工、部分失败、重启、软删除、清理、Provider refusal、warning/blocked export 与重复恢复。精确依赖图和 UI review 体验仍需 M1/M2 设计。
