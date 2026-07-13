
# 一、产品问题定义

给定一张漫画原图、检测/OCR 结果和中文译文，系统应针对可安全处理的普通文本区域：

```text
识别可编辑区域
→ 删除原文文字
→ 重建被文字遮挡的背景
→ 在可用区域内排入中文
→ 自动检查结果
→ 输出 ACCEPT / REVIEW_REQUIRED / SKIP
```

产品目标可以写成：

> 在尽量不破坏气泡边框、人物、背景线稿和原图结构的前提下，为一部分普通对话气泡和旁白框生成基础中文可读结果；无法可靠处理的区域必须主动进入 review 或 skip。

这里有两个优先级：

```text
安全性和自动接受精度 > 自动覆盖率
```

漏处理一个气泡可以显示 warning；错误清除人物、边框或背景线稿会直接破坏页面。

# 二、形式化输入与输出

对于页面图像：

```text
I ∈ H × W × C
```

每个候选文本目标 `i` 的输入为：

```text
R_i    文本检测区域或 polygon
S_i    OCR 原文
T_i    中文译文
D_i    横排 / 竖排方向
Q_i    OCR、检测等已有质量信息
π      ProcessingProfileSnapshot
```

系统需要推导：

```text
M_i    原文 glyph 的像素级 mask
B_i    气泡或旁白框实例 mask
A_i    允许修改的区域 allowed_edit_mask
P_i    禁止修改的结构 protected_mask
L_i    中文可排版区域 layout_region
```

输出为：

```text
C      cleaned image
O      typeset image
d_i    AUTO_ACCEPT / REVIEW_REQUIRED / SKIP
E_i    可审计证据、指标、reason codes、debug artifacts
```

# 三、Cleaning 子问题

Cleaning 实际包含三个不同问题。

## 1. 原文文字定位

目标是估计：

```text
M_i = TextMask(I, R_i)
```

要求覆盖：

* 字体主体；
* 灰阶和抗锯齿边缘；
* 黑字、灰字和彩色字；
* 标点和细小笔画。

同时尽量排除：

* 气泡轮廓；
* 人物和背景线稿；
* 装饰图案；
* 非目标文字。

此前实验失败的主要原因之一，就是 `M_i` 覆盖不足，导致清理后仍可辨认出原文。

## 2. 安全编辑区域

目标是估计：

```text
A_i = SafeEditableRegion(I, B_i, R_i)
P_i = ProtectedStructures(I, B_i)
```

必须满足：

```text
M_i ⊆ A_i
A_i ∩ P_i ≈ ∅
```

其中 `A_i` 通常应由气泡内部腐蚀得到，不能直接等于 OCR bbox，也不能直接等于整块气泡 mask。

硬约束：

```text
Change(C, I) outside A_i = 0
Change(C, I) inside P_i = 0
```

但这两个约束只能证明算法遵守了 mask，不能证明 mask 的语义正确。因此还必须验证 `A_i` 是否错误包含人物或背景。

## 3. 背景重建

目标是在 `M_i` 内生成背景估计：

```text
Ĉ_i = Reconstruct(I, M_i, A_i, P_i)
```

优化目标可以表示为：

```text
L_clean =
λ1 · text_residue
+ λ2 · protected_structure_damage
+ λ3 · contour_damage
+ λ4 · color_discontinuity
+ λ5 · texture_discontinuity
```

其中：

* `text_residue`：原文字是否仍可辨认；
* `protected_structure_damage`：人物、背景线稿是否被破坏；
* `contour_damage`：气泡轮廓和尾巴是否受损；
* `color_discontinuity`：填充色是否形成白块或色差；
* `texture_discontinuity`：渐变、网点、条纹是否断裂。

对于 P0，背景重建不需要覆盖所有情况。可处理域可以限制为：

```text
封闭或近似封闭的普通气泡
+ 白色或低纹理浅色内部
+ 原文字与轮廓保持安全距离
+ 无人物或复杂线稿穿过内部
```

