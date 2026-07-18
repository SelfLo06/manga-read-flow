# 项目文档入口

本页是 `docs/` 的唯一导航入口，负责说明当前阶段、权威层级、文档分类和固定放置位置。它不替代需求、架构、详细设计或 Gate 本身。

## 当前状态

项目处于 **MVP-1 高质量单页视觉闭环**。

- 整页清字台账详细设计已经完成，最终审查为 `PASS_WITH_OPEN_QUESTIONS`；这表示设计可进入实施，不表示 case-71 或 case-72 已完成。
- 整页清字实施 Slice 1 已裁决为 `ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`。
- `FULL_INTEGRATION_SUITE = ENVIRONMENT_BLOCKED`，不得写成 PASS。
- Slice F 是已接受的有界修正证据，不构成整页 Cleaning 成功。
- case-71 Closure 与 case-72 Generalization 均未运行。
- 下一允许实施任务是 Slice 2；Slice 2/3 尚未实现。

当前工作入口：

1. [整页清字台账设计包](design/full-page-cleaning-ledger/README.md)
2. [整页清字三 Slice 实施包](implementation/mvp1-full-page-cleaning/README.md)

## 权威层级

1. `AGENTS.md`：仓库工作规则、架构不变量和交付约束。
2. `docs/SRS-v1.0.md`、`docs/HLD.md`、`docs/PROJECT-PLAN.md`：产品范围、总体架构与项目路线基线。
3. `docs/design/<area>/final/` 与相应 ADR：已经接受的领域详细设计和设计决策。
4. `docs/implementation/<milestone>/`：已获设计授权的实施范围、Slice 状态和实施 Gate；不得反向改写设计基线。
5. `docs/spikes/**/REPORT.md`、`GATE.md`：受限实验的证据与裁决，只证明其明确范围。
6. `docs/handoffs/`：交接快照，不是新的设计权威源。

发生冲突时，先停止实施并报告冲突；不得用较低层的实现或实验报告静默覆盖上层基线。

## 文档状态分类

| 分类 | 含义 | 典型位置 |
| --- | --- | --- |
| 项目基线 | 当前产品范围、架构和路线的最高项目级依据 | `SRS-v1.0.md`、`HLD.md`、`PROJECT-PLAN.md` |
| 已接受设计 | 已完成审查、可约束实施的详细设计 | `design/<area>/final/`、域内 ADR |
| 当前实施 | 已获设计授权、尚在推进或刚完成的实现 Slice | `implementation/<milestone>/` |
| 实验证据 | 有界 Spike 的输入、报告和 Gate；不能外推为产品结论 | `spikes/<family>/<bounded-spike>/` |
| 历史快照 | 已被后续工作取代但仍需追溯的交接、旧版本或已关闭材料 | `handoffs/`、`archive/`、已关闭 Spike 原目录 |
| 本地过程产物 | 只服务当前设计/实施过程，不作为可克隆的权威记录 | 被 `.gitignore` 标记的 `PLAN.md`、`proposals/`、`reviews/` 等 |

历史文档不做无收益的批量改名或搬迁，以免破坏既有链接。旧式 `xxx-REPORT.md`、`xxx-GATE.md` 或其他遗留命名保留在原位置，但不得作为新文档模板。是否仍然有效由其 Gate、上层基线和本页当前状态共同判断。

## 现有文档归类

| 现有区域 | 当前分类 | 使用方式 |
| --- | --- | --- |
| `design/data-model/`、`workflow-state/`、`execution-contract/`、`persistence/` | 已接受基础设计 | 继续作为 M0/MVP-1 实施约束；优先读取各自 `final/` |
| `implementation/mvp0-fakeprovider-slice/` | 已完成的历史实施包 | 用于追溯 M0 Repository、UoW、Artifact、Workflow 和 recovery 边界，不是当前任务入口 |
| `design/mvp1-visual-contract/` | MVP-1 已接受上游设计 | 约束当前视觉对象、Cleaning 和 validator 语义 |
| `spikes/detection-ocr/`、`cleaning/`、`typesetting/`、`page-translation/` | 历史 Spike 证据 | 保留原路径；按各自 REPORT/GATE 理解，不从文件名推断当前有效性 |
| `spikes/mvp1-visual-contract/` | 当前阶段的有界证据 family | Slice E/F 等局部事实来源；不得外推为整页 Closure |
| `design/full-page-cleaning-ledger/` | 当前已接受详细设计 | Slice 1/2/3 的直接设计权威 |
| `implementation/mvp1-full-page-cleaning/` | 当前活动实施包 | Slice 1 已接受，Slice 2 下一允许，Slice 3 未开始 |
| `handoffs/**` | 历史上下文快照 | 仅在恢复对话背景时读取；始终回到本页确认当前状态 |
| `archive/**` | 已废弃项目级版本 | 只读，不用于当前设计或实施 |

