# Text-Seeded Container Association Spike — GOAL

版本：v0.3
状态：R0 Semantic + Topology + S1 Input Frozen / Association 未实施
适用范围：文字种子驱动的容器关联、虚拟边界、自由文字支持区与弃权能力验证

## 1. 文档定位

本轮只设计 `Text-Seeded Container Association Spike`，不实现算法、不运行实际 Cleaning、不生成 benchmark manifest，也不接入正式产品路径。

事实与决策的优先关系为：

```text
AGENTS.md / SRS / HLD / PROJECT-PLAN
→ 项目与架构边界

algorithm-lock-v0.1.md
→ 本 Spike 的算法、对照、指标与门禁事实来源

CLEANING-HANDOFF.md
→ 当前阶段、暂停项与下一步入口

CLEANING-DESIGN-RATIONALE.md
→ 维护者原始意图及决策理由

各 REPORT / GATE
→ 已发生实验的证据
```

Cleaning 主 REPORT 曾在 oracle mask 小样本上认为 restricted solid fill 有有限证据；之后的 Real Bubble Fill Follow-up 在真实页上得到 `0/8 ACCEPTABLE`，并发现 allowed mask 的语义越界。Handoff 与 Algorithm Lock 已明确以后者为当前结论：`restricted AUTO_FILL = disabled`。这是有明确先后关系的结论更新，不是未解决冲突。

## 2. 对维护者核心思路的准确复述

本 Spike 不从“先检测完整气泡”开始，也不把 Cleaning 简化成 inpainting。它从高召回的文字 fragment 出发：先形成保守文字组，再在局部图像图上让多个文字组作为独立 source 同时传播，搜索其所属的真实容器或局部支持区域。

当不同 source 的传播前沿相遇时，竞争脊线只产生“虚拟边界候选”。在接受该边界前，必须先判断多个文字组是否属于同一容器：同容器证据高时合并 source 后重新传播；异容器证据高时保留独立前沿与虚拟边界；证据不充分时输出 `uncertain / REVIEW_REQUIRED`，不能强制合并或拆分。

对没有气泡或旁白框的文字，算法不得伪造气泡。它只能依据文字尺度、背景方差、纹理、结构距离、其他文字组和传播代价生成动态、自适应、有限的 `support_region`；复杂自由文字、艺术字和拟声词应进入 `REVIEW_REQUIRED` 或 `SKIP`。

OCR 在这里是位置与结构先验，不是真值字符串。即使 OCR 字符串错误，只要 fragment 的位置、方向、尺度、分组与完整性证据仍有用，就可以帮助容器关联。反之，OCR 文本正确也不能证明区域完整、像素 Mask 完整或 Cleaning 安全。

本 Spike 到 `text_group + container/support association` 为止。只有该关联通过门禁后，下一项独立 Spike 才可在局部 ROI 内研究像素级文字 Mask；再之后才可研究 protected mask 与 safe edit region。任何阶段证据不足都必须主动弃权，不能以提高覆盖率为理由输出低风险候选，更不能执行清字。

## 3. 已验证事实 / 已冻结决策 / 待证假设

“已冻结决策”表示冻结为本 Spike 的实验约束，并不表示算法效果已经被证明。

