# Bubble-boundary topology review

状态：`IMPLEMENTATION_PRECONDITION_REVIEW`
范围：只评审 Stage A A1/A2 的物理气泡边界拓扑与安全合同；不改变 Slice 3、冻结输入、产品代码或验收。

## 结论

**结论：A2 可以作为“只读、保守分类器”进入受控实现，但当前没有任何依据把它视为 physical-boundary correction planner。** 其默认结果必须是 `unresolved_uncertain` / abstain；只有满足下述完整物理轮廓拓扑证据的像素才可标记 `proven_non_text_boundary`。即使该标记成立，也不授予写入权限：Stage B 仍须证明 `unresolved_uncertain=0`、`required_text` 全在 safe-edit、独立 validator 与人工 Gate 全通过。

这与冻结事实相符：g002 的 710/710、g004 的 70/70 unsafe required 都在真实 physical boundary corridor，且分别有 103/34 个 required 像素与 protected 重合。现有证据只证明 `dilate(text_core, 2)` 的 support 与边界带冲突，**不能**证明冲突像素是文字抗锯齿或可安全删除。

## 为什么不能复用 Slice F

Slice F 的对象是两个互斥 `BubbleInstance` 间的推断性 shared virtual boundary。它以 `primary_instance`、`neighbor_instance`、`current_virtual_boundary` 为输入；在两实例并集的有限 corridor 内，只移动 virtual-boundary/uncertainty，且 guarded required 一旦接触 `visible | protected` 就返回 `INCOMPLETE_REVIEW`。它不重分类真实可见结构，也不写 protected。

本 Spike 的对象则是单一 BubbleInstance 的真实、可见气泡轮廓：

- 不存在可竞争的 neighbor instance、shared separator 或可搬移的虚拟脊线；
- `required ∩ protected` 已非零，说明争议 support 已接触不可移动的真实结构；
- physical outline 是 source 图像的一部分，不能像 virtual separator 一样因文字 seed 而“让位”；
- 将 `protected` 伪装成 `current_virtual_boundary` 会改变 Slice F 输入语义，并命中其 `guard_conflicts_visible_or_protected` guard。

因此不得调用、改名复用或扩展 Slice F planner 来处理 g002/g004。若未来需要 B2，必须是新的 `physical-boundary` planner，拥有独立的 input contract、policy identity、single ordinal、replay 和 abstain 语义；本审查不批准该实现。

## A2：可接受的 ridge barrier 合同

### 输入与输出

输入固定为 hash-locked source、old required、text core、BubbleInstance mask、现有 protected/uncertainty，外加从 source 推导的梯度、方向、局部内外光度统计。输出必须保留 old required，并将其逐像素、互斥且穷尽地映射为：

```text
required_text
proven_non_text_boundary
unresolved_uncertain
evidence_error
```

同时输出 ridge mask、每个 ridge component 的 confidence/reason、与 protected corridor 的关联、方向/连续性/光度统计及输入/配置 hash。`safe`、`protected`、`uncertainty` 均为输入事实，A2 不得修改它们。

### physical ridge 的硬 guard

`gradient magnitude >= percentile` 本身不是 physical boundary 证据：文字主笔画、描边和装饰框同样可产生高梯度。一个像素或连通 ridge 只有同时满足以下条件，才可成为不可穿越的 physical-boundary barrier：

1. 位于 instance 内，且与既有 protected contour/corridor 连通或在固定、通用的容差内对应；
2. 在局部具有连续切线方向，不能只是孤立高梯度点或短文字笔画；
3. 能通过最小连续长度/曲率稳定性检查；若可见轮廓应闭合，则闭合性或与已知轮廓的接续必须成立；
4. ridge 两侧存在与 bubble interior/exterior 一致的光度/颜色转变，而不是仅有暗色笔画；
5. 不与高置信 text core 相交。相交、相邻竞争或方向/光度证据冲突一律不是“边界胜出”，而是 `unresolved_uncertain`；
6. 参数、阈值、连接性、容差和组件排序固定、可 fingerprint，且在 g002、g004 与全部控制中相同。

现有 `gradient_ridge()` 仅以 instance 内全局 92 分位梯度加 protected 构造 ridge，未验证上述方向连续、轮廓接续/闭合、内外跃迁或与 protected corridor 的拓扑关联。因此它可作为**候选 barrier 的原材料**，不能单独成为 `proven_non_text_boundary` 证据。实现应把未达到完整 predicate 的候选统一留在 unresolved；不得以 global percentile 或较小 unsafe ratio 调低门槛。

### 分类和 abstain

- `required_text`：仅限能由高置信 core 沿 old-required support 到达、路径不穿越 protected 或已证明 physical ridge、且具备局部文字外观/连通证据的像素。
- `proven_non_text_boundary`：仅限满足完整 physical-ridge predicate、且没有 text-core 竞争或可达文字路径的旧 required 像素；Stage A 人工标注前，该类别应保持空集或标为 provisional，不能驱动 Cleaner。
- `unresolved_uncertain`：任一弱/断裂 ridge、小尺度不够分辨、core-ridge 交叉、mixed component、多个 core 竞争、背景统计不足、A1/A2 不同意或无法穷尽解释时使用。
- `evidence_error`：shape/type/hash/配置不完整、非确定性或无法建立组件身份时使用，并令该 target `NO_GO`。

