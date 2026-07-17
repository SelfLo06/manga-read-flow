# 漫画翻译与基础嵌字自动化工作流应用

# 软件需求规格说明书 SRS v1.0

版本：v1.0
日期：2026-07-06（2026-07-17 MVP 路线重排修订）
状态：正式需求基线 / 当前 MVP 路线已更新
基线来源：SRS v0.9、工具可行性深度调研报告、SRS v1.0 修订建议文档

---

## 1. 引言

### 1.1 编写目的

本文档用于定义“漫画翻译与基础嵌字自动化工作流应用”的正式软件需求规格，明确系统目标、用户范围、功能性需求、非功能性需求、数据需求、状态设计、外部依赖、MVP 范围、验收标准与风险约束。

本文档作为后续概要设计、详细设计、原型开发、MVP 实现和测试验收的需求基线。

### 1.2 项目背景

大量漫画资源仅存在原语言版本。普通读者在不具备外语阅读能力、修图能力和汉化经验的情况下，难以直接阅读这些内容。

传统汉化流程通常需要翻译、校对、修图、清字、嵌字、排版等多个步骤，对普通读者门槛较高。普通读者通常并不追求专业汉化组级别的发布质量，而是更关心能否快速理解漫画剧情、人物对话和主要信息。

随着 OCR、文本检测、图像修复、大语言模型翻译和自动排版技术的发展，面向普通读者的自动化漫画翻译与基础嵌字工作流具备可行性。

本项目旨在将这些能力整合为一个低门槛、可恢复、可校对、可局部返工的个人阅读辅助工具。

### 1.3 产品目标

本系统旨在构建一个面向普通漫画读者的漫画翻译与基础嵌字自动化工作流应用。

系统以 Project 为单位管理不同漫画作品。用户可以在 Project 内上传漫画图片批次，系统自动生成普通文本区域候选、执行 OCR、生成候选译文、进行翻译质检、清除普通文字区域、嵌入中文译文，并允许用户校对、跳过、重试和导出。

系统第一优先级支持日语到简体中文。英语到简体中文作为后续扩展，不纳入 MVP-1。

系统不以专业汉化发布为目标，而是优先保证普通读者能够较顺畅地理解漫画正文内容。

### 1.4 产品边界

系统提供：

* Project 管理；
* Batch 图片批次管理；
* 普通漫画文本区域候选检测；
* 日语 OCR；
* 大模型翻译与翻译修正 loop；
* Project 内术语表；
* 普通气泡与旁白框基础清字；
* 基础中文横排嵌字；
* 人工校对与局部返工；
* 中断恢复；
* 图片与 ZIP 导出。

系统不提供：

* 漫画资源搜索；
* 漫画资源抓取；
* 漫画资源下载；
* 漫画资源分发；
* 公开发布平台；
* 专业汉化组协作流程；
* 发布级精修排版；
* 复杂拟声词重绘；
* 花体字和艺术字重绘；
* 复杂背景文字精修；
* 完整漫画阅读器。

### 1.5 术语定义

| 术语        | 定义                                      |
| --------- | --------------------------------------- |
| 生肉        | 未经过中文翻译和汉化处理的原语言漫画资源                    |
| 熟肉        | 已经过中文翻译和嵌字处理的漫画资源                       |
| Project   | 系统中表示一部漫画或一个独立漫画翻译任务集合的业务单位             |
| Batch     | Project 内一次上传和处理的图片集合，可对应一话漫画、一个章节或一组图片 |
| Page      | Batch 中的单张漫画图片                          |
| TextBlock | 页面中的一个文本区域，例如对话框文字、旁白框文字                |
| OCR       | Optical Character Recognition，光学字符识别    |
| LLM       | Large Language Model，大语言模型              |
| 清字        | 从原漫画图片中去除原文文字的过程                        |
| 嵌字        | 将中文译文重新排入漫画图片中的过程                       |
| 术语表       | Project 内维护的人名、地名、技能名、专有名词等固定译法集合       |
| 翻译 loop   | 候选译文生成、术语检查、质量检查、必要时重译、人工校对、译文锁定的循环流程   |
| 中断恢复      | 系统在暂停、失败或异常退出后，从已保存状态继续执行的能力            |
| Artifact  | 系统处理过程中产生的中间文件或结果文件                     |
| Provider  | OCR、翻译、清字、嵌字等能力的具体工具或服务提供方              |
| MVP       | Minimum Viable Product，最小可用产品           |
| M0 Architecture Proof | 已完成的 FakeProvider 架构机制验证基线，不代表产品质量或用户可用 MVP |
| ContactBubbleCluster | 两个或更多相邻、接触或串联气泡形成的候选簇；自身不是最终排版容器 |
| BubbleInstance | 视觉上独立的单个气泡或旁白框实例，拥有独立区域、文字归属、清字与排版约束 |
| TextSegment | 一个可独立追踪的原文/译文段落；一个 BubbleInstance 可包含一个或多个 TextSegment |
| LayoutSlot | BubbleInstance 内部用于安排一个或多个 TextSegment 的排版位置，不替代 BubbleInstance |

---

## 2. 总体描述

### 2.1 产品定位

本系统是一个面向普通漫画读者的个人阅读辅助工具。

系统重点解决的问题是：

用户拥有一批原语言漫画图片，但无法直接阅读。系统帮助用户将这些图片转换为基础中文可读版本，并允许用户对识别、翻译、清字和嵌字结果进行必要修正。

系统不是专业汉化组生产工具，不承诺发布级质量。

### 2.2 目标用户

#### 2.2.1 核心用户：普通漫画读者

核心用户具备以下特征：

* 不具备稳定的日语或英语漫画阅读能力；
* 不具备专业修图和嵌字能力；
* 对发布级汉化质量没有强需求；
* 更关心能否快速看懂剧情和对话；
* 能接受复杂文字区域被跳过；
* 希望一键得到基础可读结果；
* 希望结果不满意时可以做简单修改。

#### 2.2.2 次要用户：个人汉化爱好者

次要用户可能希望基于自动处理结果进行简单校对和调整，包括修改 OCR、修改译文、调整文本块、重新翻译、重新排版等。

系统暂不面向专业汉化组，不提供多人协作、审校流程、精修排版和发布工作流。

### 2.3 核心用户痛点

普通读者的主要痛点包括：

* 想看原语言漫画，但没有足够外语能力；
* 逐张截图翻译效率低；
* OCR、翻译、清字、嵌字工具分散；
* 人名、术语、技能名容易翻译不一致；
* 一章漫画处理耗时较长，中断后如果从头开始体验很差；
* 专业汉化流程门槛过高；
* 普通读者主要需要可读版本，而不是精修成品。

### 2.4 主流程

系统主流程如下：

```text
创建 Project
→ 创建 Batch
→ 上传漫画图片
→ 选择源语言
→ 启动自动处理
→ 文本区域候选检测
→ OCR 识别
→ 翻译候选生成
→ 翻译质量检查
→ 必要时进入翻译修正 loop
→ 清字
→ 嵌字
→ 保存中间结果
→ 用户查看与校对
→ 局部返工
→ 导出结果
```

