# Cleaning 设计思路与讨论演化记录

版本：v0.1  
状态：Design Rationale / Discussion Record  
建议仓库路径：`docs/spikes/cleaning/CLEANING-DESIGN-RATIONALE.md`  
目标读者：项目维护者、Codex、算法评审者、后续设计与 Spike 实施者

---

## 1. 文档定位

本文记录 Cleaning 算法方向从早期“给定 Mask 后如何修补”，演化到“从文字组出发寻找容器、虚拟边界、文字 Mask 与安全编辑区域”的完整思考过程。

本文的作用是保存：

1. 项目维护者提出的原始算法假设；
2. 这些假设产生的背景；
3. 讨论中经过保留、修正或否定的部分；
4. 当前仍需通过 Spike 验证的关键问题；
5. Codex 在设计和实现时不得丢失的意图。

本文不是最终算法规范。

权威关系：

```text
algorithm-lock-v0.1.md
  → 当前算法组合、实验矩阵、指标和门禁的事实来源

CLEANING-HANDOFF.md
  → 当前阶段、历史实验、失败证据和下一步入口

CLEANING-DESIGN-RATIONALE.md
  → 为什么形成这些决策，以及项目维护者的原始思路
```

若本文与 `algorithm-lock-v0.1.md` 冲突，以 Algorithm Lock 为准，并报告冲突。

---

## 2. 项目维护者提出的核心思路

本轮 Cleaning 方向的核心不是由外部方案直接给出，而是从项目维护者提出的一组连续问题演化而来。

这些思路必须在后续 Codex 任务中被明确保留。

### 2.1 从文字出发，而不是先假设气泡检测已经解决

核心假设：

> 如果能够以很高召回率找到页面上的文字，那么可以把文字或文字组作为种子，向外扩散搜索其所属气泡、旁白框或局部支持区域。

传统思路通常是：

```text
先检测气泡
→ 再判断气泡中有没有文字
```

本项目提出的替代思路是：

```text
先得到文字 fragment / 文字组
→ 从文字组向外搜索容器
→ 用图像边界、纹理、结构和其他文字组约束传播
```

理由：

- Detection/OCR 已经能为大量正文提供较高召回的文字位置；
- 漫画气泡可能断裂、接触、开放或部分被遮挡；
- 直接做完整气泡检测未必比从已知文字位置向外搜索更稳定；
- 对 Cleaning 而言，文字是确定的处理目标，气泡只是限制处理区域的结构。

该思路不等于假设 OCR 字符串完全正确。真正依赖的是文字区域的高召回和合理几何定位。

---

### 2.2 多个文字组竞争传播，可为接触气泡形成虚拟边界

项目维护者进一步提出：

> 如果从多个文字组同时扩散，扩散前沿遇到其他文字组或其他组的传播区域时，能否形成虚拟边界，从而避免两个连在一起的气泡被错误合并？

这是解决 `hard-09` 的关键思路。

`hard-09` 暴露的问题是：

```text
两个相邻或接触气泡
→ 文字 fragment 因空间接近被合成一个 group
→ 一个候选区域覆盖两个容器
```

新的假设是：

```text
文字组 G_i 作为 source i
文字组 G_j 作为 source j
→ multi-source propagation
→ 两个传播前沿竞争
→ geodesic Voronoi ridge
→ virtual boundary candidate
```

虚拟边界并不是凭空画一条直线，而是由以下证据共同决定：

- 两个文字组的测地传播代价；
- 可见气泡轮廓；
- 局部颜色和纹理连续性；
- 结构边缘；
- 相邻文字组排斥；
- 同容器或异容器概率。

必须同时避免另一个错误：

```text
同一气泡中的多列文字
→ 被错误当成多个独立气泡
```

因此“遇到另一组文字就建立边界”不能成为硬规则。

需要先判断：

```text
P_same_container(G_i, G_j)
```

然后：

```text
same-container 高
→ 合并种子后重新传播

different-container 高
→ 保留独立前沿和虚拟边界

不确定
→ REVIEW_REQUIRED
```

---

### 2.3 高置信文字组可缩小像素级文字 Mask 的搜索空间

