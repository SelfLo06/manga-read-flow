# 漫画翻译与基础嵌字自动化工作流应用
# 软件开发过程规划 PROJECT-PLAN v0.2

版本：v0.2
状态：2026-07-17 产品里程碑重排基线
适用范围：需求、设计、Spike、实现、测试、交付与后续演化
目标读者：项目维护者本人、AI 编码代理、后续审查者

---

## 1. 规划目的

本文档用于定义本项目从当前阶段到个人可用版、稳定版的整体推进方式。

本项目不是课程作业，也不是专业汉化组生产系统，而是一个个人兴趣项目。项目目标是构建一个面向普通漫画读者的本地漫画翻译与基础嵌字工作流应用，使用户能够上传漫画图片，经过检测、OCR、Page 级翻译、质量检查、清字、嵌字和导出，得到基础中文可读结果。

本文档解决以下问题：

1. 本项目采用什么软件开发过程模型；
2. 需求、设计、实现、测试、交付如何推进；
3. 哪些阶段需要先做设计，哪些阶段需要先做工具 Spike；
4. 一个人开发时如何控制范围和风险；
5. Codex / AI agent 如何参与设计、实现、审查和验证；
6. 每个阶段的输入、输出、退出标准是什么；
7. MVP 和后续版本如何划分。

本文档不展开：

1. 具体数据库 DDL；
2. 具体 API schema；
3. 具体 Provider JSON schema；
4. 具体 Prompt 模板；
5. 具体前端组件结构；
6. 具体 OCR、清字、嵌字算法实现；
7. 完整测试用例代码。

这些内容应在对应详细设计或实现阶段展开。

---

## 2. 当前基线

当前项目已经形成以下基线文档。

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| `docs/SRS-v1.0.md` | 已形成正式需求基线 | 定义系统目标、范围、P0/P1/P2、外部依赖、MVP 验收标准。 |
| `docs/HLD.md` | 已接受为详细设计与 MVP 实现基线 | 原 `HLD-v0.2` 已提升为稳定入口，定义应用形态、总体架构、模块边界、Workflow Loop、Quality Gate、Provider Adapter、ArtifactService 等。 |
| `docs/design/data-model/final/data-model-dd-v0.1.md` | 已形成数据模型详细设计基线 | 定义 app.db/project.db、核心实体、active pointer、WorkflowAttempt、QualityIssue、Artifact 等数据边界。 |
| `docs/design/data-model/final/schema-outline.md` | 已形成 schema outline | 作为后续 ORM / migration / repository 设计输入。 |
| `docs/design/data-model/final/state-data-impact.md` | 已形成状态数据影响说明 | 说明 OCR edit、Translation edit、Provider refusal、Cleaning skip、Typesetting overflow、Crash recovery、Export blocking 的数据影响。 |
| `docs/design/workflow-state/final/workflow-state-dd-v0.1.md` | 已形成 Workflow State 详细设计基线 | 定义状态词汇、阶段转移、决策矩阵、恢复规则、stale 传播。 |
| `docs/design/execution-contract/final/execution-contract-dd-v0.1.md` | 已形成 Execution Contract 详细设计基线 | 定义 Provider Adapter、ArtifactService、QualityCheckService、StageExecutor 和 FakeProvider 最小契约。 |
| `docs/design/persistence/final/persistence-readiness-dd-v0.1.md` | 已形成 Persistence Readiness 设计基线 | 定义 Repository / DAO、Unit of Work、migration、recovery 和 idempotency 实现准备。 |
| `docs/implementation/mvp0-fakeprovider-slice/PLAN.md` | 已形成 MVP-0 FakeProvider 实施计划 | 将首个后端实现拆为 7 个小切片，并给出验证命令与 Codex task prompt。 |
| `docs/engineering/reviews/mvp0-fakeprovider-backend-closure-review.md` | MVP-0 FakeProvider 后端闭环审查完成 | Slice 01–07 已实现并以 `PASS_WITH_DEFERRED_RISKS` 关闭；不代表 API、UI、真实 Provider 或导出已经完成。 |

当前状态判断：

```text
需求基线与 HLD 已完成。
MVP-0 所需核心详细设计已完成：Data Model、Workflow State、Execution Contract、Persistence Readiness。
历史 MVP-0 FakeProvider 单 Page 后端 Slice 01–07 已实现并通过关闭审查（`PASS_WITH_DEFERRED_RISKS`），现统一归类为 M0 Architecture Proof。
M0 证明了架构机制，不证明产品质量，也不再占用“产品 MVP”概念。
真实工具 Spike 已证明部分 Detection/OCR/Translation、局部 Cleaning/association 和 Typesetting 输入合同可运行，同时暴露 BubbleInstance 拓扑、Cleaning eligibility、实际 glyph validator 和视觉质量阻塞。
Typesetting 首轮当前裁决为：`CURRENT TYPESETTING OUTPUT = NO_GO`；`INPUT CONTRACT / REGION GROUNDING = GO_WITH_CHANGES`。已确认 OCR/译文 segment 未串块，但接触气泡仍缺少 BubbleInstance 拓扑，普通气泡存在 Cleaning eligibility 假阴性风险，旧 validator 可能未约束 renderer 实际 glyph。
当前尚未形成高质量、用户可操作的单 Page 产品闭环。
```

