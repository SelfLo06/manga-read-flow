# Cleaning Real Tool Spike — GOAL

## 1. 背景

Detection + OCR、Text Region Grouping 和 Page Translation 已完成真实能力验证。

当前 Phase 3 下一项高风险能力是 Cleaning，即从漫画原图中移除原语言文字，为后续中文嵌字提供可用背景。

Cleaning 的风险不只是“文字是否被擦除”，还包括：

* 气泡边框被破坏；
* 人物线稿被抹除；
* 网点、渐变和纹理被涂坏；
* 原文残留；
* 修复区域产生明显模糊、重复纹理或颜色断层；
* 不适合自动处理的区域被错误地强制清字。

因此本 Spike 优先验证：

```text
什么场景可以自动 fill
什么场景可以自动 inpaint
什么场景必须 skip / review
```

本 Spike 不验证正式 CleanerProvider、Workflow 接入或自动 mask 生成。

---

## 2. 核心目标

通过真实漫画样本和冻结的 oracle mask，验证 MVP 最小 Cleaning 路径：

```text
原图
+ 已知正确的文字区域 mask
→ cleaning method
→ cleaned candidate
→ 自动检查与人工评估
```

需要回答：

1. 浅色、近似纯色气泡是否可以安全使用 solid fill；
2. 简单纹理背景是否可以使用 OpenCV inpaint；
3. 不同 inpaint 算法和半径的质量差异是否足以支持 MVP；
4. 哪些场景会产生不可接受的线稿、边框或纹理破坏；
5. 是否能建立简单、可解释的 fill / inpaint / skip 决策规则；
6. Cleaning 输出能否达到“基础中文可读”的后续嵌字要求；
7. 失败时需要记录哪些 evidence 和 QualityIssue 候选；
8. 当前方案是否值得进入正式 CleanerProvider 设计。

---

## 3. 主要假设

本 Spike 验证以下假设：

### H1 — 浅色气泡可使用 solid fill

对于内部背景接近白色或浅色、文字与边框有明确间距的普通气泡：

```text
使用局部背景色估计或固定浅色填充
```

可以在不明显破坏气泡边框的情况下移除文字。

### H2 — 简单纹理可使用 OpenCV inpaint

对于低复杂度纹理、轻微渐变或简单线条背景：

```text
OpenCV Telea / Navier-Stokes inpaint
```

可以生成满足基础阅读要求的结果。

### H3 — 复杂区域必须显式跳过

以下区域无法仅靠简单 fill / OpenCV inpaint 稳定处理：

* 文字覆盖人物五官、头发或肢体；
* 密集漫画线稿；
* 网点和复杂渐变；
* 高对比纹理；
* 艺术字、花体字、拟声词；
* 文字与气泡边框严重接触；
* mask 无法可靠覆盖文字但不覆盖内容。

这些区域必须输出：

```text
skip
needs_review
cleaning_unsafe
```

而不是静默生成明显损坏结果。

---

## 4. In Scope

本 Spike 包含：

### 4.1 Cleaning 方法

至少验证：

```text
solid_fill
opencv_telea
opencv_ns
skip
```

允许加入一个简单的局部颜色估计 fill：

```text
border_sampled_fill
```

但不得扩展为复杂图像修复系统。

### 4.2 Oracle mask

使用人工或冻结的正确 mask。

Mask 表示：

```text
需要移除的原文字像素区域
```

Mask 可以包含少量文字外扩 padding，但不得依赖自动 mask 生成结果。

### 4.3 真实与 synthetic 样本

样本至少覆盖：

* 白色普通气泡；
* 浅灰色气泡；
* 旁白框；
* 竖排文字；
* 多行文字；
* 小文字；
* 文字接近气泡边框；
* 简单渐变背景；
* 简单纹理背景；
* 漫画线稿背景；
* 人物遮挡区域；
* 复杂拟声词或艺术字；
* 明确应 skip 的区域。

### 4.4 输出检查

评估：

* 文字残留；
* 边框破坏；
* 线稿破坏；
* 颜色断层；
* 模糊和纹理异常；
* mask 外像素变化；
* 对后续嵌字是否足够可用；
* 是否应自动接受、warning 或 skip。

---

## 5. Out of Scope

本 Spike 不包含：

* 自动文字 mask 生成；
* Detection 到 mask 的正式转换；
* LaMa；
* Stable Diffusion 或生成式修复；
* 云端图像修复 API；
* VLM；
* OCR 或 Translation 修改；
* 正式 CleanerProvider；
* StageExecutor 接入；
* ArtifactService 正式登记；
* Repository / SQLite 修改；
* Workflow retry / fallback；
* QualityIssue 持久化；
* Typesetting；
* UI / API；
* Batch 处理；
* GPU 性能优化；
* 专业汉化级背景重绘；
* 拟声词或艺术字重绘。

