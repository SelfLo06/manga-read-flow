# AGENTS.md

## 1. 项目与语言

本仓库是面向普通漫画读者的本地漫画翻译与基础嵌字工作流。

项目内沟通、任务报告和文档默认使用中文。代码标识符、协议字段和第三方技术名称可保留英文。

本项目只处理用户合法持有的本地内容，不提供漫画资源搜索、抓取、下载、分发或发布功能，也不实现规避第三方 Provider 内容策略的机制。

---

## 2. 默认上下文

普通任务默认只读取：

1. 本文件；
2. `docs/000-project/000-30-current.md`；
3. 与任务直接相关的一份阶段文档：
   `docs/100-stages/<stage>/NNN-00-*.md`。

按需追加：

- 产品范围：`docs/000-project/000-00-product.md`
- 架构边界：`docs/000-project/000-10-architecture.md`
- 里程碑：`docs/000-project/000-20-roadmap.md`
- 阶段注册：`docs/010-workflow/010-00-stage-map.md`
- Workflow：`docs/010-workflow/010-10-workflow-loop.md`
- 质量、修改与恢复：`docs/010-workflow/010-20-quality-review-recovery.md`
- 已知问题、实验或 Check：当前阶段目录下对应的 `-10`、`-20`、`-40` 文档

不要默认读取整个 `docs/`、全部实验报告或历史 Git 文件。

涉及真实实现时，必须检查相关代码和测试，不能只依赖文档或对话描述。

若文档、代码和测试不一致：

1. 明确指出差异；
2. 判断是实现偏离、文档过期还是设计未决；
3. 不得静默选择一方并继续扩大实现。

---

## 3. 任务模式

每个任务必须属于以下一种模式：

- `IMPLEMENT_EXISTING_DESIGN`
- `SPIKE`
- `REFACTOR`
- `DOCS`
- `DESIGN_CHANGE`

未明确指定时，默认：

```text
IMPLEMENT_EXISTING_DESIGN
```

### IMPLEMENT_EXISTING_DESIGN

沿当前设计和正式代码路径实现。

不得自行引入新的领域机制、平行数据流或替代 pipeline。

### SPIKE

用于验证高风险工具能力或算法假设。

Spike 可以探索替代方案，但：

* 不直接接入产品主线；
* 不更新正式 active pointer；
* 不登记正式 artifact；
* 不创建正式 QualityIssue；
* 不改变 Workflow 决策；
* 不宣称项目基线已经改变。

### REFACTOR

保持外部行为、接口合同、状态语义和测试语义不变。

不得顺带实现新功能或改变算法。

### DOCS

只修改文档。文档必须以当前代码、测试和维护者决定为依据。

### DESIGN_CHANGE

先说明当前设计不足及影响范围。未经维护者明确授权，不得进入实现。

---

## 4. 基本工作方式

* 默认最小变更。
* 不修改无关文件。
* 不做无关重构。
* 不升级无关依赖。
* 不以“顺手清理”为由扩大任务。
* 不通过修改断言、增加 skip 或缩小测试收集范围掩盖失败。
* 不因任务较长而自行放宽边界。
* 不因局部结果看似有效而绕开正式设计。
* 不为普通任务创建长期任务包、过程报告或重复事实源。

设计达到可实现、可验证、可演化时即可进入实现，不追求无限完备。

高风险能力优先通过 FakeProvider、受控 Spike 或最小垂直切片验证。

---

## 5. 设计链路绑定

实现任务开始修改前，必须识别并在工作记录中明确：

* Task Mode；
* Canonical Processing Path；
* 正式入口；
* Authoritative Inputs / Source of Truth；
* 必须复用的领域对象、Service 或组件；
* Allowed Extension Point；
* 对应的 Check 和 Workflow 接受路径；
* 下游依赖及 stale 影响；
* Forbidden Bypasses。

只描述“最终输出应该是什么”不足以开始实现。

## 执行自检 Harness

实现任务必须经过三个检查点。

### Checkpoint A — Preflight

修改文件前确认：

- Task Mode；
- Canonical Processing Path；
- Authoritative Inputs / Source of Truth；
- Required Reuse；
- Allowed Extension Point；
- Forbidden Bypasses；
- 正式入口和现有相关测试。

结果只能是：

- `PROCEED`
- `STOP_DESIGN_GAP`
- `STOP_SCOPE_CONFLICT`
- `STOP_WORKTREE_CONFLICT`

未得到 `PROCEED` 不得修改文件。

### Checkpoint B — Drift Check

完成首个可运行实现后检查：

- 是否新增平行 generator、pipeline 或 fallback；
- 是否从弱证据生成新的权威结果；
- 是否绕过正式 Service、Workflow、Artifact 或 Check；
- 是否只验证 helper，尚未接入正式入口；
- 是否改变了未授权合同、状态或 source of truth；
- 是否因实现困难而改变了原问题。