### 2.5 翻译阶段原则

翻译结果不得默认视为最终结果。

系统应将大模型输出视为候选译文，并支持以下流程：

```text
OCR 文本
→ 候选译文生成
→ 术语表一致性检查
→ 译文格式检查
→ 译文自然度与长度检查
→ 必要时自动重译或标记 needs_review
→ 用户校对
→ 译文锁定
→ 进入嵌字
```

系统应避免将未经检查的候选译文直接嵌入最终结果。

---

## 3. 设计约束与假设

### 3.1 设计约束

系统存在以下设计约束：

* MVP-1 第一优先支持日语到简体中文页面中的普通对白气泡、普通旁白框和清晰印刷体文字；
* MVP-1 采用“支持范围窄、范围内质量高”，不得以“非发布级”作为普通支持对象低质量、静默漏失或明显不可读的豁免；
* 复杂拟声词、花体字、艺术字、复杂背景文字默认跳过；
* MVP-1 可使用真实 OCR/翻译初稿，并允许通过最小 review 入口修正或冻结可信文字输入，以独立验证后半段视觉闭环；
* 开发期人工标注、校准和 review 用于验证系统，不得默认成为长期产品运行的必经流程；
* 系统依赖外部 OCR、翻译、清字和嵌字工具；
* 外部工具可能失败、超时、拒绝处理或输出低质量结果；
* 系统必须支持状态持久化、局部重试和中断恢复；
* 系统不得提供漫画资源搜索、抓取、下载、分发或发布功能；
* 系统不得绕过第三方 API 或模型服务商的安全策略；
* 系统应支持中低端 GPU 加速，但不应强制要求高端 GPU。

### 3.2 当前产品里程碑约束

当前路线按以下顺序推进：

```text
M0      架构机制验证（已完成）
MVP-1   高质量单页视觉闭环
MVP-2   OCR 与翻译语义质量闭环
MVP-3   规模化、性能与复杂 Workflow
```

该顺序不改变 Provider Adapter、WorkflowLoopEngine、QualityCheckService、ArtifactService、Repository / DAO、active pointer、原图不可覆盖和 export gate 等架构基线。

长期产品目标仍是一键、低人工并最终接近零人工。MVP-1 允许为隔离视觉链路而使用可信文字输入，不得据此宣称原始页面到最终页面已经全自动完成。

### 3.3 设备约束

系统应支持以下运行层级：

| 配置       | 支持能力                            |
| -------- | ------------------------------- |
| CPU-only | 可运行基础流程，但 OCR、图像处理和本地模型较慢       |
| 中低端 GPU  | 推荐配置，可加速 OCR、文本检测、LaMa、本地轻量翻译模型 |
| 8GB 显存   | 可尝试 7B 量化本地翻译模型                 |
| 12GB+ 显存 | 可尝试更大本地模型或更稳定图像修复               |
| 高端 GPU   | 不作为任何当前 MVP 的默认要求                |

系统应在 GPU 不可用时提供降级路径。

### 3.4 内容与合规约束

系统只处理用户主动上传的图片。

用户上传内容可能包含成人内容或其他敏感内容。系统应将 NSFW 视为实际使用需求和外部依赖约束。对于合法成人自用内容，系统可以通过本地 OCR、清字、嵌字和本地翻译模型降低云端拒绝风险。

如果使用第三方云端 API，系统必须遵守其服务条款和内容策略。系统不得尝试绕过第三方服务限制。

涉及违法内容、未成年人性化内容、非自愿私密内容、剥削内容或其他明显不可处理内容时，系统不应提供自动处理能力。

---

## 4. 外部工具与技术边界

### 4.1 当前候选工具路线

当前候选技术路线为：

```text
PaddleOCR detection / 漫画专用检测器候选
+ manga-ocr 日语识别
+ PaddleOCR 备用 OCR
+ 云端 LLM 翻译
+ 本地翻译模型 fallback 接口
+ 白底/浅色填充
+ OpenCV inpaint
+ Pillow 横排中文嵌字
+ SQLite + 文件系统
+ 本地 worker
```

### 4.2 工具可替换原则

OCR、文本检测、翻译、清字、嵌字模块均应通过 Provider Adapter 接入。

每个 Provider Adapter 应声明：

* provider 名称；
* 版本；
* 能力；
* 输入格式；
* 输出格式；
* 是否需要 GPU；
* 许可证；
* 是否可本地处理；
* 已知限制；
* 是否可能受 NSFW 或平台策略影响。

### 4.3 许可证约束

系统应记录外部工具及模型的许可证信息。

涉及 GPL、非商业许可证或限制性模型许可的工具，不应在未评估影响的情况下直接嵌入系统核心代码或未来商业化版本。

MVP 可参考相关开源项目架构，但具体集成方式需在设计阶段明确。

---

## 5. 功能性需求

## 5.1 Project 管理

### FR-PJ-001 创建 Project

系统应支持用户创建 Project。

每个 Project 表示一部漫画或一个独立漫画翻译任务集合。

### FR-PJ-002 查看 Project

系统应支持用户查看已有 Project 列表。

Project 列表应至少展示：

* Project 名称；
* 最近处理时间；
* Batch 数量；
* 当前处理状态摘要。

### FR-PJ-003 编辑 Project

系统应支持用户重命名 Project。

### FR-PJ-004 删除 Project

系统应支持用户删除 Project。

删除 Project 时，系统应提示用户该操作会删除 Project 下的图片、批次、术语表、中间结果和导出记录。

### FR-PJ-005 Project 数据隔离

不同 Project 之间的数据应相互隔离。

隔离数据包括：

* 图片；
* Batch；
* Page；
* TextBlock；
* OCR 结果；
* 翻译结果；
* 清字结果；
* 嵌字结果；
* 术语表；
* 处理状态；
* 导出结果。

### FR-PJ-006 Project 内共享上下文

同一 Project 内的 Batch 应共享该 Project 的术语表。

### FR-PJ-007 Project 工具配置

系统应允许 Project 保存默认处理配置。

配置至少包括：

* 源语言；
* 目标语言；
* 文本检测 Provider；
* OCR Provider；
* 翻译 Provider；
* 是否启用本地 fallback；
* 清字模式；
* 嵌字模式；
* 字体配置；
* 是否启用 NSFW 本地优先策略。

MVP-1 可以隐藏复杂配置，只保存内部默认值；完整配置体验后移到 MVP-3。

---

## 5.2 Batch 管理

### FR-BT-001 创建 Batch

用户应能在 Project 内创建 Batch。

一个 Batch 表示一次上传和处理的漫画图片集合。

### FR-BT-002 上传图片

用户应能向 Batch 上传一张或多张漫画图片。

系统应支持：

* PNG；
* JPG；
* JPEG；
* WebP。

### FR-BT-003 页面顺序

系统应优先根据上传顺序和文件名自然排序保留 Page 顺序。

若用户发现顺序错误，应允许用户在处理前调整页面顺序。

已处理 Batch 若调整顺序，不应导致 OCR、翻译、清字、嵌字结果丢失，但可能需要重新计算翻译上下文。