---

## 3. 开发过程模型

### 3.1 选择模型

本项目采用：

```text
风险驱动的增量演化模型
+ 外层阶段门禁
+ 内层短迭代
+ 关键技术 Spike 提前验证
+ 垂直切片优先实现
```

它不是纯瀑布模型，也不是完全自由的敏捷模型。

### 3.2 为什么不是纯瀑布

纯瀑布模型通常是：

```text
需求 → 全量设计 → 全量实现 → 全量测试 → 交付
```

该模型不适合作为本项目的主过程，因为本项目核心能力高度依赖外部工具：

1. 文本检测；
2. 日语 OCR；
3. Page 级 LLM 翻译；
4. 翻译质量检查；
5. 清字 / inpaint；
6. Pillow 嵌字；
7. Provider refusal 处理；
8. 中断恢复和 artifact 追踪。

这些能力存在不确定性。如果等全量设计和实现完成后才验证工具，会导致高风险问题暴露过晚。

### 3.3 为什么不是完全自由迭代

完全自由迭代容易导致：

1. 先做 UI，后发现 workflow 状态不可恢复；
2. 先接真实工具，后发现 artifact 和缓存设计不支持返工；
3. 先写 API，后发现状态机和 retry budget 没定义；
4. 后续里程碑功能过早侵入当前 MVP；
5. 一个人开发时范围失控。

因此，本项目需要阶段门禁和设计基线。

### 3.4 过程模型原则

本项目过程原则如下：

1. 用需求和架构文档控制方向；
2. 用 Spike 尽早验证工具可用性；
3. 用 FakeProvider 先验证 workflow、artifact、recovery 和 export gate；
4. 用单 Page 垂直切片先达到支持范围内的真实视觉质量；
5. 在视觉质量通过后收敛 OCR/翻译语义质量，再扩展 Batch、恢复、性能和复杂产品流程；
6. 每个阶段都有明确退出标准；
7. 每个实现增量都必须可运行、可验证、可回滚；
8. 不让复杂 SFX、专业精修、Batch 性能或高级 Workflow 阻塞 MVP-1；
9. 每个技术 Spike 必须有时间边界和回归主线条件，不能用无限算法研究替代产品结果；
10. 开发期人工标注用于验证系统，不默认成为产品运行期必经流程。

---

## 4. 项目阶段总览

| 阶段 | 名称 | 核心目标 | 当前状态 |
| --- | --- | --- | --- |
| Phase 0 | 项目治理与文档基线 | 建立 AGENTS、文档结构、ADR、协作规则 | 基本完成，后续维护 |
| Phase 1 | 需求与架构基线 | SRS 和 HLD 定版，形成实现方向 | 已完成 |
| Phase 2 | 核心详细设计 | 数据模型、状态机、Provider、Artifact、Quality、API 等详细设计 | MVP-0 前置设计已完成；API/UI/Export 详细设计后置 |
| M0 | Architecture Proof | FakeProvider 验证 workflow、artifact、quality、persistence、recovery/idempotency | 已完成并关闭 |
| MVP-1 | 高质量单页视觉闭环 | 在可信文字输入下完成普通气泡/旁白框的 association、Cleaning、Typesetting、Validator 和最小单页产品入口 | 进行中；当前主线 |
| MVP-2 | OCR 与翻译质量闭环 | 提高 OCR/reading order、Page/multi-page 翻译、术语/口吻和语义 reviewer | MVP-1 后启动 |
| MVP-3 | 规模化、性能与复杂 Workflow | Batch、资源预算、恢复、retry/fallback、ZIP、正式 Web、桌面化准备 | MVP-2 后启动 |
| Post-MVP | 扩展能力 | 英文、竖排、复杂背景、复杂排版等 | 后续 |

路线原则：

> 先把一页做得真正好，再把文字理解做准，最后把整章做快、做稳、做自动。

### 4.1 路线决策

1. 历史 `MVP-0 FakeProvider Backend` 只作为 M0 Architecture Proof；
2. 第一个产品 MVP 必须以真实单页视觉质量为核心；
3. MVP-1 可使用可信 OCR/译文隔离验证视觉后半链路；
4. MVP-1 必须包含最小用户操作入口，否则只能称为能力证明；
5. OCR/翻译自动质量独立进入 MVP-2；
6. Batch、性能、复杂 recovery/fallback 和正式产品化进入 MVP-3；
7. 底层架构基线保持有效，不因里程碑重排而重写。

### 4.2 理由

旧路线先证明“能跑、能操作、能扩多页”，再收敛真实结果质量，导致用户长期看不到可直接阅读的完整页面，也使局部 warning/skip 容易掩盖普通对白缺失。新路线先隔离并解决视觉闭环，再分别处理语义质量和规模化，可更快证伪技术方向，也更接近普通读者的实际价值。