发现任一偏航时停止，不得继续用补丁掩盖设计缺口。

### Checkpoint C — Conformance Review

交付前必须提供证据：

- 实际复用的正式链路；
- 修改的 extension point；
- 新增类、函数和文件的职责；
- 是否新增机制；
- 是否改变 source of truth；
- 正式入口集成测试；
- 相关回归测试；
- diff 是否超出范围。

以下任一情况存在时不得声明完成：

- 正式入口未调用本次实现；
- 新增未经授权的平行机制；
- 改变 source of truth；
- 绕过 Quality Check 或 Workflow；
- 只有 helper 或临时 runner 测试；
- 实际需要 DESIGN_CHANGE，但未获得授权。

自我声明不能替代调用链、测试和 diff 证据。

### 禁止旁路

不得为了更快获得局部结果而：

* 新建平行 generator；
* 新建 shadow pipeline；
* 新建未经授权的 fallback；
* 复制一套与正式路径不同的处理链路；
* 用临时几何规则替代已有领域对象；
* 从弱证据重建权威领域结果；
* 把诊断数据提升为正式 source of truth；
* 绕过 Application Service、Workflow、ArtifactService 或 Quality Check；
* 让实验 runner 承担正式产品职责；
* 只测试新 helper，而不接入正式入口；
* 在测试中手工拼装一套生产代码不会执行的流程；
* 将单个样本启发式直接加入通用实现。

例如：

* Detection/OCR bbox 可以作为定位、诊断或弱证据；
* bbox union、convex hull、矩形扩张等结果不得未经设计授权直接成为正式 BubbleInstance、container 或 cleaning region。

### 设计不足时

若目标无法沿当前设计链路完成，停止相关实现并报告：

1. 当前 canonical path；
2. 当前 source of truth；
3. 缺失能力；
4. 现有 extension point 为什么不足；
5. 最小设计变更建议；
6. 受影响的合同、状态、数据和测试。

不得自行发明替代链路后继续实现。

---

## 6. 主链路验证

实现任务不能只证明新增函数或 helper 自身正确。

至少需要一项集成证据证明：

```text
正式入口
→ 当前编排链路
→ 被修改组件
→ 正式候选或结果
→ 对应 Check 或接受路径
```

测试必须证明正式代码路径真实调用了本次实现。

仅有以下证据时，不能声称实现完成：

* helper 单元测试通过；
* 临时 runner 产生结果；
* 手工脚本输出正确；
* mock 绕开了正式编排；
* 测试直接构造最终对象；
* 单个样本视觉上改善。

若当前任务确实只实现底层能力，应明确报告“底层能力完成，正式主链路尚未接入”。

---

## 7. 固定架构边界

除非维护者明确授权重新评审，保持以下边界：

* MVP 架构为本地 Web UI + FastAPI + 同进程 TaskRunner。
* WorkflowLoopEngine 独占 accept、retry、fallback、skip 和 block 决策。
* Quality Check 负责候选质量检测和问题归因，不负责 Workflow 决策。
* Provider Adapter 只负责外部工具调用。
* Provider Adapter 不访问数据库。
* Provider Adapter 不登记正式 artifact。
* Provider Adapter 不创建正式 QualityIssue。
* Provider Adapter 不决定 retry、fallback、skip、block 或 accept。
* ArtifactService 是正式 artifact 路径、hash、登记、保留和清理的唯一入口。
* Repository/DAO 是 SQLite 访问唯一入口。
* UI 只能通过后端用例调用产品能力。
* Import、Review/Edit 和 Export 必须保持明确的应用层生命周期职责。
* Check 通过不等于自动接受，最终接受由 Workflow Loop 决定。

发现实现方案破坏上述边界时，必须停止并报告，不能以局部测试通过作为豁免理由。

---

## 8. 数据与状态不变量

* 原图永不覆盖。
* SQLite 不保存图片 BLOB 或大型 payload。
* 每个 Project 的数据必须隔离。
* OCRResult、TranslationResult 和用户修改均版本化。
* 当前有效结果由 active pointer 选择。
* recovery 不能只依赖 `Page.status`。
* 每次 WorkflowAttempt 必须持久化。
* 失败 artifact 默认保留，除非通过正式清理规则处理。
* unresolved blocking QualityIssue 阻塞 normal export。
* warning export 由 ProcessingProfileSnapshot 决定。
* 人工修改创建新 revision/result，并传播下游 stale。
* API key 不进入 `project.db`、日志、报告或 Git。
* 文件访问必须防止 path traversal，并限制允许类型。

---

## 9. 受保护数据

以下内容属于 `PROTECTED_DATA`：

* 真实漫画原图；
* 日文、textless、中文对照数据；
* benchmark 原始素材；
* 人工 GT 和不可替代标注；
* 不可替代人工复核结果；
* 用户导出结果。

不得直接删除 `PROTECTED_DATA`。