### FR-BT-004 保留原图

系统应保存用户上传的原始图片。

后续 OCR、清字、嵌字和导出不得覆盖原始图片。

### FR-BT-005 删除 Batch

用户应能删除 Batch。

删除 Batch 时，系统应提示用户该操作会删除该 Batch 下的页面、中间结果和导出结果。

### FR-BT-006 查看 Batch 状态

用户应能查看 Batch 的整体处理状态。

状态应反映页面处理进度、失败数量、跳过数量和是否已完成。

### FR-BT-007 批次处理策略

系统应支持 Batch 级处理策略。

MVP-3 至少支持：

* 全流程自动处理；
* 仅检测 + OCR；
* 仅翻译；
* 仅清字 + 嵌字；
* 从失败处继续。

---

## 5.3 Page 管理

### FR-PG-001 Page 创建

系统应为 Batch 中的每张图片创建 Page 记录。

### FR-PG-002 Page 状态查看

用户应能查看每个 Page 的处理状态。

### FR-PG-003 Page 预览

用户应能查看 Page 的以下内容：

* 原图；
* 文本区域候选；
* OCR 结果；
* 候选译文；
* 翻译检查结果；
* 清字结果；
* 嵌字结果。

MVP 不要求提供完整漫画阅读器功能，只要求满足处理预览和校对需要。

### FR-PG-004 Page 删除

用户应能删除 Batch 中的单张 Page。

### FR-PG-005 Page 重新处理

用户应能对单张 Page 重新执行部分或全部处理流程。

### FR-PG-006 Page 处理配置继承

Page 应继承所属 Batch 和 Project 的默认处理配置。

后续可支持 Page 级覆盖配置，例如跳过清字、只重翻译、只重排。

### FR-PG-007 Page 质量标记

系统应为 Page 记录质量标记。

质量标记包括：

* normal；
* needs_review；
* partial_failed；
* has_skipped_blocks；
* low_ocr_confidence；
* translation_needs_review；
* typeset_overflow；
* nsfw_provider_refused；
* manual_edited。

---

## 5.4 文本区域检测

### FR-DET-001 文本区域候选检测

系统应自动生成 Page 中普通文本区域的候选检测结果。

MVP-1 重点检测：

* 普通对话框；
* 旁白框；
* 清晰印刷体文字。

检测结果不保证覆盖所有复杂文字区域。低置信度或明确不支持的复杂区域应标记为待校对或跳过。

在 MVP-1 声明支持的普通对白气泡和旁白框范围内，不得静默丢弃已检测文字。系统必须追踪 detected、grouped、associated、cleaning eligible、translated、rendered 和 excluded 的数量及去向；未解决的普通对白缺失属于单页高质量验收 blocker。

### FR-DET-002 TextBlock 创建

系统应为检测到的每个候选文本区域创建 TextBlock 记录。

TextBlock 应至少包含：

* 所属 Project；
* 所属 Batch；
* 所属 Page；
* bbox；
* polygon；
* mask 路径；
* 源文本方向；
* 阅读顺序；
* 检测 Provider；
* 检测置信度；
* 检测质量标记；
* 是否手动调整；
* 跳过原因。

### FR-DET-003 文本方向记录

系统应记录文本方向。

文本方向至少包括：

* 横排；
* 竖排；
* 未确定。

### FR-DET-004 阅读顺序推断

系统应基于漫画阅读方向和 TextBlock 几何位置推断阅读顺序。

MVP-2 只要求提供可验证的启发式排序，不保证复杂分镜、跨栏对话、插入语和气泡嵌套场景完全正确。MVP-1 可使用冻结或人工修正后的 reading order 验证视觉闭环。

手动调整阅读顺序作为 MVP-2 review 能力。

### FR-DET-005 复杂区域跳过

对于复杂拟声词、花体字、艺术字、严重倾斜文字、复杂背景文字和难以识别文字，系统允许跳过处理。

被跳过区域应保留原图内容，不应导致整页处理失败。

### FR-DET-006 检测结果修正

MVP-1 最小 review 入口至少应能：

* 查看检测结果；
* 删除误检 TextBlock；
* 将 TextBlock 标记为跳过；
* 重新检测单页。

手动拖拽调整 TextBlock 坐标不作为 MVP-1 必需能力。

### FR-DET-007 气泡实例拓扑

系统应区分 ContactBubbleCluster 与 BubbleInstance。

对于相邻、接触或串联气泡，系统不得仅使用一个无内部拓扑的 parent container 作为最终 Cleaning 和 Typesetting 对象。一个 ContactBubbleCluster 必须允许包含任意数量的 BubbleInstance；每个 BubbleInstance 应拥有独立区域、文字归属、清字约束、排版约束和验证边界。

一个 BubbleInstance 可以包含一个或多个 TextSegment / LayoutSlot，但 LayoutSlot 不得替代 BubbleInstance。

证据不足时系统应保留不确定性并 block 或 abstain，不得强制合并、分割或清字。

---

## 5.5 OCR 识别

### FR-OCR-001 OCR 执行

系统应对 TextBlock 执行 OCR。

### FR-OCR-002 OCR 结果保存

系统应保存每个 TextBlock 的 OCR 结果。

OCR 结果应至少包含：

* OCR 文本；
* OCR 置信度，可为空；
* OCR Provider；
* 模型 ID；
* 模型版本；
* 输入裁剪图 artifact；
* 原始输出 artifact；
* 输入 hash；
* 配置 hash；
* OCR 质量标记；
* 是否被用户修改。

若 OCR 工具无法返回可靠置信度，系统允许置信度为空，但必须记录工具来源并生成质量标记。

### FR-OCR-003 OCR 结果查看

用户应能查看每个 TextBlock 的 OCR 结果。

### FR-OCR-004 OCR 结果修改

用户应能手动修改 OCR 结果。

修改后的 OCR 文本应作为后续翻译依据。

### FR-OCR-005 单块 OCR 重试

用户应能对单个 TextBlock 重新执行 OCR。

### FR-OCR-006 单页 OCR 重试

用户应能对单张 Page 重新执行 OCR。

### FR-OCR-007 OCR 失败隔离

单个 TextBlock OCR 失败不应导致整张 Page 失败。

单张 Page 部分 OCR 失败时，系统应保留已成功识别的 TextBlock 结果。

### FR-OCR-008 OCR fallback

系统应支持 OCR fallback。

推荐规则：

```text
主 OCR 失败或结果为空
→ 尝试备用 OCR
→ 仍失败则标记 ocr_failed
→ 允许用户手动输入 OCR 文本
```

### FR-OCR-009 OCR 输入裁剪记录

系统应保存 OCR 输入裁剪图或 artifact 记录，用于错误追踪和用户校对。

---

## 5.6 翻译与翻译 loop

### FR-TR-001 候选翻译生成

系统应调用翻译模块，将 OCR 文本翻译为简体中文候选译文。

翻译模块可以是云端 LLM API、本地开源模型或专用翻译 API。

MVP-2 默认采用云端 LLM API 以保证翻译质量，同时保留本地模型 fallback 接口。