| 类别 | 条目 | 证据或本轮含义 |
| --- | --- | --- |
| 已验证事实 | Detection/OCR 小样本中 real core detection 为 `16/16 hit`，但 `13/16 fragmented`。 | 文字位置具有候选价值；不能外推为真实大规模 `99%` region recall。 |
| 已验证事实 | Detection/OCR 的 synthetic core 有 `1` 个 complex-background miss。 | 上游漏种子真实存在，必须有 S2 与 abstention。 |
| 已验证事实 | Grouping 小样本为 synthetic `10/11`、real core `16/16`，reading-order error `0`。 | 纯几何 grouping 可作为初始基线。 |
| 已验证事实 | Grouping 仍产生 `9` 个 real extra groups，且未覆盖接触气泡、复杂容器与 hard-09。 | extra / auxiliary / uncertain 必须是一等输出；已有 PASS 不能替代本 Spike。 |
| 已验证事实 | oracle mask 下，简单白色/近白区域曾出现可接受 fill；OpenCV inpaint 未证明稳定优于 fill。 | 只证明给定正确 mask 时极简单重建可能成立，不证明自动 Cleaning。 |
| 已验证事实 | 真实气泡 follow-up 的 A 类为 `0/8 ACCEPTABLE`。 | restricted `AUTO_FILL` 继续关闭。 |
| 已验证事实 | 真实 follow-up 中像素级 outside/protected 检查可以通过，但 allowed mask 仍语义越界到手部/背景。 | “遵守 mask”不等于“mask 语义正确”或“视觉安全”。 |
| 已验证事实 | Benchmark Pilot 的旧 48 个 region candidates 因 `incomplete_text_instance` 失败。 | 旧 difference components 不得作为容器或文字实例 GT。 |
| 已验证事实 | 后续 10 个完整实例候选仍未通过所有人工门禁；hard supplement v1 失败。 | 当前没有可直接冻结的正式 Cleaning region benchmark。 |
| 已验证事实 | `hard-09` 暴露跨相邻容器错误合并；`hard-12/13` 是 not-text 正例误分类证据。 | 这些只能作为重新标注的回归候选，旧 mask 不能升格为 GT。 |
| 已冻结决策 | 从文字 fragment / 保守 group 出发搜索容器或支持区。 | 不改写为通用 bubble detector。 |
| 已冻结决策 | 使用 SLIC superpixel graph、multi-source geodesic propagation 和 geodesic Voronoi ridge 作为 P1。 | 多源竞争是主候选，不是独立 dilation。 |
| 已冻结决策 | 建立虚拟边界前必须先做 same-container 判断。 | 防止同一气泡多列文字被错误拆分。 |
| 已冻结决策 | 高置信结构为 hard barrier，中低置信结构为 soft cost。 | 不把所有强边缘都当硬墙。 |
| 已冻结决策 | 容器类型固定为 `explicit_container / implicit_container / free_text / uncertain`。 | `free_text` 输出动态 support，不输出假 container。 |
| 已冻结决策 | `uncertain / REVIEW_REQUIRED / SKIP` 是正式输出。 | 风险优先于覆盖率；本轮不存在 `AUTO_ACCEPT`。 |
| 已冻结决策 | B0 / B1 / P1 / P2 与 S0 / S1 / S2 / S3 为固定实验轴。 | 不在实现中临时替换对照或删除污染条件。 |
| 已冻结决策 | 本 Spike 不生成文字像素 Mask、safe edit region 或重建图。 | 这些只作为后续独立门禁。 |
| 待证假设 | 高召回文字种子足以显著缩小容器搜索空间。 | 比较 S0、S1 下的 region 正确率、leakage 与 abstention。 |
| 待证假设 | 多源竞争可降低接触气泡 false merge，并在断裂/接触处产生有意义的虚拟边界。 | hard-09 与至少 5 个相邻/接触案例是关键。 |
| 待证假设 | same-container 判断可保住同一气泡的多列文字。 | 至少 5 个同容器多列案例，观察 false split。 |
| 待证假设 | 自由文字可得到稳定、有限的动态 support region，而不吞入背景结构。 | 至少 3 个简单标签，并对复杂自由文字弃权。 |
| 待证假设 | seed 缺失或污染时，系统能降低置信度并正确 abstain。 | S2 / S3 的目标不是保持覆盖率，而是消灭 false-low-risk candidate。 |
| 待证假设 | P1 相比 B0/B1 有实际安全收益；P2 只在 P1 不确定区域有增益。 | 必须用同一输入、同一 GT 和冻结参数比较。 |

## 4. 核心目标

验证以下链路是否足以进入后续 `Pixel Text Mask Spike`：

```text
fragment geometry
→ conservative initial grouping
→ same-container evidence
→ multi-source container/support propagation
→ visible + virtual boundary
→ explicit / implicit / free_text / uncertain
→ confidence + abstention
```

本 Spike 必须回答：

1. 已知完整或真实文字 seed 时，能否找到合理、完整且不过度泄漏的容器/支持区？
2. hard-09 与其他接触气泡能否避免跨容器合并？
3. 同一气泡多列文字能否避免错误分割？
4. 边界断裂或遮挡时，可见边界与虚拟边界能否共同限定区域？
5. 简单 free text 能否得到有限 support region，复杂 free text 能否被拒绝？
6. not-text、漏 seed 与 false-positive seed 能否触发正确 abstention？
7. P1 是否比 B0/B1 更安全；P2 是否只在 P1 不确定子集上产生无安全回退的收益？

## 5. 成功含义

本 Spike 的最高正向结论只能是：

```text
GO_TO_PIXEL_TEXT_MASK_SPIKE
```

它只表示容器/支持区关联值得进入下一独立验证，不表示：

- Cleaning 可用；
- 文字 Mask 可用；
- safe edit region 可用；
- restricted fill 可重开；
- CleanerProvider 可设计或集成；
- 任何候选可自动清字或自动接受。

## 6. In Scope

- 文字 fragment 几何、方向、尺度、detector score 与 grouping evidence；
- 保守初始 grouping 和 alternative grouping；
- 局部 ROI 与只读图像特征；
- B0、B1、P1、P2；
- same-container / different-container / uncertain 决策；
- explicit / implicit / free_text / uncertain 分类；
- visible boundary、virtual boundary 与 support region；
- S0、S1、S2、S3；
- 可重复指标、overlay、失败分类和人工审查；
- abstention 与 risk–coverage 分析。

