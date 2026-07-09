# 详细设计 Prompt Pattern

detailed-design prompt-patterns 是用于编写真正 prompts 的模板。它们本身不是真正的 prompts。

使用本模式准备未来设计任务，但不要每次都复制完整 Data Model 流程。

## 适用场景

- API design
- UI flow design
- Export design
- Real tool integration design
- Testing strategy design
- 其他在写代码前需要权衡分析的架构相邻决策

## 不适用场景

- 小型实现修复
- 机械文档清理
- 直接代码生成
- 依赖升级
- 已有 slice document 和 validation command 的产品代码任务
- 只需一份聚焦 design note 即可解决的任务

## 必需输入

- `AGENTS.md`
- `docs/SRS-v1.0.md`
- `docs/HLD.md`
- `docs/PROJECT-PLAN.md`
- 相关先前详细设计
- 与设计领域相关的现有 ADR
- 任务专属 `GOAL.md`
- 任务专属 `HARNESS.md`

如果 SRS、HLD、最终详细设计和任务文件冲突，prompt 应要求 agent 在编辑最终文档前报告冲突。

## 推荐输出

根据设计领域调整文件名，但保持输出集合小：

- `final/<design-area>-dd-v0.1.md`
- 可选的聚焦支撑说明，仅在它们能澄清 contracts 或 validation 时添加
- `final/open-questions.md`
- 重要已接受权衡的 ADR
- validation report 或 validation section

除非任务明确要求 multi-agent design round，否则不要生成 proposal、review 或 ADR 文件。

## GOAL 结构

好的 GOAL 应说明：

- design area 和目的；
- 它支持的产品阶段；
- in-scope decisions；
- out-of-scope decisions；
- 权威来源文档；
- 允许修改的文件；
- 禁止修改的文件；
- 必需最终输出；
- hard invariants；
- 预期 final report；
- commit rule。

GOAL 应足够窄，使设计可以完成，而不需要重新规划整个产品。

## HARNESS 结构

设计 HARNESS 应定义设计必须证明或解释什么：

- 必需场景；
- 架构不变量；
- ownership boundaries；
- failure 和 recovery behavior；
- 相关时的 readiness 或 export behavior；
- scope-control checks；
- final design acceptance criteria；
- 必须转为 open questions 的条件。

## 设计任务的 Harness 原则

- HARNESS 不是更长的 prompt。
- HARNESS 定义必须被证明或解释的内容。
- 对于设计任务，HARNESS 应将场景映射到 invariants、ownership boundaries、recovery behavior、export / readiness behavior 和 scope-control checks。
- 如果某个场景无法由设计证据证明，将其记录为 open question 或 implementation validation need。

## Proposal Agent 结构

只有当设计存在多个可信方案或多个风险面时，才使用 proposal agents。

每份 proposal 应包含：

- scope；
- role bias；
- assumptions；
- proposed model、contract、flow 或 policy；
- 当存在 scope risk 时的 P0 / P1 / P2 classification；
- ownership and boundaries；
- interaction with existing architecture；
- failure modes；
- 相关时的 recovery and idempotency impact；
- rejected alternatives；
- validation against HARNESS scenarios；
- risks；
- open questions。

Proposal agents 不应直接编辑最终设计文件。

## Cross-Review 结构

Cross-review 应查找：

- proposals 之间的冲突；
- 缺失概念；
- 未支持的 HARNESS scenarios；
- 被违反的 architecture invariants；
- ownership ambiguity；
- duplicated source-of-truth risks；
- over-design；
- under-design；
- 相关时的 migration、recovery、readiness 或 export gaps；
- blocking issues；
- non-blocking issues；
- ADR candidates；
- 阻塞 synthesis 的 open questions；
- 可延后的 open questions。

Cross-review 不应只是总结或润色。

## 有限 Revision Loop

只对 blocking issues 使用有限 revision loop。

规则：

- 设置最大 revision rounds；
- 只修改受 blocking review findings 影响的 proposal files；
- 添加 revision notes；
- proposal revision 期间不编辑 final design 或 ADR；
- 不静默删除 open questions；
- 达到限制后仍有 blockers 时，停止并报告。

对于小型设计任务，跳过此循环，让最终作者直接记录权衡。

## Synthesis 结构

Synthesis 应产出一个一致设计，而不是合并文档。

它应包含：

- selected design；
- rationale；
- rejected alternatives；
- scope boundaries；
- ownership boundaries；
- 相关时的 state、artifact、persistence、API、UI 或 provider impacts；
- failure behavior；
- 相关时的 recovery / idempotency behavior；
- scenario replay against HARNESS；
- risks and mitigations；
- ADR list；
- open questions。

## Harness Validation 结构

Validation 应对照 HARNESS 检查最终设计：

- invariants：pass / fail / unclear；
- scenarios：pass / fail / unclear；
- ownership boundaries；
- recovery behavior；
- 相关时的 readiness / export behavior；
- missing decisions；
- over-scoped decisions；
- implementation validation needs。

当设计属于基础性或高风险设计时，validation 应与 synthesis 分离。

## ADR / Open Questions 规则

- 只有对有真实备选方案的持久架构决策才创建 ADR。
- 不要为简单任务机制或措辞偏好创建 ADR。
- Blocking questions 必须在最终基线前解决。
- Non-blocking questions 可以保留在 `open-questions.md`，并标注 owner 或 future phase。
- 如果 unresolved question 影响 MVP-0 implementation，必须明确说明。

## 停止条件

遇到以下情况应停止并报告，不要强行产出设计：

- 权威文档冲突；
- 必需来源文档缺失；
- 没有设计能满足 hard invariant；
- 任务需要实现代码来证明设计；
- 设计会扩大当前产品阶段；
- 允许的 revision loop 后仍有 blocking open question；
- 请求的文件修改超出 allowed paths。