### FR-TR-002 Project 术语表注入

翻译时系统应读取当前 Project 的术语表，并将固定译法作为翻译约束传入翻译模块。

### FR-TR-003 Page 级上下文

MVP-2 以单 Page 为基础翻译上下文粒度，并验证有限 multi-page context。

系统应将同一 Page 内 TextBlock 按阅读顺序组织为结构化输入，并注入 Project 术语表。

多 Page 上下文属于 MVP-2，首先服务于语义一致性而非 Batch 吞吐。

### FR-TR-004 结构化输入输出

系统应使用结构化格式调用翻译模块。

输入至少包含：

```json
{
  "source_language": "ja",
  "target_language": "zh-Hans",
  "project_glossary": [],
  "page_context": [],
  "text_blocks": [
    {
      "text_block_id": "tb_xxx",
      "reading_order": 1,
      "source_text": "...",
      "source_direction": "vertical",
      "ocr_quality_flag": "normal"
    }
  ]
}
```

输出至少包含：

```json
{
  "translations": [
    {
      "text_block_id": "tb_xxx",
      "translation": "...",
      "used_terms": [],
      "confidence": "medium",
      "needs_review": false,
      "note": ""
    }
  ],
  "glossary_candidates": []
}
```

### FR-TR-005 翻译结果保存

系统应保存每个 TextBlock 的翻译结果。

翻译结果应至少包含：

* 源文本 hash；
* 译文；
* Provider；
* 模型 ID；
* prompt 模板版本；
* glossary_version；
* context_hash；
* generation_config_hash；
* used_terms；
* needs_review；
* error_code；
* 是否被用户修改。

### FR-TR-006 翻译质量检查

系统应对候选译文执行基础质量检查。

检查内容至少包括：

* 是否为空；
* 是否 JSON 格式错误；
* 是否遗漏 TextBlock；
* 是否明显未翻译；
* 是否违反术语表固定译法；
* 是否长度明显过长；
* 是否需要人工校对；
* 是否包含 Provider 拒绝或安全策略提示。

### FR-TR-007 翻译修正 loop

系统应支持有界翻译修正 loop。

流程如下：

```text
生成候选译文
→ 自动质量检查
→ 若通过，进入待校对或待嵌字
→ 若未通过，尝试自动重译
→ 若达到最大重试次数仍未通过，标记 needs_review
→ 用户手动修改或选择本地 fallback
→ 用户确认后锁定译文
```

系统不得无限自动重试。

自动重译次数应可配置；MVP-2 默认建议不超过 1-2 次，复杂 retry/fallback 编排后移 MVP-3。

### FR-TR-008 术语一致性检查

系统应检查候选译文是否遵守当前 Project 术语表。

若译文未遵守高优先级术语，应标记为 `term_mismatch`，并可进入翻译修正 loop。

### FR-TR-009 翻译长度检查

系统应根据 TextBlock 区域大小估算译文长度是否可能导致嵌字溢出。

若译文过长，系统应标记为 `translation_too_long` 或 `typeset_risk`，并允许用户修改或要求模型生成更短译文。

### FR-TR-010 翻译结果查看

用户应能查看每个 TextBlock 的源文本、候选译文、质量标记和失败原因。

### FR-TR-011 翻译结果修改

用户应能手动修改译文。

手动修改后的译文应被标记为 `manual_edited`。

### FR-TR-012 译文锁定

用户确认译文后，系统应允许将译文标记为 locked。

locked 译文默认不应被自动重译覆盖，除非用户明确要求。

### FR-TR-013 单块重新翻译

用户应能对单个 TextBlock 重新翻译。

### FR-TR-014 单页重新翻译

用户应能对单张 Page 重新翻译。

### FR-TR-015 Batch 重新翻译

用户应能对整个 Batch 重新翻译。

批量重新翻译前，系统应提示可能产生额外耗时和模型调用成本。

### FR-TR-016 翻译缓存

系统应缓存翻译结果。

缓存 key 至少包含：

* source_text_hash；
* context_hash；
* glossary_version；
* provider_name；
* model_id；
* prompt_template_version；
* generation_config_hash。

### FR-TR-017 Provider 策略拒绝处理

当云端翻译 Provider 因内容策略拒绝处理时，系统应记录明确错误码。

错误码包括：

* translation_provider_refused；
* translation_nsfw_policy_refused；
* translation_child_safety_refused；
* translation_timeout；
* translation_rate_limited；
* translation_quota_exceeded；
* translation_invalid_json；
* translation_low_quality。

系统不得尝试绕过第三方 Provider 的安全策略。

### FR-TR-018 本地翻译 fallback

当云端 Provider 不可用、拒绝处理或用户启用隐私/NSFW 本地优先模式时，系统应允许切换到本地翻译模型。

MVP-2 可以只实现接口和手动切换，自动 fallback 产品化后移 MVP-3。

### FR-TR-019 人工翻译 fallback

当自动翻译不可用或质量不可接受时，系统应允许用户手动输入译文。

手动输入译文可直接进入嵌字阶段。

---

## 5.7 Project 术语表

### FR-GL-001 独立术语表

每个 Project 应拥有独立术语表。

不同 Project 的术语表不得自动互相影响。

### FR-GL-002 术语字段

术语条目应至少包含：

* term_id；
* project_id；
* 原文；
* 译文；
* 类型；
* 读音；
* 别名；
* 是否大小写敏感；
* 优先级；
* 状态；
* 备注；
* 创建来源 TextBlock；
* 创建时间；
* 更新时间。

### FR-GL-003 术语类型

术语类型至少支持：

* 人名；
* 地名；
* 组织名；
* 技能名；
* 专有名词；
* 固定表达；
* 其他。

### FR-GL-004 新增术语

用户应能新增术语。

### FR-GL-005 编辑术语

用户应能编辑已有术语。

### FR-GL-006 删除术语

用户应能删除术语。

### FR-GL-007 从译文添加术语

用户修改译文后，系统应支持将词语或短语快速加入当前 Project 的术语表。

### FR-GL-008 术语表版本

系统应在每次术语变更后更新 Project 术语表版本号。

翻译结果应记录翻译时使用的 glossary_version。

### FR-GL-009 术语候选

系统可从 OCR 文本和翻译结果中生成术语候选，供用户确认。

该能力为 P1，不进入 P0。

---

## 5.8 清字与图像修复

### FR-CL-001 清字执行

系统应根据 TextBlock 区域位置和 mask 清除原文。

### FR-CL-002 清字范围

MVP 清字主要处理：

* 白底或浅色普通对话框；
* 旁白框；
* 背景相对简单的文字区域。

对于复杂背景、网点纹理、人物身体上文字、强透视文字、拟声词、花体字、艺术字，系统默认允许跳过。

### FR-CL-003 保留原图

清字过程不得覆盖原始图片。

### FR-CL-004 清字结果保存

系统应保存清字后的中间图片。

### FR-CL-005 清字结果查看

用户应能查看清字结果。

### FR-CL-006 单块重新清字

用户应能对单个 TextBlock 区域重新清字。

### FR-CL-007 单页重新清字

