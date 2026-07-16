# 项目重新对齐证据索引

只列新对话判断优先级所需的路径；不要把本索引当作实验原始数据替代品。

## A. 产品、范围与架构基线

| 事实 | 证据 | 说明 |
| --- | --- | --- |
| 面向普通读者、基础中文可读、非专业发布工具 | `AGENTS.md`；`docs/SRS-v1.0.md` §1–2、§9 | 明确产品目标、范围和不提供内容。 |
| 一键处理、局部返工、中断恢复、导出 | `docs/SRS-v1.0.md` §5、§6、§9、§11 | 产品需求，不是当前已交付 UI。 |
| Workflow/Quality/Artifact/Provider/DAO 分工 | `docs/HLD.md` §5、§7、§10–11；`AGENTS.md` | 架构不变量。 |
| 阶段模型与原计划 | `docs/PROJECT-PLAN.md` §4、§8–11、§17、§19 | MVP-0 状态已在本次整理中修正；具体工具 Spike 以各自 final report 为准。 |

## B. MVP-0 FakeProvider 后端与详细设计

| 事实 | 证据 | 说明 |
| --- | --- | --- |
| MVP-0 7 个实现 slice 已规划 | `docs/implementation/mvp0-fakeprovider-slice/PLAN.md`；`slices/01-*.md` 至 `07-*.md` | 文档与实现顺序。 |
| FakeProvider backend 已完成历史审查 | `docs/engineering/reviews/mvp0-fakeprovider-backend-closure-review.md` | `PASS_WITH_DEFERRED_RISKS`；历史 full suite 68/68。 |
| Workflow stage/decision/recovery 设计 | `docs/design/workflow-state/final/workflow-state-dd-v0.1.md` | retry、fallback、skip、warning、block、recovery/reuse。 |
| Provider/Artifact/Quality/StageExecutor 边界 | `docs/design/execution-contract/final/execution-contract-dd-v0.1.md` | Provider 不拥有 DB/artifact/loop decisions。 |
| app.db/project.db、active pointer、artifact、attempt/decision/issue | `docs/design/data-model/final/data-model-dd-v0.1.md` | 数据不变量。 |
| Repository/UoW/recovery/idempotency | `docs/design/persistence/final/persistence-readiness-dd-v0.1.md` | SQLite 与恢复边界。 |
| 当前后端源码 | `src/manga_read_flow/{application,artifacts,domain,persistence,providers,quality,workflow}/` | 无 FastAPI/React/正式 export/真实 Provider。 |

## C. Cleaning 与关联 Spike

| 事实 | 证据 | 说明 |
| --- | --- | --- |
| oracle mask 下受限 fill，通用 inpaint 不足 | `docs/spikes/cleaning/REPORT.md` | `FURTHER_SPIKE`，未验证自动 mask 或 Workflow。 |
| 真实气泡 fill 未恢复 AUTO_FILL | `docs/spikes/cleaning/followups/real-bubble-fill/REPORT.md` | A 类 0/8 acceptable；mask 语义错误和残字。 |
| Cleaning 总体演化和最新 supersession | `docs/spikes/cleaning/CLEANING-HANDOFF.md` §15；`CLEANING-DESIGN-RATIONALE.md` §12；`algorithm-lock-v0.1.md` §19 | 最新 section 优先于早期“下一项 Spike”。 |
| Goal 4 / Gate | `docs/spikes/cleaning/followups/text-seeded-container-association/goal4-focused-correction/GOAL4-FOCUSED-CORRECTION-REPORT-v0.1.md`；`GOAL4-GATE-v0.1.md` | `B1_STRONG_BASELINE_ONLY`；不进 Pixel Mask/Cleaning。 |
| Goal 6 的局部正例 | `docs/spikes/cleaning/followups/text-seeded-container-association/goal6-minimal-cleaning/GOAL6-FINAL-REPORT-v0.1.md` | 只支持扩大人工验证；已被 Goal 7 后续边界限缩。 |
| 40 页 E1/E2 的诊断失败 | `docs/spikes/cleaning/followups/text-seeded-container-association/large-scale-e1-e2-comparison/REPORT-v0.1.md` | E2 `NO_GO`；旧 association coverage/resource failure。 |
| Goal 7 最终边界 | `docs/spikes/cleaning/followups/text-seeded-container-association/goal7-local-routing/GOAL7-FINAL-REPORT-v0.1.md` | local routing/B1 通过 Spike；自动 association/mask/cleaning 未获准。 |

