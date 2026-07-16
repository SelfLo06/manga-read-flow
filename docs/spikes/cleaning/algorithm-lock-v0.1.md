# Cleaning Algorithm Lock v0.1

版本：v0.1  
状态：Proposed Lock / 待 Spike 验证  
适用范围：Cleaning 感知、容器关联、文字 Mask、安全区域与受限重建 Spike  
目标读者：项目维护者、算法评审者、Codex / coding agent  
建议仓库路径：`docs/spikes/cleaning/algorithm-lock-v0.1.md`

---

## 1. 文档目的

本文冻结下一轮 Cleaning 算法 Spike 的候选组合、实验边界、对照组、指标与门禁。

当前目标不是实现通用 CleanerProvider，也不是追求高自动覆盖率，而是验证下列核心链路是否成立：

```text
高召回文字 fragment
→ 保守 grouping
→ 文字种子驱动的容器搜索
→ 同容器合并 / 异容器虚拟边界
→ explicit / implicit / free-text / uncertain 分类
→ 像素级文字 Mask
→ protected mask
→ safe edit region
→ 受限 E1 重建候选
```

本文是下一轮 Spike 的算法事实来源。未经新的证据和评审，不得在实现过程中自行扩展到 LaMa、Diffusion、ControlNet、通用 inpainting、正式 CleanerProvider 或 AUTO_ACCEPT。

---

## 2. 当前证据与冻结结论

### 2.1 已有正向证据

在人工冻结的 oracle mask 下：

- 简单白色或近白气泡、旁白框可由固定填充或周边采样填充得到部分可接受结果；
- OpenCV Telea 在一个低半径、简单标签案例中得到过可接受候选；
- 装饰文字、复杂纹理、人物线稿和非对白覆盖层适合进入 review / skip，而不是静默自动接受。

### 2.2 已有反向证据

真实气泡复验显示：

- 4 张真实页；
- 8 个 A 类区域；
- `0/8` 达到自动可接受；
- 存在主笔画残留、抗锯齿残留、气泡边框损伤；
- 一个 allowed mask 语义上延伸到人物手部或背景；
- 即使 outside/protected 像素变化检查通过，也不能证明 mask 的语义正确和视觉结果可用。

### 2.3 当前能力结论

```text
Cleaning capability = FURTHER_SPIKE
restricted AUTO_FILL = disabled
general AUTO_INPAINT = disabled
CleanerProvider integration = blocked
AUTO_ACCEPT = disabled
```

当前主要风险不是重建模型能力，而是：

```text
文字实例完整性
→ fragment grouping
→ container association
→ text mask
→ protected mask
→ safe edit region
```

---

## 3. 与 Translation / OCR 的关系

### 3.1 Translation 与 Cleaning 并行

推荐依赖关系：

```text
                         ┌─→ Translation → Translation Check ─┐
Detection → Grouping → OCR                                   ├→ Typesetting
                         └─→ Cleaning Perception → Cleaning ──┘
```

Cleaning 不依赖中文译文；Translation 不依赖 cleaned image。两者在 Typesetting 汇合。

### 3.2 OCR 对 Cleaning 的用途

Cleaning 使用 OCR / Detection 的结构证据：

- fragment bbox / polygon；
- detector score；
- 方向与尺度；
- text group；
- reading order；
- grouping uncertainty；
- auxiliary / unmatched group；
- 未分配 fragment；
- OCR crop 与识别结果作为完整性弱先验。

OCR 字符串是否完全正确不是 Cleaning 的核心条件。

以下等式禁止成立：

```text
OCR bbox == pixel text mask
high OCR confidence == safe cleaning
correct OCR text == complete anti-alias mask
container bbox == allowed edit region
```

当前不得假设 Detection/OCR 已稳定达到 `99%` 区域召回。必须验证漏种子与误种子条件下的主动弃权能力。

---

## 4. 统一概念模型

每个 Cleaning 候选围绕一个 `TextRegionPerception` 形成：