### 4.3 拒绝的替代顺序

1. **先做完整 Web 和 Batch，再处理视觉质量**：拒绝；会放大错误链路并增加返工面。
2. **MVP-1 同时要求 OCR、翻译、视觉和 Batch 全自动达标**：拒绝；目标耦合过多，无法定位失败阶段。
3. **只做算法 Harness，直到所有边缘场景都解决后再做用户入口**：拒绝；会再次长期偏离产品主线。
4. **将所有 E2/E3 直接升级为自动处理**：拒绝；必须保留逐实例风险原因和安全 abstention。
5. **为提高质量推翻 Workflow/Artifact/Persistence 架构**：拒绝；现有 M0 已证明这些机制，当前问题位于真实视觉能力和质量 Gate。

### 4.4 当前开放问题

1. BubbleInstance 是否成为持久化实体，或先以 revision/artifact metadata 表达；
2. MVP-1 冻结样本的最小组成和人工 `ACCEPTABLE` 判定说明；
3. 最小单页入口复用现有后端到什么程度，哪些能力可先由开发工具承载；
4. Cleaning eligibility 的风险特征与 QualityIssue taxonomy；
5. actual-glyph Validator 的占用率、留白和视觉中心阈值如何只在 calibration 子集冻结。

---

## 5. Phase 0：项目治理与文档基线

### 5.1 目标

建立项目治理规则，使一个人开发和 AI agent 协作时不会失控。

### 5.2 输入

无。

### 5.3 输出

建议输出：

```text
AGENTS.md
docs/SRS-v1.0.md
docs/HLD.md
docs/PROJECT-PLAN.md
docs/design/<area>/（含 final/ 与域内 adr/）
docs/spikes/
docs/adr/architecture/
```

### 5.4 主要工作

1. 建立 `AGENTS.md`；
2. 明确 Git、commit、push、pull、rebase 规则；
3. 明确 AI agent 的最小变更原则；
4. 明确设计任务和实现任务的区别；
5. 建立 ADR 目录；
6. 建立 `docs/design/` 目录；
7. 建立工具 Spike 记录目录；
8. 建立项目级风险记录方式。

### 5.5 退出标准

1. AI agent 知道必须读取哪些基线文档；
2. AI agent 知道哪些文件可改、哪些不可改；
3. AI agent 不会自动 push / pull / rebase；
4. 设计任务不会被误写成实现任务；
5. 敏感信息、日志、缓存和 AI 工具运行文件不会被提交。

---

## 6. Phase 1：需求与架构基线

### 6.1 目标

明确系统要解决什么问题、面向谁、做什么、不做什么、如何组织。

### 6.2 输入

1. 初始需求草案；
2. 工具可行性调研；
3. 用户目标和约束。

### 6.3 输出

1. `docs/SRS-v1.0.md`；
2. `docs/HLD.md`；
3. 架构 ADR 初始清单。

### 6.4 主要工作

1. 确认目标用户是普通漫画读者；
2. 确认第一阶段为日语到简体中文；
3. 确认 Project / Batch / Page / TextBlock 结构；
4. 确认复杂拟声词、花体字、艺术字、复杂背景文字移出 MVP；
5. 确认本地 Web + FastAPI + SQLite + filesystem；
6. 确认 WorkflowLoopEngine、QualityCheckService、Provider Adapter、ArtifactService、Repository/DAO 边界；
7. 确认一键处理默认无人值守，人工 review 是后处理；
8. 确认 Provider refusal、NSFW、API key、export gate 和 debug artifact 边界。

### 6.5 退出标准

1. SRS v1.0 可作为需求基线；
2. HLD v0.2 已提升为 `docs/HLD.md`，可作为详细设计与实现基线；
3. 无阻塞性需求问题；
4. M0、MVP-1、MVP-2、MVP-3 与 Post-MVP 范围明确；
5. MVP-1 验收标准明确。

---

## 7. Phase 2：核心详细设计

### 7.1 目标

将 HLD 中的核心架构机制细化到可实现、可测试、可审查的程度。

### 7.2 当前状态

已完成：

1. Data Model 详细设计 v0.1；
2. Workflow State / Workflow Loop 详细设计 v0.1；
3. Execution Contract 详细设计 v0.1，覆盖 Provider Adapter、ArtifactService、QualityCheckService、StageExecutor 和 FakeProvider 最小契约；
4. Persistence Readiness 详细设计 v0.1；
5. MVP-0 FakeProvider Single-Page Backend Slice 实施计划。

### 7.3 后续详细设计顺序