如果 oracle mask 下的简单方案不可用，后续再决定是否需要 LaMa Spike，不能在本轮自动扩大范围。

---

## 6. 样本要求

建议准备 8–12 个 region-level fixture。

每个 fixture 至少包含：

```json
{
  "fixture_id": "bubble-white-01",
  "source_image": "relative/path/source.webp",
  "mask_image": "relative/path/mask.png",
  "region_bbox": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "scenario": "white_bubble",
  "expected_policy": "solid_fill",
  "evaluation_tags": [
    "bubble_border",
    "light_background"
  ]
}
```

样本分层：

### Core

必须参与 verdict：

* 白色普通气泡；
* 浅灰气泡；
* 旁白框；
* 简单纹理；
* 文字接近边框；
* 复杂线稿；
* 人物遮挡；
* 明确 skip。

### Auxiliary

用于观察但不决定主 verdict：

* 彩色气泡；
* 极小文字；
* 大面积文字；
* 艺术字；
* 拟声词；
* 强网点背景。

---

## 7. 实验组

### Group A — Solid Fill

输入：

```text
source image
+ oracle mask
+ fixed or estimated fill color
```

输出：

```text
filled image
```

至少验证：

* 固定白色；
* 局部边缘颜色中位数；
* 可选的浅色背景估计。

目标：

* 判断普通气泡是否需要复杂 inpaint；
* 判断简单 fill 是否更加稳定、快速、可解释。

---

### Group B — OpenCV Telea

输入：

```text
source image
+ oracle mask
+ inpaint radius
```

输出：

```text
Telea cleaned image
```

验证少量固定参数，例如：

```text
radius = 2
radius = 3
radius = 5
```

不得进行大规模参数搜索。

---

### Group C — OpenCV Navier-Stokes

与 Group B 使用相同 mask 和 radius 集合。

用于判断：

* 是否在漫画线条或渐变中优于 Telea；
* 是否存在明显性能或质量差异。

---

### Group D — Expected Skip Baseline

对已标记复杂区域：

```text
不生成正式 cleaned candidate
```

记录：

```text
skip_reason
risk_tags
review_required
```

可以生成 debug preview，但不得将其计为可接受输出。

---

## 8. Mask 规则

本 Spike 使用 oracle mask，但仍需固定 mask 语义。

要求：

* mask 为单通道或明确可转换为二值图；
* 白色表示需要清除；
* 黑色表示保留；
* mask 尺寸必须与 source image 一致；
* mask 必须位于目标 region 内或有明确 padding；
* 不允许 mask 覆盖整个气泡；
* 不允许 mask 人为避开难处理文字以美化结果；
* 正式运行后不得修改 mask。

允许测试少量固定 dilation：

```text
0 px
1 px
2 px
```

其目的是处理文字边缘残留，不是自动寻找最佳 mask。

---

## 9. 评价维度

### 9.1 自动指标

自动指标只作为辅助证据。

至少记录：

```text
masked_pixel_count
changed_pixel_count_inside_mask
changed_pixel_count_outside_mask
outside_mask_change_ratio
processing_time_ms
output_dimensions
output_hash
```

建议增加：

```text
boundary_change_ratio
local_color_discontinuity
```

不得仅凭 PSNR、SSIM 或单一像素指标判断漫画修复质量。

### 9.2 人工或独立 reviewer 评级

每个 candidate 评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

评价：

* 原文是否明显残留；
* 气泡边框是否破坏；
* 人物或线稿是否破坏；
* 是否出现明显模糊；
* 是否出现颜色块或纹理断层；
* 是否足以覆盖中文译文；
* 是否应进入自动流程。

### 9.3 Policy 评级

每个 fixture 最终归类：

```text
AUTO_FILL
AUTO_INPAINT
REVIEW_REQUIRED
SKIP
```

---

## 10. Failure Taxonomy

至少记录：

```text
text_residue
mask_undercoverage
mask_overcoverage
bubble_border_damage
line_art_damage
character_detail_damage
texture_smear
color_discontinuity
gradient_break
repeated_pattern
blur_artifact
outside_mask_change
unsupported_complex_background
unsafe_to_clean
processing_error
invalid_mask
```

这些是 Spike evidence，不直接创建正式 QualityIssue。

---

## 11. 初始决策规则候选

本 Spike 需要验证，而不是预先证明以下规则。

### Candidate Rule 1 — Fill

当满足：

```text
背景为白色或低方差浅色
mask 与气泡边框保持安全距离
区域内无重要线稿
```

候选策略：

```text
solid_fill / border_sampled_fill
```