用户应能对单张 Page 重新清字。

### FR-CL-008 清字模式

系统应支持以下清字模式：

* bubble_fill：白底或纸色填充；
* opencv_inpaint：OpenCV 局部修复；
* skip：跳过清字；
* lama_inpaint：LaMa 修复，P1 或高级选项。

### FR-CL-009 mask 保存

系统应保存清字使用的 mask artifact。

mask 来源应可追踪：

* 来自文本检测；
* 来自 OCR 区域扩张；
* 来自用户手动框选；
* 来自后续编辑。

### FR-CL-010 复杂区域默认跳过

若 TextBlock 满足以下条件之一，系统可以默认跳过清字：

* 检测区域不在气泡或旁白框内；
* 背景颜色复杂；
* 区域内边缘密度高；
* 检测器判断为拟声词或装饰文字；
* mask 面积过大；
* 用户标记跳过。

每个自动跳过或降级区域必须保存风险原因、触发规则和关键特征值。普通白色对白气泡若仅因保守阈值被排除，必须作为潜在 eligibility 假阴性进入 QualityIssue；不得把 E2/E3 或其他内部风险标签本身当作充分解释。

### FR-CL-011 清字失败处理

清字失败时，系统应保留原图和已有中间结果，并允许用户重试、跳过或手动处理。

---

## 5.9 嵌字与排版

### FR-TY-001 嵌字执行

系统应将中文译文嵌入清字后的图片中。

### FR-TY-002 基础横排嵌字

MVP-1 必须支持高质量的基础中文横排嵌字。

系统应优先保证译文可读且不溢出。MVP-1 不追求发布级精修，但在声明支持的普通气泡和旁白框范围内，字号、断行、留白和视觉居中必须达到普通读者可直接阅读的质量，不得以“基础排版”为由接受明显拥挤、跨气泡或错误中心聚集。

### FR-TY-003 竖排文本处理

系统应记录原文本方向。

对于原竖排日文，MVP-1 默认允许使用基础中文横排嵌字。

基础竖排中文嵌字作为 Post-MVP 增强，不作为 MVP-1 成功必要条件。

### FR-TY-004 自动换行

系统应根据 TextBlock 区域宽度自动换行。

### FR-TY-005 字号自适应

系统应根据译文长度和文本区域大小自动调整字号。

### FR-TY-006 边界约束

嵌字结果不得超出其唯一归属 BubbleInstance 的 typesetting region。Renderer 和 Validator 必须引用同一 `region_id`、同一 mask hash 和实际写入的 glyph 像素；不得退回更宽松的 bbox 或 parent cluster region 后仍报告通过。

### FR-TY-007 排版溢出处理

当译文在最小字号下仍无法放入目标区域时，系统应：

* 标记 TextBlock 为 typeset_overflow；
* 保留自动排版尝试结果；
* 提示用户修改译文、调整区域或手动排版；
* 不导致整页失败。

### FR-TY-008 排版结果保存

系统应保存嵌字后的 Page 结果。

### FR-TY-009 排版结果查看

用户应能查看嵌字结果。

### FR-TY-010 单块重新排版

用户应能对单个 TextBlock 重新排版。

### FR-TY-011 单页重新排版

用户应能对单张 Page 重新排版。

### FR-TY-012 字体配置

系统应提供默认中文字体配置。

系统不得在开源仓库中随意分发未授权字体文件。

### FR-TY-013 手动调整

P1 阶段用户应能调整：

* 文本框位置；
* 字号；
* 换行；
* 排版方向；
* 字体样式。

### FR-TY-014 排版完整性与实例归属

系统必须验证：

* 每个 eligible TextSegment 恰好渲染一次；
* 每个 rendered TextSegment 唯一归属一个 BubbleInstance；
* 不跨 BubbleInstance；
* 不使用 ContactBubbleCluster 外轮廓代替 BubbleInstance 边界；
* 同一 BubbleInstance 内多个 TextSegment 保持顺序和段落边界；
* excluded TextSegment 有明确、可解释原因。

---

## 5.10 校对与返工

### FR-RV-001 校对界面

系统应提供校对界面，使用户能够查看：

* 原图；
* TextBlock 区域；
* OCR 原文；
* 候选译文；
* 翻译质量标记；
* 清字结果；
* 嵌字结果。

### FR-RV-002 修改 OCR

用户应能修改 OCR 文本。

### FR-RV-003 修改译文

用户应能修改翻译结果。

### FR-RV-004 跳过 TextBlock

用户应能将 TextBlock 标记为跳过。

用户也应能取消跳过，并重新执行对应步骤。

### FR-RV-005 局部返工

用户应能对局部内容重新处理。

粒度至少包括：

* 单个 TextBlock；
* 单张 Page。

### FR-RV-006 避免全量重跑

除非用户主动要求，系统不应因为局部修改而重新处理整个 Batch。

### FR-RV-007 修改后联动

当用户修改 OCR 文本后，系统应允许重新翻译相关 TextBlock。

当用户修改译文后，系统应允许重新排版相关 TextBlock。

### FR-RV-008 错误原因可见

校对界面应展示用户可理解的失败原因。

示例：

| 错误码                          | 用户提示                       |
| ---------------------------- | -------------------------- |
| ocr_no_text                  | 未能识别出文字，可手动输入或重试 OCR       |
| translation_provider_refused | 当前翻译服务拒绝处理该文本，可切换本地模型或手动翻译 |
| cleaning_complex_background  | 背景复杂，已跳过自动清字               |
| typeset_overflow             | 译文过长，无法在当前区域内排版            |

---

## 5.11 任务状态与中断恢复

### FR-TS-001 状态持久化

系统应持久化保存 Batch、Page 和 TextBlock 的处理状态。

### FR-TS-002 中间结果持久化

系统应保存关键中间结果，包括：

* 检测结果；
* OCR 结果；
* 翻译结果；
* 翻译检查结果；
* 清字结果；
* 嵌字结果。

### FR-TS-003 手动暂停

用户应能手动暂停正在处理的 Batch。

### FR-TS-004 被动中断恢复

系统应支持异常关闭、网络中断、外部 API 失败等情况下的恢复。

### FR-TS-005 继续处理

用户重新打开 Project 或 Batch 后，系统应显示上次处理进度，并允许用户从未完成步骤继续处理。

### FR-TS-006 单页失败隔离

单张 Page 失败不应导致整个 Batch 失败。

### FR-TS-007 单块失败隔离

单个 TextBlock 失败不应导致整张 Page 已完成结果丢失。

### FR-TS-008 避免重复调用

已完成且未被用户要求重做的步骤，不应重复调用 OCR、翻译、清字或嵌字工具。

### FR-TS-009 失败重试

系统应允许用户对失败的 Page 或 TextBlock 进行重试。

### FR-TS-010 幂等处理

每个处理步骤应以输入 hash、配置 hash、工具版本和输出 artifact 为边界，确保重复运行不会破坏已完成结果。

### FR-TS-011 工具运行日志

系统应记录每次外部工具调用。

字段至少包括：