| 顺序 | 设计项 | 输出目录 | 说明 |
| --- | --- | --- | --- |
| 1 | Data Model 详细设计 | `docs/design/data-model/` | 已完成 v0.1。 |
| 2 | Workflow State / Workflow Loop 详细设计 | `docs/design/workflow-state/` | 已完成 v0.1。 |
| 3 | Execution Contract 详细设计 | `docs/design/execution-contract/` | 已完成 v0.1，覆盖 MVP-0 所需 Provider、Artifact、Quality、StageExecutor 契约。 |
| 4 | Repository / ORM / Migration 最小设计 | `docs/design/persistence/` | 已完成 Persistence Readiness v0.1。 |
| 5 | MVP-0 FakeProvider 实施计划 | `docs/implementation/mvp0-fakeprovider-slice/` | 已完成 7 个实现切片、review、checklist 和 Codex task template。 |
| 6 | MVP-1 视觉对象合同 | `docs/design/` 或 bounded spike | ContactBubbleCluster、N BubbleInstance、TextSegment/LayoutSlot、provenance 对账。 |
| 7 | MVP-1 Cleaning/Typesetting/Validator | 对应 spike 与设计目录 | eligibility、pixel mask、safe region、actual glyph、视觉 Gate。 |
| 8 | 最小单页 API/UI/Export | `docs/design/api/`、`docs/design/ui/`、`docs/design/export/` | 仅覆盖单页预览、文字修正、局部返工、单图导出。 |
| 9 | MVP-2 语义质量设计 | 后续设计目录 | OCR reviewer、multi-page translation、术语/口吻与 stale propagation。 |
| 10 | MVP-3 规模化设计 | 后续设计目录 | Batch、资源预算、复杂 recovery、ZIP 和正式产品闭环。 |

### 7.4 退出标准

Phase 2 不要求所有详细设计一次性完成；历史上进入 M0 Architecture Proof 前已完成：

1. Workflow State / Workflow Loop 详细设计；
2. Provider Adapter 接口设计；
3. ArtifactService 详细设计；
4. QualityCheckService 详细设计；
5. Repository / persistence 最小设计；
6. 历史 MVP-0 实现计划。

---

## 8. 架构验证与真实工具 Spike

### 8.1 目标

尽早验证最高风险的架构机制、外部工具可用性和真实视觉质量。M0 架构验证已经完成；当前 Spike 只服务于 MVP-1 的明确阻塞项。

### 8.2 总体策略

FakeProvider 架构验证已完成。后续顺序更新为：

推荐顺序：

```text
M0 架构回归
→ MVP-1 BubbleInstance / Cleaning eligibility / Validator bounded spike
→ 高质量单页视觉 Gate
→ 最小单页产品入口
```

### 8.3 架构验证 Spike

| ID | 验证项 | 目标 | 通过标准 |
| --- | --- | --- | --- |
| AV-001 | FakeProvider 单 Page 垂直切片 | 不依赖真实 OCR/LLM，先跑通 workflow | 生成 TextBlock、OCRResult、TranslationResult、artifact、QualityIssue、ready_for_export。 |
| AV-002 | Artifact 生命周期 | 验证正式 artifact 只由 ArtifactService 管理 | active artifact 不被清理，缺失文件被标记 missing，原图不覆盖。 |
| AV-003 | Workflow 决策 | 验证 retry、fallback、skip、warning、block | 每次决策有 WorkflowAttempt、QualityIssue、WorkflowDecision。 |
| AV-004 | Crash recovery | 验证进程中断后恢复 | OCR 后崩溃，重启不重复 OCR，从 translation 继续。 |
| AV-005 | Provider refusal | 验证 refusal 是 workflow 路径 | ToolRunLog、WorkflowAttempt、QualityIssue、WorkflowDecision 均有记录。 |
| AV-006 | Export gate | 验证 blocking issue 阻止正常导出 | ExportRecord blocked，不生成正常 output artifact。 |
| AV-007 | Warning export | 验证 warning export profile | allow_warning_export true/false 时行为不同且可解释。 |
| AV-008 | Idempotency | 验证重复处理不重复调用工具 | 记录 reused_cached，不重复调用对应 Provider。 |

### 8.4 真实工具 Spike

| Spike | 目标 | 最小输出 | 失败时降级 |
| --- | --- | --- | --- |
| Detection + OCR | 验证检测框、裁剪、manga-ocr / PaddleOCR | TextBlock geometry + OCRResult 样例 | 降低自动检测目标，保留手动/跳过能力。 |
| Page Translation JSON | 验证 Page 级输入输出 JSON 稳定性 | page translation response + TranslationCheck 结果 | 收紧 Prompt、减少 schema、增加 retry / manual fallback。 |
| Glossary Effect | 验证术语表改善一致性 | 有/无术语表对比报告 | 将术语表降为辅助，不承诺强一致。 |
| Cleaning | 验证 bubble_fill / OpenCV inpaint | cleaned artifact 样例 | 复杂背景默认 skip。 |
| Typesetting | 验证 Pillow 自动换行、字号、溢出 | typeset artifact + overflow report | 缩短译文、warning、手动 review。 |
| Mini real workflow | 验证真实工具链最小接入 | import → detect → OCR → translate → clean → typeset → export | 记录失败点，调整 MVP 范围。 |

### 8.5 退出标准

