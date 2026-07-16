# 漫画翻译与基础嵌字自动化工作流应用
# 软件开发过程规划 PROJECT-PLAN v0.1

版本：v0.1  
状态：规划初稿 / 可作为后续详细设计与 MVP 推进基线  
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
MVP-0 FakeProvider 单 Page 后端 Slice 01–07 已实现并通过关闭审查（`PASS_WITH_DEFERRED_RISKS`）。
当前尚未形成用户可操作的单 Page 产品闭环：API/UI、真实 Provider、正式导出和端到端可见结果仍待后续阶段验证。
Cleaning 及真实工具 Spike 的结论应以各自最新 final report 为准；它们不自动等同于产品能力授权。
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
4. P1/P2 功能过早侵入 MVP；
5. 一个人开发时范围失控。

因此，本项目需要阶段门禁和设计基线。

### 3.4 过程模型原则

本项目过程原则如下：

1. 用需求和架构文档控制方向；
2. 用 Spike 尽早验证工具可用性；
3. 用 FakeProvider 先验证 workflow、artifact、recovery 和 export gate；
4. 用单 Page 垂直切片先跑通真实闭环；
5. 用增量方式扩展到 Batch、恢复、review 和导出；
6. 每个阶段都有明确退出标准；
7. 每个实现增量都必须可运行、可验证、可回滚；
8. 不让 P1/P2 功能阻塞 P0 MVP。

---

## 4. 项目阶段总览

| 阶段 | 名称 | 核心目标 | 当前状态 |
| --- | --- | --- | --- |
| Phase 0 | 项目治理与文档基线 | 建立 AGENTS、文档结构、ADR、协作规则 | 基本完成，后续维护 |
| Phase 1 | 需求与架构基线 | SRS 和 HLD 定版，形成实现方向 | 已完成 |
| Phase 2 | 核心详细设计 | 数据模型、状态机、Provider、Artifact、Quality、API 等详细设计 | MVP-0 前置设计已完成；API/UI/Export 详细设计后置 |
| Phase 3 | 架构验证与工具 Spike | 用 FakeProvider 和真实工具验证高风险点 | FakeProvider 后端闭环已完成；真实工具 Spike 仍有能力边界待裁决 |
| Phase 4 | MVP-0 单 Page 后端垂直切片 | CLI / 后端方式跑通一页端到端 | Slice 01–07 已完成并审查关闭；尚未接入 API/UI、真实 Provider 或正式导出 |
| Phase 5 | MVP-1 单 Page Web 闭环 | 本地 Web UI 支持单页上传、处理、预览、返工、导出 | 待启动 |
| Phase 6 | MVP-2 Batch / Recovery / Review / Export | 多页批次、中断恢复、局部返工、ZIP 导出 | 待启动 |
| Phase 7 | 稳定化测试与质量收敛 | 样本回归、错误提示、日志清理、性能修正 | 待启动 |
| Phase 8 | 本地交付与桌面化准备 | 启动器、配置向导、个人稳定版交付 | 待启动 |
| Phase 9 | P1/P2 演化 | 英文、竖排、LaMa、本地模型、复杂排版等增强 | 后续 |

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
docs/design/
docs/research/
docs/adr/
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
4. P0/P1/P2/P3 范围明确；
5. MVP 第一阶段验收标准明确。

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
| 6 | API 设计 | `docs/design/api/` | MVP-1 前需要。 |
| 7 | UI Flow 设计 | `docs/design/ui/` | MVP-1 前需要。 |
| 8 | Export 设计 | `docs/design/export/` | 实际导出图片、ZIP、manifest、ExportRecord 行为后置。 |
| 9 | 真实工具 Spike | `docs/research/` 或后续 spike 目录 | Detection/OCR、Translation JSON、Cleaning、Typesetting 真实工具验证。 |

### 7.4 退出标准

Phase 2 不要求所有详细设计一次性完成，但进入 MVP-0 实现前至少应完成：

1. Workflow State / Workflow Loop 详细设计；
2. Provider Adapter 接口设计；
3. ArtifactService 详细设计；
4. QualityCheckService 详细设计；
5. Repository / persistence 最小设计；
6. MVP-0 实现计划。

---

## 8. Phase 3：架构验证与工具 Spike

### 8.1 目标

尽早验证最高风险的架构机制和外部工具可用性。

### 8.2 总体策略

先用 FakeProvider 验证架构机制，再接真实工具做 Spike。

推荐顺序：