* tool_run_id；
* tool_name；
* tool_version；
* model_id；
* input_artifact_id；
* output_artifact_id；
* config_hash；
* started_at；
* finished_at；
* status；
* error_code；
* error_message。

### FR-TS-012 任务取消

系统应允许用户取消正在处理的 Batch。

取消后已完成结果应保留，未完成任务应标记为 cancelled 或 paused。

---

## 5.12 导出

### FR-EX-001 单页导出

用户应能导出单张 Page 的处理结果。

### FR-EX-002 批次导出

用户应能导出整个 Batch 的处理结果。

### FR-EX-003 ZIP 导出

系统应支持将 Batch 结果导出为 ZIP 压缩包。

### FR-EX-004 页面顺序

导出结果应保持 Page 顺序。

### FR-EX-005 图片质量

导出图片应尽量保持原始分辨率和清晰度。

### FR-EX-006 可编辑数据保留

导出结果后，系统仍应保留 Project 内可编辑数据，方便用户继续修改。

### FR-EX-007 导出 manifest

ZIP 导出时应生成可选 manifest 文件，记录：

* Project 名称；
* Batch 名称；
* 导出时间；
* Page 顺序；
* 每页输出文件名；
* 是否存在跳过区域；
* 是否存在失败 TextBlock。

---

## 6. 非功能性需求

### 6.1 可用性

#### NFR-USE-001 一键处理

系统应提供一键处理入口，使普通读者不需要理解 OCR、模型参数、图像修复参数和排版参数。

#### NFR-USE-002 进度展示

系统应展示处理进度。

进度信息至少包括：

* 当前处理阶段；
* 当前处理页面；
* 已完成页面数量；
* 失败页面数量；
* 跳过区域数量；
* 是否暂停；
* 是否完成。

#### NFR-USE-003 错误提示

系统应在失败时给出用户可理解的错误提示。

#### NFR-USE-004 普通模式与高级模式

系统应默认提供普通模式。

普通模式只暴露：

* 创建 Project；
* 上传图片；
* 一键处理；
* 查看结果；
* 修改 OCR；
* 修改译文；
* 重试；
* 导出。

高级模式可暴露：

* OCR 工具选择；
* 翻译 Provider 选择；
* 清字模式；
* 本地模型 fallback；
* LaMa 清字；
* 排版参数。

### 6.2 可靠性

#### NFR-REL-001 中断恢复

系统应在任务中断后恢复到最近可继续处理的状态。

#### NFR-REL-002 局部失败隔离

系统应避免单个 Page 或 TextBlock 失败导致整个 Batch 报废。

#### NFR-REL-003 数据不丢失

系统应尽量避免因应用关闭、网络失败或外部工具失败导致已完成结果丢失。

#### NFR-REL-004 原图安全

系统不得覆盖或破坏用户上传的原始图片。

### 6.3 结果质量

#### NFR-QLT-001 可读性优先

系统输出结果应优先保证普通读者能够理解剧情和对话。MVP-1 的单页视觉结果必须在声明支持范围内达到“干净、舒适、可直接阅读”，而不只是完成技术写回。

#### NFR-QLT-002 术语一致性

系统应尽量保持同一 Project 内人名、地名、技能名、专有名词和称呼一致。

#### NFR-QLT-003 译文自然度

系统应尽量避免明显生硬直译、语义不通顺和 AI 模板化表达。

#### NFR-QLT-004 图像质量

系统应尽量避免降低原图分辨率和清晰度。

#### NFR-QLT-005 嵌字可读性

嵌字结果在声明支持范围内不得出现：

* 文字超出气泡；
* 字号过小；
* 换行严重不自然；
* 中文排版影响理解；
* 文字覆盖重要画面信息。

#### NFR-QLT-006 非发布级质量声明

系统不承诺生成发布级汉化成品。

非发布级不等于低质量豁免。MVP-1 目标是在窄支持范围内生成个人阅读可直接使用的高质量单页结果；复杂艺术效果、专业字体匹配和发布级精修仍不在范围内。

#### NFR-QLT-007 可跳过质量标准

复杂区域被正确跳过，不应被视为 MVP 失败。

跳过对象包括：

* 拟声词；
* 花体字；
* 艺术字；
* 复杂背景文字；
* OCR 无法可靠识别区域；
* 清字可能明显破坏画面区域。

普通对白气泡和普通旁白框不因内部风险分类而自动获得跳过豁免。自动系统无法可靠处理时，可以安全保留原图并继续其他区域，但必须记录 QualityIssue；未解决的支持范围对象会阻塞该页“高质量单页结果”验收。

#### NFR-QLT-008 开发期人工与产品运行期人工

开发期人工标注、盲审和 calibration 用于验证算法，不应默认转化为产品运行期必经步骤。长期运行期目标是最大限度减少人工参与并接近零人工；自动失败时允许局部跳过、保留原图、记录 QualityIssue 并继续处理其他区域。

### 6.4 性能

#### NFR-PERF-001 异步处理

系统应支持 Batch 异步处理，避免用户界面长时间阻塞。

#### NFR-PERF-002 进度反馈

处理耗时较长时，系统应持续提供进度反馈。

#### NFR-PERF-003 避免重复处理

系统应复用已保存中间结果，避免不必要的重复 OCR、翻译、清字和嵌字。

#### NFR-PERF-004 局部处理

系统应支持局部重新处理，降低等待时间和外部调用成本。

#### NFR-PERF-005 中低端 GPU 支持

系统应支持在中低端 GPU 上加速 OCR、文本检测、图像修复或本地翻译模型。

系统不应默认要求高端 NVIDIA GPU。

#### NFR-PERF-006 资源降级

如果 GPU 不可用、显存不足或模型加载失败，系统应允许降级到：

* CPU OCR；
* 跳过 LaMa；
* 使用云端翻译；
* 使用轻量模型；
* 手动处理失败块。

#### NFR-PERF-007 分阶段性能门禁

MVP-1 不以吞吐量作为验收门禁。单页顺序执行、模型初始化较慢和几十秒处理时间可以接受，但以下问题始终为 blocker：

* 无界内存增长；
* OOM；
* 无限循环；
* 单页无法结束；
* 输出不可复现；
* 算法依赖机器偶然状态。

批处理吞吐、模型常驻、缓存、并发和资源预算的产品级优化属于 MVP-3。

### 6.5 成本控制

#### NFR-COST-001 缓存翻译结果

系统应缓存翻译结果。

除非用户主动要求重新翻译，否则不应重复调用大模型处理相同文本和上下文。

#### NFR-COST-002 缓存 OCR 结果

系统应缓存 OCR 结果。

除非用户主动要求重新识别，否则不应重复 OCR 已完成的 TextBlock。

#### NFR-COST-003 局部重试

系统应支持单页或单块重试，避免局部错误造成整批次重跑。

#### NFR-COST-004 云端调用预算提示

如果使用云端 LLM API，系统应记录请求数量和估算 token 用量。

批量重翻译前应提示可能产生额外成本。

### 6.6 可维护性

#### NFR-MNT-001 模块解耦

系统应将以下模块解耦：

