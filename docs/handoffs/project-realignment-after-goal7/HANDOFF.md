# 项目重新对齐交接：Goal 7 后

快照日期：2026-07-16。本文是给新 Codex 对话的项目级决策输入，不是新 Goal、实现计划或对任何 Cleaning 路线的授权。

## 1. 产品目标与固定边界

产品是本地运行的“漫画翻译与基础嵌字自动化工作流应用”，面向拥有合法本地图片的普通漫画读者，而不是专业汉化生产系统。核心体验是：尽量一键完成检测、OCR、Page 级翻译、清字、嵌字、预览、局部返工和导出；复杂拟声、艺术字、复杂背景可安全跳过。

运行期目标是最大限度减少人工参与，长期方向接近零人工。自动失败时系统可以保留原图、跳过局部、记录 `QualityIssue`、继续处理其他目标，并在有界预算内 retry / fallback / revert；开发期人工标注和人工审查只用于验证，不能默认成为产品必经步骤。

固定合规边界：不提供漫画搜索、抓取、下载、分发或发布；不绕过第三方 Provider 政策。

固定架构边界：

| 责任 | 唯一所有者 |
| --- | --- |
| retry / fallback / skip / warning / block / loop 决策 | `WorkflowLoopEngine` |
| 质量问题检测与根因归属 | `QualityCheckService` |
| 正式 artifact 路径、hash、登记、保留、清理与缺失状态 | `ArtifactService` |
| SQLite 访问 | Repository / DAO |
| 外部/本地工具调用与结构化结果 | Provider Adapter |

原图不得覆盖；图片和大 payload 不进 SQLite；OCR/Translation 结果版本化；当前有效结果由 active pointer 选择，不使用独立 active flag；`WorkflowAttempt`、`WorkflowDecision`、`QualityIssue`、ToolRun 与相关 artifact 必须能解释恢复和 export gate。

## 2. 当前整体阶段

最准确的阶段判断是：**需求、架构、核心详细设计和 MVP-0 FakeProvider 后端垂直切片已经形成；真实工具能力已有多个独立 Spike；产品仍未完成真实 Provider 的端到端单页闭环，也没有 API/UI/正式导出。**

因此项目不应被描述为“仅做文档、尚未实现”，也不能描述为“已有可用 MVP”。它处于“后端架构已验证、真实工具碎片证据较多、产品闭环尚未验证”的重新排序点。

`PROJECT-PLAN.md` 已在本次仓库整理中更新为真实阶段状态：MVP-0 FakeProvider Slice 01–07 已完成并通过关闭审查，但 API/UI、真实 Provider、正式导出和用户可操作的端到端结果仍未完成。

## 3. 已确认事实

### 3.1 正式工程与架构

- Slice 01–07 的 FakeProvider 单页后端已实现并进入历史提交：Project store、Repository/UoW、ArtifactService/import、FakeProvider/StageExecutor、Workflow happy path、Quality/readiness、idempotency/recovery。
- `mvp0-fakeprovider-backend-closure-review.md` 的结论为 `PASS_WITH_DEFERRED_RISKS`；历史完整测试为 68/68。Provider、Artifact、Quality、Workflow、Repository 的职责边界经审查未发现 Category A blocker。
- Workflow 设计已定义 canonical stages：`import → detection → ocr → translation → translation_check → cleaning → typesetting → export_check`，以及持久化 attempt/decision、有限 retry、provider refusal、recovery、reuse、warning/block export 语义。
- 当前仓库的 `src/manga_read_flow/` 只包含后端/领域/持久化/工作流/FakeProvider；未发现 FastAPI route、React/Next.js 前端、正式导出实现或真实 Provider 接入。

### 3.2 真实工具与 Cleaning