迁移流程必须是：

```text
登记源路径
→ 复制
→ 逐文件 SHA-256 验证
→ 更新引用
→ 再次验证
→ 删除旧副本
```

无法可靠判断的图片必须标记为人工确认，不得根据 `sample`、`test`、`run` 等目录名推断可以删除。

可重建的 crop、overlay、preview、contact sheet、运行输出和缓存可以按任务授权清理，但必须与真实数据明确区分。

不提交：

* `data/local/**`
* secrets
* 本地模型
* 运行日志
* 缓存
* 构建产物
* 本地 IDE 配置

---

## 10. 算法与实验

必须区分：

* Observation
* Hypothesis
* Experiment
* Run
* Verdict
* Project Decision

不得把以下内容直接当作算法结论：

* 单个样本结果；
* Provider 成功返回；
* fail-closed；
* mask 外变化为零；
* 人工直觉；
* 单次相关性；
* 未执行阶段；
* 未定位首个分歧阶段的结果；
* 临时 generator 产生了合理输出。

实验应明确：

* 问题；
* 假设；
* baseline；
* 主要变量；
* 输入和配置；
* 指标；
* 反证条件；
* 首个差异阶段；
* 结论边界。

新实验运行按约定使用：

* `LOG.jsonl`
* `MANIFEST.json`
* `METRICS.json`
* `REPORT.md`
* `artifacts/`

`REPORT.md` 只解释单次 run，不自动成为：

* 算法规范；
* 项目基线；
* 里程碑裁决；
* 下一任务授权。

保留 tracked 实验工具或测试时，其直接依赖必须同时进入正式开发/实验依赖闭包。

---

## 11. 测试与验证

根据任务范围考虑：

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

执行测试前先确认测试发现范围没有被意外缩小。

不得通过以下方式获得绿色结果：

* 删除应保留测试；
* 增加未经授权的 skip；
* 扩大 ignore；
* 修改 pytest 收集规则隐藏失败；
* 修改断言迎合错误实现；
* 只运行新测试而忽略现有相关测试。

无法运行测试时，必须说明：

* 未运行的测试；
* 具体原因；
* 已执行的替代验证；
* 尚存风险。

不得虚构测试结果。

---

## 12. 文档治理

长期事实只写入已有编号文档。

普通任务不得默认创建：

* GOAL；
* HARNESS；
* PLAN；
* GATE；
* FORM；
* proposal；
* cross-review；
* 独立 code-health report；
* 长期 handoff；
* 重复实验总结。

需要更新文档时，优先修改：

* 当前状态文档；
* 对应阶段事实文档；
* 已知问题；
* 实验索引；
* Check 合同。

单次运行的日志和报告留在本地运行目录，不进入当前事实文档。

不要为了保留过程而建立新的 `docs/archive`。Tracked 历史由 Git 保存。

---

## 13. Git 与工作区

开始前至少检查：

* branch；
* HEAD；
* `git status --short --untracked-files=all`。

无关的未跟踪或已忽略文件本身不是停止条件，应保持不触碰。

若工作区已有修改与当前任务范围重叠，应停止并报告冲突。

默认不得：

* commit；
* push；
* pull；
* rebase；
* stash；
* reset；
* 覆盖用户修改；
* 清理无关文件。

只有用户明确授权时才提交。

提交前必须检查 staged diff，禁止未经审查直接 `git add .`。

不得提交：

* `.codex/`
* `.claude/`
* `.idea/`
* secrets
* 日志
* 缓存
* 构建输出
* 本地配置
* `data/local/**`

---

## 14. 停止条件

出现以下情况时停止相关实现：

* 当前设计链路无法支持目标；
* 需要新增未经授权的领域机制；
* 需要绕过正式 source of truth；
* 需要修改固定架构边界；
* 需要改变 Workflow 状态或决策语义；
* 需要修改测试来掩盖失败；
* 发现行为失败但任务只授权路径或文档修改；
* 受保护数据存在 hash 冲突或丢失风险；
* secret 可能进入 Git；
* 任务需要扩大到其他里程碑；
* 现有用户修改与任务范围冲突；
* 验证结果与预期不一致且原因不明。

停止时给出事实、影响和最小下一步，不继续扩大任务。

---

## 15. 交付要求

最终报告应包含：

1. Task Mode；
2. branch / HEAD；
3. 初始与最终工作区状态；
4. 实际读取的事实来源；
5. Canonical Processing Path；
6. Authoritative Inputs；
7. 实际复用的现有组件；
8. 修改的 extension point；
9. 变更文件；
10. 是否新增机制；
11. 是否存在设计偏离；
12. 主链路集成证据；
13. 实际运行的测试和验证；
14. 风险与未解决问题；
15. Git 操作状态。

没有验证不能声称完成。

若任务只完成底层能力、Spike 或设计准备，应明确说明尚未完成的产品主链路部分。