### Candidate Rule 2 — Inpaint

当满足：

```text
背景存在简单连续纹理或渐变
mask 面积较小
区域内无重要人物细节
```

候选策略：

```text
opencv_telea 或 opencv_ns
```

### Candidate Rule 3 — Skip

当满足任一：

```text
文字覆盖人物细节
文字与复杂线稿重叠
mask 跨越气泡边框
文字面积过大
背景高复杂度
艺术字或拟声词
```

候选策略：

```text
SKIP / REVIEW_REQUIRED
```

最终阈值必须由实验结果支持，不能只凭主观设定。

---

## 12. 性能记录

记录：

```text
method
fixture_id
image_size
mask_area
processing_time_ms
peak_memory_if_available
error
```

MVP 不要求 GPU。

目标是确认 CPU 下单个 region 的 fill / OpenCV inpaint 不构成主要性能瓶颈。

---

## 13. 安全与数据边界

* 原始图片不可覆盖；
* 输出必须写入独立 Spike 目录；
* mask、source 和 output 都必须使用相对路径或受控路径；
* 不得写入 Project 正式 workspace；
* 不得登记正式 ProcessingArtifact；
* 不得把图片存入 SQLite；
* 不得修改原图；
* 不得将本地真实图片提交到 Git，除非它们已明确作为可提交测试资产；
* debug output 可能包含原图内容，应保持 local-only；
* 不得扫描未指定目录寻找漫画资源。

---

## 14. 实现边界

允许创建：

```text
tools/spikes/cleaning/spike.py
tests/unit/test_cleaning_spike.py

local_samples/cleaning/**
local_samples/spike_outputs/cleaning/**
```

允许修改：

```text
docs/spikes/cleaning/REPORT.md
```

不得修改：

```text
src/manga_read_flow/**
docs/design/**/final/**
prompts/**
依赖或锁文件
Detection/OCR 和 Translation 已关闭报告
```

若当前环境缺少 OpenCV，不得直接修改项目依赖。

应先报告环境事实，再决定是否：

* 使用当前环境已有 `cv2`；
* 创建隔离 Spike 环境；
* 或停止等待显式依赖授权。

---

## 15. 成功条件

Cleaning Spike 可判为 `GO`，至少满足：

1. oracle mask 下，普通白色或浅色气泡存在稳定可接受的自动策略；
2. 至少一种 OpenCV inpaint 对简单纹理有实际价值；
3. mask 外像素变化受到控制；
4. 不会静默接受明显边框、线稿或人物破坏；
5. 能形成明确的 fill / inpaint / skip 最小决策规则；
6. 所有 source image 保持不变；
7. 输出和指标可复现；
8. 性能适合单 Page MVP；
9. 能定义正式 CleanerProvider 所需的最小输入输出和错误证据；
10. 不需要通过复杂模型才能覆盖 MVP 普通气泡和旁白框。

---

## 16. Verdict

最终 verdict 只能是：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

### GO

* 普通浅色气泡稳定可自动清理；
* 简单纹理有稳定 inpaint 路径；
* skip 边界清晰；
* 无阻塞性质量或性能问题。

### CONDITIONAL_GO

* 普通气泡可用；
* 简单纹理部分可用；
* 复杂区域必须 warning / skip；
* 需要严格 mask 和安全规则。

### FURTHER_SPIKE

* fill 可用但 inpaint 证据不足；
* 需要进一步 mask 或 LaMa 验证；
* 样本不足以确定策略；
* 自动质量检查无法区分明显破坏。

### NO_GO

* 即使 oracle mask 下，普通气泡也无法稳定清理；
* 简单方法大比例破坏边框或线稿；
* MVP 必须依赖复杂生成式修复才能处理普通目标区域。

---

## 17. 最终输出

必须产出：

```text
docs/spikes/cleaning/REPORT.md

local_samples/spike_outputs/cleaning/<run_id>/
├── metadata.json
├── results.json
├── summary.json
├── candidates/
├── comparisons/
└── logs/
```

REPORT 至少包含：

* 环境；
* fixture；
* mask 规则；
* 实验方法；
* 自动指标；
* reviewer 评级；
* failure taxonomy；
* fill / inpaint / skip 决策规则；
* 性能；
* 限制；
* verdict；
* 正式集成前置条件；
* 下一步。

---

## 18. 非阻塞后续

本 Spike 完成后可能的后续包括：

```text
Mask Generation Follow-up
LaMa Necessity Spike
CleanerProvider Detailed Design
Cleaning QualityCheck Design
```

这些不是本轮自动任务。

只有在 oracle-mask Cleaning 已证明基本可行后，才允许进入自动 mask 或正式 CleanerProvider 设计。