```text
FakeProvider 单 Page 垂直切片
→ Artifact 生命周期验证
→ Workflow retry / fallback / warning / block 验证
→ Crash recovery 验证
→ Provider refusal 验证
→ Export gate 验证
→ 真实工具 Spike
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

1. FakeProvider 架构验证通过；
2. 至少 Detection/OCR、Page Translation JSON、Cleaning、Typesetting 四个 Spike 有结果；
3. 每个 Spike 有失败模式和降级策略；
4. 不可行需求已反馈到 SRS/HLD 或 backlog；
5. 可以进入 MVP-0 后端垂直切片。

---

## 9. Phase 4：MVP-0 单 Page 后端垂直切片

### 9.1 目标

在没有完整 UI 的情况下，跑通单 Project / 单 Batch / 单 Page 后端端到端闭环。

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
7. P1/P2 能力。

### 9.4 退出标准

一个命令或脚本可以完成：

```text
create project
→ import one page
→ run one-page workflow
→ output typeset image
→ create quality report
→ export
```

且满足：

1. 原图不覆盖；
2. 失败可解释；
3. attempt 和 decision 可追踪；
4. 重跑时可复用已完成结果；
5. export gate 可工作。

---

## 10. Phase 5：MVP-1 单 Page Web 闭环

### 10.1 目标

让用户通过本地 Web UI 完成单页完整流程。

### 10.2 范围

包含：

1. Project 列表；
2. 创建 Project；
3. 上传 1 张图片；
4. 选择 ProcessingProfile；
5. 启动一键处理；
6. 处理进度展示；
7. 结果预览；
8. 质量报告摘要；
9. 修改 OCR；
10. 修改译文；
11. 单块重翻；
12. 单块重嵌字；
13. 导出单页。

### 10.3 退出标准

用户不通过命令行即可完成：

```text
创建 Project
→ 上传一页
→ 一键处理
→ 查看结果
→ 修改译文
→ 重新嵌字
→ 导出图片
```

---

## 11. Phase 6：MVP-2 Batch / Recovery / Review / Export

### 11.1 目标

从单页能力扩展到批次能力，并强化恢复、局部返工和导出。

### 11.2 范围

包含：

1. 多 Page 上传；
2. 页面顺序；
3. Batch 处理；
4. 暂停；
5. 取消；
6. 中断恢复；
7. 单页失败隔离；
8. 单块失败隔离；
9. 单页重试；
10. 单块重试；
11. 跳过 TextBlock；
12. Warning export；
13. Blocking export gate；
14. ZIP 导出。

### 11.3 退出标准

1. Batch 中某一页失败不影响其他页；
2. TextBlock 失败不导致整页已完成结果丢失；
3. 进程中断后能恢复；
4. open blocking QualityIssue 阻止正常导出；
5. warning export 由 ProcessingProfileSnapshot 决定；
6. ZIP 导出顺序正确。

---

## 12. Phase 7：稳定化测试与质量收敛

### 12.1 目标

将 MVP 从“能跑”提升到“自己日常可用”。

### 12.2 测试层次

| 层次 | 内容 |
| --- | --- |
| 单元测试 | hash、artifact path、active pointer、stale propagation、export gate。 |
| 集成测试 | FakeProvider workflow、Repository、ArtifactService、WorkflowLoopEngine。 |
| 样本回归 | 固定漫画样本跑检测、OCR、翻译、清字、嵌字。 |
| E2E 测试 | Project → Batch → Page → Process → Review → Export。 |
| 手工验收 | 本地真实使用流程。 |

### 12.3 重点测试场景

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

### 12.4 退出标准

1. P0 E2E 流程稳定；
2. 主要 failure path 有测试；
3. 主要错误有用户可理解提示；
4. debug artifact 不泄漏 secret；
5. 样本回归有记录；
6. 已知问题进入 backlog。

---

## 13. Phase 8：本地交付与桌面化准备

### 13.1 目标

准备个人可用版本和后续桌面化。

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

## 14. Phase 9：P1/P2 演化

P1/P2 不阻塞 MVP。

候选演化方向：

1. 英语到中文；
2. 竖排中文嵌字；
3. LaMa 清字增强；
4. 本地翻译模型自动 fallback；
5. 多 Page 上下文翻译；
6. 自动术语候选；
7. 更复杂排版；
8. 气泡形状感知；
9. 简单阅读器；
10. 桌面应用壳。

P1/P2 必须遵守：

1. 不破坏 P0 数据模型；
2. 不破坏 Provider Adapter 边界；
3. 不绕过 WorkflowLoopEngine；
4. 不绕过 ArtifactService；
5. 不改变资源边界和合规边界。

---

## 15. 版本路线图

| 版本 | 名称 | 范围 |
| --- | --- | --- |
| v0.0 | 工具 Spike | 检测/OCR、翻译 JSON、清字、嵌字、mini workflow。 |
| v0.1 | 后端单 Page 垂直切片 | CLI / 脚本跑通单页，FakeProvider + 最小真实 Provider。 |
| v0.2 | 单 Page Web MVP | 本地 Web UI 上传一页、一键处理、预览、返工、导出。 |
| v0.3 | Batch MVP | 多页上传、Batch 进度、暂停/取消、ZIP 导出。 |
| v0.4 | Recovery / Quality / Export Gate | crash recovery、QualityIssue、warning/blocking export、provider refusal。 |
| v0.5 | 个人可用版 | 设置页、错误提示、样本回归、日志和 artifact 清理。 |
| v1.0 | 本地稳定版 | 本地启动器、数据备份、稳定 migration、使用说明、桌面化准备。 |

---

## 16. 详细设计路线图

| 设计项 | 状态 | 是否阻塞 MVP-0 | 备注 |
| --- | --- | --- | --- |
| Data Model | 已完成 v0.1 | 否 | 已可作为后续输入。 |
| Workflow State / Loop | 已完成 v0.1 | 否 | 状态词汇、阶段转移、决策矩阵、恢复和 stale 传播已定义。 |
| QualityCheckService / IssueType | MVP-0 最小契约已完成 | 否 | Execution Contract 覆盖 P0 issue taxonomy、severity、blocking、root_stage。 |
| Provider Adapter Interface | MVP-0 最小契约已完成 | 否 | Execution Contract 覆盖 ProviderResult、错误/refusal、FakeProvider modes。 |
| ArtifactService | MVP-0 最小契约已完成 | 否 | Execution Contract 覆盖 official artifact lifecycle、storage_state、temp promotion、missing 检测。 |
| ProcessingProfile | Snapshot 语义已覆盖 | 否 | Data Model / Workflow State / Persistence 覆盖 MVP-0 所需 snapshot 和 retry budget 输入；完整 UI/config 后置。 |
| Repository / ORM / Migration | Persistence Readiness 已完成 v0.1 | 否 | Repository/UoW/migration 最小设计已可支持 FakeProvider slice。 |
| MVP-0 实施计划 | 已完成 | 否 | 下一步为 Slice 01：Foundation and Project Store。 |
| API | 待做 | 阶段性 | MVP-1 前需要。 |
| UI Flow | 待做 | 阶段性 | MVP-1 前需要。 |
| Export Design | 待做 | 阶段性 | 实际 ExportRecord、ZIP、manifest 后置到 export milestone。 |

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

### 17.3 实现门禁

实现增量完成必须满足：

1. 有可运行入口；
2. 有最小测试或替代验证；
3. 有错误路径验证；
4. 没有误改无关文件；
5. Git diff 可审查；
6. 已知风险已记录。

### 17.4 MVP 门禁

MVP 完成必须满足：

1. P0 验收标准通过；
2. 单 Page Web 闭环可用；
3. Batch 基础流程可用；
4. 中断恢复可验证；
5. export gate 可验证；
6. 原图不覆盖；
7. Provider refusal 可解释；
8. warning 不默认打断一键处理；
9. blocking 阻止正常导出。

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

优先测试：

1. WorkflowLoopEngine；
2. ArtifactService；
3. QualityCheckService；
4. Repository；
5. Provider Adapter contract；
6. Export gate；
7. Crash recovery。

不要先把测试重点放在 UI 样式。

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
| 文本检测漏检/误检 | OCR、清字、嵌字全链路受影响 | Detection + OCR Spike | 允许删除误检、跳过复杂区域、P1 手动调整。 |
| OCR 质量不稳定 | 翻译错误 | OCR Spike + OCRCheck | fallback OCR、手动输入、needs_review。 |
| Page 级翻译 JSON 不稳定 | 翻译结果无法落库 | Translation JSON Spike | 收紧 schema、重试、manual fallback。 |
| 术语不一致 | 阅读体验差 | Glossary Spike | 术语检查、warning、用户修正。 |
| Provider refusal | 无法自动翻译部分内容 | FakeProvider + real provider test | fallback、manual、warning/block。 |
| 清字毁图 | 图像质量下降 | Cleaning Spike | 复杂背景默认 skip。 |
| 嵌字溢出 | 可读性下降 | Typesetting Spike | 缩字号、缩短译文、warning。 |
| crash recovery 复杂 | 用户失去进度 | FakeProvider crash test | 以 attempt、artifact、active pointer 恢复。 |
| artifact 文件漂移 | 预览/导出失败 | Artifact lifecycle test | missing 状态、可重建则重建。 |
| SQLite migration 风险 | 项目数据损坏 | Migration design + backup | per-project migration、schema_migrations。 |
| 一个人开发范围失控 | MVP 延期 | 阶段门禁、P0/P1/P2 | P1/P2 不进入 MVP。 |

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

MVP 交付必须满足：

1. 本地可启动；
2. 可创建 Project；
3. 可上传图片；
4. 可一键处理；
5. 可查看预览和质量报告；
6. 可修改 OCR/译文；
7. 可局部返工；
8. 可导出；
9. 可中断恢复；
10. 不覆盖原图；
11. warning/blocking 语义正确。

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