# 四、Typesetting 子问题

给定 cleaned image、中文译文和排版区域：

```text
θ_i = {
  font,
  font_size,
  line_breaks,
  orientation,
  alignment,
  stroke_width,
  line_spacing,
  character_spacing
}
```

求解：

```text
θ_i* = argmin L_typeset(θ_i)
```

其中：

```text
L_typeset =
μ1 · overflow
+ μ2 · boundary_violation
+ μ3 · protected_overlap
+ μ4 · unreadability
+ μ5 · excessive_shrinking
+ μ6 · poor_visual_balance
```

硬约束包括：

```text
RenderedText(θ_i) ⊆ L_i
RenderedText(θ_i) ∩ P_i = ∅
font_size ≥ profile.minimum_font_size
```

需要检测：

* 文本是否溢出；
* 字号是否过小；
* 是否压到气泡轮廓；
* 是否覆盖人物或装饰；
* 行宽和行数是否明显失衡；
* 横排中文是否仍具备基本可读性。

如果最小字号下仍无法放入，应产生：

```text
translation_too_long
typesetting_overflow
review_required
```

而不是继续无限缩字。

# 五、端到端问题

最终结果为：

```text
O = Render(C, T, θ)
```

但自动接受不能只依据“程序成功生成图片”。

自动门禁应同时检查：

```text
mask validity
cleaning quality
structure preservation
typesetting fit
visual readability
```

决策函数：

```text
d_i = Gate(metrics_i, profile)
```

推荐决策规则：

| 条件                       | 决策                |
| ------------------------ | ----------------- |
| mask、安全区域、清字、排版均通过       | `AUTO_ACCEPT`     |
| 结果可用但存在文字残留、边界敏感或排版风险    | `REVIEW_REQUIRED` |
| 复杂背景、装饰文字、非气泡文字、无法获得安全区域 | `SKIP`            |

# 六、P0 可处理域

建议把正式问题域分成四类：

| 类别 | 场景                 | P0 策略        |
| -- | ------------------ | ------------ |
| E1 | 白色/浅色、低纹理、封闭普通气泡   | 候选自动处理       |
| E2 | 边框附近、气泡尾巴附近、多个气泡接触 | Review       |
| E3 | 渐变、网点、纹理、人物线稿穿过    | Skip 或后续模型路线 |
| E4 | 拟声词、艺术字、背景文字、无气泡文字 | Skip         |

P0 的成功标准应限定为：

> 在 E1 数据集上，以较高自动接受精度完成清字和基础排版；E2–E4 能被可靠识别并进入 review 或 skip。

# 七、当前真正缺失的能力

从形式化结果看，缺口共有五个：

```text
1. 自动 glyph-level text mask
2. 自动 bubble / narration region
3. safe editable region 与 protected constraints
4. 受限背景重建方法
5. Cleaning + Typesetting 的产品级质量门禁
```

其中任何一个缺失，都不能形成可靠的自动闭环。

可以。这个问题不应继续被理解为“找一个更强的 inpainting 模型”，而应被建模为一个**带安全约束、允许弃权的联合感知与生成问题**：

[
\text{Page Image}
\rightarrow
\text{Region Understanding}
\rightarrow
\text{Safe Cleaning}
\rightarrow
\text{Constrained Typesetting}
\rightarrow
\text{Risk Gate}
]

对当前项目，最合理的主路线是：

> **学习式感知 + 确定性约束处理 + 多候选生成 + 风险估计与主动弃权。**

不建议优先做完全端到端的“输入原图和译文，直接输出嵌字图”。那种方案难以解释错误、难以保护原图结构，也不利于 QualityIssue、局部返工和恢复机制。项目本身要求 Provider 只提供工具结果，由 WorkflowLoopEngine 决定接受、review、skip 或 block，这与分阶段可观测算法更匹配。

---

# 1. 总体数学模型