1. M0 FakeProvider 架构验证保持通过；
2. 每个 MVP-1 Spike 有输入、输出、失败模式、降级策略、耗时和明确 Gate；
3. ContactBubbleCluster、BubbleInstance、TextSegment 和 LayoutSlot 语义不混用；
4. Cleaning eligibility 假阴性可解释；
5. Renderer 与 Validator 使用同一 BubbleInstance region 和实际 glyph；
6. 一轮实现加一轮修正后仍无明显视觉改善时停止当前路线并重新裁决；
7. Spike 一旦解除阻塞，立即回到完整单页结果，不继续无限扩样本或算法分支。

---

## 9. M0：Architecture Proof（历史 MVP-0）

### 9.1 目标

在没有完整 UI 和真实 Provider 的情况下，验证单 Project / 单 Batch / 单 Page 后端架构机制。该阶段已完成并关闭。

### 9.2 范围

包含：

1. Project 创建；
2. Batch 创建；
3. Page import；
4. ArtifactService 保存原图；
5. TextBlock 创建；
6. OCRResult 创建；
7. TranslationResult 创建；
8. QualityIssue 创建；
9. WorkflowAttempt / WorkflowDecision；
10. Cleaning / Typesetting artifact；
11. export readiness / `export_check`，达到 `ready_for_export` 或明确 warning/block 状态；
12. CLI 或脚本触发。

### 9.3 不包含

1. 完整 Web UI；
2. FastAPI route 设计与实现；
3. 多页 Batch；
4. 高级设置页；
5. 实际导出图片、ZIP、manifest 或 `ExportRecord`；
6. 桌面化；
7. MVP-2/MVP-3 和 Post-MVP 能力。

### 9.4 退出标准

历史实现可以完成：

```text
create project
→ import one page
→ run one-page workflow
→ output fake cleaned/typeset artifacts
→ create quality report
→ reach export readiness / explicit warning or block
```

且满足：

1. 原图不覆盖；
2. 失败可解释；
3. attempt 和 decision 可追踪；
4. 重跑时可复用已完成结果；
5. export readiness gate 可工作。

M0 不证明真实 OCR、翻译、Cleaning、Typesetting、UI、正式导出或产品质量；后续不得再以“MVP-0 已完成”表达产品 MVP 已完成。

---

## 10. MVP-1：高质量单页视觉闭环

### 10.1 目标

对一张真实漫画页，在可信 OCR/译文输入下生成完整、干净、舒适、可直接阅读的中文结果，并提供最小用户操作入口。

### 10.2 范围

支持范围：

1. 普通对白气泡；
2. 普通旁白框；
3. 横排简体中文；
4. 有明确文字区域的常规内容；
5. 复杂拟声词、艺术字和复杂背景文字允许明确排除。

核心工作：

1. Detection / Grouping / Association provenance 完整对账；
2. `ContactBubbleCluster → N BubbleInstance`；
3. 每个 BubbleInstance 独立 mask、文字归属、Cleaning 和 Typesetting 边界；
4. Cleaning eligibility 假阴性诊断；
5. pixel text mask、safe edit region 和 protected boundary；
6. 完整清字且不损坏结构；
7. BubbleInstance-aware typesetting region；
8. 自然字号、断行、留白和视觉居中；
9. actual-glyph Validator 检查归属、丢失、重复、跨实例、溢出和占用率；
10. 一次有界局部修正或重跑；
11. 最小单页上传/选择、预览、OCR/译文修正、局部返工和图片导出入口。

OCR/Translation 采用真实初稿，但允许最小 review 修正或冻结可信输入。该做法用于隔离视觉质量，不宣称 OCR/翻译已经全自动可靠。

### 10.3 退出标准

固定真实单页必须达到：

```text
可信文字输入
→ 所有支持对象有去向
→ BubbleInstance 正确
→ 清字完整且结构安全
→ 嵌字自然且不越界
→ Validator 与人工观察一致
→ 预览 / 必要修正 / 单图导出
```

且满足：

1. 普通对白不静默漏失；
2. unresolved 普通对白缺失阻塞高质量验收；
3. excluded 对象有明确原因；
4. 无明显残字、结构损坏、跨实例或溢出；
5. 人工视觉结果为 `ACCEPTABLE`；
6. 无 OOM、无限循环、无界内存增长和不可复现输出；
7. 不以吞吐量为门禁，单页几十秒可接受；
8. 一轮实现加一轮修正后仍无明显改善则停止并重新评估技术路线。

---

## 11. MVP-2：OCR 与翻译质量闭环

### 11.1 目标

从真实页面自动获得可信 OCR 和高质量译文，并在连续页面中保持上下文、术语、称谓和人物口吻一致。

### 11.2 范围

包含：

1. Detection/OCR 召回率和字符准确率；
2. reading order；
3. OCR 多候选、校验与局部修正；
4. Page 级和 multi-page context；
5. Project 术语、人名、称谓、代词和口吻一致；
6. 翻译 reviewer 与局部重翻；
7. 长短句与气泡空间协调；
8. OCR/翻译不确定性可见；
9. OCR/译文修改后的 stale 传播和局部重排。

