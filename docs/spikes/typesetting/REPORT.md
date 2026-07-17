# 自动嵌字可行性 Spike 首轮报告

## 裁决

```text
CURRENT_TYPESETTING_INPUT_AND_VALIDATION_CHAIN: NO_GO
AUTOMATIC_TYPESETTING_DIRECTION: NOT_REJECTED
LAYOUT_OPTIMIZATION: BLOCKED_BY_INPUT_CONTRACT
```

本轮只证明：在当前输入合同下，机器指标不能可靠代表真实气泡内排版，且 Typesetting 结果不足以解释文字组如何进入、合并或排除。不得把该结论扩大为“规则式自动嵌字不可行”。

## 范围与证据

- 页面：`case-71`、`case-72`。
- 候选：R0（bbox）、R1（region-aware）、R2（R1 + 样式继承）。
- 文字：预声明中文排版探针，不是真实翻译。
- 人工证据：`data/local/typesetting-feasibility-v0.1/review-runs/r0-r1-r2-v0.4/FORM.md`。
- 机器证据：同目录的 `matrix.json`、逐页 `result.json` 和 `comparison.png`。

表单总体选择为 `NO_GO`，优先改进项为 `typesetting region 输入`。

## 已确认事实

### case-71：输入粒度与排版密度均有问题

S1 将右侧大气泡范围内 7 个 fragment 统一记录为 `case-71__g002`，其 bbox 为 `(906, 453, 233, 356)`；Goal 6 又将其记录为单一 `container-002`。本轮 harness 按一个 container 分配一条 probe text。因此现有证据更接近：

```text
两个视觉文字段
→ S1 已表示为一个 group
→ 一个 container
→ 一条 typesetting probe
```

这不是已经证明的“Typesetter 随机漏画”，而是上游 grouping、同容器多段表示和 probe 构造共同造成的信息不足。当前结果没有持久化 `fragment_ids → text_group_ids → container_id → typesetting_block_id` 映射，无法可靠区分错误合并与有意的同容器多段。

人工观察同时确认：字号与文字占用率偏高、留白不足、自然断句和视觉中心不稳定。R2 相对 R1 更好，但仍需返工。

表单中 case-71 同时勾选了 `ACCEPTABLE`，自由文本却写明“整体仍需返工”。该内部不一致原样保留；按文字描述更接近 `REVIEW`，但本报告不修改人工原始证据。它不改变总体 `NO_GO`。

### case-72：region 语义错误导致 validator 假通过

人工观察确认 R1/R2 文字越过真实气泡边界，而结果仍报告：

```text
overflow_ratio = 0
boundary_touch = false
minimum_inner_margin > 0
```

当前 harness 没有消费冻结的真实 bubble/typesetting mask。旧资产未持久化 coarse context mask，harness 从 Goal 6 诊断 overlay 恢复 context union，再用 S1 group seed 做归属。机器指标只证明 glyph 位于这个恢复 region 内，不能证明 glyph 位于真实气泡内。因此这是输入 region 语义错误引起的 validator false negative，而不是通过调字号即可修复的问题。

case-72 的 7 个 Goal 6 context 去向已有上游证据：

| Context | 风险 | 上游处理 | Typesetting v0.4 |
|---|---|---|---|
| 001 | E1 | E1-only 写回 | 进入 |
| 002 | E3 | SKIP | 未进入 |
| 003 | E3 | SKIP | 未进入 |
| 004 | E1 | E1-only 写回 | 进入 |
| 005 | E2 | comparison-only | 未进入 |
| 006 | E1 | E1-only 写回 | 进入 |
| 007 | E2 | comparison-only | 未进入 |

所以 3 个 eligible context 并非完全无解释的静默丢失；阻塞点是 Typesetting `result.json` 只列进入者，没有携带 002/003/005/007 的 exclusion reason，也没有形成从 source fragment 到最终 block 的统一账本。页面仍有原文残留，说明当前 E1-only 输入不具备整页完成度。

## 当前不能宣称

- 不能宣称 R1/R2 已通过真实气泡边界验证。
- 不能宣称 8 个 E1 context 完整覆盖原始文字实例。
- 不能用 `overflow_ratio=0` 证明视觉安全。
- 不能把 OCR 成功等同于 Detection、Grouping、Association、Cleaning 和 Typesetting 均成功。
- 不能进入全局字号、换行或样式阈值冻结。
- 不能接入 Workflow 或进行整书推广。

## 下一验证路径

下一轮应是 **Typesetting Input Contract & Validator Grounding Spike**，而不是继续优化排版观感：

1. 为每个 source fragment、text group、container、cleaning context、translation segment 和 typesetting block 建立稳定 ID 映射。
2. 对 merged、excluded、unassigned、risk downgrade 和 abstention 保存明确 reason。
3. 输入模型允许一个 container 对应多个 text group / paragraph，不默认压成单一字符串。
4. 直接持久化独立 `typesetting_region`；禁止从展示 overlay 反推正式 region。
5. 用人工确认的真实气泡边界做正反例：安全排版应通过，故意越界/触边必须失败。
6. region 与 validator 对齐后，才继续占用率、留白、自然断句、视觉中心和样式继承。

## 风险与开放问题

- 一个容器内多个原文字组应保持多个 block，还是合并为带段落约束的单 block？
- `typesetting_region` 应来自独立容器感知结果，还是由 container mask 内缩并附带置信度？
- E2/E3 未清字区域是否应完全阻止 Typesetting，还是允许保留原图并产生局部 QualityIssue？
- 开发期人工真实边界只用于验证，不得演变为产品运行期必填步骤。

## 最终结论

自动嵌字仍值得验证，但当前优先级已从“优化换行和字号”切换为“冻结可追踪输入合同并使 validator 对真实 region 有效”。在该门禁通过前，任何排版美学优化都不能作为产品证据。