```text
TextRegionPerception
├── text_group_id
├── fragment_ids
├── container_type
│   ├── explicit_container
│   ├── implicit_container
│   ├── free_text
│   └── uncertain
├── grouping_confidence
├── text_mask_core
├── text_mask_soft
├── text_mask_uncertain_band
├── container_mask_probability
├── support_region
├── visible_boundary
├── virtual_boundary
├── protected_mask
├── safe_edit_mask
├── reconstruction_risk
└── recommended_decision
```

### 4.1 容器类型

#### `explicit_container`

完整封闭气泡、旁白框或规则标签。

输出：

```text
container_mask
visible_boundary
contour_band
```

#### `implicit_container`

边界断裂、轮廓被遮挡、两个气泡接触、开放式气泡。

边界：

```text
complete_boundary = visible_boundary ∪ virtual_boundary
```

输出：

```text
container_mask
visible_boundary
virtual_boundary
boundary_uncertainty
```

#### `free_text`

无气泡文字不伪造气泡。

输出：

```text
container_mask = null
support_region = adaptive_virtual_envelope
```

#### `uncertain`

容器归属、分组或边界不稳定。

默认：

```text
expected_decision = REVIEW_REQUIRED
```

---

## 5. C1：文字 Fragment Grouping

### 5.1 输入

```text
fragment bbox / polygon
detector score
direction
estimated character scale
projection overlap
fragment distance
page-normalized geometry
optional OCR grouping evidence
optional reading-order evidence
```

禁止使用：

- GT container assignment；
- expected text；
- asset-specific hardcode；
- 用户为当前样本手写的隐藏规则。

### 5.2 固定方法

```text
fragment graph
→ 生成保守候选边
→ agglomerative grouping
→ 保留 alternative grouping
```

候选合并特征：

- 方向一致性；
- 字符尺度相似性；
- 行列投影重叠；
- 相对间距；
- 中间是否存在强边界；
- 是否位于连续低纹理区域；
- reading order 是否合理；
- 容器竞争证据。

语言和阅读顺序只能作为弱先验。禁止使用“日文绝对右到左、上到下”的硬规则。

### 5.3 输出

```text
text_group_id
fragment_ids
grouping_confidence
alternative_grouping
grouping_uncertain
```

### 5.4 硬规则

- 禁止仅因为距离近就合并；
- 禁止仅因为存在多个 fragment 就拆成多个容器；
- extra / auxiliary / unmatched group 不得静默丢弃；
- upstream detection miss 不得归因给 grouping。

### 5.5 固定回归案例

```text
hard-09:
两个相邻气泡中的文字不得形成同一个 text_group
```

同时必须包含反例：

```text
同一气泡中的多列竖排文字不得被错误拆成多个容器
```

---

## 6. C2：容器搜索与虚拟边界

### 6.1 固定主算法

```text
局部 ROI
→ 图像特征图
→ SLIC superpixels
→ superpixel graph
→ multi-source geodesic propagation
→ geodesic Voronoi virtual boundary
```

### 6.2 局部特征

每个 ROI 固定计算：

```text
Lab color
grayscale
gradient magnitude
edge map
local variance
texture complexity
panel-line evidence
structure-line evidence
```

### 6.3 Polarity

记录：

```text
dark_on_light
light_on_dark
color_or_outlined
mixed_or_uncertain
```

Polarity 主要服务于文字 Mask，不改变容器传播的基本方向。

### 6.4 硬障碍与软代价

高置信硬障碍 `H(x)` 包括：

- 明确分镜线；
- 高置信相邻容器边界；
- 已确认 protected structure；
- 其他文字组核心 seed；
- 已接受的虚拟边界。

规则：

```text
H(x) = 1 → 传播不可穿过
```

中低置信结构进入软代价：

```text
c(x) =
  w_e * edge
+ w_t * texture
+ w_p * soft_protected
+ w_o * other_group_penalty
+ w_m * appearance_mismatch
```

禁止简单使用“interior 概率减去 protected 概率”的线性抵消设计。