项目维护者提出：

> 当得到了置信度较高的文字组后，对应的文字 Mask 是否会更容易确定？

结论是：会明显更容易，但 OCR bbox 仍不能直接作为文字 Mask。

高置信文字组提供：

- 局部 ROI；
- 文字方向；
- 字符尺度；
- fragment seed；
- 可能的文字颜色或极性；
- 预计行列结构；
- 需要覆盖的组件数量。

因此文字 Mask 可以从全图分割问题降为：

```text
在已知容器或支持区域内
→ 以 detector/OCR geometry 为 seed
→ 做局部 polarity-aware segmentation
→ 选择与 seed 相连的组件
→ 补足描边和抗锯齿
```

但必须保持：

```text
OCR bbox != pixel text mask
```

因为 bbox 会包含背景，也可能碰到边框、人物线稿或相邻文字。

---

### 2.4 气泡 Mask、文字 Mask 和保护结构可共同推出安全区域

项目维护者提出：

> 如果得到完整气泡区域和文字组 Mask，是否就更容易得到安全区域？

当前设计由此形成：

```text
container/support region
+ text mask
+ protected mask
→ safe edit mask
```

对显式或隐式容器：

```text
M_safe =
  erode(M_container)
  \ M_protected
```

对自由文字：

```text
M_safe =
  M_support
  \ M_protected
```

最终：

```text
M_effective =
  M_text
  ∩ M_safe
```

该设计的关键不是尽可能扩大编辑区域，而是通过：

- 容器边界保护带；
- 相邻容器边界；
- 虚拟边界；
- 人物和背景线稿；
- 分镜线；
- 不确定带

缩小到可以解释和审查的区域。

---

### 2.5 OCR 内容可以错误，但区域先验仍然有价值

项目维护者明确提出：

> OCR 不一定绝对可信，但在不考虑识别文本对错、只考虑绝大多数文字区域不遗漏的情况下，它能否作为 Cleaning 的强先验？

该问题促成了以下区分：

```text
OCR string accuracy
≠
text region recall
≠
glyph coverage
≠
pixel mask recall
```

Cleaning 最需要的是：

1. 是否找到所有待处理文字区域；
2. fragment 几何是否合理；
3. grouping 是否正确；
4. 是否有未分配或冲突 fragment；
5. pixel mask 是否覆盖主笔画、描边和抗锯齿。

即使 OCR 将某个日文词识别错误，只要其位置、方向、分组和像素覆盖正确，对 Cleaning 仍可能是有效先验。

但目前尚未证明：

```text
R_region >= 99%
```

因此 Algorithm Lock 要求在以下条件下测试：

```text
S0：人工完整 seed
S1：真实 detector/OCR seed
S2：删除 1%、3%、5% fragment
S3：注入 false-positive fragment
```

目标不是证明污染输入下仍然高覆盖，而是证明证据不足时能够正确 abstain。

---

### 2.6 无气泡文字不应被强行拟合成气泡

项目维护者继续追问：

> 无气泡文字如何处理？是否可以在其自身范围设置动态适应的虚拟边界？

由此形成了：

```text
free_text
→ adaptive virtual support envelope
```

自由文字的输出是：

```text
container_mask = null
support_region = dynamic virtual envelope
```

支持区域由：

- 文字尺度；
- 局部背景方差；
- 纹理复杂度；
- 周围结构；
- 其他文字组；
- 距离和传播代价

动态确定。

它不是虚构一个真实存在的气泡，而是提供：

- 局部背景估计范围；
- protected structure 限制；
- 重建上下文；
- 风险判定依据；
- REVIEW_REQUIRED / SKIP 的审查区域。

当前分类：

```text
简单低方差标签
→ 可进入候选

普通背景自由文字
→ REVIEW_REQUIRED

艺术字、拟声词、复杂结构文字
→ SKIP
```

---

## 3. 思路演化过程

### 3.1 起点：把 Cleaning 当成重建问题

最初问题被表达为：

```text
给定文字 Mask
→ 选择 fill / Telea / Navier-Stokes / LaMa
→ 输出 cleaned image
```

