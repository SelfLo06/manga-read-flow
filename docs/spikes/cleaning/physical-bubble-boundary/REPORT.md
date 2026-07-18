# Physical Bubble Boundary Spike Report v0.1

## Stage A 结论

Stage A 已完成 hash-locked 输入重放、A1/A2/A5 只读分类与维护者逐组件 FORM。人工标签是评估 oracle，不是算法输入：它不能直接修改 `required`、`safe`、`protected` 或 `uncertainty`。

维护者结论显示：g002 的大部分争议组件为文字边缘，g004 的两个组件为真实气泡边界；另有 2 个 g002 像素仍为 `UNCERTAIN`。这证实当前 fail-closed blocker 不是“彩色字体”归因，也不授权降低全局阈值。

## 通用能力评估

每个 arm 必须同时满足：

1. 不把人工 boundary/uncertain 像素分类为 `required_text`；
2. 覆盖全部人工确认、允许保留的文字边缘；
3. 证明全部人工 boundary 像素为 `proven_non_text_boundary`；
4. 不存在人工 unresolved/mixed 像素。

历史 Stage A `v0.2` evidence 中，A1 在人工争议组件的 text precision 为 `1.0`，但 text recall 仅为 `0.40677966`，仍有 420 个确认文字像素 unresolved；另有 2 个非文字、人工不确定像素曾被给为 `required_text`。该历史记录保持不可变。审查后，当前 A1 实现已将 uncertainty 纳入硬 barrier，并以回归测试禁止任何 arm 将 uncertainty 认证为 `required_text`；这项 fail-closed 修复不改变历史 `NO_GO`，也不授权生成新 candidate 或进入 Stage B。A2/A5 保持更保守的 abstain，text recall 均为 `0`。g004 的 70 个人工确认 boundary 像素在三个 arm 中均 unresolved，没有自动 boundary proof。

因此结论不是“人工标签可直接修正 mask”，而是：当前通用证据不足以安全构造新的 physical-boundary protected/safe revision。任何 Stage B correction、Cleaner 调用或 Slice 3 集成都会违反 fail-closed 合同。

## 边界保持

- 未修改 Slice 3、现有 run、schema/migration、artifact metadata 或 active pointer。
- 未运行 Cleaner、Composer、validator 或 acceptance。
- 未调用 Slice F virtual-boundary planner；未创建 correction reservation。
- `protected` 仍不可写，`required` 未缩小，`safe` 未扩大。

本报告所引用的完成 FORM 与自动评估 evidence 位于 gitignored 本地输出目录；输出锁记录 human FORM 这一预期的 post-lock 变更，其余 Stage A material 均保持 hash-valid。

## 决策、拒绝方案与风险

**决策**：终止本 Spike 于 `NO_GO`，不进入 Stage B。g002 仍有 103 个 human-confirmed text-edge 像素位于 frozen `protected`；g004 的 70 个争议像素均是 high-risk physical boundary。现有 A1/A2/A5 既没有建立完整、安全的 text support，也没有建立通用 boundary proof。

**拒绝方案**：不以人工标签直接改 safe/protected；不缩小 required；不扩大 safe；不按 g002/g004、左缘、蓝/橙色或坐标调参；不把 physical boundary 伪装成 Slice F virtual boundary；不运行一次“试试看”的 Cleaner。它们都会绕过而非验证 fail-closed 合同。

**主要风险**：把 `ALLOW_AS_REQUIRED_TEXT=YES` 误解为允许写 protected；把 g004 的窄组件或低 unsafe ratio 当作安全依据；把深蓝文本观察错误外推为颜色根因；把 Stage A no-write 指标误报为 Cleaning PASS。

## 验证与开放问题

- Stage A focused tests：`8 passed`；覆盖 mask/type、deterministic replay、component ordering、无 case/target branch、正/负 physical-boundary 与颜色控制，以及冻结 case-71 interior／既有 support 对照的 fail-closed 行为。对照仅检验 evidence 不越出旧 required、protected 或 uncertainty，绝不产生写权限。
- `human-review-lock.json` 锁定完成 FORM，`stage-a-evaluation-lock.json` 锁定自动评估；原 review-material manifest 的 FORM mismatch 是人工填写后预期的 pre-label 版本差异，其他 110 项保持匹配。
- 未解决：若未来研究继续，必须在新授权范围内先获得通用 physical-boundary pixel GT / controls，并证明 g002 类别的 protected-text separation；不得复用本轮人工标签作为产品规则。