给定页面图像：

[
I \in [0,255]^{H\times W\times C}
]

页面上有 OCR 或检测得到的文字候选：

[
\mathcal{R}={R_1,R_2,\ldots,R_n}
]

每个目标区域 (i) 具有：

[
X_i=
\left(
R_i,,
S_i,,
T_i,,
D_i,,
Q_i
\right)
]

其中：

* (R_i)：检测框、polygon 或文字行集合；
* (S_i)：OCR 原文；
* (T_i)：中文译文；
* (D_i)：方向；
* (Q_i)：检测、OCR、关联置信度等证据。

需要估计的隐变量包括：

[
Z_i=
\left(
B_i,,
M_i,,
P_i,,
A_i,,
L_i
\right)
]

其中：

* (B_i)：气泡或旁白框实例 mask；
* (M_i)：原文 glyph mask；
* (P_i)：人物、线稿、气泡轮廓等 protected mask；
* (A_i)：允许修改区域；
* (L_i)：中文排版区域。

最终算法生成：

[
C = G_{\text{clean}}(I,Z)
]

[
O = G_{\text{typeset}}(C,T,Z)
]

并输出决策：

[
d_i \in
{
\text{AUTO_ACCEPT},
\text{REVIEW_REQUIRED},
\text{SKIP}
}
]

整个问题可以写成带约束的风险最小化：

[
\min_{Z,C,O}
;
\mathcal{L}*{\text{perception}}
+
\mathcal{L}*{\text{clean}}
+
\mathcal{L}*{\text{typeset}}
+
\lambda_r\mathcal{R}*{\text{damage}}
]

满足：

[
\Delta(I,C)(x)=0,
\qquad
x\notin A
]

[
\Delta(I,C)(x)=0,
\qquad
x\in P
]

[
\operatorname{RenderMask}(O)(x)=0,
\qquad
x\notin L
]

这里的核心不是让总损失最低，而是让**破坏风险有硬上界**。

---

# 2. 思考方向一：将问题分解为多任务感知

目前最基础的缺口是，系统没有真正理解页面区域。可以把感知阶段设计成多任务模型：

[
F_\theta(I)
\rightarrow
\left(
p_{\text{text}},
p_{\text{bubble}},
p_{\text{character}},
p_{\text{line}},
p_{\text{panel}}
\right)
]

分别输出：

* 文字像素概率；
* 气泡内部概率；
* 人物或前景结构概率；
* 线稿概率；
* 分镜边界概率。

## 方案 A：独立模型

分别使用：

* Text segmentation model；
* Bubble instance segmentation model；
* Character / structure segmentation model。

优点是模型替换和评估简单。

缺点是不同模型输出可能不一致，例如文字属于某个气泡，但两个 mask 没有空间对应关系。

## 方案 B：共享编码器的多任务模型

使用共享特征编码器：

[
F = E_\theta(I)
]

然后多个 head：

[
p_{\text{text}}=H_t(F)
]

[
p_{\text{bubble}}=H_b(F)
]

[
p_{\text{structure}}=H_s(F)
]

联合损失：

[
\mathcal{L}_{\text{multi}}
==========================

\lambda_t\mathcal{L}*{\text{text}}
+
\lambda_b\mathcal{L}*{\text{bubble}}
+
\lambda_s\mathcal{L}_{\text{structure}}
]

优点是各任务可以共享漫画线稿和区域语义。

缺点是需要更完整标注数据，训练成本较高，不适合作为第一个 Spike。

## 工程判断

P0 应先使用独立模型或现有模型组合，不应先训练大型多任务网络。多任务模型属于结果证明后再考虑的优化。

---

# 3. 思考方向二：Bubble 与文字块关联应建模为匹配问题

检测器通常输出文字行或 fragment，而不是完整对话单位。需要把 OCR fragment 与气泡实例关联。

设气泡实例集合：

[
\mathcal{B}={B_1,\ldots,B_m}
]

