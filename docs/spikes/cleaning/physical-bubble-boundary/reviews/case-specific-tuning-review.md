# Stage A Case-specific Tuning Review

状态：`PASS（无发现的 case-specific algorithm tuning）`；该结论**支持 Stage A `NO_GO`**，并不构成能力通过。

审查范围仅限 Stage A 的 `tools/spikes/cleaning/physical_boundary/`、对应 tests、Spike 文档及 hash-locked 本地 Stage A 输入／人工评估。未读取其他 reviewer 文档，未改动产品、Slice 3、FORM、GATE 或 REPORT。

## 审查问题与决定

**决定**：接受 A1/A2/A5 的算法实现在当前证据下为同一通用路径；未发现按 case id、target id、文件名、固定坐标或颜色名称改变像素分类／阈值／写入资格的逻辑。Stage A 的既有 `NO_GO` 应维持，因为这种“未专调”结论不能弥补文本覆盖、物理边界证明和 unresolved 方面的安全缺口。

**理由**：

1. [`evidence.py`](../../../../../tools/spikes/cleaning/physical_boundary/evidence.py) 的三种分类函数只接收 `source_rgb`、`old_required`、`instance`、`protected`、`uncertainty`；模块内不存在 case／target／filename／坐标输入，也没有 `case-72`、`g002`、`g004` 字面量。
2. A1、A2 使用同一 `luminance_max=180`、instance 内局部梯度第 92 百分位 ridge 和掩码连通性；A5 使用同一 Lab 局部背景中位数、core 距离第 20 百分位与 `max(4.0, ...)` 下界。它们都是每个输入实例的图像统计或全局固定 policy 参数，不依 target 选择不同值。
3. A5 没有深蓝／橙色／HSV 区间或颜色名称判断。颜色只通过 RGB→Lab、局部背景中位数和欧氏距离参与候选像素证据；`protected`、ridge、`uncertainty` 仍是通用 hard guard。`color_evidence()` 的 `deep_blue`／`orange`／`antialias_edge` 仅为报告所需的待人工标注分层，未被分类函数读取。
4. Stage A 锁定评估的所有 arm 仍将 `proven_non_text_boundary` 保持为零，未通过任何样本标签将 protected／uncertainty 改为可写，故不存在以样本结果反向扩大 safe 或缩小 required 的路径。

## 样本选择与算法决策的边界

[`run_stage_a.py`](../../../../../tools/spikes/cleaning/physical_boundary/run_stage_a.py) 固定 `case-72` 冻结根目录，默认列出 g002/g004。这是本受限 Spike 的**实验 fixture selector**：它读取已冻结 bytes、为这两个受审 target 生成可视化与 component id，并将相同的 mask 数组传入 A1/A2/A5。它不把 target 字符串传给 `classify_a1`、`classify_a2` 或 `classify_a5`，也不据此选择 policy、阈值、颜色分支或 correction 行为。

同样，[`evaluate_stage_a.py`](../../../../../tools/spikes/cleaning/physical_boundary/evaluate_stage_a.py) 读取目标和人工 `COLOR_STRATUM` 仅用于按组件汇总指标与报告 `NO_GO` 原因；它不调用 evidence classifier，也不产出 safe-edit mask、Cleaner candidate 或 write decision。评价文本中出现 g002/g004 是对已经锁定的实验结果的描述，不能构成算法分支。

因此，目标选择的 case-specific 性质在本实验范围内是允许且可追溯的；禁止的是把该身份信息流入 evidence policy 或写入决策。审查中未见后者。

## 复核证据

| 复核项 | 结果 | 证据 |
| --- | --- | --- |
| 算法身份分支 | PASS | 静态 AST／字面量审计：`evidence.py` 无禁止标识符，也无 g002/g004/case-72 字面量；其输入签名无身份字段。 |
| 运行器身份分支 | PASS（fixture-only） | 运行器含冻结路径和默认 target 列表，但仅用于读取材料、目录／FORM 名称与循环；没有 target 条件分支。 |
| 坐标专调 | PASS | 唯一坐标计算是从实际 unsafe component 推导 crop bounds，且只用于 review 图像；分类器不接收坐标。 |
| A5 颜色专调 | PASS | 仅 Lab 局部距离；无蓝／橙色名称、RGB/HSV 色段或分层驱动的阈值／分支。 |
| 人工标签反灌 | PASS | evaluator 只统计已生成的 `a*_required_text`／`a*_unresolved`；不重算或修改 evidence。 |
| 锁定评估完整性 | PASS | `stage-a-evaluation.json` SHA-256 与 `stage-a-evaluation-lock.json` 一致；`human-review-lock.json` 与 FORM 一致；review-material manifest 的非 FORM 110 项均一致。 |
| 定向测试 | PASS | `python -m pytest -q tests/spikes/cleaning/physical_boundary`：`7 passed`。 |

## 与 `NO_GO` 的关系

“没有 case-specific tuning”只是必要的负向审计结论，不足以授权 Stage B。锁定评估仍显示：

- A1 的 disputed-text recall 为 `0.40677966`，420 个确认文字像素 unresolved，且 2 个 `UNCERTAIN` 像素进入 `required_text`；
- A2/A5 的 disputed-text recall 均为 `0`；
- g004 的 70 个人工确认 physical boundary 像素在 A1/A2/A5 中均 unresolved，未获通用 `proven_non_text_boundary` 证明；
- g002 存在人工确认文字边缘落在冻结 protected corridor，protected 仍不可写。

这些是没有依赖 target 专调也依然成立的 fail-closed 缺口。故本审查的结论是：`CASE_SPECIFIC_TUNING = NOT_FOUND`，`STAGE_A_DISPOSITION = NO_GO_SUPPORTED`，`STAGE_B = DENIED`。

## 拒绝的解释与风险

- 不把默认 g002/g004 fixture 列表误报为算法专调：那会混淆受限实验的输入选择与 evidence policy。
- 不把“无专调”误报为通用能力证明：当前控制矩阵和人工标签只足以否定放行，不足以证明物理边界分离。
- 不把 A5 的 Lab 参数误报为“颜色无关”：A5 本来就是颜色 evidence；本审查证明的是没有按颜色**名称／样本**选择不同规则，而不是证明其参数从未受实验设计影响。

主要剩余风险是静态审查无法证明固定通用参数在历史上从未参考过样本；但当前代码和锁定 replay 均表明它们在 g002、g004 与测试控制中走同一实现。若未来新 Spike 继续，应预先固定 policy 参数和独立控制集，再做同样的 identity-flow audit。

## 验证场景与开放问题

- 已验证：深蓝、橙色 synthetic control 均调用同一个 `classify_a5` 路径；真 physical outline 即使足够深色也被 protected hard guard 留为 unresolved。
- 已验证：评估中的 `COLOR_STRATUM` 只影响 metrics 的分组键；不能影响 prediction。
- 未解决：现有 Stage A 评价是“维护者标注的争议组件”范围，不能证明全页或未来样本的 precision/recall，也不能替代对新参数设定来源的预注册。
