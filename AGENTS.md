# AGENTS.md

## 项目与语言

本仓库是面向普通漫画读者的本地漫画翻译与基础嵌字工作流。项目内回复使用中文。系统只处理用户合法持有的本地内容，不提供搜索、抓取、下载、分发或发布。

## 默认上下文

普通任务只读取：

1. 本文件；
2. `docs/000-project/000-30-current.md`；
3. 与任务直接相关的一份 `docs/100-stages/<stage>/NNN-00-*.md`。

只有架构、范围、路线或跨阶段任务，才按需读取 `000-00-product.md`、`000-10-architecture.md`、`000-20-roadmap.md` 和 `docs/010-workflow/`。不要默认加载历史文档或整个 `docs/`。

## 工作方式

- 默认最小变更，不修改无关文件、不做无关重构、不升级依赖。
- 设计任务不写实现代码，除非用户明确要求；设计结果应包含决定、理由、拒绝的替代方案、风险、验证场景和开放问题。
- 代码任务先识别测试，适合时先更新测试；不得改变断言来掩盖失败。
- 普通任务不创建独立任务包、过程报告、评审提案、长期交接或重复事实源；高风险任务可增加必要验证，但不自动扩张文档资产。
- 开始前检查 branch 和工作区，结束前检查 diff。默认不 commit、push、pull、rebase、stash、reset 或覆盖用户修改。
- 无关的未跟踪或已忽略文件本身不是停止条件；保持不触碰并继续处理当前范围。
- 不提交 `.codex/`、`.claude/`、`.idea/`、日志、缓存、构建输出、本地配置、secrets 或 `data/local/**`。

## 架构边界

- WorkflowLoopEngine 独占 retry、fallback、skip、block 与 accept 决策。
- QualityCheckService 独占质量问题检测与根阶段归因。
- Provider Adapter 不访问数据库、不管理 artifact 生命周期、不决定流程行为。
- ArtifactService 独占 artifact 路径、hash、登记、保留与清理。
- Repository/DAO 独占 SQLite；UI 只能通过后端用例调用能力。

## 数据不变量

- SQLite 不存图片 BLOB；原图永不覆盖；每个 Project 隔离数据。
- OCRResult、TranslationResult 和用户编辑都版本化；当前有效结果只由 active pointer 选择。
- 每次 WorkflowAttempt 都持久化；失败 artifact 默认保留。
- API key 不进入 project.db 或日志；外部文件操作必须防止 path traversal 并限制类型。
- 受保护本地数据迁移必须先复制、逐文件 SHA-256 验证、更新引用、再次验证，再删除旧副本。

## 验证与交付

至少考虑正常、失败、边界、重启恢复、部分失败、幂等、Provider refusal、文件清理、软删除和导出阻断。无法运行测试时说明原因和替代验证，不得虚构结果。

交付说明包含：变更文件、关键决定、风险、实际运行的测试/验证和未解决问题。没有验证就不能声称成功。