这一阶段测试了：

- fixed white；
- border-sampled fill；
- OpenCV Telea；
- OpenCV Navier-Stokes；
- dilation 和 radius。

在 oracle mask 下，简单白色区域存在有限可行性。

### 3.2 真实页结果推翻“只需换重建模型”

真实气泡复验显示：

```text
A 类 0/8 ACCEPTABLE
```

失败包括：

- 主笔画残留；
- 抗锯齿残留；
- 边框损坏；
- allowed mask 覆盖到人物或背景。

这证明：

```text
正确执行给定 Mask
≠
给定 Mask 本身正确
```

因此问题重心从 reconstruction 转向 perception 和 constraint。

### 3.3 Cleaning 被重新分解

形成：

```text
文字实例
→ fragment grouping
→ container association
→ container/support region
→ text mask
→ protected mask
→ safe edit region
→ reconstruction
→ validation
→ abstention
```

### 3.4 Cleaning 与 Translation 被拆成并行分支

重新审视依赖后确认：

```text
OCR / grouping
├── Translation
└── Cleaning Perception
```

Cleaning 不需要译文，Translation 不需要 cleaned image。二者在 Typesetting 汇合。

### 3.5 OCR 被重新定位为共享上游证据

OCR 不再仅仅是翻译输入，也成为 Cleaning 的：

- 文字 seed；
- fragment geometry；
- grouping evidence；
- completeness check；
- residual validation prior。

### 3.6 从文字种子搜索容器

项目维护者提出的核心转折：

```text
不要先假设完整气泡已经可检测
而是从文字位置向外寻找容器
```

该思路发展为：

```text
SLIC superpixels
+ superpixel graph
+ multi-source geodesic propagation
+ hard/soft barriers
+ geodesic Voronoi virtual boundary
```

### 3.7 从真实容器扩展到自由文字支持区域

对于没有气泡的文字，算法不再强行寻找气泡，而是生成动态支持区域。

### 3.8 最终冻结 Algorithm Lock v0.1

当前冻结：

```text
C1 fragment grouping
C2 container/support propagation
C3 text mask
C4 protected/safe region
受限 E1 重建
```

重建不是下一轮主目标。

---

## 4. 当前核心算法假设

下列内容是待验证假设，不是已证事实。

### H1：高召回文字种子足以显著缩小容器搜索空间

验证：

- S0 与 S1 条件下 container/support region 质量；
- 漏种子后是否正确 abstain；
- false-positive seed 是否产生错误区域。

### H2：多源竞争传播可降低接触气泡的 false merge

验证：

- `hard-09`；
- 至少 5 个相邻/接触气泡；
- cross-container merge；
- virtual-boundary correctness。

### H3：同容器判断可避免多列文字被错误拆分

验证：

- 同一气泡多列文字；
- false split；
- alternative grouping；
- same-container merge 后的 container quality。

### H4：文字组先验可提高文字 Mask 召回并降低结构误覆盖

验证：

- pixel recall；
- soft-edge recall；
- protected overlap；
- residual text。

### H5：container/support + protected mask 可生成可审计 safe region

验证：

- protected overlap；
- cross-container modification；
- contour damage；
- unexplained fragment。

### H6：不确定度与弃权可控制 false low-risk candidate

验证：

- risk–coverage curve；
- negative abstention；
- uncertain grouping；
- false-positive seed；
- complex free text。

---

## 5. 当前未解决问题

### 5.1 Grouping 与 container association 的先后关系

可能的循环依赖：

```text
grouping 帮助找容器
容器又帮助判断 grouping
```

当前方向是迭代式：

```text
初始保守 grouping
→ 初始多源传播
→ same/different-container evidence
→ 合并或拆分
→ 重新传播
```

需通过 Spike 确认是否稳定。

### 5.2 虚拟边界的置信度

需要确定：

- 竞争脊线是否足够稳定；
- 是否应采用概率带而非单像素线；
- 如何与可见边界连接；
- 如何判断 boundary uncertainty；
- P1 与 Random Walker refinement 的收益。

### 5.3 protected structure 的可靠来源