* Project 管理；
* Batch 管理；
* 图片管理；
* 文本检测；
* OCR；
* 翻译；
* 翻译 loop；
* 术语表；
* 清字；
* 嵌字；
* 校对；
* 导出；
* 任务调度。

#### NFR-MNT-002 Provider Adapter

OCR、检测、翻译、清字、嵌字均应通过统一 adapter 接口接入。

#### NFR-MNT-003 错误记录

系统应记录任务处理错误，方便定位失败原因。

#### NFR-MNT-004 状态可追踪

系统应能追踪 Batch、Page 和 TextBlock 的处理状态。

---

## 7. 数据需求

### 7.1 project

```text
project_id
name
created_at
updated_at
default_source_language
default_target_language
status
note
```

### 7.2 project_config

```text
project_config_id
project_id
source_language
target_language
detector_provider
ocr_provider
translation_provider
local_translation_enabled
cleaning_mode
typesetting_mode
font_config
nsfw_local_first
created_at
updated_at
```

### 7.3 batch

```text
batch_id
project_id
name
source_language
target_language
page_count
status
created_at
updated_at
last_processed_at
```

### 7.4 page

```text
page_id
project_id
batch_id
page_index
original_image_path
cleaned_image_path
typeset_image_path
export_image_path
status
quality_flags
error_code
error_message
created_at
updated_at
```

### 7.5 text_block

```text
text_block_id
project_id
batch_id
page_id
reading_order
skip_reason
is_skipped
is_manual_adjusted
created_at
updated_at
```

### 7.6 text_block_geometry

```text
text_block_id
bbox_x
bbox_y
bbox_width
bbox_height
polygon_json
mask_artifact_id
source_direction
reading_order
is_manual_adjusted
```

### 7.7 ocr_result

```text
ocr_result_id
text_block_id
source_text
ocr_confidence
ocr_quality_flag
provider
model_id
tool_version
input_artifact_id
raw_output_artifact_id
input_hash
config_hash
is_user_edited
created_at
updated_at
```

### 7.8 translation_result

```text
translation_result_id
text_block_id
source_text_hash
translation_text
provider
model_id
prompt_template_version
glossary_version
context_hash
generation_config_hash
used_terms_json
confidence
needs_review
quality_flags
error_code
is_user_edited
is_locked
created_at
updated_at
```

### 7.9 glossary_term

```text
term_id
project_id
source_text
target_text
term_type
reading
aliases
case_sensitive
priority
status
created_from_text_block_id
created_by_user
note
created_at
updated_at
```

### 7.10 glossary_version

```text
glossary_version_id
project_id
version_number
terms_hash
created_at
created_reason
```

### 7.11 processing_artifact

```text
artifact_id
project_id
batch_id
page_id
text_block_id
artifact_type
file_path
file_hash
source_step
tool_run_id
created_at
```

### 7.12 tool_run_log

```text
tool_run_id
project_id
batch_id
page_id
text_block_id
stage
tool_name
tool_version
model_id
input_hash
config_hash
status
error_code
error_message
started_at
finished_at
```

---

## 8. 状态设计

### 8.1 Batch 状态

```text
created
uploaded
queued
processing
paused
cancelled
reviewing
partially_failed
failed
completed
exported
```

### 8.2 Page 状态

```text
uploaded
detecting
detected
ocr_processing
ocr_done
translating
translation_checking
translation_done
cleaning
cleaned
typesetting
typeset_done
reviewing
partially_failed
failed
skipped
exported
```

### 8.3 TextBlock 阶段状态

TextBlock 不应只使用一个单一状态，而应保留分阶段状态：

```text
detection_status
ocr_status
translation_status
translation_check_status
cleaning_status
typesetting_status
review_status
```

每个阶段状态可取：

```text
pending
running
done
failed
skipped
user_edited
needs_review
locked
```

### 8.4 推荐错误码

```text
detect_no_text
detect_low_confidence
detect_complex_region
ocr_no_text
ocr_low_confidence
ocr_model_error
translation_timeout
translation_rate_limited
translation_quota_exceeded
translation_provider_refused
translation_nsfw_policy_refused
translation_child_safety_refused
translation_invalid_json
translation_low_quality
translation_term_mismatch
translation_too_long
cleaning_mask_missing
cleaning_complex_background
cleaning_model_error
typeset_overflow
typeset_font_missing
export_failed
user_skipped
```

---

## 9. 产品里程碑范围

### 9.1 M0 Architecture Proof（已完成）

历史名称保留为 `MVP-0 FakeProvider Backend`，在当前路线中统一解释为架构验证基线。

M0 已证明：

* WorkflowLoopEngine；
* Provider Adapter；
* ArtifactService；
* Repository / Unit of Work；
* QualityIssue 与 export gate；
* active pointer；
* recovery / idempotency 基础。

M0 没有证明真实 Provider、UI、正式导出、视觉质量或用户产品闭环。

### 9.2 MVP-1：高质量单页视觉闭环

核心目标：

```text
给定一张真实漫画页和可信 OCR/译文，
系统对声明支持的区域生成完整、干净、舒适、可直接阅读的中文结果。
```

必须覆盖：

* 普通对白气泡；
* 普通旁白框；
* 横排简体中文；
* Detection / Grouping / Association provenance；
* ContactBubbleCluster 与任意数量 BubbleInstance 的拓扑；
* Cleaning eligibility、pixel text mask 和 safe edit region；
* BubbleInstance-aware typesetting region；
* 清字、嵌字和实际 glyph validator；
* 一次有界局部修正或重跑；
* 最小单页预览、OCR/译文修正、局部返工和图片导出入口。

OCR 与 Translation 在 MVP-1 中使用真实初稿，但允许人工修正或冻结可信输入，以隔离验证视觉闭环。MVP-1 不宣称任意页面能够全自动得到正确 OCR 和译文。

复杂拟声词、艺术字、复杂背景文字和无可靠支持区域的自由文字可以明确排除；排除必须可解释且不得阻塞其他区域。

### 9.3 MVP-2：OCR 与翻译质量闭环

核心目标：

```text
从真实页面自动获得可信 OCR 和高质量译文，
并在连续页面中保持术语、人物称谓、代词和口吻一致。
```

重点包括：

* Detection/OCR 召回率与字符准确率；
* reading order；
* OCR 多候选、校验与局部修正；
* Page 级及多 Page 上下文翻译；
* Project 术语表、人物口吻和称谓一致；
* 翻译 reviewer 与局部重翻；
* OCR/译文修改后的 stale 传播和局部重排；
* OCR/翻译不确定性可见。

MVP-2 的多页首先服务于语义上下文，不以高吞吐 Batch 体验为验收目标。

### 9.4 MVP-3：规模化、性能与复杂 Workflow

核心目标：

```text
一章漫画能够稳定、高效、少人工地处理完成。
```

重点包括：

* 多 Page Batch、顺序和 ZIP 导出；
* 模型常驻、批处理、缓存、并发和资源预算；
* 暂停、取消、恢复和页面失败隔离；
* retry / fallback / Provider refusal；
* 复杂 QualityIssue loop 与 ProcessingProfile；
* 长任务进度和正式本地 Web 产品闭环；
* 性能基准、稳定 migration、备份与桌面化准备。