多页在本阶段首先服务于语义上下文，不要求高性能 Batch 产品体验。

### 11.3 退出标准

1. 固定连续多页样本关键文字无静默漏识；
2. OCR 和 reading order 达到冻结门槛；
3. 译文语义正确；
4. 术语、称谓、代词和口吻跨页一致；
5. 修正 OCR 后 Translation/Typesetting 正确 stale 并局部重跑；
6. 修正译文后 Typesetting 正确 stale 并局部重跑；
7. 语义质量问题不会被漂亮排版掩盖。

---

## 12. MVP-3：规模化、性能与复杂 Workflow

### 12.1 目标

回答“一章漫画能否稳定、高效、少人工地处理完成”，并完成正式本地产品闭环。

### 12.2 范围

1. 多 Page Batch、页面顺序和 ZIP/manifest；
2. 模型常驻、Detection/OCR 批处理；
3. 翻译请求合并、缓存和成本控制；
4. 并发、资源预算和单页隔离 worker；
5. 暂停、取消、恢复和页面失败隔离；
6. retry、fallback、Provider refusal 和复杂 QualityIssue loop；
7. ProcessingProfile 与长任务进度；
8. 正式本地 Web 上传、处理、review、返工和导出；
9. 配置、备份、migration、日志与桌面化准备。

### 12.3 测试层次

| 层次 | 内容 |
| --- | --- |
| 单元测试 | hash、artifact path、active pointer、stale propagation、export gate。 |
| 集成测试 | FakeProvider workflow、Repository、ArtifactService、WorkflowLoopEngine。 |
| 样本回归 | 固定漫画样本跑检测、OCR、翻译、清字、嵌字。 |
| E2E 测试 | Project → Batch → Page → Process → Review → Export。 |
| 手工验收 | 本地真实使用流程。 |

### 12.4 重点测试场景

1. Happy path；
2. OCR 后崩溃恢复；
3. Provider refusal；
4. invalid LLM JSON；
5. cleaning skip；
6. typesetting overflow；
7. artifact missing；
8. warning export；
9. blocking export；
10. OCR edit stale；
11. translation edit stale；
12. same filename in different Projects；
13. project soft delete / restore。

### 12.5 退出标准

1. P0 E2E 流程稳定；
2. 主要 failure path 有测试；
3. 主要错误有用户可理解提示；
4. debug artifact 不泄漏 secret；
5. 样本回归有记录；
6. 已知问题进入 backlog。

额外要求：固定整章样本无 OOM，资源预算有界；页面失败可隔离；重复运行不重复调用未变化阶段；open blocking QualityIssue 阻止正常导出。

---

## 13. MVP-3 交付与桌面化准备

### 13.1 目标

在 MVP-1 视觉质量和 MVP-2 语义质量通过后，准备个人可用版本和后续桌面化。本节不作为当前 MVP-1 的前置条件。

### 13.2 范围

包含：

1. 本地启动脚本；
2. workspace 选择；
3. Provider/API key 设置；
4. 字体路径设置；
5. 日志位置说明；
6. 数据备份说明；
7. 样本测试说明；
8. 后续桌面壳评估。

### 13.3 不包含

1. 商业化发布；
2. 云端多用户；
3. 漫画资源分发；
4. 专业汉化组协作；
5. 复杂桌面安装器。

### 13.4 退出标准

1. 用户可本地启动；
2. 项目数据可备份；
3. 配置路径清楚；
4. 日志和 debug artifact 策略清楚；
5. 桌面化不会改变核心后端和 workspace 架构。

---

## 14. Post-MVP 演化

以下增强不阻塞 MVP-1、MVP-2 或 MVP-3 的既定退出标准。

候选演化方向：

1. 英语到中文；
2. 竖排中文嵌字；
3. 更复杂背景修复；
4. 本地翻译模型自动 fallback；
5. 自动术语候选；
6. 更复杂字体与排版；
7. 气泡外文字与复杂拟声词；
8. 简单阅读器；
9. 专业精修辅助能力。

Post-MVP 增强必须遵守：

1. 不破坏 P0 数据模型；
2. 不破坏 Provider Adapter 边界；
3. 不绕过 WorkflowLoopEngine；
4. 不绕过 ArtifactService；
5. 不改变资源边界和合规边界。

---

## 15. 版本路线图

| 版本 | 名称 | 范围 |
| --- | --- | --- |
| M0（历史 v0.1） | Architecture Proof | FakeProvider 后端机制验证；已完成，不代表产品 MVP。 |
| MVP-1 | 高质量单页视觉闭环 | 可信文字输入下的 BubbleInstance、Cleaning、Typesetting、Validator、最小单页预览/修正/导出。 |
| MVP-2 | OCR 与翻译质量闭环 | OCR/reading order、Page/multi-page 翻译、术语/口吻、语义 reviewer 和 stale propagation。 |
| MVP-3 | 规模化与个人产品 | Batch、性能、资源预算、复杂 Workflow、正式 Web、ZIP、配置、备份和桌面化准备。 |
| Post-MVP | 扩展能力 | 其他语言、竖排、复杂背景、复杂拟声词与高级排版。 |

