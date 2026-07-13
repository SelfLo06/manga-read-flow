# Real Bubble Fill Validation Follow-up — HARNESS

## 1. 目的

验证：

```text
真实对白气泡
+ glyph-level text mask
+ allowed_edit_mask
+ protected_mask
→ fill
→ 是否可安全支持 restricted AUTO_FILL
````

必须分别判断：

```text
fixture 是否有效
mask 是否有效
算法输出是否有效
P0 策略是否可接受
```

---

## 2. Fixture 集合

正式实验固定 12 个 core fixtures：

```text
8 个 A 类：AUTO_FILL 候选
2 个 B 类：REVIEW_REQUIRED
2 个 D 类：SKIP control
```

只使用：

```text
local_samples/real/black1.webp
local_samples/real/black2.webp
local_samples/real/gura.webp
local_samples/real/gura_color.webp
```

来源要求：

* 四张真实页都必须被使用；
* 单页最多提供 4 个 fixture；
* A 类不得全部来自同一页面；
* 不得重复同一气泡或近似区域凑数量。

---

## 3. Fixture Manifest

每个 fixture 至少记录：

```json
{
  "fixture_id": "black2-bubble-top-right",
  "source_image": "local_samples/real/black2.webp",
  "region_bbox": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "fixture_class": "A",
  "expected_policy": "AUTO_FILL",
  "text_mask": "masks/text/black2-bubble-top-right.png",
  "allowed_edit_mask": "masks/allowed/black2-bubble-top-right.png",
  "protected_mask": "masks/protected/black2-bubble-top-right.png",
  "risk_tags": []
}
```

合法值：

```text
fixture_class:
A
B
D

expected_policy:
AUTO_FILL
REVIEW_REQUIRED
SKIP
```

---

## 4. 三层 Mask 规则

### text_mask

* 白色表示需清除的文字像素；
* 必须接近 glyph 轮廓；
* 禁止使用整块矩形 bbox；
* 不得覆盖整个气泡内部；
* 不得覆盖轮廓、尾巴或无关线稿。

### allowed_edit_mask

* 表示算法允许修改的最大范围；
* 必须位于气泡内部；
* 必须排除边框、尾巴和重要线稿。

### protected_mask

必须覆盖：

```text
气泡边框
气泡尾巴
人物线稿
背景结构线
面板边界
其他不可修改区域
```

---

## 5. Mask 预审门禁

正式 run 前，每个 A/B fixture 必须满足：

```text
text_mask ⊆ allowed_edit_mask
text_mask ∩ protected_mask = ∅
allowed_edit_mask ∩ protected_mask = ∅
```

并记录：

```text
text_mask_area
allowed_edit_area
protected_area
mask_to_bbox_ratio
mask_to_allowed_ratio
minimum_distance_to_protected_region
```

以下任一情况直接判定 fixture 无效：

```text
text_mask 为大矩形块
text_mask 越过气泡内部
text_mask 覆盖边框或尾巴
minimum_distance_to_protected_region < 1 px
mask_to_bbox_ratio > 0.45 且无人工说明
```

---

## 6. Mask Review 输出

每个 fixture 必须生成四联图：

```text
source crop
text mask overlay
allowed/protected overlay
combined boundary overlay
```

Reviewer 必须在算法运行前确认：

```text
VALID
INVALID
```

只有 `VALID` fixture 才能进入正式 run。

---

## 7. 方法矩阵

仅运行：

```text
fixed_white:
  dilation 0
  dilation 1

border_sampled_fill:
  dilation 0
  dilation 1
```

B 类可以生成 preview candidate，但默认 policy 仍为 `REVIEW_REQUIRED`。

D 类：

```text
不生成正常 candidate
只记录 skip reason 和 risk tags
```

---

## 8. 自动硬门禁

每个 candidate 必须满足：

```text
source hash 未变化
输出尺寸和模式不变
changed_outside_allowed_edit = 0
changed_inside_protected = 0
路径未越界
无处理异常
```

任一失败：

```text
rating = UNUSABLE
```

记录：

```text
changed_inside_text_mask
changed_inside_allowed_edit
changed_outside_allowed_edit
changed_inside_protected
changed_in_dilation_ring
processing_time_ms
source_hash
text_mask_hash
allowed_mask_hash
protected_mask_hash
output_hash
```

---

## 9. 视觉评级

评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

### ACCEPTABLE

必须全部满足：

```text
无可辨认文字残留
无矩形填充块
无明显填充边缘
填充色与内部一致
边框连续
尾巴完整
无线稿或人物损伤
无明显抗锯齿黑边
足以承载后续中文排版
```

### REVIEW

适用于：

* 放大后存在轻微色差；
* 少量抗锯齿残留；
* 边界接近安全阈值；
* 不规则气泡需要人工确认。

### UNUSABLE

适用于：

```text
明显白块
边框破坏
尾巴破坏
背景线稿消失
大面积过度填充
可辨认文字残留
结构性视觉损伤
```

---

## 10. 独立 Reviewer

Reviewer 必须只读检查：

```text
source
三层 mask overlay
candidate
difference overlay
```

Reviewer 不得只看 contact sheet 缩略图。

Reviewer 不修改：

```text
source
manifest
mask
code
candidate
rating
```

若 reviewer 与原评级冲突，以更严格评级为准，并记录冲突。

---

## 11. 成功门槛

### A 类

```text
至少 7/8 fixture 的最佳 candidate 为 ACCEPTABLE
8/8 protected-region damage = 0
8/8 明显矩形填充 = 0
```

### B 类

```text
0 个进入 AUTO_FILL
允许 ACCEPTABLE preview
但最终 policy 必须保持 REVIEW_REQUIRED
```

### D 类

```text
0 个正常 candidate
0 个自动接受
```

### 全局安全

```text
source mutation = 0
invalid fixture admitted to run = 0
changed_inside_protected = 0
changed_outside_allowed_edit = 0
severe damage accepted = 0
```

---

## 12. Verdict

### GO

* A 类 8/8 ACCEPTABLE；
* B/D 边界正确；
* 无安全失败。

### CONDITIONAL_GO

* A 类至少 7/8 ACCEPTABLE；
* 仅允许低方差浅色气泡；
* B 类 review-only；
* D 类 skip。

### FURTHER_SPIKE

* A 类不足 7/8；
* mask 质量仍无法稳定保证；
* 不同真实页面间表现不一致；
* 需要进一步 mask 方法验证。

### NO_GO

* A 类普通气泡仍频繁产生明显损伤；
* 严格 mask 下 fill 仍不可稳定使用。

---

## 13. 停止条件

立即停止：

```text
发现 rectangle mask
正式 run 后 mask 被修改
source 被修改
fixture 分类不满足 8/2/2
需要修改 src/**
需要新增依赖
需要自动 mask 生成
需要 inpaint / LaMa
无法区分 mask failure 与 algorithm failure
```

---

## 14. 最终报告要求

REPORT 必须分别汇报：

```text
fixture validity
mask validity
algorithm results
review conflicts
A/B/D policy results
final verdict
P0 product decision
remaining limitations
```