## D. Goal 7 数据产物（只在需要查数或看图时打开）

```text
data/local/text-seeded-container-association/goal7-local-routing-v0.1/
  phase-a-v0.1/PHASE-A-MATRIX.json
  phase-b-v0.1/PHASE-B-HUMAN-REVIEW.json
  phase-c-v0.1/PHASE-C-FROZEN-CONFIG.json
  phase-c-v0.1/run-v0.1/PHASE-C-RESULTS.json
  phase-c-v0.1/run-v0.1/SAMPLE-CONTACT-SHEET.png
```

Goal 7 的 frozen upstream S1：

```text
data/local/text-seeded-container-association/
  large-scale-e1-e2-comparison-v0.1/s1-runs/s1-book-40-v0.1/results.json
```

## E. 历史提交与当前分支

快照时 branch/HEAD：

```text
spike/yolo-open-vocabulary-model-selection
c707972e200c1740ffaeaf13a358b19741769b19  docs(spike): organize association evidence
```

关键提交：

```text
374d57e  feat(slice-07): add idempotency and recovery
d177e67  feat(slice-06): add quality issues and readiness gates
7a65230  feat(slice-05): add workflow loop happy path
2af6c10  feat: Implement FakeProvider and StageExecutor for workflow processing
33b67d5  feat(slice-03): import pages through ArtifactService
77aaa5d  feat(slice-02): add repository unit of work core
fb98736  feat: add project store foundation
aca74c7  feat(review): 添加 MVP-0 FakeProvider 后端关闭审查文档
c707972  docs(spike): organize association evidence
5e097aa  feat(spike): prepare minimal cleaning trial
eaf420f  feat(spike): validate routed spatial association
faf776d  feat(spike): complete focused association correction
```

Goal 7 文档、工具、测试与 R0 证据已在本次整理中独立提交；新对话应通过 `git log HEAD` 和本索引的路径检查其版本，而不是依赖旧工作区快照。

## F. 状态与文档不一致

1. Goal 6 的“expanded cleaning validation”早于 Goal 7，不能覆盖后者的 mask/cleaning block。
2. Cleaning handoff/design/lock 的早期 sections 仍含过去时态；它们的 Goal 7 supersession section 才是最新状态。
5. Goal 6/7 和相关数据/报告未进入版本历史，存在证据丢失与不可审查风险。
6. `git log --all` 会遍历指向 tree 的 Codex checkpoint ref，因而不适合本仓库的提交历史审查；使用 `git log HEAD`、`git log --branches` 或显式 commit 范围可读。

## G. 当前测试证据

| 命令 | 结果 | 解释 |
| --- | --- | --- |
| 历史 backend closure review 的 `pytest -q` | 68/68 | 仅代表当时干净提交与环境。 |
| 本快照 `python -m pytest -q` | collection failure，52 errors | 收集了 `data/local/vendor/yolo-world-v2.1` 的第三方测试，且当前 Python 缺 torch/mmcv/mmdet/mmengine/cv2。 |
| 本快照 `python -m pytest tests/integration -q` | 69 passed，2 failed | Windows SQLite 文件锁阻止两个删除 `project.db` 的测试；不是架构断言失败。 |
| Goal 7 相关测试 | 36 passed（本轮前已记录） | 只代表 Goal 7/association 相关工作树测试。 |

新对话应先决定稳定的 pytest 收集边界与平台策略，再把任何一次通过率宣称为全项目基线。
