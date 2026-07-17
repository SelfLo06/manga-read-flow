# 项目文档地图与放置规则

本文定义 `docs/` 的导航、权威层级和后续文档的固定位置。它不重写历史，也不替代需求、架构或已冻结的详细设计。

## 权威层级

1. `AGENTS.md`：仓库工作规则、架构不变量和交付约束。
2. `docs/SRS-v1.0.md`、`docs/HLD.md`、`docs/PROJECT-PLAN.md`：产品范围、总体架构与当前路线的项目级基线。
3. `docs/design/<area>/final/` 与相应 ADR：已经接受的领域详细设计和设计决策。
4. `docs/spikes/**/REPORT.md`、`GATE.md`：受限实验的证据与裁决。它们只证明其明确范围；除非项目级基线随之更新，否则不自动改写上层决策。

发生冲突时，先停止实施并报告冲突；不得以较低层的实验报告静默覆盖上层基线。

## 目录职责与未来放置位置

| 位置 | 用途 | 新文档应放什么 |
| --- | --- | --- |
| `docs/SRS-v1.0.md`、`docs/HLD.md`、`docs/PROJECT-PLAN.md` | 项目级基线 | 仅放范围、架构、路线和项目级验收标准的修订。 |
| `docs/design/<area>/` | 一个稳定设计域的详细设计包 | `GOAL.md`、`HARNESS.md`、必要的 `PLAN.md`、`final/`、以及该域的 `adr/`。过程性 `proposals/`、`reviews/` 仅服务于该设计轮。 |
| `docs/spikes/<family>/<bounded-spike>/` | 有明确假设、样本、门禁和停止条件的技术 Spike | 新 Spike 默认使用 `GOAL.md`、`HARNESS.md`、`PLAN.md`、`REPORT.md`、`GATE.md`；若需要先冻结具体设计，可增加 `DESIGN.md`。后续验证留在同一 family 下。 |
| `docs/implementation/<milestone-or-slice>/` | 已批准、跨多个实现步骤的产品实施计划 | 里程碑/切片计划、切片清单、检查表和实施交接；不存放单一 Spike 的实验报告。 |
| `docs/adr/architecture/` | 跨多个设计域的架构 ADR | 例如运行时、数据隔离、任务执行或 Artifact 生命周期等全局决策。 |
| `docs/engineering/` | 工程健康、测试基线、代码审查与发布门禁 | 可复用的工程规则和健康报告。 |
| `docs/handoffs/` | 一次对话或阶段结束时的交接快照 | `HANDOFF.md`、`EVIDENCE-INDEX.md`、新对话 prompt；不是长期权威设计。 |
| `docs/reader/` | 面向维护者的中文导读 | 只做导航和解释，必须链接权威源；不能作为 agent 的任务或架构依据。 |
| `docs/prompt-patterns/` | Prompt 模板与案例 | 不承载项目事实或冻结决策。 |
| `docs/archive/` | 已废弃或历史版本 | 只读保留，不在其中继续演进当前设计。 |

运行产物、表单、图片、JSON 证据、临时 benchmark 输出放在 `data/local/` 或其他已忽略的本地路径，不进入 `docs/` 或 Git；正式结论以短报告和 Gate 进入对应 Spike 目录。

## ADR 的两层位置

现有 `docs/design/<area>/adr/` 是**设计域内**的 ADR：决策只影响一个详细设计域时，继续放在那里。

`docs/adr/architecture/` 是**跨域** ADR：决策同时影响多个设计域、项目级运行时或多个 Provider/Repository/Workflow 边界时，才放这里。两者并存，不重复复制同一 ADR。

## 当前 MVP-1 Visual Contract 的示例

- 视觉契约的稳定详细设计：`docs/design/mvp1-visual-contract/`。
- 有界验证实验：`docs/spikes/mvp1-visual-contract/bounded-spike-*/`。
- Spike E 的单页清字纵向切片，即使产生了实现代码，也仍属于实验，因此报告位于 `docs/spikes/mvp1-visual-contract/bounded-spike-e-single-page-cleaning-vertical-slice/`。
- 实现代码、测试和可复现实验入口分别位于 `src/`、`tests/` 和 `tools/mvp1/`；其本地输出位于已忽略的 `data/local/`。

如果后续启动 text-aware boundary/safe-edit 修正，它应作为新的有界 Spike 放入同一 family，例如 `docs/spikes/mvp1-visual-contract/bounded-spike-f-text-aware-boundary-correction/`；在未启动前不预建目录或伪造报告。

## 新建文档的最小规则

- 使用小写 kebab-case 目录名；同一目录中的固定终件命名为 `REPORT.md`、`GATE.md`，避免再创建 `xxx-REPORT.md` 一类重复命名。
- 设计或 Spike 开始前，先写明目标、范围、允许/禁止事项、验证样本、门禁和停止条件。
- 实验报告必须区分已确认事实、假设、失败原因和下一步，不得把局部样本结论扩展为产品结论。
- 实现切片只在已获得相应设计授权后创建；切片计划与实现证据链接到其所属详细设计或 Spike。

## 导航入口

维护者可从 [reader/README.md](reader/README.md) 获得中文导读；开始设计或实施工作时，应从 `AGENTS.md` 及本页列出的项目级基线进入。
