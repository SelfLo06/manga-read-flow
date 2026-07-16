# Cleaning 阶段交接说明

版本：v0.1  
状态：Current Handoff  
适用范围：新对话接续、Cleaning 算法设计、下一轮 Spike 规划  
建议仓库路径：`docs/spikes/cleaning/CLEANING-HANDOFF.md`

---

## 1. 交接目的

本文记录 Cleaning 阶段目前已经完成的工作、失败证据、已冻结决策、暂停项和下一步入口。

它负责回答：

- 为什么当前不能继续直接做 inpainting；
- 为什么需要先验证 text-seeded container association；
- 哪些历史候选和实验仍有效；
- 哪些候选已经被判失败；
- 下一轮允许做什么、禁止做什么。

详细算法事实来源为：

```text
docs/spikes/cleaning/algorithm-lock-v0.1.md
```

本文不替代该 Algorithm Lock。

---

## 2. 项目阶段

项目已完成：

```text
MVP-0 FakeProvider backend closure
Detection + OCR Real Tool Spike
Text Region Grouping follow-up
Page Translation Real Tool Spike
Cleaning initial reconstruction Spike
Real Bubble Fill Validation follow-up
Cleaning Dataset Audit
Cleaning Benchmark Pilot 页面级人工复核
```

尚未完成：

```text
稳定的 Cleaning region benchmark
Text-Seeded Container Association Spike
自动像素级文字 Mask
自动 protected / safe region
LaMa oracle/auto-mask comparison
正式 CleanerProvider
Typesetting Spike
真实单 Page Provider 垂直集成
```

当前正式结论：

```text
Cleaning capability = FURTHER_SPIKE
restricted AUTO_FILL = disabled
general AUTO_INPAINT = disabled
CleanerProvider integration = blocked
AUTO_ACCEPT = disabled
```

---

## 3. Cleaning 阶段全过程复盘

### 3.1 第一阶段：oracle mask 下的重建比较

最初验证：

```text
source image + frozen oracle mask
→ fixed white / border-sampled fill
→ OpenCV Telea / Navier-Stokes
→ local cleaned candidate
```

得到：

- 简单白色或近白气泡、旁白框存在有限可行性；
- 一个低半径 Telea 标签案例可接受；
- OpenCV inpaint 没有证明稳定优于简单 fill；
- 复杂渐变、纹理、人物线稿和装饰文字容易出现模糊、涂抹、线稿损伤；
- 结论为 `FURTHER_SPIKE`。

该实验只证明：

```text
当正确 oracle mask 已存在时，极简单区域可能可重建
```

没有证明自动 Cleaning 可用。

### 3.2 第二阶段：真实气泡受限 fill 复验

真实页复验使用：

```text
text_mask
allowed_edit_mask
protected_mask
```

并验证：

- allowed 外变化；
- protected 内变化；
- mask provenance；
- 200% 视觉审查。

结果：

```text
4 张真实页
8 个 A 类区域
0/8 ACCEPTABLE
```

主要失败：

- 主笔画残留；
- 抗锯齿残留；
- 边框损伤；
- allowed mask 语义越界到人物或背景；
- 像素安全指标通过，但视觉结果仍失败。

核心结论：

```text
算法遵守 mask
≠
mask 语义正确
≠
视觉结果安全
```

因此 restricted `AUTO_FILL` 继续关闭。

### 3.3 第三阶段：问题重新分解

Cleaning 被拆为：

```text
A. 文字实例与 grouping
B. container/support region
C. pixel text mask
D. protected mask / safe edit region
E. reconstruction
F. independent verification / abstention
```

当前主要风险集中在 A–D，不在 E。

### 3.4 第四阶段：真实 benchmark 建设

已有数据：

```text
10 个作品
3 个版本：JP / textless / Chinese
约 2.5GB
```

完成只读审计：

```text
1664 files processed
555 JP anchors
552 complete triplets
189 Gold candidate
358 Silver candidate
5 Reference-only
```

形成候选分区：

```text
Exploration: work-003 / work-004
Dev: work-001 / work-002 / work-006
Frozen Test candidate: work-005 / 007 / 008 / 009 / 010
```

该分区仍标记为：

```text
proposal_not_frozen
```

### 3.5 页面级人工复核

17 个 unresolved item 已全部处理：

```text
confirmed_match: 13
corrected_match: 1
confirmed_extra_page: 2
reject_pair: 1
defer: 0
```

结论安全回写至：

```text
manual-review-resolution.csv
```

未生成：

```text
benchmark-manifest.jsonl
```

### 3.6 第一版 region candidate 失败

从 24 页生成 48 个候选后，人工检查发现大量候选：

- 只覆盖部分文字；
- 以差异连通域而非完整文字实例为单位；
- 裁断字符或文字列；
- 无法作为 Cleaning benchmark region。

