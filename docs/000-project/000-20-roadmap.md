# 产品路线 M0–M3

仓库重构是工程治理任务，不是新的产品里程碑，也不改变任何算法门禁。

| 里程碑 | 定义 | 当前状态 |
| --- | --- | --- |
| M0 — Architecture Proof | 用 FakeProvider 证明 Repository/UoW、ArtifactService、Provider Adapter、Workflow Loop、QualityIssue、active pointer、幂等/恢复与 export readiness 等核心机制 | 已关闭；不是产品 MVP，不证明真实工具质量或用户可用性 |
| M1 — Single-Page Visual Closure | 首个且唯一的产品 MVP：可信 OCR/译文、BubbleInstance 或等价关联、Cleaning/Check、Typesetting/Check、最小单页 Web 预览、人工修改、局部返工、单图导出 | 当前主线；未完成，Cleaning physical-boundary capability 与完整视觉闭环仍阻塞 |
| M2 — Semantic Quality Closure | Detection/OCR、reading order、Page/必要多页翻译上下文、术语/称谓/代词/口吻一致性、semantic review、编辑后的 stale propagation 与局部重翻/重检/重嵌 | M1 后续；未开始产品闭环 |
| M3 — Scale & Personal Product | Batch、模型复用/缓存、性能资源预算、暂停取消恢复、页面失败隔离、retry/fallback/refusal、完整 Web、ZIP/manifest、设置备份日志和本地交付 | M2 后续；未开始产品闭环 |
| Post-MVP | 英文、竖排、复杂背景/艺术字、专业级排版等明确后置能力 | 不进入 M1 |

## 当前 M1 门禁

1. 用独立 controls 与像素级证据重设计并验证通用 physical-boundary capability；当前 A1/A2/A5 均为 NO_GO，不能调用 Cleaner 放行 g002/g004。
2. 在冻结单页样本上完成 Cleaning → CleaningCheck → Typesetting → TypesettingCheck 的实际视觉闭环，普通正文不得静默缺失。
3. 建立最小单页 Web 预览、OCR/译文编辑、局部返工与单图导出，并用 active pointer/staleness/export readiness 验证端到端语义。

以上门禁均未因信息架构重构而通过。

## 里程碑边界与裁决

M1 可使用可信 OCR/译文隔离视觉后半链路；自动 OCR/翻译的系统性质量提升属于 M2。Batch、资源预算和复杂恢复产品化属于 M3。拒绝把 M1、M2、M3统称为多个产品 MVP，也拒绝将 M0 的后端机制闭环描述为用户可用产品。

风险是未来能力被提前写成已实现、单样本证据被泛化，或为追求里程碑名称而重写稳定架构。每个里程碑必须由真实验收证据关闭。M1 冻结样本规模和最小 UI 交互仍待专门设计。
