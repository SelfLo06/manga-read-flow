# Cleaning Real Tool Spike — PLAN

## 1. 目标

使用现有 `local_samples` 图片和冻结的 oracle mask，执行：

```text
solid fill
OpenCV Telea
OpenCV Navier-Stokes
skip baseline
```

最终确定 MVP 的：

```text
fill / inpaint / review / skip
```

适用边界。

---

## 2. 输入目录

优先复用：

```text
local_samples/generated/
local_samples/real/
```

当前可选来源包括：

```text
generated/synthetic_01_clean_dialogue.webp
generated/synthetic_02_narration_boxes.webp
generated/synthetic_03_small_bubble_overflow.webp
generated/synthetic_04_complex_background_skip.webp

real/black1.webp
real/black2.webp
real/gura.webp
real/gura_color.webp
```

不需要新增或下载漫画图片。

---

## 3. Cleaning fixture 目录

创建：

```text
local_samples/cleaning/
├── manifest.json
├── masks/
├── previews/
└── ratings/
```

输出：

```text
local_samples/spike_outputs/cleaning/<run_id>/
├── metadata.json
├── results.json
├── summary.json
├── candidates/
├── comparisons/
└── logs/
```

以上目录保持 gitignored。

---

## 4. Fixture 选择

从现有图片选择 8–12 个 region。

建议：

| 来源                | 场景               |
| ----------------- | ---------------- |
| synthetic_01      | 白色普通气泡           |
| synthetic_02      | 旁白框、竖排文字         |
| synthetic_03      | 小气泡、文字接近边框       |
| synthetic_04      | 弱对比、复杂背景、明确 skip |
| black1 / black2   | 黑白漫画线稿           |
| gura / gura_color | 彩色、人物遮挡、复杂背景     |

至少包括：

```text
3–4 个 AUTO_FILL 候选
2–3 个 AUTO_INPAINT 候选
2–3 个 REVIEW / SKIP 候选
```

不要为了凑数量重复相同场景。

---

## 5. Manifest

`manifest.json` 每个 fixture 记录：

```json
{
  "fixture_id": "white-bubble-01",
  "source_image": "../generated/synthetic_01_clean_dialogue.webp",
  "mask_image": "masks/white-bubble-01.png",
  "region_bbox": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "scenario": "white_bubble",
  "expected_policy": "AUTO_FILL",
  "evaluation_tags": [
    "light_background",
    "bubble_border"
  ]
}
```

`source_image` 指向现有图片，不复制原图。

---

## 6. Oracle mask 准备

人工创建 mask：

```text
白色 = 删除区域
黑色 = 保留区域
```

要求：

* 与 source 图片尺寸一致；
* 只覆盖原文字和必要边缘；
* 不覆盖整个气泡；
* 不覆盖不需要清除的线稿；
* mask 完成后记录 hash；
* 正式 run 后不得修改。

可以先生成空白 mask 和 bbox preview，之后人工绘制。

---

## 7. 实现文件

新增：

```text
tools/spikes/cleaning/spike.py
tests/unit/test_cleaning_spike.py
```

不得修改：

```text
src/manga_read_flow/**
项目依赖文件
其他 Spike 报告
```

---

## 8. CLI

脚本至少支持：

```bash
python tools/spikes/cleaning/spike.py validate
python tools/spikes/cleaning/spike.py preview
python tools/spikes/cleaning/spike.py run
python tools/spikes/cleaning/spike.py verify
python tools/spikes/cleaning/spike.py summarize
```

### validate

检查：

* manifest schema；
* source 存在；
* mask 存在；
* source / mask 尺寸一致；
* bbox 合法；
* expected policy 合法；
* source 和 mask hash。

### preview

生成：

* bbox overlay；
* mask overlay；
* crop preview。

不修改 source 或 mask。

### run

对每个非 skip fixture 执行：