文字区域集合：

[
\mathcal{R}={R_1,\ldots,R_n}
]

定义关联分数：

[
s_{ij}
======

\alpha
\frac{|R_i\cap B_j|}{|R_i|}
+
\beta
\operatorname{IoU}(R_i,B_j)
+
\gamma
\exp\left(
-\frac{|c_i-c_j|^2}{2\sigma^2}
\right)
+
\eta q_{ij}
]

其中：

* (c_i,c_j)：文字与气泡中心；
* (q_{ij})：方向、阅读顺序、气泡类型等附加一致性。

可以求解：

[
a_i
===

\arg\max_j s_{ij}
]

更复杂时可使用：

* 匈牙利匹配；
* 二部图匹配；
* 图聚类；
* 条件随机场；
* 图神经网络。

必须允许：

[
a_i=\varnothing
]

即文字不属于任何普通气泡，例如拟声词或背景文字。不能强制把每个 OCR 区域分配给某个气泡。

关联置信度低时应直接进入：

[
d_i=\text{REVIEW_REQUIRED}
]

---

# 4. 思考方向三：安全编辑区域不是一个二值 mask，而是风险场

过去的问题之一是把 `allowed_edit_mask` 看成绝对正确的二值答案。更稳妥的方法是先构造每像素风险场：

[
\rho_i(x)
=========

\alpha\left(1-p_{\text{bubble}}(x)\right)
+
\beta p_{\text{protected}}(x)
+
\gamma u(x)
+
\delta \exp\left(
-\frac{d_{\partial B_i}(x)}{\tau}
\right)
]

其中：

* (p_{\text{bubble}}(x))：像素属于目标气泡内部的概率；
* (p_{\text{protected}}(x))：属于人物、线稿或边框的概率；
* (u(x))：模型不确定性；
* (d_{\partial B_i}(x))：距离气泡边界的距离。

然后定义：

[
A_i
===

\left{
x
\mid
\rho_i(x)<\tau_A
\right}
]

在确定性实现中，可以近似为：

[
A_i
===

\operatorname{Erode}(B_i,r_b)
\setminus
\operatorname{Dilate}(P_i,r_p)
]

气泡轮廓保护区域可以定义为：

[
P_i^{\text{contour}}
====================

\operatorname{Dilate}
\left(
\partial B_i,r_c
\right)
]

最终：

[
P_i
===

P_i^{\text{contour}}
\cup
P_i^{\text{character}}
\cup
P_i^{\text{line}}
]

这意味着 Bubble segmentation 不是直接生成 cleaning mask，而是生成安全约束的一部分。

---

# 5. 思考方向四：文字 Mask 应采用“概率预测 + 图像证据”混合方法

单独依赖检测框太粗，单独依赖 threshold 又容易误删线稿。可以采用混合估计：

[
p_M(x)
======

w_1 p_{\text{seg}}(x)
+
w_2 p_{\text{color}}(x)
+
w_3 p_{\text{geometry}}(x)
+
w_4 p_{\text{ocr}}(x)
]

其中：

* (p_{\text{seg}})：文本分割模型概率；
* (p_{\text{color}})：颜色与局部背景差异；
* (p_{\text{geometry}})：文字连通分量、笔画宽度、排列规律；
* (p_{\text{ocr}})：OCR polygon 或文字行约束。

初始 mask：

[
M_i^{(0)}
=========

\mathbf{1}
\left[
p_M(x)>\tau_M
\right]
\cap
\operatorname{Expand}(R_i)
]

再经过 connected-component 筛选：

[
M_i^{(1)}
=========

\bigcup_{k\in\mathcal{K}_{\text{valid}}}
CC_k
]

有效连通分量可以按照以下特征判断：

[
\phi(CC_k)
==========

\left(
\text{area},
\text{aspect ratio},
\text{stroke width},
\text{distance to OCR line},
\text{color contrast}
\right)
]

最后施加安全约束：

