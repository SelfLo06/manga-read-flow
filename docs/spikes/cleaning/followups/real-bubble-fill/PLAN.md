# Real Bubble Fill Validation Follow-up — PLAN

## 1. 目标

使用 4 张真实漫画页和严格三层 mask，重新验证 restricted `AUTO_FILL`。

核心输出必须同时包含：

```text
可复现 JSON 数据
+ 逐 fixture 图片对比
+ ACCEPTABLE / REVIEW / UNUSABLE 图集
+ 最终 P0 决策
````

---

## 2. 输入

只使用：

```text
local_samples/real/black1.webp
local_samples/real/black2.webp
local_samples/real/gura.webp
local_samples/real/gura_color.webp
```

正式 fixture：

```text
8 个 A 类 AUTO_FILL 候选
2 个 B 类 REVIEW_REQUIRED
2 个 D 类 SKIP control
```

四张页面都必须使用，单页最多 4 个 fixture。

---

## 3. 本地目录

```text
local_samples/cleaning/real_bubble_fill/
├── manifest.json
├── masks/
│   ├── text/
│   ├── allowed/
│   └── protected/
├── previews/
└── ratings/

local_samples/spike_outputs/cleaning-real-bubble-fill/<run_id>/
├── metadata.json
├── results.json
├── summary.json
├── mask-review/
├── candidates/
├── comparisons/
├── accepted-gallery/
├── review-gallery/
├── rejected-gallery/
└── logs/
```

以上内容保持 local-only。

---

## 4. Fixture 选择流程

对每张真实页面先生成带编号的 region proposal 图。

每个候选记录：

```text
fixture_id
source image
region bbox
fixture class
expected policy
risk tags
selection rationale
```

先完成 12 个 fixture 的人工确认，再制作 mask。

不得先做 mask、后倒推 fixture 分类。

---

## 5. 三层 Mask

每个 A/B fixture 创建：

```text
text_mask
allowed_edit_mask
protected_mask
```

D 类只需：

```text
protected_mask
skip_reason
risk_tags
```

Mask 必须人工审查，并生成四联图：

```text
1. source crop
2. text mask overlay
3. allowed/protected overlay
4. combined boundary overlay
```

输出路径：

```text
mask-review/<fixture_id>.png
```

正式 run 前，12 张 mask-review 图必须逐张确认。

---

## 6. 实现文件

新增：

```text
tools/spikes/cleaning/real_bubble_fill_followup.py
tests/unit/test_real_bubble_fill_followup.py
```

不得修改：

```text
src/**
依赖文件
其他 Spike 原始结果
```

---

## 7. CLI

脚本支持：

```bash
python tools/spikes/cleaning/real_bubble_fill_followup.py validate
python tools/spikes/cleaning/real_bubble_fill_followup.py preview
python tools/spikes/cleaning/real_bubble_fill_followup.py freeze
python tools/spikes/cleaning/real_bubble_fill_followup.py run
python tools/spikes/cleaning/real_bubble_fill_followup.py verify
python tools/spikes/cleaning/real_bubble_fill_followup.py summarize
```

### validate

检查：

* fixture 数量为 8/2/2；
* 四张真实页面均使用；
* 路径安全；
* bbox 合法；
* mask 尺寸一致；
* 三层 mask 关系合法；
* 无矩形 text mask；
* source hash 正确。

### preview

生成：

* 页面候选框编号图；
* mask-review 四联图；
* source crop。

### freeze

记录：

```text
manifest hash
source hashes
text mask hashes
allowed mask hashes
protected mask hashes
fixture set hash
```

freeze 后不得修改输入。

### run

方法仅限：

```text
fixed_white:
  dilation 0 / 1

border_sampled_fill:
  dilation 0 / 1
```

A/B 类生成 candidate；D 类只记录 skip evidence。

### verify

检查：

```text
source 未变化
输出尺寸、模式一致
changed_outside_allowed_edit = 0
changed_inside_protected = 0
candidate 与 results.json 一致
freeze hash 未变化
```

### summarize

生成统计、评级分母、fixture 最佳结果和 verdict 输入。

---

## 8. 明确图片交付物

每个 A/B fixture 必须生成一张完整对比图：

```text
comparisons/<fixture_id>.png
```

固定布局：

```text
第一行：
source crop | text-mask overlay | protected overlay

第二行：
fixed_white d0 | fixed_white d1
border_sampled d0 | border_sampled d1

第三行：
difference overlay | 200% best-candidate zoom | final rating
```

图片上必须直接标注：

```text
fixture_id
method
dilation
rating
changed_inside_protected
changed_outside_allowed
failure tags
```

禁止只提供缩略图而不保留原始 candidate PNG。

---

## 9. 三类结果图集

最终必须生成：

### Accepted Gallery

```text
accepted-gallery/index.png
```

包含所有最终 `ACCEPTABLE` fixture：

```text
source crop
best output
200% detail
method / dilation
```

### Review Gallery

```text
review-gallery/index.png
```

包含所有 `REVIEW` fixture，并标记具体原因。

### Rejected Gallery

```text
rejected-gallery/index.png
```

包含：

* `UNUSABLE` candidate；
* B 类未自动接受案例；
* D 类 skip control；
* 矩形填充、边框损坏、残留文字等典型失败。

这三张总图必须成为 REPORT 的直接证据。

---

## 10. Ratings

评级文件：

```text
local_samples/cleaning/real_bubble_fill/ratings/ratings.csv
```

字段：

```text
fixture_id
method
dilation
rating
final_policy
failure_tags
review_note
reviewer
```

评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

每个 A/B candidate 都必须有评级，不允许遗漏。

---

## 11. 单元测试

至少覆盖：

```text
fixture 8/2/2 分类
四张真实页面均使用
path traversal
非法 bbox
mask 尺寸不一致
rectangle text mask 检测
text_mask 超出 allowed_edit
text_mask 与 protected 重叠
fill 不修改 protected 区域
fill 不修改 allowed_edit 外像素
source hash 不变
D 类不生成 candidate
comparison 图生成
gallery 分类正确
summary 分母正确
severe damage 不得 ACCEPTABLE
```

---

## 12. 执行顺序

```text
Preflight
→ baseline tests
→ 标注 12 个真实 fixture
→ 生成 region proposal 图
→ 人工确认分类
→ 制作三层 mask
→ validate
→ preview
→ 逐张审查 mask-review
→ freeze
→ 实现脚本和测试
→ focused tests
→ full pytest
→ formal run
→ verify
→ 人工评级
→ 只读 reviewer
→ 生成 comparisons 和三类 gallery
→ summarize
→ 完成 REPORT
```

正式 run 后发现 mask 错误：

```text
当前 run 作废
保留旧输出
修改 mask
重新 freeze
创建新 run
```

---

## 13. 验证命令

```bash
pytest tests/unit/test_real_bubble_fill_followup.py -q
pytest -q

python tools/spikes/cleaning/real_bubble_fill_followup.py validate
python tools/spikes/cleaning/real_bubble_fill_followup.py preview
python tools/spikes/cleaning/real_bubble_fill_followup.py freeze
python tools/spikes/cleaning/real_bubble_fill_followup.py run
python tools/spikes/cleaning/real_bubble_fill_followup.py verify
python tools/spikes/cleaning/real_bubble_fill_followup.py summarize

python -m json.tool \
  local_samples/spike_outputs/cleaning-real-bubble-fill/<run_id>/results.json \
  >/dev/null

python -m json.tool \
  local_samples/spike_outputs/cleaning-real-bubble-fill/<run_id>/summary.json \
  >/dev/null

git diff --check
```

---

## 14. Final REPORT 必须展示的图片

REPORT 必须直接引用：

```text
1 张 fixture selection overview
至少 4 张 mask-review 示例
12 张 per-fixture comparison 图的路径
accepted-gallery/index.png
review-gallery/index.png
rejected-gallery/index.png
至少 2 张 200% 局部放大成功例
至少 2 张 200% 局部放大失败例
```

最终回复也必须明确列出这些图片路径，不得只汇报通过率。

---

## 15. Verdict 门槛

恢复 restricted `AUTO_FILL`：

```text
A 类至少 7/8 ACCEPTABLE
B 类 0 个进入 AUTO_FILL
D 类 0 个正常 candidate
changed_inside_protected = 0
changed_outside_allowed_edit = 0
明显矩形填充 = 0
severe damage accepted = 0
source mutation = 0
```

最终 verdict：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```