- Detection/OCR、Grouping、Page Translation、Cleaning 等已有独立 Spike 资产；它们不是与产品 Workflow 集成的端到端能力证明。
- 初始 Cleaning Spike 在 **oracle mask** 下证明：严格受限的浅色气泡/旁白框 fill 有局部可行性；通用 OpenCV inpaint 没有显示可重复优势。
- 真实气泡 fill follow-up 进一步证明：即使 mask 外改动为 0，人工 allowed/protected mask 本身也可能语义错误，且存在可读残字；受限 `AUTO_FILL` 仍 disabled。
- Goal 4：`B1_STRONG_BASELINE_ONLY`；corrected P1 未被选中；不得进入 Pixel Text Mask 或 Cleaning。
- 40 页激进 E1/E2 对比：E2 自动推广 `NO_GO`；E1 整书证据 `INCONCLUSIVE`；旧 page-global association coverage 与 full-page B1 batch readiness 均失败。根因已定位为 page-global geometry/topology 与无界 full-page priority-flood，不是 E1/E2 本身的泛化结论。
- Goal 7 修正了粒度和资源问题：40 页、366 group 被分为 311 local cluster；255 local B1 candidate、55 local review、1 local abstain。Phase B 人工确认 10/12 普通对白 group 有可见 coarse candidate（83.3%），接触/相邻容器 topology 2/2 正确。Phase C 255/255 local B1 完成且非空，0 crash/timeout/OOM，峰值 165.5 MB、p95 0.657 s。
- Goal 7 同时证明限制：`LOCAL_B1_CANDIDATE != confirmed container`。普通对白中已有 `WRONG_OR_LEAK`；标题、SFX、复杂画面也可产生非空 region。因此 Pixel Text Mask、safe edit region、E1/E2 自动清字和 `AUTO_ACCEPT` 仍被阻断。

## 4. 已冻结决策与淘汰项

| 项目 | 状态 | 含义 |
| --- | --- | --- |
| page-global association / global extreme gate / global topology gate | 淘汰 | 不能再让一组异常或不确定关系毒死整页。 |
| full-page Python priority-flood B1 | 淘汰 | 已有约 14 GB OOM 证据。 |
| per-group / small local-cluster routing | 保留 | 是后续 association 唯一允许的粒度。 |
| bounded local B1 | 仅通过 Spike | 有 ROI/L1/队列/内存/时间边界；输出只是 `REVIEW_REQUIRED` coarse candidate。 |
| corrected P1 | 未选中 | 对 false/free-text 有局部收益，但未保持 B1 的真实 bubble scope。 |
| unrestricted OpenCV inpaint / E2 自动推广 | 淘汰 | E2 没有普通对白正例，唯一有效样本残字明显。 |
| restricted fill | 仅 oracle/严格局部证据 | 真实页面语义 mask 与完整清字仍不成立。 |
| Pixel Text Mask / safe edit region / 自动清字 | 阻断 | 缺少 confirmed container、可靠文字 mask 与保护结构证据。 |
| Provider DB/Artifact/loop 决策权 | 禁止 | 不因真实工具 Spike 改变架构边界。 |

最新的 Goal 7 section 应优先于 Cleaning 文档中的早期“下一项 Spike”文字；Goal 6 的“expanded manual cleaning validation”也已被后续 Goal 7 的 blocking conclusion 限缩，不能作为自动清字授权。

## 5. Cleaning Spike 的压缩时间线

1. **重建层**：oracle mask 下，浅色气泡 fill 有局部价值；通用 inpaint 不足。
2. **真实 mask 层**：真实页出现 mask undercoverage、anti-alias residue、mask 语义越界；restricted auto fill 被关闭。
3. **关联层（Goal 3/4/5）**：B1 是 explicit/contact bubble 的强基线，但 topology、free text 与 false seed 不稳定；corrected P1 未胜出。
4. **最小清字（Goal 6）**：少数冻结、良好上下文中 E1 清字可接受，说明 fill/mask 在可靠局部输入下仍可能有价值；这不是全局自动清字证据。
5. **40 页与 Goal 7**：先定位并修复 page-global routing/OOM；修复后得到局部 coarse candidate 覆盖和资源稳定性，但仍没有 semantic qualification，更没有 safe edit evidence。

## 6. 为什么 Workflow Loop、Quality Gate 与自动重试尚未真正验证产品价值

FakeProvider 后端确实验证了它们的**机制**：attempt/decision 持久化、retry/fallback/skip/warning/block、provider refusal、artifact lifecycle、recovery、reuse 和 readiness 都有设计与测试证据。

但真实 Detection/OCR/Translation/Cleaning/Typesetting Spike 都在独立 harness 中运行，明确不接入 Provider Adapter、ArtifactService、SQLite、WorkflowLoopEngine 或真实 export。这意味着尚未验证：