```text
fixed_white
border_sampled_fill

telea radius 2 / 3 / 5
navier_stokes radius 2 / 3 / 5

mask dilation 0 / 1 / 2
```

预计每个 fixture 最多：

```text
2 fill
+ 6 inpaint
× 3 dilation
= 24 candidates
```

如果数量过大，可将 fill 固定为 dilation 0/1，inpaint 使用 0/1/2，但必须在正式运行前冻结。

### verify

检查：

* source hash 未变化；
* 输出尺寸一致；
* candidate 完整；
* results 和文件相符；
* 没有路径越界；
* skip fixture 没有正式 accepted candidate。

### summarize

输出：

* method success count；
* ACCEPTABLE / REVIEW / UNUSABLE；
* failure taxonomy；
* fixture policy；
  -性能统计；
* verdict 输入数据。

---

## 9. OpenCV 环境检查

先运行：

```bash
python - <<'PY'
import cv2
print(cv2.__version__)
PY
```

如果 `cv2` 不存在：

```text
停止；
不要直接修改 pyproject.toml 或 lockfile；
报告当前环境缺失；
再决定使用隔离 Spike 环境。
```

如果存在，记录版本。

---

## 10. 自动指标

每个 candidate 记录：

```text
processing_time_ms
masked_pixel_count
changed_inside_mask
changed_outside_mask
outside_mask_change_ratio
boundary_change_ratio
output_hash
```

实现方式应使用 source 与 output 像素差。

不得用自动指标直接代替视觉评级。

---

## 11. 评级文件

生成：

```text
local_samples/cleaning/ratings/ratings.csv
```

字段：

```text
fixture_id
method
radius
dilation
rating
policy
failure_tags
review_note
```

评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

Policy：

```text
AUTO_FILL
AUTO_INPAINT
REVIEW_REQUIRED
SKIP
```

---

## 12. 单元测试

不得读取真实模型或网络。

至少覆盖：

* manifest 校验；
* mask 尺寸不一致；
* 非法 bbox；
* 路径越界；
* source 不被修改；
* fill 只修改 mask 区域；
* inpaint 输出尺寸一致；
* dilation 固定；
* outside-mask 变化计算；
* skip fixture 不执行算法；
* summary 分母正确；
* severe damage 不得自动接受。

---

## 13. 执行顺序

```text
Preflight
→ 检查 cv2
→ 选择现有 local_samples regions
→ 创建 manifest
→ 制作 oracle masks
→ validate
→ preview
→ 冻结 fixture 和 mask hash
→ 实现脚本与单元测试
→ focused tests
→ full pytest
→ run
→ verify
→ 人工评级
→ summarize
→ 独立只读 reviewer
→ 填写 REPORT
```

正式 `run` 后不得修改 mask 或 fixture。

---

## 14. 验证命令

```bash
pytest tests/unit/test_cleaning_spike.py -q
pytest -q

python tools/spikes/cleaning/spike.py validate
python tools/spikes/cleaning/spike.py preview
python tools/spikes/cleaning/spike.py run
python tools/spikes/cleaning/spike.py verify
python tools/spikes/cleaning/spike.py summarize

python -m json.tool \
  local_samples/spike_outputs/cleaning/<run_id>/results.json \
  >/dev/null

python -m json.tool \
  local_samples/spike_outputs/cleaning/<run_id>/summary.json \
  >/dev/null

git diff --check
```

---

## 15. 停止条件

停止并报告：

```text
cv2 不可用
source 或 mask 被修改
需要新增项目依赖
oracle mask 无法可靠制作
需要自动 mask 生成
需要 LaMa 或生成式模型
脚本需要修改 src/**
输出覆盖原图
fixture 路径越界
```

---

## 16. 完成条件

完成后必须产出：

```text
冻结的 manifest 和 mask hashes
可复现的 cleaning candidates
自动指标
人工评级
fill / inpaint / skip 规则
Cleaning Spike verdict
正式 CleanerProvider 的前置条件
```