[
M_i^{\text{effective}}
======================

\operatorname{Dilate}
\left(
M_i^{(1)},r_m
\right)
\cap
A_i
]

关键点是：

[
M_i^{\text{effective}}
\neq R_i
]

[
M_i^{\text{effective}}
\neq B_i
]

它只是气泡安全内部中的文字像素。

---

# 6. 思考方向五：把抗锯齿边缘建模为软 Mask

过去 `dilation=0/1` 的思路过于离散。文字边缘通常是 alpha blending：

[
I(x)
====

\alpha(x)F(x)
+
\left(1-\alpha(x)\right)B(x)
]

其中：

* (F(x))：文字前景色；
* (B(x))：背景色；
* (\alpha(x)\in[0,1])：抗锯齿覆盖率。

因此可以估计软文字 mask：

[
\hat{\alpha}(x)
===============

\operatorname{clip}
\left(
\frac{|I(x)-\hat B(x)|}
{|\hat F(x)-\hat B(x)|+\varepsilon},
0,1
\right)
]

然后不再只处理二值 mask，而是使用 alpha 混合：

[
C(x)
====

\hat{\alpha}(x)\hat B(x)
+
\left(1-\hat{\alpha}(x)\right)I(x)
]

不过实际工程中估计 (F)、(B) 不稳定，因此 P0 可以采用更简单的软膨胀：

[
\tilde M
========

\operatorname{GaussianBlur}
\left(
\operatorname{Dilate}(M,r),\sigma
\right)
]

再用软 mask 合成：

[
C
=

\tilde M\odot \hat C
+
(1-\tilde M)\odot I
]

这比直接把 dilation 区域全部替换成白色更不容易产生生硬边缘。

---

# 7. 思考方向六：Cleaning 不应只有一个算法，而应是算法选择问题

不同区域适合不同重建器。令候选重建算法集合为：

[
\mathcal{G}
===========

{
G_{\text{solid}},
G_{\text{harmonic}},
G_{\text{patch}},
G_{\text{lama}},
G_{\text{structure}}
}
]

为每个区域提取特征：

[
f_i=
\left(
\operatorname{Var}(I|_{B_i}),
\operatorname{EdgeDensity},
\operatorname{ColorCount},
\operatorname{TextureEntropy},
\operatorname{LineCrossing},
\operatorname{MaskRatio}
\right)
]

选择算法：

[
k_i^*
=====

\arg\min_{k\in\mathcal{G}}
\left[
\widehat{\mathbb E}
\left(
\mathcal{L}_k
\mid f_i
\right)
+
\lambda_c\operatorname{Cost}(G_k)
\right]
]

这可以从规则开始，而不必一开始训练 selector。

例如：

[
k_i=
\begin{cases}
\text{solid fill},
&
\operatorname{Var}<\tau_v
\land
\operatorname{EdgeDensity}<\tau_e
[4pt]
\text{harmonic / local interpolation},
&
\operatorname{Var}<\tau_v'
\land
\operatorname{LineCrossing}=0
[4pt]
\text{LaMa},
&
\operatorname{TextureEntropy}<\tau_t
[4pt]
\text{structure-guided},
&
\operatorname{LineCrossing}>0
[4pt]
\text{skip},
&
\text{otherwise}
\end{cases}
]

## 可考虑的重建算法族

### 7.1 鲁棒颜色填充

背景颜色：

[
c_i^*
=====

\arg\min_c
\sum_{x\in \operatorname{Ring}(M_i)}
\rho
\left(
|I(x)-c|
\right)
]

若 (\rho) 使用绝对损失，结果接近中位数。

适用于均匀白色或浅色气泡。

### 7.2 Harmonic Inpainting

求解：

[
\min_C
\int_{M_i}
|\nabla C(x)|^2,dx
]

边界条件：

[
C(x)=I(x),
\qquad
x\in\partial M_i
]

等价于在区域内求拉普拉斯方程：

