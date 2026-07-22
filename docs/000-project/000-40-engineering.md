# 工程规则

## 1. 默认工作方式

普通任务默认只读取：

1. `AGENTS.md`；
2. `docs/000-project/000-30-current.md`；
3. 一份直接相关的阶段 `NNN-00` 文档；
4. 与任务直接相关的代码入口和测试。

只有架构、范围、Roadmap 或跨阶段任务，才按需读取产品、架构和 Workflow 文档。不得默认加载整个 `docs/`、历史报告或旧实验材料。

默认原则：

- 最小变更；
- 不修改无关文件；
- 不做无关重构；
- 不升级无关依赖；
- 不创建重复事实源；
- 不因局部困难自行扩大任务；
- 不因任务较长而放宽架构边界。

设计达到可实现、可验证、可演化即可进入实现，不鼓励无设计编码，也不允许无限设计。

开始前检查 branch、HEAD 和工作区；结束前检查 diff。默认不 commit、push、pull、rebase、stash、reset 或覆盖用户修改。

无关的未跟踪或已忽略文件不是自动停止条件，但不得触碰。

---

## 2. 任务模式

每个任务应明确属于以下一种模式：

- `IMPLEMENT_EXISTING_DESIGN`
- `SPIKE`
- `REFACTOR`
- `DOCS`
- `DESIGN_CHANGE`

未明确指定时，默认是：