## 目录职责与固定位置

| 位置 | 用途 | 新文档应放什么 |
| --- | --- | --- |
| `docs/design/<area>/` | 一个稳定设计域的详细设计包 | `README.md`、`GOAL.md`、`HARNESS.md`、`final/` 和必要 ADR；过程性 `PLAN.md`、`proposals/`、`reviews/` 不作为最终权威。 |
| `docs/spikes/<family>/<bounded-spike>/` | 有明确假设、样本、门禁和停止条件的技术 Spike | `GOAL.md`、`HARNESS.md`、本地 `PLAN.md`、可选 `DESIGN.md`、`REPORT.md`、`GATE.md`。 |
| `docs/implementation/<milestone>/` | 跨多个实现步骤的产品实施包 | 里程碑 `README.md`、`slices/<nn-name>/README.md`，完成后在同一 Slice 目录写 `REPORT.md`、`GATE.md`。 |
| `docs/adr/architecture/` | 跨多个设计域的架构 ADR | 影响多个设计域或项目级运行时的持久决策。 |
| `docs/engineering/` | 工程健康、测试基线和发布门禁 | 可复用规则与健康报告。 |
| `docs/handoffs/<topic>/` | 一次对话或阶段结束时的交接快照 | `HANDOFF.md`、必要的 `EVIDENCE-INDEX.md`、新对话 prompt。 |
| `docs/prompt-patterns/` | Prompt 模板与案例 | 不承载项目事实或冻结决策。 |
| `docs/archive/` | 已废弃的项目级文档版本 | 只读保留，不继续演进当前设计。 |

运行产物、人工 FORM、图片、JSON 证据、临时 benchmark 输出放在 `data/local/` 或其他已忽略的本地路径。只有任务明确要求版本化的冻结样本例外；正式结论仍以对应 `REPORT.md` 和 `GATE.md` 为准。

## ADR 的两层位置

- `docs/design/<area>/adr/`：只影响一个详细设计域的 ADR。
- `docs/adr/architecture/`：同时影响多个设计域或项目级运行时的 ADR。

两者可以并存，但不得重复复制同一个决策。

## 技术 Spike 与实施 Slice

### 技术 Spike

用于降低技术、算法或合同不确定性。输出冻结证据、REPORT 和 GATE。
Spike 的有效结果可以是 GO、PASS_WITH_LIMITS、CHANGES_REQUIRED 或 NO_GO。
Spike 不自动形成正式产品能力。

### 实施 Slice

用于实现已被接受设计授权的最小垂直能力。输出生产代码、测试、
REPORT、GATE 和独立提交。Slice 必须遵守正式架构、持久化和恢复合同。

判断原则：

- 主要问题是“是否可行”时使用 Spike；
- 主要问题是“如何把已接受方案接入正式系统”时使用 Slice。

## 新文档的最小规则

- 使用小写 kebab-case 目录名。
- 当前维护文档和后续新文档统一使用中文；代码标识符、数据库对象名、固定枚举值和无法准确翻译的产品术语可以保留原文。
- 每个工作单元拥有自己的目录；固定终件命名为 `REPORT.md`、`GATE.md`，不再创建 `xxx-REPORT.md`。
- 设计或 Spike 开始前必须写明目标、范围、允许/禁止事项、验证样本、门禁和停止条件。
- 实验报告必须区分已确认事实、假设、失败原因和下一步，不得把局部样本结论扩展为产品结论。
- 实现 Slice 只在获得相应设计授权后创建，并链接所属详细设计与前置证据。
- `PLAN.md` 若命中 `.gitignore`，就是本地过程产物；不得用 `git add -f` 将其临时提升为权威文档。需要版本化的里程碑状态写入 `README.md`。

维护者和 agent 都应从本页进入，不再维护第二套导读目录。