[
\Delta C=0
]

适合平滑渐变，不适合复杂纹理。

### 7.3 Poisson Reconstruction

若能够估计背景梯度场 (v)：

[
\min_C
\int_{M_i}
|\nabla C-v|^2,dx
]

对应：

[
\Delta C=\nabla\cdot v
]

适合需要保持一定结构连续性的区域。

### 7.4 Patch-based Reconstruction

从附近候选 patch 中寻找：

[
p^*
===

\arg\min_{p\in\mathcal P}
D
\left(
I_{\partial M},
p_{\partial M}
\right)
]

适合重复网点、条纹和局部纹理，但容易复制错误线条。

### 7.5 学习式 Inpainting

[
\hat C
======

G_\theta
\left(
I,
M,
P,
S
\right)
]

其中 (S) 可以是：

* line map；
* edge map；
* screentone map；
* bubble interior；
* semantic segmentation。

对漫画而言，结构条件通常比单纯输入 (I,M) 更有价值。

---

# 8. 思考方向七：使用“重建后残留检测”形成闭环

当前 mask 一次生成后就固定，容易留下抗锯齿残影。可以设计有限迭代：

[
M^{(0)}
=======

F_{\text{text}}(I)
]

第 (t) 轮：

[
C^{(t)}
=======

G
\left(
I,M^{(t)}
\right)
]

使用 residual detector 检测清理结果中的剩余原文字：

[
R^{(t)}
=======

F_{\text{residual}}
\left(
C^{(t)},R_i
\right)
]

更新：

[
M^{(t+1)}
=========

M^{(t)}
\cup
R^{(t)}
]

停止条件：

[
\frac{|R^{(t)}|}{|M^{(t)}|}
<
\varepsilon
]

或者达到固定上限：

[
t\ge T_{\max}
]

必须保持：

[
M^{(t+1)}\subseteq A_i
]

否则不能继续扩张，直接进入 review。

这里的 residual detector 不一定是 OCR。也可以是：

* text segmentation；
* 原文模板差分；
* edge residue 检查；
* 原图与清理图的局部相关性。

---

# 9. 思考方向八：Typesetting 是离散与连续混合优化

排版变量包括：

[
\theta_i=
\left(
b_i,
s_i,
p_i,
o_i,
\ell_i,
w_i
\right)
]

其中：

* (b_i)：换行方案；
* (s_i)：字号；
* (p_i)：位置；
* (o_i)：方向；
* (\ell_i)：行距；
* (w_i)：描边宽度。

目标函数：

[
\mathcal{L}_{\text{type}}
=========================

\lambda_1L_{\text{overflow}}
+
\lambda_2L_{\text{boundary}}
+
\lambda_3L_{\text{center}}
+
\lambda_4L_{\text{balance}}
+
\lambda_5L_{\text{small-font}}
+
\lambda_6L_{\text{collision}}
]

## 硬约束

[
\operatorname{RenderMask}(T_i,\theta_i)
\subseteq L_i
]

[
\operatorname{RenderMask}(T_i,\theta_i)
\cap P_i
========

\varnothing
]

[
s_i\ge s_{\min}
]

## 换行可以用动态规划

设译文字符序列：

[
T=t_1t_2\cdots t_N
]

定义将字符 (i) 到 (j) 放入一行的代价：

[
c(i,j)
======

\lambda_w
\left(
W_{\max}-W(i,j)
\right)^2
+
\lambda_p P(i,j)
+
\lambda_o O(i,j)
]

其中：

* (W(i,j))：实际渲染宽度；
* (P(i,j))：标点违规；
* (O(i,j))：区域边界或 overflow 代价。

动态规划：

[
DP[j]
=====

\min_{i<j}
\left(
DP[i]+c(i+1,j)
\right)
]

然后对字号使用二分搜索：

[
s^*
===

\max
\left{
s
\mid
\exists b:
\operatorname{Fit}(T,b,s,L_i)=1
\right}
]