旧的 v0.2–v0.5 顺序不再作为执行优先级；其中有效能力已重新归入上述三个产品 MVP。

---

## 16. 详细设计路线图

| 设计项 | 状态 | 当前里程碑关系 | 备注 |
| --- | --- | --- | --- |
| Data Model | 已完成 v0.1 | 架构基线 | active pointer、result versioning、project isolation 保持有效。 |
| Workflow State / Loop | 已完成 v0.1 | 架构基线 | MVP-1 只落地一次局部 loop；复杂策略后移 MVP-3。 |
| QualityCheckService / IssueType | M0 最小契约已完成 | MVP-1 需扩展视觉 issue | 增加实例归属、缺失/重复、残字、glyph overflow、占用率和视觉中心。 |
| Provider Adapter Interface | M0 最小契约已完成 | 保持有效 | 不允许视觉 Spike 绕过 Provider 责任边界进入正式集成。 |
| ArtifactService | M0 最小契约已完成 | 保持有效 | BubbleInstance mask、glyph mask 和 validator evidence 仍经 ArtifactService。 |
| Repository / ORM / Migration | 已完成 v0.1 | 保持有效 | 新视觉对象的持久化方案需单独详细设计，不在 HLD 中猜测。 |
| M0 FakeProvider 实施 | 已完成并关闭 | 历史基线 | 不再作为下一步。 |
| MVP-1 Visual Contract | 进行中 | 当前 blocker | cluster/instance/segment、eligibility、Cleaning、Typesetting、Validator。 |
| MVP-1 最小 API/UI/Export | 待做 | 视觉 Gate 后立即进行 | 单页预览、文字修正、局部返工和图片导出。 |
| MVP-2 Semantic Quality | 待做 | MVP-1 后 | OCR 与翻译质量。 |
| MVP-3 Scale/Product | 待做 | MVP-2 后 | Batch、性能、复杂 Workflow、正式产品。 |

---

## 17. 阶段门禁

### 17.1 设计门禁

进入实现前必须满足：

1. 对应详细设计文档存在；
2. 无 blocking open question；
3. 重要决策已有 ADR；
4. harness scenario 可以解释；
5. 不变量没有被破坏。

### 17.2 Spike 门禁

Spike 完成必须满足：

1. 输入样本明确；
2. 输出 artifact 可复现；
3. 失败模式已分类；
4. 降级策略已记录；
5. 是否影响 SRS/HLD/MVP 范围已判断。
6. 已记录阶段耗时与总耗时；
7. 已定义回到产品主线的条件；
8. 一轮实现加一轮修正后仍不能改善核心指标时停止，不无限扩样本或调参。

### 17.3 实现门禁

实现增量完成必须满足：

1. 有可运行入口；
2. 有最小测试或替代验证；
3. 有错误路径验证；
4. 没有误改无关文件；
5. Git diff 可审查；
6. 已知风险已记录。

### 17.4 MVP 门禁

MVP 按阶段独立验收，不再要求在一个总门禁中同时完成视觉质量、语义质量、Batch 和复杂恢复。

MVP-1：

1. 固定真实单页视觉结果人工 `ACCEPTABLE`；
2. 支持对象无静默漏失、残字、结构损坏、跨实例和溢出；
3. excluded 原因可解释；
4. actual-glyph Validator 与人工观察一致；
5. 最小单页预览、修正、返工和导出可用；
6. 原图不覆盖，资源有界。

MVP-2：OCR/翻译与多页上下文质量达到冻结标准，修改后的 stale / 局部重跑正确。

MVP-3：Batch、性能、恢复、复杂 loop、Provider refusal、ZIP 和正式 Web 产品门禁通过。

---

## 18. AI / Codex 协作流程

### 18.1 设计阶段

设计阶段采用：

```text
GOAL.md
→ HARNESS.md
→ proposal agents
→ reviewer agent
→ synthesizer agent
→ harness validation
→ ADR
```

适用于：

1. Workflow State / Loop；
2. Provider Adapter；
3. ArtifactService；
4. QualityCheckService；
5. API；
6. Testing Design。

### 18.2 实现阶段

实现阶段采用：

```text
small goal
→ short plan
→ tests or validation first
→ implementation
→ local verification
→ diff review
→ commit
```

### 18.3 AI agent 约束

1. 不主动 push / pull / rebase；
2. 不做无关重构；
3. 不混入依赖升级；
4. 不提交 `.codex/`、`.claude/`、日志、缓存、IDE 文件；
5. 不硬编码 secret；
6. 不伪造测试结果；
7. 不跳过失败说明；
8. 不突破 SRS/HLD 边界；
9. 不让 Provider Adapter 访问数据库或登记 artifact；
10. 不让 UI 直接调用 OCR/LLM/清字/嵌字工具。

### 18.4 Commit 策略

设计文档阶段可以及时 commit，但必须：