```text
IMPLEMENT_EXISTING_DESIGN
````

### IMPLEMENT_EXISTING_DESIGN

沿现有设计和正式代码主链路实现，不得自行引入新的领域机制、平行 pipeline 或替代 source of truth。

### SPIKE

验证高风险工具能力或算法假设。Spike 必须与产品主线隔离，不登记正式 artifact，不更新 active pointer，不改变 Workflow 决策，也不自动成为当前设计基线。

### REFACTOR

保持外部行为、合同、状态和测试语义不变，不顺带增加功能或修改算法。

### DOCS

只修改文档，不改变运行行为。文档必须基于真实代码、测试和维护者决定。

### DESIGN_CHANGE

现有设计无法支持目标时使用。必须先说明设计缺口、受影响合同、不变量、数据流和迁移影响，获得授权后才能实现。

---

## 3. Design Binding

实现任务不能只描述目标输出，还必须绑定当前设计。

修改前应确认：

* Canonical Processing Path；
* 正式入口；
* Authoritative Inputs / Source of Truth；
* 必须复用的领域对象、Service 或组件；
* Allowed Extension Point；
* Quality Check 和 Workflow 接受路径；
* 下游依赖及 stale 影响；
* Forbidden Bypasses。

不得为了更快获得局部结果而：

* 新建平行 generator；
* 新建 shadow pipeline；
* 新建未经授权的 fallback；
* 从弱证据重建权威领域结果；
* 用临时几何规则替代正式领域对象；
* 绕过 Application Service、Workflow、ArtifactService 或 Quality Check；
* 在测试中复制一套产品不会执行的处理逻辑；
* 只验证 helper，却不接入正式入口；
* 将实验 runner 当作正式产品实现；
* 将单个 case 的启发式写入通用路径。

例如，Detection/OCR bbox 可以作为定位、诊断或弱证据，但 bbox union、convex hull、矩形扩张等结果不得未经设计授权直接成为正式 container、BubbleInstance 或 cleaning region。

若现有链路无法支持目标，应停止实现并报告：

1. 当前 canonical path；
2. 当前 source of truth；
3. 缺失能力；
4. 现有 extension point 为什么不足；
5. 最小设计变更建议；
6. 受影响的合同、状态和测试。

不得自行补造替代链路后继续执行。

---

## 4. Harness Lite

实现任务应经过三个轻量检查点，不单独创建 `HARNESS.md`。

### Checkpoint A — Preflight

修改前确认：

* Task Mode；
* canonical path；
* source of truth；
* required reuse；
* allowed extension point；
* forbidden bypasses；
* 正式入口；
* 现有相关测试；
* 当前代码是否支持任务假设。

结果只能是：

* `PROCEED`
* `STOP_DESIGN_GAP`
* `STOP_SCOPE_CONFLICT`
* `STOP_WORKTREE_CONFLICT`

未得到 `PROCEED` 不得开始修改。

### Checkpoint B — Drift Check

首个可运行实现完成后检查：

* 是否新增平行 generator、pipeline 或 fallback；
* 是否把弱证据升级为 source of truth；
* 是否绕过正式 Service、Workflow、Artifact 或 Check；
* 是否只验证 helper；
* 是否改变未经授权的合同、状态或数据语义；
* 是否因实现困难改变了原问题；
* diff 是否超出预定范围。

发现偏航时停止，不得继续用补丁掩盖设计缺口。

### Checkpoint C — Conformance Review

交付前必须提供证据：

* 实际复用的正式链路；
* 修改的 extension point；
* 新增类、函数和文件的职责；
* 是否新增机制；
* 是否改变 source of truth；
* 是否存在设计偏离；
* 正式入口集成测试；
* 相关回归测试；
* diff 范围。

以下任一情况成立时不得声明完成：

* 正式入口未调用本次实现；
* 新增未经授权的平行机制；
* 改变 source of truth；
* 绕过 Quality Check 或 Workflow；
* 只有 helper 或临时 runner 测试；
* 实际需要 `DESIGN_CHANGE`，但未获得授权。

自我声明不能替代调用链、测试和 diff 证据。

---

## 5. 最低证据预算

Harness Lite 负责防止执行偏航；最低证据预算负责防止任务过早结束。二者都不规定执行时长。

### 实现任务

`IMPLEMENT_EXISTING_DESIGN` 在声明完成前，除非明确不适用，至少需要：

- 一条从正式入口到目标组件的真实调用链；
- 目标组件直接调用者和直接下游的检查；
- 对已有相关测试的阅读；
- 对 allowed extension point 的确认；
- 聚焦测试；
- 至少一项正式入口或集成路径测试；
- 对新增符号和调用路径的平行实现检查；
- 对完整 diff、测试收集范围和无关修改的检查；
- 未验证行为与剩余风险列表。

helper 测试、临时 runner、手工脚本和测试内拼装链路只能作为补充证据，不能替代主链路证据。

### 实验任务

`SPIKE` 在形成 Verdict 前，除非明确缩小范围，至少需要：

- 已冻结的问题、假设、baseline 和反证条件；
- 已冻结的输入、配置和工具版本；
- 预定样本覆盖率；
- 配置、输入输出标识和指标记录；
- baseline 或对照比较；
- 首个差异阶段定位；
- 失败样本检查；
- 结论边界；
- 完整、部分或无效运行状态。

未完成预定样本时，不得形成超出已有证据的最终结论。

### 重构与文档任务

`REFACTOR` 至少需要变更前基线、行为等价证据、相关回归、测试收集范围检查和完整 diff。

`DOCS` 至少需要事实核对、链接和路径检查、重复事实源检查，以及运行行为未变化确认。

### 设计变更

`DESIGN_CHANGE` 在实现前至少需要：

- 当前设计与缺口；
- 现有 extension point 不足的证据；
- 受影响合同、不变量、状态、数据和测试；
- 最小方案及主要替代方案；
- 迁移、回滚和验证策略；
- 维护者授权。

### 状态与例外

证据项统一标记为：

- `SATISFIED`
- `PARTIAL`
- `NOT_APPLICABLE`
- `BLOCKED`

`NOT_APPLICABLE` 必须给出原因。关键项为 `PARTIAL` 或 `BLOCKED` 时，只能报告部分完成或阻塞，不能声称完整完成。

最低证据预算不要求：

- 无关全仓库审计；
- 重复运行没有新增信息的测试；
- 创建新的过程文档；
- 扩大任务范围；
- 人为延长任务时间。

工程质量由证据完整性决定，不由运行分钟数决定。

---

## 6. 测试与验证

代码任务应先识别现有测试，适合时先补测试。不得修改断言、增加 skip、扩大 ignore 或缩小 pytest 收集范围来掩盖失败。

根据任务范围至少考虑：

* 正常路径；
* 失败路径；
* 边界条件；
* 幂等；
* 重启恢复；
* 部分失败；
* Provider refusal；
* stale propagation；
* 文件清理；
* 软删除；
* 导出阻断；
* 正式入口集成；
* 受保护数据安全。

实现任务至少需要两层验证：

### 局部验证

验证修改组件自身的正常、失败和边界行为。

### 主链路验证

证明：

```text
正式入口
→ 当前编排链路
→ 被修改组件
→ 正式候选或结果
→ 对应 Check 或 Workflow 接受路径
```

以下证据不能单独证明任务完成：

* helper 单元测试通过；
* 临时 runner 生成结果；
* mock 绕过正式编排；
* 测试直接构造最终对象；
* 单个样本视觉改善；
* fail-closed 正常触发。

若任务只完成底层能力，应明确写明：

> 底层能力已完成，正式产品主链路尚未接入。

无法运行测试时，必须说明具体原因、已执行的替代验证和剩余风险，不得虚构结果。

路径或仓库重构还需检查：

* Markdown 链接；
* fixture、CLI 和配置路径；
* 测试发现范围；
* `git diff --check`；
* 本地数据 ignore 状态；
* secret 是否进入 Git。

---

## 7. 独立复核

普通任务只需 Harness Lite。

以下情况增加一次独立只读复核：

* 修改 canonical processing path；
* 修改 source of truth；
* 新增正式 generator、Provider、Service 或领域对象；
* 修改 Workflow、ArtifactService、active pointer 或状态语义；
* 修改 Cleaning 或 Typesetting 核心算法；
* 修改恢复、导出或质量门禁；
* 迁移或删除受保护数据；
* diff 明显超出预定范围；
* Codex 自己报告存在设计偏离。

独立复核只回答：

* 是否遵守当前设计；
* 是否存在平行实现；
* 正式入口是否真实接入；
* 测试是否覆盖生产路径；
* 是否需要 `DESIGN_CHANGE`。

不默认生成 proposal、synthesis 或长期评审文档。

---

## 8. 文档与实验

当前事实只写入编号化文档。

普通任务不创建：

* GOAL；
* HARNESS；
* PLAN；
* GATE；
* FORM；
* proposal；
* cross-review；
  -独立 code-health report；
* 长期 handoff；
* 重复实验总结。

重要架构决定可以在对应当前文档中保留：

* 决定；
* 理由；
* 被拒绝方案；
* 风险；
* 验证；
* 开放问题。

只有需要长期、独立追踪的架构决定才建立 ADR。

实验代码进入：

```text
tools/experiments/<stage>/
```

只保留可复用的 runner、evaluator、config 和 helper。

本地输入、运行结果、模型和导出进入：

```text
data/local/
```

单次运行使用：

* `LOG.jsonl`
* `MANIFEST.json`
* `METRICS.json`
* `REPORT.md`
* `artifacts/`

单次 REPORT 只解释该 run，不充当算法规范、项目基线、Roadmap 或下一任务授权。

保留 tracked 实验工具和测试时，其直接依赖必须进入正式开发/实验依赖闭包。

---

## 9. 数据与安全边界

不得硬编码或记录 secrets。

外部输入必须：

* 验证格式；
* 限制上传类型；
* 防止路径穿越；
* 限制输出目录；
* 避免日志泄露原图、OCR、译文或 Provider 响应。

Debug artifact 可能包含敏感本地内容，必须显式标记并按本地数据处理。

以下内容属于 `PROTECTED_DATA`：

* 真实漫画原图；
* 日文、textless、中文对照数据；
* benchmark 原始素材；
* 人工 GT 和不可替代标注；
* 不可替代人工复核结果；
* 用户导出结果。

受保护数据迁移必须：

```text
登记源路径
→ 复制
→ 逐文件 SHA-256 验证
→ 更新引用
→ 再次验证
→ 删除旧副本
```

无法可靠判断的图片必须交由人工确认，不得根据 `sample`、`test` 或 `run` 等名称推断可以删除。

不得提交：

* `data/local/**`
* secrets
* 日志
* 缓存
* 构建输出
* 本地模型
* IDE 或 AI 工具配置

---

## 10. Git 与交付

开始前至少记录：

* branch；
* HEAD；
* `git status --short --untracked-files=all`。

工作区已有修改与当前任务范围重叠时，应停止并报告。

默认不执行：

* commit；
* push；
* pull；
* rebase；
* stash；
* reset；
* 覆盖用户修改。

仅在明确授权后提交。提交前必须审查 staged diff，不得未经检查直接 `git add .`。

最终交付至少包含：

1. Task Mode；
2. branch / HEAD；
3. 初始与最终工作区状态；
4. 实际读取的事实来源；
5. canonical path 和 source of truth；
6. 实际复用的组件；
7. 修改的 extension point；
8. 变更文件；
9. Checkpoint A/B/C 状态；
10. 是否新增机制或产生设计偏离；
11. 主链路集成证据；
12. 实际测试和验证；
13. 风险与未解决问题；
14. Git 操作状态。

没有验证不能声称完成。

---

## 11. 拒绝的做法

明确拒绝：

* 删除或隐藏测试来获得绿色结果；
* 让 Provider 管理持久化或流程决策；
* 让 UI 直接调用工具；
* 将历史运行报告继续作为当前权威源；
* 将弱证据升级为正式领域结果；
* 建立平行 generator 或 shadow pipeline；
* 用局部启发式绕过既有设计链路；
* 只通过 helper 测试便声明产品能力完成；
* 为普通任务自动扩张文档和流程资产；
* 为未来需求提前引入复杂机制；
* 用流程完整性掩盖证据不足。

工程质量通过以下证据验证：

* 小而可解释的 diff；
* 正式主链路集成测试；
* 清晰的 artifact、attempt、decision 和 provenance；
* 可恢复的 Git 历史；
* 明确的 source of truth；
* 可复现的测试和实验结果。

具体算法阈值、模型选择和部署方式由对应阶段设计决定，不在本文件中冻结。