这比“根据字符数估算字号”可靠得多，因为它使用真实字体渲染尺寸。

---

# 10. 思考方向九：使用距离变换获得安全排版区域

对 layout mask (L_i) 计算距离变换：

[
D_i(x)
======

\min_{y\notin L_i}
|x-y|
]

较大的 (D_i(x)) 表示离边界更远。

排版中心可以选择：

[
x_i^*
=====

\arg\max_{x\in L_i}
D_i(x)
]

这比使用 bbox 中心更适合不规则气泡。

对于每个文字像素 (x)，可要求：

[
D_i(x)\ge d_{\min}
]

于是边界代价为：

[
L_{\text{boundary}}
===================

\sum_{x\in R_\theta}
\max
\left(
0,
d_{\min}-D_i(x)
\right)^2
]

其中 (R_\theta) 为译文渲染 mask。

---

# 11. 思考方向十：多候选生成与自动评审

不要让重建器只输出一个答案。对于同一个区域，可以生成：

[
\mathcal C_i
============

\left{
C_i^{(1)},
C_i^{(2)},
\ldots,
C_i^{(K)}
\right}
]

例如：

* solid fill；
* local median；
* harmonic；
* LaMa；
* structure-guided。

然后由独立 critic 评分：

[
q_k
===

Q_\phi
\left(
I,
C_i^{(k)},
M_i,
A_i,
P_i
\right)
]

选择：

[
k^*
===

\arg\max_k q_k
]

但 critic 不能只输出一个模糊“美观度”。应拆成：

[
Q_\phi
\rightarrow
\left(
q_{\text{residue}},
q_{\text{structure}},
q_{\text{boundary}},
q_{\text{color}},
q_{\text{texture}}
\right)
]

最终分数：

[
q_k
===

\sum_j w_jq_j
]

如果多个候选评分接近，可能说明模型不确定：

[
u_i
===

1-
\left(
q_{(1)}-q_{(2)}
\right)
]

其中 (q_{(1)})、(q_{(2)}) 是最高和第二高分。

不确定性高时应 review，而不是盲选第一名。

---

# 12. 思考方向十一：把主动弃权建模为 Selective Prediction

产品不需要处理所有区域，真正目标是自动处理部分区域时足够可靠。

定义风险：

[
r_i
===

\mathbb{E}
\left[
\mathcal{L}_i
\mid
I,R_i,Z_i
\right]
]

接受规则：

[
d_i=
\begin{cases}
\text{AUTO_ACCEPT},
&
r_i\le\tau_{\text{auto}}
[4pt]
\text{REVIEW_REQUIRED},
&
\tau_{\text{auto}}<r_i\le\tau_{\text{skip}}
[4pt]
\text{SKIP},
&
r_i>\tau_{\text{skip}}
\end{cases}
]

评估时不应只看整体准确率，而要看风险—覆盖率曲线。

覆盖率：

[
\operatorname{Coverage}(\tau)
=============================

\frac{
|{i:r_i\le\tau}|
}{N}
]

选择性风险：

[
\operatorname{Risk}(\tau)
=========================

\frac{
\sum_{i:r_i\le\tau}\mathcal{L}_i
}{
|{i:r_i\le\tau}|
}
]

P0 更应追求：

[
\operatorname{Risk}(\tau)\downarrow
]

即使代价是：

[
\operatorname{Coverage}(\tau)
]

暂时较低。

---

# 13. 思考方向十二：不确定性应进入门禁

可以使用三类不确定性。

## 模型置信度

例如 segmentation probability 的熵：

[
u_{\text{entropy}}(x)
=====================

-p(x)\log p(x)
-(1-p(x))\log(1-p(x))
]

## 多模型分歧

若有多个模型：

[
u_{\text{ensemble}}(x)
======================

\operatorname{Var}
\left(
p_1(x),\ldots,p_K(x)
\right)
]

## 输入分布偏移