结论：

```text
region-candidate-generation = FAIL
reason = incomplete_text_instance
```

页面选择和页面级人工结论保留，region candidates 不再继续人工审核。

### 3.7 完整文字实例修复

后续候选改为 container/text-instance crop，完整性明显改善。

但发现选择偏差：

- 大字；
- 规则容器；
- 清晰 JP-textless 差异；
- 易配准；
- 易分组；
- 偏向简单正例。

因此要求增加 hard-case supplement。

### 3.8 hard supplement v1 再次失败

确认问题：

```text
hard-01 / 02 / 07 → 与 calibration/control 重复
hard-09 → 相邻两个气泡跨容器错误合并
hard-12 / 13 → 网点或配准噪声，不是文字
hard-06 / 08 / 10 / 11 → 普通 control，不是 hard positive
```

当前诊断：

```text
supplement-v1 = FAIL
supplement-v2 = IN_PROGRESS / 未完成
```

历史候选未删除，保留为失败证据。

---

## 4. OCR / Grouping 当前证据

### 4.1 Detection / OCR 主 Spike

现有核心结果：

```text
real core detection hit: 16/16
real core fragmented: 13/16
unmatched predictions: 15
synthetic exact OCR: 8/11
real core exact OCR: 9/16
native real exact: 7/16
native real CER <= 0.30: 14/16
oracle-group real CER <= 0.30: 14/16
```

结论：

```text
Detection/OCR = CONDITIONAL_GO / PASS_WITH_LIMITATIONS
```

已知问题：

- line-level fragmentation；
- 小字；
- 彩色字；
- 低对比；
- 倾斜文字；
- 标点；
- vertical layout；
- auxiliary/unmatched groups；
- synthetic complex-background 存在 detection miss。

当前没有完成：

- detector confidence calibration；
- OCR confidence calibration；
- high/medium/low 阈值；
- 99% region recall 证明；
- 字符级 uncertainty。

### 4.2 Grouping Follow-up

当前小样本结果：

```text
synthetic group hit: 10/11
real core group hit: 16/16
real extra groups: 9
reading order correct: 16
reading order error: 0
verdict: PASS_WITH_LIMITATIONS
```

必须保留一等证据：

```text
grouping_uncertain
extra_group
auxiliary_text
review_required
```

现有 grouping 没有覆盖：

- 接触气泡；
- 复杂容器；
- hard-09 类型的跨容器误合并；
- 真实大规模 99% recall 假设。

---

## 5. Translation 与 Cleaning 的关系

Translation 与 Cleaning 应作为并行分支：

```text
                         ┌─→ Translation → Translation Check ─┐
Detection → Grouping → OCR                                   ├→ Typesetting
                         └─→ Cleaning Perception → Cleaning ──┘
```

Translation 需要：

```text
OCR text
TextBlock IDs
reading order
glossary
translation configuration
```

Cleaning 需要：

```text
original image
fragment geometry
container association
text mask
protected mask
cleaning configuration
```

Cleaning 不依赖中文译文。Translation 不依赖 cleaned image。

OCR 对 Cleaning 的价值：

- 提供文字种子；
- 提供 fragment/group geometry；
- 提供方向和尺度；
- 提供遗漏与冲突检查；
- 提供 weak prior；
- 提供 cleaned-image residual validation 的对照信息。

OCR 字符串内容正确与否不是 Cleaning 的关键条件。

---

## 6. 已冻结算法方向

事实来源：

```text
docs/spikes/cleaning/algorithm-lock-v0.1.md
```

主组合：

```text
geometry-aware fragment grouping
+ SLIC superpixels
+ multi-source geodesic propagation
+ hard/soft barrier separation
+ geodesic Voronoi virtual boundaries
+ explicit/implicit/free-text/uncertain classification
```

文字 Mask：

```text
detector seed
+ polarity-aware local segmentation
+ seeded connected components
+ stroke-width evidence
+ soft-edge completion
```

安全区域：

```text
eroded container/support region
- contour band
- protected structures
- virtual-boundary band
- uncertainty band
```

受限重建：

```text
E1 → fixed/border-sampled fill only
E2 → Telea comparison only, REVIEW_REQUIRED
E3 → REVIEW_REQUIRED
E4 → SKIP
```

---

## 7. 暂停与禁止事项

暂停：

```text
hard supplement v2
region-review full expansion
benchmark-manifest generation
actual Cleaning implementation
```

当前禁止：

```text
LaMa
ControlNet
Diffusion
FFT screentone reconstruction
通用 inpainting
正式 CleanerProvider
Workflow integration
AUTO_ACCEPT
Typesetting implementation
```

禁止以“算法设计看起来完整”为理由跳过 Spike。

禁止以当前 OCR / Detection 小样本结果声称已达到 `99%` 区域召回。