### 6.5 多源竞争传播

对文字组 `G_i`：

```text
D_i(x) = 从 G_i 到 x 的最小累计传播代价
```

归属：

```text
L(x) = argmin_i D_i(x)
```

两个文字组的竞争脊线：

```text
V_ij = { x | |D_i(x) - D_j(x)| < ε }
```

`V_ij` 是虚拟边界候选。

### 6.6 同容器判断

必须计算：

```text
P_same_container(G_i, G_j)
```

规则：

```text
same-container 高
→ 合并种子，重新传播

different-container 高
→ 独立传播，保留虚拟边界

不确定
→ container_type = uncertain
→ REVIEW_REQUIRED
```

不得为提高覆盖率而强制合并或强制拆分。

---

## 7. C3：自由文字支持区域

自由文字不建立假气泡，使用动态支持区域。

固定方法：

```text
文字 group seed
→ 按字符尺度初始化 dilation
→ 受 hard barrier / soft cost 约束的 geodesic expansion
→ 与其他文字组多源竞争
```

初始尺度：

```text
r_i = clip(α * character_height + β * stroke_width, r_min, r_max)
```

支持区域：

```text
S_i = { x | D_i(x) <= τ_i }
```

动态阈值考虑：

- 文字尺度；
- 背景方差；
- 纹理复杂度；
- 与人物线稿距离；
- 与其他文字组距离；
- 边界稳定性。

固定策略：

```text
简单低方差标签
→ 可进入后续候选

普通背景自由文字
→ REVIEW_REQUIRED

艺术字、拟声词、复杂线稿文字
→ SKIP
```

---

## 8. C4：像素级文字 Mask

### 8.1 固定组合

只在已确定的 container/support ROI 内运行：

```text
detector polygon / probability seed
+
polarity-aware local segmentation
+
seeded connected-component filtering
+
stroke-width evidence
+
soft-edge completion
```

### 8.2 Polarity-aware segmentation

```text
dark_on_light:
  adaptive threshold / Sauvola / Otsu

light_on_dark:
  inverted adaptive threshold

color_or_outlined:
  Lab clustering + edge evidence

mixed_or_uncertain:
  多候选输出，不自动定案
```

### 8.3 Connected component 过滤

只保留：

- 与 detector seed 重叠；
- 尺度合理；
- 方向合理；
- stroke width 合理；
- 位于目标 container/support region 内的组件。

OCR bbox 不能直接成为文字 Mask。

### 8.4 SWT / skeleton 边界

SWT 和 skeleton 只允许作为：

```text
归属证据
分离证据
不确定性证据
```

禁止：

- 强制制造 1–2 像素缝隙；
- 破坏性切割边框、人物线稿或字形；
- 仅凭 stroke width 自动决定文字/结构归属。

文字与结构无法高置信分离时：

```text
text_structure_overlap = true
expected_decision = REVIEW_REQUIRED
```

### 8.5 输出

```text
text_mask_core
text_mask_soft
text_mask_uncertain_band
text_mask_confidence
```

---

## 9. Protected Mask 与 Safe Edit Region

### 9.1 Protected Mask 固定组成

```text
container contour band
panel-line mask
high-confidence structure edges
virtual-boundary band
neighbor-container boundary
```

定义：

```text
M_protected =
  M_contour_band
∪ M_panel_line
∪ M_structure
∪ M_virtual_boundary
∪ M_neighbor_boundary
```

### 9.2 气泡安全区域

```text
M_safe =
  erode(M_container, r_s)
  \ M_protected
```

### 9.3 自由文字安全区域

```text
M_safe =
  M_support
  \ M_protected
```

### 9.4 最终编辑 Mask

```text
M_effective =
  M_text
  ∩ M_safe
```

自动候选至少满足：

```text
text_mask_core 全部位于 safe region
text_mask_soft 不触碰高置信 protected structure
uncertain_band 不参与自动修改
不存在未分配高置信 fragment
不存在跨容器共享 fragment
```

---

## 10. 风险分类

固定分类：