- 一个真实工具失败/低质量后，QualityCheck 是否能产生正确 root-stage `QualityIssue`；
- Loop 是否会在不破坏原图的前提下 retry、fallback、skip local target、保留候选、继续该页或批次；
- 真实 cleaning 的 `REVIEW_REQUIRED` 是否能作为产品运行期的 warning/skip，而非要求产品用户逐个填写开发期 FORM；
- 有真实 artifact/provenance 时，export gate、局部返工和恢复能否共同工作；
- 多次尝试是否比“单次必须完美”更接近普通读者的零人工目标。

## 7. 未证明的假设

- 多策略 Cleaning Loop 是否能借助自动验证、retry、fallback、revert 和 local skip 达到低人工/近零人工；
- coarse association 是否必须先独立达到极高正确率，还是可由下游 qualification/mask/verification 在 loop 中安全处理；
- 当前 P0 mask 与 E1 fill 在可靠 local input 下的价值能否迁移到真实自动输入；
- Cleaning 是否应继续拆成独立 Spike，还是应通过一个受限的端到端 loop 才能验证产品价值；
- 独立 bubble/container perception 是否会比 B1/text-first 更有性价比；
- 当前 MVP 自动化目标是否应定义为“普通对话尽量自动、其余安全跳过并可导出”，而非“无条件清除所有检测到的文字”。

## 8. 当前过程风险

1. **局部研究吞噬主线**：Cleaning 已积累大量精细 Spike，但用户尚未看到真正的一页产品流程、预览、返工和导出。
2. **人工 gate 误用**：FORM/overlay 是开发期判定工具；若将其映射为产品运行期必须人工确认，会违背一键处理与零人工方向。
3. **单次直出心智模型**：Workflow 的价值本应是安全失败、记录证据、局部重试/回退/保留原图；当前实验过多要求一个算法在一次运行中证明所有能力。
4. **证据层级混淆**：mask 内/外像素安全、非空 coarse region、人工可读性、container 语义正确性、export readiness 是不同门禁，不能互相替代。
5. **版本历史风险**：历史实验曾在未提交工作区中积累；本次已按证据和 Goal 分批版本化。后续新实验仍必须避免把报告、工具、测试与输入资产长期混在未跟踪状态。
6. **计划维护风险**：`PROJECT-PLAN.md` 已修正 MVP-0 状态，但真实工具 Spike 的结论仍分散在各自 final report；排优先级时应优先读取本交接和证据索引。
7. **测试基线失真**：根目录 `pytest -q` 会收集 vendor 第三方测试；Windows 环境还有 SQLite 文件锁用例失败。没有稳定、可复现的项目测试入口。

## 9. 当前仓库状态

快照开始时：

```text
branch: spike/yolo-open-vocabulary-model-selection
HEAD:   c707972e200c1740ffaeaf13a358b19741769b19
subject: docs(spike): organize association evidence
```

Goal 7 的文档、工具、测试和 R0 证据已作为独立历史资产提交。最近相关历史：

| Area | 最近可见提交 |
| --- | --- |
| Cleaning / association | `c707972`、`5e097aa`、`eaf420f`、`faf776d`、`f5bb3fe`、`e8f7a34`、`1721e57` |
| FakeProvider / Workflow | `374d57e`、`d177e67`、`7a65230`、`2af6c10`、`33b67d5`、`77aaa5d`、`fb98736` |
| 后端关闭审查 | `aca74c7` |

初始审计时工作区包含未跟踪的 Cleaning/Goal 6/7 证据与暂存的 YOLO 校准扩展。本次整理后：Goal 6/7 及其支撑证据已分批提交；Real Bubble Fill 报告已恢复为规范 `REPORT.md`；YOLO 本地数据被显式 ignore，只保留最终 `NOT_ADOPTED` 决策报告。

新对话仍应先查看 `git status --short --untracked-files=all`，并且不得对用户后续改动执行 reset、stash、rebase、clean 或 broad stage。

`git log HEAD ...` 与 `git log --branches ...` 可用。`git log --all` 会遍历 Codex 的 `refs/codex/turn-diffs/...` checkpoint ref；这些 ref 指向 Git tree 而非 commit，因此 `log` 报错。这不是项目提交历史损坏，也不应删除 checkpoint；历史审查应使用 `HEAD`、`--branches` 或显式 commit 范围。

## 10. 候选下一路径（不在本文裁决）