尚未冻结完整模型或算法，仅冻结：

```text
高置信结构 → hard barrier
中低置信结构 → soft penalty
```

不得将所有强边缘都当作不可穿越墙。

### 5.4 自动 Mask 的 soft edge

需要覆盖：

- 抗锯齿；
- 描边；
- 彩色边缘；
- 小字和标点。

但不能通过大范围 dilation 损坏边框或线稿。

### 5.5 无气泡复杂文字的收益边界

当前 P0 倾向：

```text
简单标签可候选
普通背景文字 review
艺术字/SFX skip
```

不得为了自动覆盖率扩大 P0。

---

## 6. 已否定或降级的方向

### 6.1 “换成更强 inpainting 就能解决”

否定。

原因：Mask 和 safe region 错误会被更强模型放大。

### 6.2 “Detector/OCR bbox 可直接擦除”

否定。

bbox 不是 pixel mask。

### 6.3 “距离近的 fragment 应直接合并”

否定。

`hard-09` 已证明跨容器误合并风险。

### 6.4 “遇到另一组文字就必然画边界”

否定。

同一气泡可能包含多列文字。

### 6.5 “日文阅读顺序可作为硬规则”

降级为弱先验。

### 6.6 “SWT / skeleton 可强制切开文字与边框”

否定破坏性切割，只保留为证据。

### 6.7 “网点单独定义为 E4”

否定。

网点是 background property；E4 保留为非 P0 自动目标。

### 6.8 “立即加入 LaMa / Diffusion / ControlNet”

后置。

只有 C1–C3 和自动 Mask 通过后，才讨论 LaMa；Diffusion 不进入当前 P0。

### 6.9 “先优化快慢路径和性能”

后置。

先验证正确性，再 profiling。

---

## 7. Codex 必须保留的设计意图

Codex 在读取本文后，不得把任务重写成普通的 bubble detector 或 inpainting benchmark。

必须保留：

1. **Text-first hypothesis**  
   从文字 fragment / group 出发搜索容器。

2. **Multi-source competition**  
   多组文字同时传播，而不是独立 dilation。

3. **Virtual boundary**  
   用竞争传播形成接触气泡的候选分界。

4. **Same-container decision**  
   在虚拟分界前判断同容器多列文字。

5. **Free-text support region**  
   无气泡文字生成动态支持区域，不伪造气泡。

6. **OCR as prior, not truth**  
   OCR 字符串允许错误；几何召回、分组和完整性证据才是重点。

7. **Hard/soft barrier separation**  
   高置信结构硬阻断，中低置信结构软惩罚。

8. **Abstention as first-class output**  
   不确定时输出 `uncertain / REVIEW_REQUIRED / SKIP`，不得强制决策。

9. **Perception before reconstruction**  
   下一轮不运行实际 inpainting。

10. **Risk before coverage**  
    宁可低覆盖，也不得产生跨容器低风险候选。

---

## 8. 下一轮 Codex 任务应回答的问题

下一轮 `Text-Seeded Container Association Spike` 必须回答：

1. 在已知文字 seed 下，是否能找到合理完整容器？
2. 相邻或接触气泡能否由竞争传播形成正确虚拟边界？
3. 同一气泡多列文字是否会被错误分割？
4. 断裂边界能否通过 visible + virtual boundary 补全？
5. 无气泡简单文字能否得到有限、稳定的 support region？
6. not-text seed 是否会被正确拒绝？
7. 漏 seed 和 false-positive seed 是否会触发正确 abstention？
8. P1 相比 B0/B1 是否有实际提升？
9. Random Walker refinement 是否只在不确定区域提供可测收益？
10. 当前证据是否足以进入 text-mask Spike？

---

## 9. 推荐 Codex 阅读顺序

```text
1. AGENTS.md
2. docs/SRS-v1.0.md
3. docs/HLD.md
4. docs/PROJECT-PLAN.md
5. docs/spikes/cleaning/CLEANING-HANDOFF.md
6. docs/spikes/cleaning/CLEANING-DESIGN-RATIONALE.md
7. docs/spikes/cleaning/algorithm-lock-v0.1.md
8. Detection/OCR REPORT
9. Grouping REPORT
10. Cleaning REPORT
11. Real Bubble Fill Follow-up REPORT
12. Benchmark Pilot REPORT / GATE
```

