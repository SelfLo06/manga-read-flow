# Cleaning Real Tool Spike — HARNESS

## 1. 目的

本 HARNESS 用于验证：

```text
oracle mask
→ solid fill / OpenCV inpaint / skip
→ 是否满足 MVP 基础清字要求
```

不得把 mask 生成质量与 cleaning 算法质量混在一起。

---

## 2. 冻结范围

主实验开始后必须冻结：

```text
fixture set
source images
oracle masks
region bbox
method list
parameter matrix
evaluation rubric
```

记录：

```text
git_head
fixture_set_sha256
source_hashes
mask_hashes
OpenCV version
Pillow version
OS / Python
```

正式运行后不得修改 fixture 或 mask。

---

## 3. Fixture

准备：

```text
8–12 个 core fixtures
```

至少覆盖：

* 白色气泡；
* 浅灰气泡；
* 旁白框；
* 多行或竖排文字；
* 文字接近边框；
* 简单渐变；
* 简单纹理；
* 复杂线稿；
* 人物细节遮挡；
* 明确应 skip 区域。

每个 fixture 需要：

```text
fixture_id
source_image
mask_image
region_bbox
scenario
expected_policy
evaluation_tags
```

---

## 4. Mask 规则

Mask 语义：

```text
white = remove
black = preserve
```

要求：

* 与 source 尺寸一致；
* 二值或可确定性转换为二值；
* 不覆盖整个气泡；
* 不故意避开难清文字；
* 不越出声明 region；
* 原始 mask 保留不变。

固定 dilation：

```text
0 px
1 px
2 px
```

不得动态搜索最佳 dilation。

---

## 5. 方法矩阵

### Fill

```text
fixed_white
border_sampled_fill
```

### OpenCV

```text
telea: radius 2 / 3 / 5
navier_stokes: radius 2 / 3 / 5
```

### Skip

复杂区域不生成可接受 candidate，只记录：

```text
skip_reason
risk_tags
review_required
```

不得加入其他算法或大规模参数搜索。

---

## 6. 输出要求

每个 candidate 必须记录：

```text
fixture_id
method
radius
dilation
source_hash
mask_hash
output_hash
processing_time_ms
output_path
error
```

输出不得覆盖 source。

---

## 7. 自动检查

至少计算：

```text
masked_pixel_count
changed_inside_mask
changed_outside_mask
outside_mask_change_ratio
boundary_change_ratio
processing_time_ms
```

必要时增加：

```text
local_color_discontinuity
```

自动指标只作辅助，不单独决定质量。

---

## 8. 人工评级

每个 candidate 评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

检查：

* 原文残留；
* 气泡边框破坏；
* 线稿破坏；
* 人物细节破坏；
* 颜色断层；
* 模糊或纹理涂抹；
* mask 外变化；
* 是否足够支持后续嵌字。

---

## 9. Policy 结果

每个 fixture 最终归类：

```text
AUTO_FILL
AUTO_INPAINT
REVIEW_REQUIRED
SKIP
```

必须给出原因，不能只给标签。

---

## 10. Failure Taxonomy

使用：

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
blur_artifact
outside_mask_change
unsupported_complex_background
unsafe_to_clean
invalid_mask
processing_error
```

---

## 11. 安全门槛

以下任一情况不得自动接受：

```text
明显人物细节破坏
明显气泡边框断裂
大面积线稿消失
明显 mask 外变化
仍有影响阅读的文字残留
输出尺寸或格式异常
```

复杂区域不得因为算法成功返回图片就自动视为可用。

---

## 12. 成功门槛

### Solid fill

普通白色或浅色气泡中：

```text
至少 80% core fixtures 为 ACCEPTABLE
无明显边框或线稿破坏
```

### Inpaint

简单纹理 / 渐变 fixtures 中：

```text
至少一种 OpenCV 方法
在多数样本中达到 ACCEPTABLE 或 REVIEW
且优于 fill baseline
```

### Skip policy

所有明确危险 fixture：

```text
不得被归入 AUTO_FILL 或 AUTO_INPAINT
```

### Safety

```text
source files unchanged
outside-mask destructive change = 0
silent acceptance of severe damage = 0
```

---

## 13. Verdict

### GO

* fill 和 inpaint 均有稳定适用场景；
* skip 边界清晰；
* 无阻塞性质量问题。

### CONDITIONAL_GO

* 普通气泡稳定可用；
* 简单纹理部分可用；
* 复杂区域必须 warning / skip。

### FURTHER_SPIKE

* fill 可用；
* inpaint 证据不足；
* 需要 mask 或 LaMa 专项验证。

### NO_GO

* oracle mask 下普通气泡仍无法稳定清理；
* 简单方法大比例破坏背景或边框。

---

## 14. 独立审查

使用只读 reviewer 检查：

* mask 是否真实冻结；
* sample 是否覆盖危险场景；
* 自动指标是否被过度解释；
* severe damage 是否漏判；
* expected skip 是否被强行算作成功；
* verdict 是否符合门槛。

Reviewer 不修改 fixture、结果或代码。

---

## 15. 停止条件

立即停止：

```text
source 或 mask 被修改
需要修改 src/**
需要新增项目依赖
需要自动 mask 生成
需要 LaMa 或生成式模型
输出覆盖原图
无法区分算法失败与 mask 失败
发现样本泄漏或路径越界
```

---

## 16. 最终报告

REPORT 必须给出：

```text
fixture summary
method comparison
failure taxonomy
fill / inpaint / skip policy
performance
limitations
verdict
formal integration conditions
```