这不是静默 shrink mask：old required 始终保留为审计基线，每个移出 future `required_text` 的像素都带有上述明确分类和证据。任何 unresolved 像素仍保持 blocking，不能借由“未选中”成为 safe 或被 Cleaner 忽略。

## 控制测试与验收重点

所有 arm 复用同一实现、阈值和 policy fingerprint；不得读取 case/target/name/坐标。除现有 shape、partition、determinism、无 target-id 分支测试外，应在实现前补齐：

| 控制 | 必须结果 | 要防止的错误 |
| --- | --- | --- |
| case-71 ordinary interior-text | 不扩大 write domain；既有 PASS evidence 不退化 | 把正常文字或背景 ridge 误当 physical boundary |
| case-71 Slice F virtual-boundary accepted fixture | A2 不请求 neighbor/virtual rewrite、不改变 Slice F artifact；原 Slice F regression 保持 PASS | 把 virtual separator 混入 physical topology |
| 简单、远离边界的 BubbleInstance | required support 保持可审计；若证据不足则 abstain，不得引入新 unsafe | 以物理边界算法破坏 interior 路径 |
| 文字真实触碰 outline | contested component 全部 abstain；protected 零可写 | `false boundary-to-text`：把真实边界列为可清文字 |
| outline 被 dark-core 阈值命中 | core/ridge overlap 为 unresolved | 让暗色 outline 变成 text seed 后穿越 guard |
| 高梯度装饰框 | 不满足 bubble contour topology 时 abstain | 把任意高梯度线当气泡边界 |
| 小气泡 | 连续性/内外证据分辨率不足时 abstain | 低分辨率下伪造 ridge confidence |
| mixed text/boundary component | 不得拆成可写 text 或 proven boundary；保持 block | 用单一标签掩盖不可区分成分 |

g002/g004 的 A0 必须分别复现 `15802/15092/710` 与 `13133/13063/70`。人工 FORM 回填后，安全门禁至少为：人工确认的 boundary 被分类为 `required_text` 的数目为 0（`false boundary-to-text=0`）；任何 unresolved、protected conflict 或人工不确定均为 Stage A `NO_GO`，不进入 Cleaner。

## 被拒绝的替代方案

1. **直接复用 Slice F。** 输入拓扑和可移动对象不同，且会违反其 visible/protected guard。
2. **仅用梯度百分位作 barrier。** 无法区分文字笔画、装饰线与气泡轮廓。
3. **缩小 required 或扩大 safe。** 会掩盖 residue/结构风险，违反旧 support 的逐像素审计要求。
4. **A3 uncertainty-only 自动放行。** 它只能量化“避开 protected 后剩余文本是否可见”，不能证明 protected conflict 可删。
5. **按 g002/g004 分别调参。** 违反同配置与非 case-specific 要求，不能形成能力边界。

## 风险、验证与开放问题

### 风险

- 真实漫画中文字与 outline 相交或低分辨率，可能使所有严格 topology predicate 都 abstain；这是安全结果，不应通过放宽 ridge guard 回避。
- 当前 instance mask 的 contour 是 coarse topology evidence，并非像素级 bubble GT；必须将其只用作 ridge 关联约束，不能当作可编辑边界真值。
- A2 若将所有强文字笔画都当 ridge，可能产生大量 unresolved；这提示证据不足，而非可将这些像素归为 non-text。

### 验证场景

1. hash-locked 输入两次重放，组件 ID、分类掩码、evidence fingerprint 完全一致；
2. 修改任一 source/mask/config hash 后拒绝重放；
3. 对每个 old required pixel 验证四类精确分割；protected 永不进入 `required_text` 或 writable mask；
4. 注入 weak/broken/overlapping ridge，断言 `unresolved_uncertain`；
5. 对全部正负控制执行无 case-specific branch AST audit；
6. 若未来进入 Stage B，由独立 validator 从 source/candidate bytes 重算 actual changed、outside-safe、protected、uncertainty、boundary damage 与 residue，任一硬失败即 `NO_GO`。

### 开放问题

- 哪些固定、跨样本可复现的连续性/曲率/内外光度阈值足以支持 `proven_non_text_boundary`，仍待 Stage A 与人工 FORM 证伪；本审查不预设数值。
- g002/g004 是否存在零 unresolved 的通用子类尚未知；不应从其 unsafe 比例或组件大小推断。
- 若 A2 能完成 evidence 分离，是否需要 B1 evidence derivation 即可解决，或仍需独立 physical planner，必须由 Stage B 事实决定。

## 评审裁决

```text
IMPLEMENTATION_SCOPE = Stage A read-only A1/A2 evidence only
SLICE_F_REUSE = FORBIDDEN
PHYSICAL_PLANNER = NOT_APPROVED
DEFAULT_ON_AMBIGUITY = ABSTAIN
STAGE_B_ENTRY = only after human-confirmed false_boundary_to_text = 0
```