阅读后先输出：

```text
- 复述项目维护者的核心 text-first 假设；
- 区分已验证事实、设计决策和待证假设；
- 列出冲突、歧义和实现前置条件；
- 给出 Spike GOAL / HARNESS / PLAN；
```

未经评审，不得直接写实现代码。

---

## 10. 可直接交给 Codex 的入口指令

```text
暂停实现。

先完整阅读以下文件：

- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/PROJECT-PLAN.md
- docs/spikes/cleaning/CLEANING-HANDOFF.md
- docs/spikes/cleaning/CLEANING-DESIGN-RATIONALE.md
- docs/spikes/cleaning/algorithm-lock-v0.1.md
- Detection/OCR 与 Grouping 的相关 REPORT
- Cleaning 主 REPORT 与 Real Bubble Fill Follow-up REPORT
- Cleaning Benchmark Pilot REPORT / GATE

本任务的核心思路由项目维护者提出，必须保留：

1. 从高召回文字 fragment / 文字组出发搜索气泡或支持区域；
2. 多个文字组进行多源竞争传播；
3. 接触气泡在传播竞争处形成虚拟边界候选；
4. 在建立虚拟边界前判断多个文字组是否属于同一容器；
5. 无气泡文字使用动态适应的虚拟支持区域，而不是伪造气泡；
6. OCR 字符串可以错误，但文字位置、分组、方向和完整性证据可作为 Cleaning 先验；
7. 得到文字组和容器后，再局部生成像素级文字 Mask 与 safe edit region；
8. 证据不足时必须 abstain，不能强制合并、分割或清字。

先不要实现算法。

第一轮只输出：

- 对上述思路的准确复述；
- 已验证事实 / 已冻结决策 / 待证假设三分表；
- Text-Seeded Container Association Spike 的 GOAL；
- HARNESS；
- PLAN；
- 允许文件、禁止文件；
- B0 / B1 / P1 / P2 对照矩阵；
- S0 / S1 / S2 / S3 seed 鲁棒性实验；
- 指标、门禁、停止条件；
- 预期失败模式。

禁止：

- LaMa；
- Diffusion；
- ControlNet；
- FFT 网点重建；
- 实际 Cleaning；
- CleanerProvider；
- Workflow 集成；
- benchmark manifest；
- AUTO_ACCEPT；
- 未经授权的 commit / push。

若来源文档冲突，停止并报告冲突。
```

---

## 11. 一句话保留

本项目当前 Cleaning 方向的核心不是：

```text
找到气泡后擦字
```

而是：

```text
以文字组为可靠起点，
通过多源竞争传播寻找真实或虚拟容器边界，
再由文字 Mask、容器/支持区域和保护结构共同限定安全编辑区域；
证据不足时主动弃权。
```

---

## 12. Goal 7 的粒度修正与边界（2026-07-16）

Goal 7 确认保留 text-first 思路，但拒绝 page-first association：

```text
Page
└── local group / small local cluster
    ├── oversized / SFX / uncertain → local abstain
    ├── free text → bounded support（仍需独立 qualification）
    └── ordinary dialogue → bounded local B1 coarse candidate
```

其理由不是阈值“过保守”，而是原先 crop 级 geometry/topology 被错误地作用于整页文字联合几何。任何异常 seed 或 uncertain pair 都不再有权让同页其他 cluster 失效。

bounded local B1 的工程合同已获 Spike 证据：ROI 在 L1 上限内、队列/内存/时间有预算、超限仅 local abstain、worker 隔离。它只生成 coarse association review candidate，不生成容器真值、像素 mask 或 safe edit region。

Phase B 同时给出限制性反证：普通对白可见 candidate 覆盖达到 10/12，但已有 `WRONG_OR_LEAK`。故不能把“B1 非空”解释为“B1 正确”，更不能从 B1 直接进入 Cleaning。下一步必须先补 local candidate qualification，而不是增强 inpainting。
