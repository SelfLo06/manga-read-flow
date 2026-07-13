# Real Bubble Fill Validation Follow-up — GOAL

## 1. 背景

首轮 Cleaning Spike 的 `FURTHER_SPIKE` 结论保留。

该实验存在两个关键缺口：

1. fill 样本过度依赖 synthetic 页面；
2. `changed_outside_mask = 0` 只能证明算法未越出处理 mask，不能证明 mask 本身没有覆盖气泡边框、背景线稿或其他受保护区域。

本 follow-up 使用现有真实漫画页面，重新验证受限 `AUTO_FILL` 是否成立。

---

## 2. 核心目标

验证以下受限路径：

```text
真实漫画对白气泡
+ 人工审核的 glyph-level text mask
+ allowed-edit / protected 区域
→ fixed or sampled fill
→ 严格安全与视觉检查
```

需要回答：

1. 普通白色或浅色气泡能否稳定自动清字；
2. fill 是否会形成矩形块、色差、文字残留或边框损伤；
3. 哪些气泡只能进入 `REVIEW_REQUIRED`；
4. 是否有足够证据恢复 P0 的 restricted `AUTO_FILL`。

---

## 3. 输入图片

只使用现有真实样本：

```text
local_samples/real/black1.webp
local_samples/real/black2.webp
local_samples/real/gura.webp
local_samples/real/gura_color.webp
```

不得下载、搜索或新增外部图片。

---

## 4. Fixture 分类

准备恰好 12 个 core fixtures：

```text
8 个 A 类：平坦浅色气泡
2 个 B 类：边界敏感气泡
2 个 D 类：明确 skip control
```

### A 类：AUTO_FILL 候选

要求：

* 白色或低方差浅色内部；
* 文字完整位于气泡内部；
* 与气泡轮廓、尾巴和重要线稿保持距离；
* 不需要纹理重建。

### B 类：REVIEW_REQUIRED

包括：

* 文字靠近边框；
* 不规则或连接气泡；
* 尖角、多边形、云状轮廓；
* 彩色文字、描边或复杂抗锯齿；
* 安全间距不足。

### D 类：SKIP

包括：

* 拟声词或艺术字；
* 摄像机 UI、时间码等 overlay；
* 文字覆盖人物、面板线稿或复杂背景；
* 无法建立安全编辑区域。

---

## 5. 三层 Mask

每个 A/B fixture 必须提供：

```text
text_mask
allowed_edit_mask
protected_mask
```

### text_mask

* 仅覆盖需要删除的文字像素；
* 必须是 glyph-level；
* 禁止直接使用文本 bbox 矩形；
* 允许固定 dilation `0 / 1`。

### allowed_edit_mask

表示算法最多允许修改的区域：

```text
气泡内部
- 边框保护带
- 尾巴保护带
- 重要线稿
```

必须满足：

```text
effective_text_mask ⊆ allowed_edit_mask
```

### protected_mask

至少保护：

* 气泡轮廓；
* 气泡尾巴；
* 人物和背景线稿；
* 面板边框；
* 重要结构。

必须满足：

```text
effective_text_mask ∩ protected_mask = ∅
changed_pixels ∩ protected_mask = ∅
```

---

## 6. 方法范围

只验证：

```text
fixed_white
border_sampled_fill
```

参数：

```text
dilation = 0 / 1
```

不得运行：

* OpenCV inpaint；
* LaMa；
* 自动 mask 生成；
* 生成式修复；
* 其他颜色拟合或大规模参数搜索。

---

## 7. Fixture 预审门禁

正式 run 前，每个 fixture 必须通过：

```text
source hash 固定
mask 尺寸正确
text mask 为 glyph-level
text mask 未越出 allowed-edit 区域
text mask 未触碰 protected 区域
气泡轮廓与尾巴完整可辨认
人工确认 overlay
```

必须生成：

```text
source crop
text-mask overlay
allowed/protected overlay
combined boundary overlay
```

任一项失败则 fixture 不得进入正式 run。

---

## 8. Candidate 硬门禁

每个 candidate 必须满足：

```text
输出尺寸与模式不变
source 文件未修改
changed outside allowed-edit mask = 0
changed inside protected mask = 0
无路径越界
无处理异常
```

记录：

```text
text_mask_area
effective_mask_area
allowed_edit_area
mask_to_bbox_ratio
mask_to_bubble_interior_ratio
minimum_distance_to_protected_region
changed_in_dilation_ring
processing_time_ms
source_hash
mask_hash
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

只有同时满足以下条件才可评为 `ACCEPTABLE`：

* 无可辨认原文残留；
* 无矩形填充块或明显填充边缘；
* 气泡轮廓连续；
* 气泡尾巴完整；
* 无人物、线稿或背景结构损伤；
* 填充色与气泡内部一致；
* 无明显抗锯齿黑边；
* 有足够区域支持后续中文嵌字。

任意明显结构损伤直接为 `UNUSABLE`。

---

## 10. 成功条件

恢复 restricted `AUTO_FILL` 至少需要：

```text
A 类至少 7/8 ACCEPTABLE
B 类 0 个自动接受
D 类 0 个正常 candidate
protected-region damage = 0
明显矩形填充 = 0
source mutation = 0
所有正式 fixture 通过 mask 预审
```

---

## 11. Verdict

最终 verdict：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

### CONDITIONAL_GO

仅当 A 类通过门槛时，允许：

```text
低方差白色/浅色气泡
+ 严格 glyph mask
+ 安全编辑区域
→ restricted AUTO_FILL
```

B 类继续 `REVIEW_REQUIRED`，D 类继续 `SKIP`。

---

## 12. In Scope

允许创建：

```text
tools/spikes/cleaning/real_bubble_fill_followup.py
tests/unit/test_real_bubble_fill_followup.py

local_samples/cleaning/real_bubble_fill/**
local_samples/spike_outputs/cleaning-real-bubble-fill/**
```

允许修改：

```text
docs/spikes/cleaning/followups/real-bubble-fill/REPORT.md
```

---

## 13. Out of Scope

不得修改：

```text
src/**
项目依赖文件
其他已关闭 Spike 的原始结果
```

不得实施：

* 正式 CleanerProvider；
* Workflow / ArtifactService / SQLite 接入；
* Typesetting；
* 自动气泡或文字 mask 检测；
* OpenCV inpaint；
* LaMa；
* UI / API。

---

## 14. 安全边界

* 原图只读，永不覆盖；
* fixture 和输出保持 local-only；
* 正式 run 后不得修改 mask；
* mask 有误时必须作废 run 并创建新 run；
* 不得用自动指标替代人工视觉审查；
* 不得因为算法成功返回图片就判定成功。

---

## 15. 最终输出

必须产出：

```text
docs/spikes/cleaning/followups/real-bubble-fill/REPORT.md

local_samples/spike_outputs/cleaning-real-bubble-fill/<run_id>/
├── metadata.json
├── results.json
├── summary.json
├── candidates/
├── mask-review/
├── comparisons/
└── logs/
```

REPORT 必须明确区分：

```text
fixture validity
mask validity
algorithm quality
P0 product decision
```