| 路径 | 产品价值 | 技术风险 / 成本 | 现有复用 | 人工参与风险 | 最短可证伪实验 |
| --- | --- | --- | --- | --- | --- |
| A. 继续独立 Candidate Qualification | 直接补 Goal 7 的语义缺口，可能降低 SFX/标题误候选。 | 中高；容易继续增加 calibration 和局部启发式，延长看不到完整结果的时间。 | 高：S1、Goal 7 ROI/B1、人工标签与审查图。 | 高：若没有自动验证代理，可能继续依赖人工 FORM。 | 固定 30–50 个 local candidate，预先定义 explicit/bounded/SFX/uncertain 标签与 leakage gate；若普通对白的语义正确率不能明显高于当前 review 级候选，则停止。 |
| B. Autonomous Cleaning Loop Spike | 最符合 Workflow/零人工方向；可验证“失败可安全继续”而不是单算法完美。 | 高；mask、quality verification、retry/fallback/revert 仍未证明，不能把 Goal 7 candidate 直接清字。 | 高：Workflow/FakeProvider、Artifact/Quality 边界、Goal 7 candidate。 | 中：开发期可用少量标注；运行期必须设计自动 quality/skip。 | 一页、少量普通 bubble：candidate → qualification → mask → E1 attempt → automatic verifier → accept/retry/skip/revert；证明错误不覆盖原图、能产生 issue/decision 并继续。 |
| C. 恢复单 Page MVP 主线 | 最快产生用户可操作的上传、处理、预览、局部返工、导出价值；Cleaning 可作为保守可插拔 stage。 | 中；需完成 API/UI/正式 export 接缝，并决定真实 Provider 最小接口。 | 很高：MVP-0 后端、FakeProvider、状态/数据/Artifact 设计与真实 Detection/OCR/Translation Spike。 | 低到中：把复杂 Cleaning 作为 warning/skip，不让其阻塞核心翻译可读性。 | 单 Page Web 或 CLI+最小 UI：真实或受限 Provider 完成 detect/OCR/translate/typeset，Cleaning 允许明确 skip；用户能预览、改译文、重嵌字、导出。 |
| D. 停止 B1/text-first 组合，转 bubble/container perception | 可能从根本改善 container 语义，减少下游修补。 | 高且资产复用中等；需避免重新陷入模型选择而无产品验证。 | 中：可复用 S1、人工局部标签、质量指标，但算法主体需替换。 | 中高：初期仍需标注验证。 | 先定义同一固定样本、same metrics 和 stop gate；若新 perception 在普通气泡 semantic correctness/leakage 上实质超过 local B1 qualification，才考虑替换。 |

**供新对话审查的初步判断，不是结论**：路径 C 最接近产品价值和既有后端资产；路径 B 最直接检验 Workflow 的设计初衷；路径 A/D 只有在它们能以小范围、可证伪门禁证明不会继续吞噬主线时才值得优先。新对话必须给出唯一推荐，而不是并行启动四条线。

## 11. 新对话必须回答的决策问题

1. 在“后端机制已验证、产品闭环未验证”的阶段，最高优先级是否应从 Cleaning 单点转回 single-page product loop？
2. Cleaning 对 MVP 的最小承诺应是什么：普通浅色气泡自动、保守 local attempt、还是默认 skip 且不阻塞译文嵌字？
3. Workflow Loop 是否应先通过一个真实/受限工具链的端到端 Spike 证明价值，再继续扩展 container qualification？
4. 若选择 Cleaning Loop，如何保证 `REVIEW_REQUIRED` 是产品的可解释 warning/skip，而非强制人工操作？
5. 若选择 MVP 主线，真实 Provider 最小集和 cleaning fallback 应如何限定，才能在不篡改架构边界的情况下交付单页价值？
6. 哪一条路线有最短的产品价值验证与最清晰的停止条件？
7. 是否先处理计划文档过期、未提交 Goal 6/7 资产、测试收集配置和坏 ref 等工程卫生风险？哪些必须先做，哪些可后置？

## 12. 推荐阅读顺序

1. 本文与 `EVIDENCE-INDEX.md`；
2. `NEW-CONVERSATION-PROMPT.md`；
3. SRS、HLD、PROJECT-PLAN；
4. FakeProvider backend closure review 与 Workflow/Execution/Data/Persistence final design；
5. Cleaning handoff、algorithm lock、Goal 4、40-page report、Goal 7 final report；
6. 再查看代码、git status 和数据产物。

在上述决策完成前：不写代码、不启动 Goal、不修改 Cleaning 算法、不进行大规模实验、不提交或 push。
