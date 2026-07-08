# Phase 1 需求与架构基线：真实结果

本文给项目维护者看，解释需求和架构阶段最终得到了什么。它不是给 Codex 的任务说明。

## 源文件

- [../SRS-v1.0.md](../SRS-v1.0.md)
- [../HLD.md](../HLD.md)
- [../PROJECT-PLAN.md](../PROJECT-PLAN.md)

## 产品边界已经定下来了

这个项目是本地个人阅读辅助工具：

- 输入是用户自己提供的本地漫画图片。
- 输出是基础中文可读版本。
- 核心目标是“普通读者看懂剧情和对话”，不是专业汉化组级别质量。
- 系统不提供搜索、抓取、下载、分发、发布平台。

这直接影响底层实现：系统不会有爬虫模块、资源索引服务、下载队列、发布服务，也不会设计多用户协作和公开分发权限。

## 第一阶段语言和处理范围

MVP 第一阶段只优先支持：

```text
日语 -> 简体中文
```

底层处理范围偏向普通气泡、旁白框、清晰印刷体文字。复杂拟声词、花体字、艺术字、复杂背景文字默认跳过或进入 warning/review 路径。

这意味着后端实现不需要一开始支持所有漫画文字形态。它需要先做到：

- 文本区域候选检测；
- OCR；
- Page 级翻译；
- 质量检查；
- 清字；
- 基础横排中文嵌字；
- warning/block/retry/skip/review 的解释。

## 系统形态已经定下来了

MVP 采用：

```text
本地 Web UI
+ Python FastAPI 后端
+ 同进程 TaskRunner
+ SQLite
+ 本地 filesystem workspace
```

最终可包装成桌面应用，但桌面壳不改变核心架构。

底层含义：

- 前端不直接碰数据库。
- 前端不直接调 OCR、翻译、清字、嵌字工具。
- FastAPI 是唯一业务后端入口。
- 长任务不能在 API handler 里同步跑。
- API 创建 ProcessingTask 后返回 task id。
- TaskRunner 后台推进 workflow。
- SQLite 保存元数据，图片和大 payload 在 filesystem。

## 核心模块边界已经定下来了

模块分工是后续所有设计的骨架：

| 模块 | 真正负责什么 | 不负责什么 |
| --- | --- | --- |
| WorkflowLoopEngine | 推进阶段、做 retry/fallback/skip/warning/block/finish 决策。 | 不直接调用模型，不直接判断质量，不管理文件生命周期。 |
| QualityCheckService | 判断输出质量问题，给出 issue draft、severity、blocking、root_stage。 | 不推进 workflow，不更新 active pointer。 |
| Provider Adapter | 调用 OCR/翻译/清字/嵌字等工具，返回结构化结果。 | 不访问数据库，不注册 artifact，不决定 retry/skip/block。 |
| ArtifactService | 文件路径、hash、官方 artifact 注册、retention、missing 检测。 | 不决定 workflow 结果。 |
| Repository / DAO | SQLite 访问。 | 不做业务决策，不暴露 SQL/ORM session 给上层。 |
| TaskRunner | 后台执行任务。 | 不绕过 WorkflowService/WorkflowLoopEngine。 |

## 为什么架构重点是 workflow 而不是工具链

普通“一条线工具链”是：

```text
检测 -> OCR -> 翻译 -> 清字 -> 嵌字
```

本项目最终定下来的不是简单线性链，而是：

```text
阶段执行
-> 质量检查
-> WorkflowLoopEngine 做决策
-> 持久化 attempt / issue / decision / artifact
-> 可恢复、可重试、可跳过、可 warning、可 block
```

原因是外部工具会失败、拒绝、输出不完整、输出质量差，用户也会编辑 OCR/译文。系统必须能解释“为什么现在卡住了、为什么可以导出、为什么只能 warning 导出、为什么重跑不用再调工具”。

## 当前架构基线对实现的约束

实现时不能突破这些约束：

- 不把图片 BLOB 放进 SQLite。
- 不覆盖原图。
- API key 不进 project.db。
- logs/debug artifacts 不含 secrets。
- Provider refusal 是一等路径，不是普通 crash。
- WorkflowAttempt metadata 总是持久化。
- active OCR/translation/cleaned/typeset 通过 active pointer 选择，不靠最新时间戳。
- Project 数据隔离：一个 Project 一个 project.db 和 workspace。

## 这个阶段没有产出什么

没有产出代码、数据库 DDL、API schema、前端页面、真实 OCR/翻译/清字/嵌字集成。

这些都进入后续详细设计或实现阶段。