### E1：简单低风险

- 显式封闭容器；
- 白色或近白低方差内部；
- 文字远离边界；
- 无线稿穿过；
- grouping、container、text mask 均高置信。

### E2：边界敏感

- 文字靠近边框或尾巴；
- 相邻/接触气泡；
- 不规则容器；
- 小字、标点靠近结构。

### E3：复杂背景

- 透明气泡；
- 网点；
- 渐变；
- 纹理；
- 人物或背景线稿穿过。

### E4：非 P0 自动目标

- 拟声词；
- 艺术字；
- 大型装饰文字；
- 复杂自由文字；
- 无法可靠分组的高风险区域。

注意：网点是 `background property`，不是 E4 的重新定义。

---

## 11. 固定重建范围

### E1

仅测试：

```text
R1 fixed white / median fill
R2 border-sampled robust fill
```

`border-sampled` 必须：

- 仅从安全内环带采样；
- 排除文字候选像素；
- 排除边缘与 protected 像素；
- 使用中位数或截断均值。

### E2

只允许：

```text
low-radius Telea comparison candidate
```

默认：

```text
REVIEW_REQUIRED
```

### E3

本轮不自动重建：

```text
REVIEW_REQUIRED
```

可保留输入作为后续 LaMa Spike 样本，但不得在本轮调用 LaMa。

### E4

```text
SKIP
```

### 11.1 明确禁止

```text
LaMa
ControlNet
Diffusion
FFT screentone reconstruction
通用 inpainting
正式 CleanerProvider
AUTO_ACCEPT
```

---

## 12. 固定实验对照组

| 编号 | 算法 | 用途 |
|---|---|---|
| B0 | geometry grouping + bbox/dilation | 最低基线 |
| B1 | geometry grouping + seeded watershed | 简单图像边界基线 |
| P1 | SLIC + multi-source geodesic + virtual boundary | 主候选 |
| P2 | P1 + Random Walker refinement | 仅在 P1 边界不确定时运行 |

P2 不是默认路径。

本轮禁止扩展：

```text
GrabCut
Active Contour
CRF
LaMa
Diffusion
FFT reconstruction
```

---

## 13. OCR / Detection 不完美鲁棒性实验

每套算法运行四种 seed 条件：

```text
S0：人工确认完整 seed
S1：真实 detector/OCR seed
S2：随机删除 1%、3%、5% fragment
S3：注入少量 false-positive fragment
```

观察：

- 是否漏掉容器；
- 是否跨容器合并；
- false-positive 是否生成虚假支持区；
- 是否产生未解释 fragment；
- 是否正确输出 `uncertain`；
- 是否错误进入低风险候选。

核心目标：

```text
证据不足时正确 abstain
```

不是在污染输入下维持高覆盖率。

---

## 14. 固定测试样本

最低样本组成：

| 类型 | 最低数量 |
|---|---:|
| 规则白气泡 | 5 |
| 同一气泡多列文字 | 5 |
| 相邻或接触气泡 | 5 |
| 断裂或遮挡边界 | 5 |
| 矩形旁白框 | 3 |
| 无气泡简单标签 | 3 |
| 透明或纹理气泡 | 5 |
| 非文字误检 | 3 |
| 艺术字 / SFX 弃权 | 3 |

必须固定：

```text
hard-09 → 相邻/接触气泡跨容器合并回归案例
```

旧 Cleaning Benchmark Pilot 的差异 mask 只能作为候选和诊断材料，不得直接视为 ground truth。

---

## 15. 固定指标

### 15.1 Grouping

```text
fragment pair precision / recall
false merge count
false split count
unassigned fragment ratio
cross-container merge count
```

### 15.2 Container / Support Region

```text
container IoU
boundary F1
seed coverage
container leakage ratio
virtual-boundary correctness
abstention correctness
```

### 15.3 Text Mask

```text
pixel precision
pixel recall
soft-edge recall
protected-overlap ratio
residual-text score
```

优先保证召回，但不得以覆盖 protected structure 为代价。