### 9.5 全阶段非目标

* 漫画资源搜索、下载、抓取、分发或发布；
* 专业汉化组协作与发布平台；
* 复杂拟声词、花体字和艺术字自动重绘；
* 发布级精修承诺；
* 云端多人任务队列和商业化云端批处理。

---

## 10. 需求优先级

### 10.1 P0：当前 MVP-1 必须实现

* 单页支持对象完整追踪，不静默漏失；
* BubbleInstance 拆分与 segment 唯一归属；
* Cleaning eligibility 可解释，普通气泡假阴性可发现；
* 可靠 text mask、safe edit region 和不损坏结构的清字；
* BubbleInstance-aware region、自然字号/断行/留白/居中；
* Renderer 与 Validator 使用同一 region 和实际 glyph mask；
* eligible / excluded / rendered 数量一致且原因可追踪；
* 一次有界局部 loop；
* 原图安全、QualityIssue、active pointer 和 export gate；
* 最小单页预览、修正、返工和导出入口。

### 10.2 P1：MVP-2 语义质量

* OCR 召回、字符准确率和 reading order；
* OCR 多候选与 reviewer；
* Page / multi-page 翻译上下文；
* 术语、称谓、代词和口吻一致；
* 翻译 reviewer、局部重翻和长度适配；
* OCR/翻译不确定性和 stale 传播。

### 10.3 P2：MVP-3 规模化与产品化

* Batch、性能、模型常驻、缓存与并发；
* 中断恢复、复杂 retry/fallback 和 Provider refusal；
* ZIP、manifest、长任务进度与正式 Web 闭环；
* 配置、备份、migration、日志与桌面化准备。

### 10.4 P3：后续增强或暂不考虑

* 英语及其他语言；
* 竖排中文、复杂字体和复杂背景修复；
* 半自动气泡外文字；
* 简单阅读器；
* 专业协作、发布平台、资源获取与分发；
* 复杂拟声词、花体字、艺术字和发布级精修。

---

## 11. 验收标准

### 11.1 M0 验收状态

FakeProvider 后端切片已证明架构机制可运行，并以历史关闭审查为准。M0 不参与视觉、OCR、翻译或产品可用性验收。

### 11.2 MVP-1 单页视觉质量验收

固定真实单页必须满足：

* 给定可信 OCR 和译文，声明支持的普通对白气泡和旁白框全部有明确去向；
* 不静默漏掉 TextSegment；
* 相邻或接触气泡不会被错误压成一个无内部拓扑的最终容器；
* 每个 TextSegment 唯一归属 BubbleInstance，且 eligible segment 恰好渲染一次；
* 普通气泡不因不可解释的保守风险分类被大量排除；
* 清字后无明显可读原文残留；
* 人物、线稿、气泡边界和不同容器隔离关系不被破坏；
* glyph 不超出对应 BubbleInstance mask，不跨实例；
* 字号、断行、留白和视觉居中达到人工 `ACCEPTABLE`；
* excluded 区域有风险原因、触发规则和可理解说明；
* unresolved 的普通对白缺失产生 blocking QualityIssue；
* 用户可通过最小单页入口预览、修正 OCR/译文、局部重跑并导出；
* 一次有界局部 loop 后明确通过或 block；
* 无 OOM、无界内存增长、无限循环和不可复现输出。

MVP-1 通过不表示 OCR/翻译已全自动可靠，也不表示整章 Batch 已可用。

### 11.3 MVP-2 OCR 与翻译质量验收

固定连续多页样本必须满足：

* 支持范围内关键文本无静默漏识；
* OCR 字符与 reading order 达到冻结样本门槛；
* 译文语义正确，连续页面术语、称谓、代词和口吻一致；
* OCR/翻译不确定性可见；
* 修改 OCR 后，Translation/Typesetting 正确 stale 并局部重跑；
* 修改译文后，Typesetting 正确 stale 并局部重跑；
* 翻译质量问题不会被视觉质量或漂亮排版掩盖。

### 11.4 MVP-3 规模化与产品验收

一章固定样本必须满足：

* 多 Page 顺序正确，页面失败相互隔离；
* 暂停、取消和 crash recovery 行为可解释；
* 已完成且输入未变化的阶段不重复调用；
* Provider refusal、retry、fallback、warning 和 block 有完整记录；
* 资源预算有界，无 OOM；
* open blocking QualityIssue 阻止正常导出；
* ZIP / manifest 与页面结果一致；
* 用户可在正式本地 Web 流程中完成上传、处理、review、局部返工和导出；
* 处理进度、常见错误、配置、备份和日志位置可理解。

---

## 12. 风险与约束

### 12.1 技术风险

* 文本检测漏检或误检；
* OCR 对竖排日文、低清图片、花体字和复杂背景文字识别不稳定；
* 阅读顺序启发式排序可能错误；
* 大模型可能错译、漏译或术语漂移；
* 大模型可能输出格式错误；
* 云端模型可能因内容策略拒绝处理；
* 清字可能破坏背景；
* 嵌字可能溢出；
* 批次处理耗时较长；
* 外部工具调用可能失败、超时或成本较高。

### 12.2 产品风险

* 用户对“可读”的接受标准不同；
* 自动结果质量过低时，用户可能认为校对成本过高；
* 如果交互流程过复杂，普通读者可能失去使用意愿；
* 如果功能范围过度扩张，MVP 难以完成；
* 用户可能误以为系统能生成发布级汉化成品。

### 12.3 内容风险

* 用户上传内容可能包含成人内容或敏感内容；
* 云端 API 可能拒绝处理；
* 本地 fallback 质量可能低于云端模型；
* 系统不得绕过第三方服务策略；
* 系统不得处理违法或明显不可处理内容；
* 系统不提供资源分发能力。

### 12.4 许可证风险

* 部分漫画翻译相关开源项目可能使用 GPL；
* 部分本地模型可能存在非商业限制；
* 字体文件可能存在再分发限制；
* 设计阶段必须明确工具集成方式、许可证边界和未来开源/商业化影响。

---

## 13. 后续工作

需求、HLD、核心详细设计和 M0 Architecture Proof 已完成。当前工作必须按新的产品里程碑推进，不再以“先扩 Batch、最后收敛质量”为路线。

下一阶段是 MVP-1 高质量单页视觉闭环，优先顺序为：

```text
provenance 完整性
→ BubbleInstance 拓扑
→ Cleaning eligibility
→ pixel text mask / safe edit region
→ Cleaning
→ BubbleInstance-aware typesetting region
→ Typesetting
→ actual-glyph Validator
→ 一次局部 loop
→ 单页预览、修正与导出
```

MVP-1 应使用固定少量真实单页和可信文字输入，尽快产出可直接阅读的完整结果；不得再次以大规模样本替代单页视觉质量判断，也不得无限延长局部算法研究。

MVP-1 通过后再进入 MVP-2 OCR/翻译语义质量，最后进入 MVP-3 Batch、性能、复杂恢复和产品化。
