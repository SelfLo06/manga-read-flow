# 阶段编号注册表

编号用于文档和工具归属，不自动改变现有持久化状态机。Owner 是职责所有者，不等于当前已实现模块。

| 编号 | 领域 | 类型 | 运行时地位 | Owner | 当前状态 | 文档 |
| --- | --- | --- | --- | --- | --- | --- |
| 100 | Import | 线性处理 | 后端正式路径 | WorkflowService / ArtifactService | `FORMAL_PATH_INTEGRATED`：backend 已接通；用户 API/Web 入口未实现 | [100 Import](../100-stages/100-import/100-00-import.md) |
| 110 | Detection | 线性处理 | Provider stage | Provider Adapter + QualityCheckService | `FAKEPROVIDER_ONLY`：lifecycle/check/acceptance 部分存在；real Paddle product Adapter 未实现 | [110 Detection](../100-stages/110-detection/110-00-detection.md) |
| 120 | Grouping | 线性处理 | 视觉/语义桥接 | Workflow/Grouping capability | `PRODUCT_PARTIAL`：Slice 1A–1E 已实现；production producer/orchestration 未实现 | [120 Grouping](../100-stages/120-grouping/120-00-grouping.md) |
| 130 | OCR | 线性处理 | Provider stage | OCR Adapter + QualityCheckService | `FAKEPROVIDER_ONLY`：lifecycle/persistence 部分存在；real manga-ocr Adapter 未实现 | [130 OCR](../100-stages/130-ocr/130-00-ocr.md) |
| 140 | Translation | 线性处理 | Provider stage | Translation Adapter + QualityCheckService | `FAKEPROVIDER_ONLY`：FakeProvider lifecycle + historical experiment；real LLM path 未实现 | [140 Translation](../100-stages/140-translation/140-00-translation.md) |
| 150 | Cleaning | 线性处理 | 本地/Provider stage | Cleaning capability + CleaningCheck | `PRODUCT_PARTIAL`：real Cleaner/Check/acceptance 存在；权威 Physical Boundary/VisualContract 上游未实现 | [150 Cleaning](../100-stages/150-cleaning/150-00-cleaning.md) |
| 160 | Typesetting | 线性处理 | 本地 stage | Typesetting capability + TypesettingCheck | `FAKEPROVIDER_ONLY`：artifact/pointer lifecycle 存在；real renderer 仅有 `EXPERIMENT_ONLY` 历史 `NO_GO`，glyph-based acceptance 未关闭 | [160 Typesetting](../100-stages/160-typesetting/160-00-typesetting.md) |
| 170 | Export | 线性处理 | readiness-gated | WorkflowService / ExportCheck | `LIFECYCLE_ONLY`：readiness 已实现；actual writer/output/download 未实现 | [170 Export](../100-stages/170-export/170-00-export.md) |
| 200 | Review / Edit | 跨阶段控制 | 横切能力 | WorkflowService | `LIFECYCLE_ONLY`：目标语义已定义；OCR/Translation edit entry 与完整 stale 未关闭 | [Quality/Review](010-20-quality-review-recovery.md) |
| 210 | Workflow Loop | 跨阶段控制 | 运行时决策核心 | WorkflowLoopEngine | M0 已验证 | [Workflow Loop](010-10-workflow-loop.md) |
| 220 | Quality Validation | 跨阶段控制 | 每阶段检查 | QualityCheckService | M0 合同已验证，真实阈值逐阶段收敛 | [Quality/Review](010-20-quality-review-recovery.md) |
| 230 | Retry / Recovery | 跨阶段控制 | 横切能力 | WorkflowLoopEngine / Repository | M0 基础已验证，产品化属 M3 | [Quality/Review](010-20-quality-review-recovery.md) |
| 240 | Reuse / Staleness | 跨阶段控制 | 横切能力 | WorkflowService / Repository | M0 基础已验证，完整编辑传播属 M2 | [Quality/Review](010-20-quality-review-recovery.md) |
| 300 | Artifact Management | 平台 | 基础设施 | ArtifactService | M0 已验证 | [Architecture](../000-project/000-10-architecture.md) |
| 310 | Persistence | 平台 | 基础设施 | Repository / DAO / UoW | M0 已验证 | [Architecture](../000-project/000-10-architecture.md) |
| 320 | Provider Adapters | 平台 | 基础设施 | Adapter implementations | FakeProvider 已验证，真实适配逐阶段推进 | [Architecture](../000-project/000-10-architecture.md) |
| 330 | Task Runner | 平台 | 本地执行 | TaskRunner | MVP 使用本地 runner；产品化属 M3 | [Architecture](../000-project/000-10-architecture.md) |
| 340 | API | 平台 | 产品边界 | FastAPI | `NOT_IMPLEMENTED` | [Roadmap](../000-project/000-20-roadmap.md) |
| 350 | Web UI | 平台 | 产品边界 | Next.js UI | `NOT_IMPLEMENTED` | [Roadmap](../000-project/000-20-roadmap.md) |
| 360 | Configuration | 平台 | 横切基础 | Application configuration | 不存 project secrets；产品设置属 M3 | [Architecture](../000-project/000-10-architecture.md) |

新增编号前必须确认存在真实独立职责；不得创建空目录或用编号暗示运行时已实现。状态变更以真实测试、实验和产品验收为依据。