### 15.4 Safe Region

```text
protected overlap
cross-container modification
unexplained high-confidence fragment
```

### 15.5 系统级

```text
risk–coverage curve
low-risk candidate count
REVIEW_REQUIRED count
SKIP count
false-low-risk-candidate count
```

本轮不产生正式 `AUTO_ACCEPT`。

---

## 16. Spike 门禁

### 16.1 Grouping / Container

```text
关键接触气泡回归集 false merge = 0
明显字符裁断 = 0
跨集合重复 = 0
高置信 fragment 单一归属率 >= 98%
人工判断正确的 container/support region >= 90%
```

### 16.2 Text Mask

在人工确认 Gold 区域：

```text
text pixel recall >= 97%
protected overlap = 0
明显主笔画残缺 = 0
```

### 16.3 Abstention

以下必须进入 `REVIEW_REQUIRED` 或 `SKIP`：

```text
跨容器不确定
非文字误检
复杂艺术字
严重结构粘连
```

### 16.4 Reconstruction

本轮不启用 `AUTO_ACCEPT`。

只有后续独立 E1 跨作品测试满足：

```text
0 次结构性误修改
0 次跨容器修改
残字率通过冻结阈值
人工可接受率通过冻结门禁
```

才允许讨论重新开启 restricted `AUTO_FILL`。

---

## 17. 下一项 Spike

下一项任务固定为：

```text
Text-Seeded Container Association Spike
```

只验证：

```text
文字 fragment
→ 保守 grouping
→ SLIC/geodesic propagation
→ 同容器合并
→ 异容器虚拟边界
→ explicit / implicit / free-text / uncertain
```

本轮不运行实际 Cleaning，不生成正式 benchmark manifest，不接入 Workflow。

---

## 18. 来源文档

实施前按需读取：

```text
AGENTS.md
docs/SRS-v1.0.md
docs/HLD.md
docs/PROJECT-PLAN.md
docs/spikes/detection-ocr/REPORT.md
docs/spikes/detection-ocr/followups/grouping/REPORT.md
docs/spikes/cleaning/REPORT.md
真实气泡 fill follow-up REPORT
docs/spikes/cleaning-dataset-audit/REPORT.md
docs/spikes/cleaning-benchmark-pilot/REPORT.md
docs/spikes/cleaning-benchmark-pilot/GATE.md
docs/spikes/cleaning-benchmark-pilot/manual-review-resolution.csv
docs/spikes/cleaning-benchmark-pilot/page-selection.csv
```

若文档与本 Algorithm Lock 冲突，停止并报告，不得在实现时自行选择一方。

---

## 19. Goal 7 lock supersession（2026-07-16）

以下决策取代第 17 节中“下一项 Spike”的未来时态：

```text
page-global association      = REJECTED
page-global extreme gate     = REJECTED
page-global topology gate    = REJECTED
full-page B1                 = REJECTED
local group/cluster routing  = REQUIRED
bounded local B1             = PASS_FOR_SPIKE_ONLY
AUTO_ACCEPT                  = FORBIDDEN
Pixel Text Mask              = BLOCKED
safe edit region             = BLOCKED
Cleaning promotion           = BLOCKED
```

锁定的 local B1 资源边界：

```text
max L1 ROI pixels = 262144
max queue entries = 500000
peak working memory < 512 MB / ROI
p95 runtime < 2 s / ROI
overflow/failure = local abstain only
```

Goal 7 通过的是路由隔离、覆盖与资源门禁；未通过的是 coarse region 的全语义正确性。任何后续工作不得把 `LOCAL_B1_CANDIDATE` 或 non-empty region 升格为 confirmed container、Pixel Text Mask、safe edit region 或可清字区域。

允许的下一项仅是 local candidate qualification 的独立 Spike。它必须沿用冻结 S1 和 Goal 7 artifacts，提供内容角色、container/support correctness 与 leakage 的独立证据；在此之前不得重新打开 E1/E2 自动清字、CleanerProvider 或 Workflow。