禁止把旧 difference mask 当作 ground truth。

---

## 8. 下一项任务

下一项唯一任务：

```text
Text-Seeded Container Association Spike
```

只验证：

```text
文字 fragment
→ 保守 grouping
→ SLIC / geodesic propagation
→ same-container merge
→ different-container virtual boundary
→ explicit / implicit / free-text / uncertain
→ abstention
```

不验证：

```text
actual inpainting
LaMa
CleanerProvider
Workflow integration
benchmark manifest
AUTO_ACCEPT
```

---

## 9. 下一项 Spike 的固定对照

```text
B0:
geometry grouping + bbox/dilation

B1:
geometry grouping + seeded watershed

P1:
SLIC + multi-source geodesic + virtual boundary

P2:
P1 + Random Walker refinement
```

P2 仅用于 P1 边界置信度不足的区域。

---

## 10. 固定回归样本

新 Spike 至少需要：

```text
hard-09：
相邻/接触气泡不得跨容器合并

同一气泡多列文字：
不得错误拆分为多个容器

边界断裂气泡：
需要 visible + virtual boundary

free-text 简单标签：
生成 support region，不伪造气泡

not-text 误检：
正确 SKIP / abstain

透明或纹理气泡：
正确识别为高风险，不进入低风险候选
```

---

## 11. 交付与工程边界

Real Tool Spike 代码必须留在：

```text
tools/spikes/**
tests/unit/**
docs/spikes/**
local ignored artifacts/**
```

不得进入正式产品路径：

```text
src/manga_read_flow/**
```

Provider Adapter 边界保持：

- 不访问 Repository / SQLite；
- 不登记正式 artifact；
- 不创建 QualityIssue；
- 不决定 retry / fallback / skip / block；
- 不更新 active pointer。

ArtifactService 仍是正式 artifact 生命周期唯一入口。

Repository / DAO 仍是 SQLite 唯一入口。

原图永不覆盖。

---

## 12. 新对话启动顺序

新对话开始后：

1. 读取本 Handoff；
2. 读取 `algorithm-lock-v0.1.md`；
3. 读取 Detection/OCR 与 Grouping REPORT；
4. 读取 Cleaning 主 REPORT 与真实气泡 follow-up；
5. 抽取 5–6 个固定回归样本；
6. 设计 `Text-Seeded Container Association Spike` 的 GOAL / HARNESS / PLAN；
7. 评审后再交给 Codex 实现。

不要直接进入代码实现。

---

## 13. 建议同时提供的文件

```text
docs/spikes/cleaning/algorithm-lock-v0.1.md
docs/spikes/cleaning/CLEANING-HANDOFF.md
docs/spikes/detection-ocr/REPORT.md
docs/spikes/detection-ocr/followups/grouping/REPORT.md
docs/spikes/cleaning/REPORT.md
真实气泡 fill follow-up REPORT
docs/spikes/cleaning-dataset-audit/REPORT.md
docs/spikes/cleaning-benchmark-pilot/REPORT.md
docs/spikes/cleaning-benchmark-pilot/GATE.md
docs/spikes/cleaning-benchmark-pilot/manual-review-resolution.csv
docs/spikes/cleaning-benchmark-pilot/page-selection.csv
hard-09 等固定回归图
```

项目基线文件按需读取：

```text
AGENTS.md
docs/SRS-v1.0.md
docs/HLD.md
docs/PROJECT-PLAN.md
```

---

## 14. 当前一句话状态

```text
Cleaning 不是在等待更强 inpainting，而是在等待 text-seeded container association、pixel text mask 和 safe edit region 的可验证证据。
```

---

## 15. Goal 7 supersession（2026-07-16）

此前“下一项 Spike 是 Text-Seeded Container Association”的表述已完成，不再表示待启动。

Goal 7 已证明 page-global association 不可用：全页 union geometry、全页 topology 联锁和 full-page B1 分别造成误弃权、连带丢失与 OOM 风险。替代方案为 per-group / 小型 local-cluster routing + bounded local B1。

已通过的范围：普通对白在整页内独立进入 coarse candidate 的覆盖与资源稳定性。Phase B 人工确认 10/12 个普通对白 group 有可见 candidate；Phase C 40 页中 255/255 local B1 成功，0 crash/timeout，p95 0.657 s，峰值 165.5 MB。

未通过、不得夸大的范围：非空 coarse region 不是 confirmed container。标题、SFX 和复杂画面仍会出现错误或泄漏候选。所有 B1 输出继续为 `REVIEW_REQUIRED`；Pixel Text Mask、safe edit region、E1/E2 自动清字仍 blocked。

下一项仅可考虑 `Goal 8 — Local Candidate Qualification Spike`；它须复用冻结 S1/Goal 7 artifacts，验证 local candidate 的内容角色与语义正确性，不能直接进入 Cleaning。