## 7. Out of Scope

- 像素级文字 Mask 的生成或优化；
- protected mask、safe edit region 和 effective edit mask；
- fixed fill、border-sampled fill、Telea 或任何实际 Cleaning；
- LaMa、Diffusion、ControlNet、FFT 网点重建及通用 inpainting；
- CleanerProvider、ArtifactService、Repository、SQLite、QualityIssue 或 Workflow 集成；
- Typesetting；
- benchmark manifest；
- `AUTO_ACCEPT` 或恢复任何自动清字策略；
- 依赖升级、生产性能优化、UI/API；
- 未经授权的 commit、push、pull、rebase。

## 8. 关键理由与已拒绝替代

| 决策 | 理由 | 拒绝的替代 |
| --- | --- | --- |
| 先验证 association，再验证 text mask。 | 真实 follow-up 已证明 mask 语义错误会使像素安全检查失效。 | 同时实现完整 Cleaning 链路。 |
| 使用多源竞争。 | 接触容器需要相对归属，而非每组独立扩张。 | 独立 bbox/dilation 作为主方案。 |
| same-container 先于虚拟边界接受。 | 同一气泡可能有多列文字。 | 前沿一相遇就硬切。 |
| free text 只生成 support region。 | 支持区是计算上下文，不是对真实气泡的断言。 | 将所有文字拟合成闭合气泡。 |
| hard / soft barrier 分离。 | 边缘证据有置信度层级，断裂边界和线稿不能用单一阈值处理。 | 所有强边缘都不可穿越；或线性相消 interior/protected 分数。 |
| 弃权为一等结果。 | 当前最严重风险是 false-low-risk candidate。 | 为追求覆盖率强制 merge、split 或归类。 |
| B0/B1 保留。 | 必须证明复杂 P1 相对简单基线有可测收益。 | 只展示 P1 成功案例。 |
| P2 按条件运行。 | Random Walker 只用于 P1 边界不确定子集。 | 将 P2 作为默认路径掩盖 P1 失败。 |

## 9. 风险

- 初始 grouping 与 container association 存在循环依赖，可能在迭代中振荡；
- SLIC 尺度可能切断细边界或把文字、边框与背景混入同一 superpixel；
- broken boundary 处的软代价可能导致大范围泄漏；
- same-container 模型可能以高置信错误合并相邻气泡，或拆分同一气泡多列；
- free-text support 可能退化为固定 dilation，吞入人物/线稿；
- detector seed 的漏检、误检和 extra group 可能被错误包装成低风险区域；
- 小样本人工 GT 可能存在边界歧义；
- 使用旧 difference mask 或失败 supplement 结论会造成 GT 泄漏或错误验证。

## 10. 当前实例决策与剩余开放项

维护者已撤回 v0.2 的过早冻结；`FREEZE.md` 仅保留为历史记录。扩大候选筛选、A/B 独立选择题与 coordinator 裁决现已完成。v0.3 的 R0 source、ROI、crop identity、semantic labels 与 container topology 已冻结；Annotator A overlay 冻结为 coarse target-region reference。详见 `R0-SELECTION-v0.3.md` 与 `R0-ADJUDICATION-v0.3.md`。

下列事项仍未冻结：

- pixel-accurate visible / virtual boundary GT；
- visible / virtual boundary uncertainty-band 数值；
- pixel-accurate R0 scoring protocol；
- P1 相对 B0/B1 的 R0 实际安全收益；
- expanded validation 的 R1 / S2 / S3 设计（当前最小 Spike 延后）。

剩余开放项不得在实现中静默猜测：

1. R0 只允许使用分类、容器数量、same/different topology、跨容器泄漏、abstention 与相对 A coarse reference 的定性/宽容差评估；
2. R0 禁止宣称 pixel-accurate segmentation、精确 boundary F1、双人边界一致性或已冻结 uncertainty-band 数值；
3. S1 已冻结为新的六例统一 blind run `20260715T075811Z-3e9711`；历史 base chain 只保留为证据，不与新结果拼接；
4. Goal 2 已实现最小 scorer，并仅用 `cal-01/cal-02` 冻结 `T_different=0.40`、`T_same=0.75`；Goal 3 只读且不得根据 R0 回调；
5. Goal 3 verdict 为 `FURTHER_SPIKE`：P1 topology 2/3、无 false-low-risk，但未优于 B1，且存在 false split 与大面积背景传播；当前不得进入 Pixel Text Mask；
6. R1 最低 37 region 已由维护者从当前最小技术 Spike 延后，不是本轮 GO/FURTHER/NO-GO 的前置条件。