提取区域特征 (z_i)，计算与训练集特征中心的距离：

[
u_{\text{ood}}
==============

\min_k
\left|
z_i-\mu_k
\right|_{\Sigma_k^{-1}}
]

总体不确定性：

[
u_i
===

\alpha u_{\text{seg}}
+
\beta u_{\text{association}}
+
\gamma u_{\text{reconstruction}}
+
\delta u_{\text{ood}}
]

只要 (u_i) 超过阈值，就不允许自动接受。

---

# 14. 三种总体算法路线

## 路线 A：纯规则与传统图像算法

```text
阈值/轮廓检测气泡
→ adaptive threshold 提取文字
→ erosion/dilation 构造安全区域
→ median/harmonic/inpaint
→ Pillow 排版
```

优点：

* 可解释；
* 易部署；
* CPU 可运行；
* 容易设置硬安全约束。

缺点：

* 对风格变化、彩色文字和破损气泡泛化差；
* 规则数量容易膨胀。

适合做最低基线，不适合成为唯一方案。

## 路线 B：学习式感知 + 确定性处理

```text
模型预测 bubble/text/structure
→ 确定性构造安全区域
→ 按区域复杂度选择重建器
→ 确定性排版
→ 风险门禁
```

这是最推荐的 P0 路线。

优点：

* 感知阶段能适应漫画风格；
* 修改和排版仍可严格约束；
* 每个中间结果可保存和人工修正；
* 与现有 Artifact、QualityIssue、WorkflowLoop 架构兼容。

## 路线 C：端到端生成

[
O=G_\theta(I,T)
]

优点：

* 理论上可以联合优化清字、背景和排版；
* 可能生成视觉更自然的结果。

缺点：

* 需要大量配对数据；
* 容易改动非目标区域；
* 难以解释和局部返工；
* 难以保证文字内容完全正确；
* 很难满足“原图结构不被破坏”的硬约束。

不适合作为当前 MVP 路线。

---

# 15. 推荐的 P0 算法架构

建议把正式算法固定为以下形态：

[
\boxed{
\text{Learned Perception}
+
\text{Constrained Reconstruction}
+
\text{Deterministic Layout}
+
\text{Selective Gate}
}
]

具体流程：

```text
1. Bubble instance candidate generation
2. OCR fragment–bubble association
3. Text probability mask generation
4. Image-driven mask refinement
5. Protected structure extraction
6. Safe editable region construction
7. Region complexity classification
8. Multi-strategy cleaning
9. Residual-text and damage checking
10. Shape-aware deterministic typesetting
11. Overflow and readability checking
12. AUTO_ACCEPT / REVIEW_REQUIRED / SKIP
```

其中产品边界仍然保持：

* Provider 返回 mask、候选图片、指标和标准化错误；
* ArtifactService 登记正式 mask 和图片；
* QualityCheckService 生成问题分类；
* WorkflowLoopEngine 决定选择候选、重试、review、skip 或 block。 

---

# 16. 最短验证顺序

不要一次实现全部算法。应按依赖顺序验证：

### Gate 1：Bubble

证明：

[
B_i
]

能稳定表示正确气泡实例，并且不会泄漏到人物和相邻白区。

### Gate 2：Text Mask

证明：

[
M_i
]

具有足够高的文字 recall，同时气泡轮廓和人物 false positive 足够低。

### Gate 3：Safe Region

证明：

[
M_i^{\text{effective}}\subseteq A_i
]

且：

[
A_i\cap P_i=\varnothing
]

### Gate 4：Cleaning

在固定且正确的 mask 下比较重建方法。

### Gate 5：Typesetting

使用 oracle bubble mask 和 oracle cleaned image 独立验证排版，不要等待 Cleaning 完全通过。

### Gate 6：联合流程

最后才测试：

[
I
\rightarrow
O
]

这样任何失败都能准确归因，而不是得到一个“最终图片不好看”却不知道问题来自哪里。