1. 只 stage 目标文件；
2. commit message 准确；
3. 不 push；
4. 不混入临时文件；
5. 不混入实现代码。

实现阶段建议一个小功能或一个可验证切片一个 commit。

---

## 19. 测试策略

### 19.1 测试优先级

M0 架构测试继续作为回归。当前 MVP-1 优先测试：

1. provenance 完整性；
2. ContactBubbleCluster / BubbleInstance 拓扑；
3. Cleaning eligibility 假阴性；
4. pixel text mask、safe edit region 与结构安全；
5. renderer/validator region identity；
6. actual glyph 的丢失、重复、跨实例和溢出；
7. 字号、断行、留白、占用率和视觉中心；
8. 一次局部 loop 与 blocking QualityIssue。

不要先把测试重点放在 UI 样式、Batch 吞吐或复杂恢复；但必须保留最小用户入口验证，避免只得到表格而长期看不到完整单页结果。

### 19.2 FakeProvider 测试

FakeProvider 必须支持：

1. 成功输出；
2. 空输出；
3. invalid JSON；
4. provider_timeout；
5. provider_refusal；
6. partial translation output；
7. typeset_overflow；
8. cleaning_complex_background；
9. 调用计数。

### 19.3 样本回归

建立固定样本集：

```text
普通气泡
旁白框
竖排日文
低清扫描
复杂背景文字
拟声词
长译文溢出
Provider refusal 文本
```

每个样本记录：

1. 输入；
2. 期望现象；
3. 自动结果；
4. warning / blocking；
5. 是否进入导出；
6. 是否需要降级。

---

## 20. 风险登记与应对

| 风险 | 影响 | 提前验证方式 | 降级策略 |
| --- | --- | --- | --- |
| 支持范围文字静默漏失 | 单页结果不完整 | provenance stage accounting | unresolved 普通对白产生 blocker，不以 skip 掩盖。 |
| 接触气泡错误合并 | 清字/排版跨实例、中心错误 | BubbleInstance topology harness | cluster 分解 N 个 instance；证据不足 abstain/block。 |
| Cleaning eligibility 假阴性 | 普通气泡残留原文且无 Typesetting 输入 | 保存风险原因、规则、特征值 | 重评局部 eligibility，不批量把 E2/E3 升级。 |
| OCR 质量不稳定 | 翻译错误 | OCR Spike + OCRCheck | fallback OCR、手动输入、needs_review。 |
| Page 级翻译 JSON 不稳定 | 翻译结果无法落库 | Translation JSON Spike | 收紧 schema、重试、manual fallback。 |
| 术语不一致 | 阅读体验差 | Glossary Spike | 术语检查、warning、用户修正。 |
| Provider refusal | 无法自动翻译部分内容 | FakeProvider + real provider test | fallback、manual、warning/block。 |
| 清字毁图或残字 | 图像质量下降 | actual mask + visual review | 修正 mask/safe region；支持范围内未解决则 block。 |
| 嵌字溢出或跨气泡 | 可读性下降 | BubbleInstance mask + actual glyph validator | 重排一次；仍失败则 block，不使用 parent region 假通过。 |
| 局部算法研究失控 | 长期没有产品结果 | bounded Goal + visible page gate | 一轮实现加一轮修正后停止或回主线。 |
| crash recovery 复杂 | 用户失去进度 | FakeProvider crash test | 以 attempt、artifact、active pointer 恢复。 |
| artifact 文件漂移 | 预览/导出失败 | Artifact lifecycle test | missing 状态、可重建则重建。 |
| SQLite migration 风险 | 项目数据损坏 | Migration design + backup | per-project migration、schema_migrations。 |
| 一个人开发范围失控 | 当前 MVP 延期 | 分阶段门禁与 bounded Goal | 后续里程碑不提前侵入，Spike 到期必须回主线。 |

---

## 21. 交付定义

### 21.1 开发交付

每个开发任务完成时应交付：

1. 修改文件列表；
2. 实现说明；
3. 测试或验证结果；
4. 已知风险；
5. 后续事项；
6. git diff 可审查。

### 21.2 MVP 交付

MVP-1 交付必须满足：

1. 本地可启动；
2. 可创建 Project；
3. 可选择或上传单张图片；
4. 可执行单页视觉流程；
5. 可查看完整结果、provenance 和质量报告；
6. 可修改 OCR/译文；
7. 可局部返工；
8. 可导出单张结果图；
9. 支持范围内结果通过视觉 Gate；
10. 不覆盖原图；
11. unsupported exclusion 与 blocking 语义正确；
12. 无 OOM、无限循环和不可复现输出。

MVP-1 不要求 Batch、ZIP、复杂中断恢复或 Provider fallback 产品化。这些属于 MVP-3。

### 21.3 个人稳定版交付

个人稳定版应额外满足：

1. 配置路径清楚；
2. API key 配置清楚；
3. workspace 可备份；
4. 日志和 debug artifact 可清理；
5. 样本回归稳定；
6. 常见错误有用户提示；
7. 迁移策略可执行；
8. 有基础使用说明。
