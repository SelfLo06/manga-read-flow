# 新 Codex 对话 Prompt（可直接复制）

请执行一次“项目重新对齐与下一阶段裁决”，不要立即写代码、创建 Goal、修改 Cleaning 算法、运行大规模实验、commit 或 push。

先完整阅读：

1. `docs/handoffs/project-realignment-after-goal7/HANDOFF.md`
2. `docs/handoffs/project-realignment-after-goal7/EVIDENCE-INDEX.md`
3. `AGENTS.md`
4. `docs/SRS-v1.0.md`
5. `docs/HLD.md`
6. `docs/PROJECT-PLAN.md`
7. `docs/engineering/reviews/mvp0-fakeprovider-backend-closure-review.md`
8. `docs/design/workflow-state/final/workflow-state-dd-v0.1.md`
9. `docs/design/execution-contract/final/execution-contract-dd-v0.1.md`
10. `docs/design/data-model/final/data-model-dd-v0.1.md`
11. `docs/design/persistence/final/persistence-readiness-dd-v0.1.md`
12. `docs/spikes/cleaning/CLEANING-HANDOFF.md`
13. `docs/spikes/cleaning/algorithm-lock-v0.1.md`
14. Goal 4、40 页 E1/E2、Goal 7 的最终报告（见 Evidence Index）

然后先做只读仓库审计：branch、HEAD、`git status --short --untracked-files=all`、与 FakeProvider/Workflow/Cleaning 相关的 `git log HEAD`、可运行的项目测试入口。保留既有改动；不得 reset、stash、checkout、rebase、clean 或提交。

从整体产品目标出发审查，而不是默认继续 Cleaning：本产品服务普通漫画读者，应尽量一键完成检测、OCR、Page 级翻译、清字、嵌字、预览、局部返工和导出；运行期目标是最大限度减少人工，长期接近零人工。复杂区域可安全跳过、记录 QualityIssue、保留原图并继续处理。开发期人工标注不是产品必经步骤。

请明确区分：

- 已确认事实；
- 已冻结架构/算法决策；
- 尚未证明的假设；
- 当前过程和版本管理风险；
- 哪些结论只是 Spike 证据，不能夸大为产品能力。

重点回答：

1. 当前是否已在 Cleaning 局部算法上投入过深；
2. FakeProvider 已验证的 Workflow/Quality/Artifact/Recovery 机制为何尚未与真实工具形成产品证据；
3. 最短、最有产品价值的下一验证应是：
   - A：继续独立 Candidate Qualification；
   - B：端到端 Autonomous Cleaning Loop Spike；
   - C：恢复单 Page MVP 主线；
   - D：停止 B1/text-first 并探索独立 bubble/container perception；
   或者经过论证后的另一条单一路径；
4. `REVIEW_REQUIRED` 应如何在产品中成为可解释 warning/skip，而不是强迫用户逐项人工确认；
5. Cleaning 对 MVP 的最小承诺是什么，才既安全又不阻塞“基础中文可读”的产品价值。

输出一个**唯一推荐下一步**，并提供：

- 推荐理由及拒绝其余路径的理由；
- 最小范围；
- 允许/禁止文件与能力；
- 阶段门禁；
- 可量化验证标准；
- 停止条件；
- 需要先处理的工程卫生问题；
- 是否需要更新 PROJECT-PLAN / HLD / SRS；
- 决策完成前的禁止事项。

在这份决策完成并经维护者确认前，禁止写实现代码或启动下一 Goal。
