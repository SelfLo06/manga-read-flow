# Text-Seeded Container Association Spike — HARNESS

版本：v0.3
状态：R0 Semantic + Topology + S1 Input Frozen / Association 未实施

## 1. 目的

本 Harness 隔离验证：

```text
文字 seed 的完整性与污染
×
grouping / container association 方法
→
容器、支持区、虚拟边界、置信度与弃权
```

它不验证像素级文字 Mask、safe edit region 或任何重建输出。

## 2. Harness 不变量

1. 原图与已有 source artifact 全部只读，运行前后 hash 必须一致。
2. 算法输入不得包含 GT container assignment、GT boundary、expected text 或人工 verdict。
3. GT 只在输出冻结后进入 evaluator。
4. 旧 difference mask、旧 48 个失败 candidates、supplement-v1 mask 均不得作为 GT。
5. `hard-09`、`hard-12/13` 如被采用，必须重新独立标注；旧 failure label 只用于选例，不用于算法输入。
6. 所有方法使用同一 ROI、同一 seed condition、同一 GT 与同一评分代码。
7. 参数只在 calibration 子集冻结；最终评估子集只运行一次，不按结果回调参数。
8. 任何 uncertain case 都不得被人工改写为低风险候选以提高覆盖率。
9. 不生成 `benchmark-manifest.jsonl` 或任何正式 benchmark manifest。
10. 本轮不存在 `AUTO_ACCEPT`。

## 3. 两级样本集

### 3.1 R0 identity freeze

维护者已从扩大后的 18 候选中选定六类 source/ROI。下表冻结 identity，但精确语义、边界和 support GT 仍以 A/B 独立标注为准：

| 回归 ID | 场景 | 当前候选来源 | 必须断言 |
| --- | --- | --- | --- |
| R0-contact-different-containers | 相邻/接触气泡 | `_017.jpg` ROI `[0,40,430,540]` | 不得跨容器合并；不确定时必须 abstain。 |
| R0-same-container-multicol | 同一气泡多列文字 | `black2.webp / black2_r02` ROI `[800,300,440,620]` | 不得因多 source 竞争错误拆分。 |
| R0-broken-or-occluded-boundary | 断裂/遮挡边界 | `104.jpg` ROI `[600,100,300,390]` | 候选为 `implicit_container`；A/B 若不确认则重开。 |
| R0-free-text | 无气泡简单文字 | `015.jpg` ROI `[820,0,225,420]` | 输出有限 support region；`container_mask = null`。 |
| R0-not-text | not-text 误 seed | `_033.jpg` ROI `[620,0,560,430]` | `SKIP`；不得产生低风险 support。 |
| R0-textured-decorative-risk | 复杂背景装饰文字 | `01.png` ROI `[0,0,2263,1200]` | 只验证高风险负例与 abstention，不代表普通对话气泡。 |

source/crop hashes 与选择证据见 [`../r0/R0-SELECTION-v0.3.md`](../r0/R0-SELECTION-v0.3.md)；分层证据裁决见 [`../r0/R0-ADJUDICATION-v0.3.md`](../r0/R0-ADJUDICATION-v0.3.md)。A/B 选择题已冻结 semantic labels 与 container topology，A overlay 已冻结为 coarse target-region reference。pixel-accurate boundary/support GT 与双人边界一致性不可用。

### 3.2 Boundary uncertainty

v0.2 曾提出以下候选规则，但维护者已重开数值冻结。R0 没有双人 pixel boundary annotation，不能用于冻结这些数值；它们只能作为未来独立 calibration 的起始假设：

```text
delta = clip(round(0.15 * median_character_height), 2, 8)
visible GT band half-width = delta
virtual GT band half-width = 2 * delta
P1 ridge core = normalized geodesic margin <= 0.05
P1 uncertainty band = normalized geodesic margin <= 0.15
```

SLIC `-20% / nominal / +20%` 扰动发生归属或拓扑变化的区域仍必须作为 uncertainty 证据；具体 margin 数值需在扩展后的 calibration 设计中重新批准。

### 3.3 R1 最低正式样本组成（当前最小 Spike 延后）

维护者已将当前目标收窄为“判断容器关联方案是否值得继续”。下表只保留为未来扩大验证的参考，不是本轮 R0 GO/FURTHER/NO-GO 的有效性门禁，也不得在 Goal 1 中扩建。

| 类型 | 最低数量 |
| --- | ---: |
| 规则白气泡 | 5 |
| 同一气泡多列文字 | 5 |
| 相邻或接触气泡 | 5 |
| 断裂或遮挡边界 | 5 |
| 矩形旁白框 | 3 |
| 无气泡简单标签 | 3 |
| 透明或纹理气泡 | 5 |
| 非文字误检 | 3 |
| 艺术字 / SFX 弃权 | 3 |

最低合计为 `37` 个独立 region。应跨作品取样，并以 source hash、ROI 与感知 hash 检查跨类别和 calibration/evaluation 重复；重复率必须为 `0`。

## 4. 人工 GT 与盲评

每个 region 的 evaluator-only GT 至少包含：

- 完整文字 fragment polygon 与 fragment ID；
- fragment 到真实文字实例/容器的归属；
- `explicit_container / implicit_container / free_text / uncertain`；
- explicit/implicit 的容器区域；
- visible boundary；
- 可接受的 virtual-boundary band 或 boundary-uncertain band；
- free text 的最小/最大合理 support envelope；
- not-text / SFX / complex-free-text 的预期弃权；
- 人工风险标签与说明。

R0 采用分层证据：A/B 独立选择题冻结语义与容器拓扑，A overlay 冻结 coarse target-region reference。B 未提供 overlay 只意味着 inter-annotator boundary agreement 不可用；不得回写为 semantic/topology uncertainty。R0 不参与精确 IoU/boundary-F1 门禁，只使用分类、容器数量、same/different topology、跨容器泄漏、abstention 与相对 coarse reference 的定性或宽容差评估。R1 若要求精确 IoU/F1，仍须另行取得符合该指标的 pixel-accurate GT。

## 5. 统一输出契约

四种方法都必须输出同一最小结构，缺失能力显式为 `null`，不得伪造：

```text
region_id
method_id
seed_condition
input_fragment_ids
output_group_ids
fragment_assignment
alternative_grouping
grouping_confidence
container_type
container_mask_or_null
support_region_or_null
visible_boundary
virtual_boundary_or_null
boundary_uncertainty_band
same_container_decisions
unassigned_fragments
confidence_components
recommended_decision
abstention_reasons
runtime_metadata
```

`recommended_decision` 只允许：

```text
LOW_RISK_ASSOCIATION_CANDIDATE
REVIEW_REQUIRED
SKIP
```

`LOW_RISK_ASSOCIATION_CANDIDATE` 只表示关联候选，不表示可清字或可自动接受。

## 6. B0 / B1 / P1 / P2 对照矩阵

| 维度 | B0 | B1 | P1 | P2 |
| --- | --- | --- | --- | --- |
| 名称 | geometry grouping + bbox/dilation | geometry grouping + seeded watershed | SLIC + multi-source geodesic + virtual boundary | P1 + Random Walker refinement |
| 初始 grouping | 冻结的纯几何保守 grouping | 同 B0 | fragment graph + 保守 grouping + alternative grouping | 继承 P1 |
| 区域生成 | group union bbox，按字符尺度冻结 dilation | 在同一 ROI 的图像边界上 seeded watershed | SLIC superpixel graph 上多源累计代价传播 | 仅细化 P1 的 uncertain boundary band |
| 多源竞争 | 无；重叠仅报告冲突 | watershed seed 竞争 | 有，输出 geodesic Voronoi ridge | 继承 P1 |
| same-container 决策 | 仅使用初始 geometry grouping；无二次图证据 | 仅使用 watershed 后冲突诊断，不重写基线 | 显式计算 `P_same_container`；高则合并重跑，低则保留竞争，不确定则弃权 | 不改变 P1 的 same-container 决策 |
| hard / soft barrier | 无 | 边界图作为 watershed 高程 | 高置信结构 hard barrier；中低置信结构 soft cost | 继承 P1 |
| virtual boundary | 无 | watershed ridge 仅作基线边界 | 有，须带 uncertainty band | 在 P1 不确定 band 内细化 |
| free text | 固定尺度 dilation support | watershed basin，仍标为 support 而非 container | 动态 geodesic support envelope | 仅细化 uncertain support edge |
| uncertain 输出 | bbox overlap、越界或低 grouping confidence 时弃权 | basin 泄漏、seed 冲突或边界不稳定时弃权 | same-container、boundary 或 support 不稳定时弃权 | 继承或增加弃权，不得把 P1 uncertainty 强制改为低风险 |
| 运行条件 | 全部 case | 全部 case | 全部 case | 仅 P1 预先判定边界不确定的 case |
| 角色 | 最低几何基线 | 简单图像边界基线 | 主候选 | 条件 refinement，不是默认路径 |

公平性约束：B0/B1 不得获得 P1 的 GT-informed same-container 决策；P1/P2 也不得获得 GT container assignment。所有方法的 ROI 生成规则和 seed condition 必须冻结并可追踪。

## 7. S0 / S1 / S2 / S3 Seed 鲁棒性实验

| 条件 | 输入构造 | 固定运行方式 | 主要问题 | 安全期望 |
| --- | --- | --- | --- | --- |
| S0 | 人工确认完整 fragment seed；只含几何、方向、尺度，不含 container GT。 | B0/B1/P1 全量运行；P2 只处理 P1 uncertain case；作为 oracle-seed 上限。 | 方法在完整文字位置下能否正确关联？ | 不得以完整 seed 掩盖 false merge/false split。 |
| S1 | 冻结真实 Detector + Grouping 输出，包括 extra、auxiliary、uncertain 与 detector score；OCR 字符串只作可选弱证据。 | B0/B1/P1 在同一冻结 run 上运行；P2 仍按条件运行。 | 真实 fragmentation、extra group 和方向误差影响多大？ | 对无法解释的 seed 降置信或弃权。 |
| S2 | 以 S1 为基础，在全体合格真实 fragments 上按 `1% / 3% / 5%` 删除；每档使用 5 个预先冻结随机种子，按场景分层，记录被删 fragment。 | 四种方法都运行；P2 仍只在 P1 uncertain case 运行。 | 漏 seed 是否造成漏容器、错误合并或虚假低风险？ | 覆盖可下降，但 false-low-risk 必须为 0；证据不足时 `REVIEW_REQUIRED/SKIP`。 |
| S3 | 以 S1 为基础，按全体真实 fragment 数的 `1% / 3% / 5%` 注入 plausible false-positive boxes；每档 5 个冻结随机种子，来源覆盖纹理、结构线与 independently confirmed not-text。 | 注入框不得带 not-text 标签给算法；四种方法同输入。 | FP 是否生成虚假 container/support 或污染邻近归属？ | FP 不得产生低风险独立区域；污染真实组时必须降置信或弃权。 |

S2/S3 的百分比按完整 R1 集合的 fragment 总数计算，避免在单页 fragment 很少时把“1%”放大成删除/注入三分之一。每个 region 的局部扰动结果仍单独报告。

禁止把 S2/S3 的目标写成“污染下仍保持高覆盖”。本实验的首要目标是证明不确定时能正确 abstain。

### 7.1 S1 final run 与历史限制

v0.2 使用过以下 cold chain；当前只保留为历史证据，不是 final S1 freeze：

```text
Detection/OCR: 20260710T091753Z-0676c2 / cold
Grouping:      20260710T142823Z-b08c9c / cold
```

历史 chain 只明确覆盖当前 R0 的 `black2`，且当时 Detection runner 位于 Git ignored 路径，不能证明新 extension 与历史代码逐字一致。因此 final S1 改为对六个 blind R0 crop 运行一条新的统一 chain：

```text
Run:           20260715T075811Z-3e9711
Results hash:  33f1061aac43e5b4ca4b86d66c8aec262d19eb33151a965aaf81e656d406da0a
Spec hash:     95d7d627eefb2b8d7c119364c6e362528848399e5b06a6de7f3c28a1bd7995e7
Detector:      PP-OCRv6_medium_det
Grouping:      orientation=1.25 / overlap=0.15 / relative-gap=0.35 / min-gap=16
```

六例均有可追踪 fragments/groups，输入 hash 运行前后一致。完整 provenance、覆盖和 calibration 隔离见 [`../goal1-s1-input-freeze/S1-INPUT-FREEZE-v0.1.md`](../goal1-s1-input-freeze/S1-INPUT-FREEZE-v0.1.md)。

### 7.2 P_same_container calibration-only 规则

以下网格是 v0.2 历史提案，不再是冻结值。新的 calibration/evaluation split 批准前不得运行阈值选择：

```text
T_different ∈ {0.05, 0.10, 0.15, 0.20}
T_same      ∈ {0.80, 0.85, 0.90, 0.95}
```

数值冻结前所有 pair 都必须 `uncertain / REVIEW_REQUIRED`。R0 与其他 evaluation-only asset 不得参与阈值选择；evaluation 失败不得触发重调。

Goal 2 已在维护者批准的最小 `cal-01/cal-02` split 上重新批准并执行独立网格，旧 v0.2 网格仍保持退役：

```text
T_different ∈ {0.40, 0.45, 0.50, 0.55, 0.60}
T_same      ∈ {0.70, 0.75, 0.80, 0.85, 0.90}
minimum empirical margin = 0.20

selected T_different = 0.40
selected T_same      = 0.75
empirical margin     = 0.42618291751598514
```

完整 feature、pair、hash、sanity 输出和限制见 [`../goal2-harness-calibration/GOAL2-HARNESS-CALIBRATION-v0.1.md`](../goal2-harness-calibration/GOAL2-HARNESS-CALIBRATION-v0.1.md)。该 lock 只供 Goal 3 的冻结 R0 轻量矩阵读取；R0 不得用于回调阈值。

### 7.3 Goal 3 R0 result

Goal 3 已按冻结输入和阈值完成一次 `6 × B0/B1/P1` 轻量矩阵：三种方法 safety decision 均为 6/6、false-low-risk 均为 0；P1 topology 为 2/3，与 B0/B1 相同，且相对 A coarse reference 未证明优于 B1。Gate verdict 为 `FURTHER_SPIKE`，当前不得进入 Pixel Text Mask。详见 [`../goal3-r0-validation/GOAL3-R0-VALIDATION-REPORT-v0.1.md`](../goal3-r0-validation/GOAL3-R0-VALIDATION-REPORT-v0.1.md) 与 [`../goal3-r0-validation/GOAL3-GATE-v0.1.md`](../goal3-r0-validation/GOAL3-GATE-v0.1.md)。

## 8. 指标定义

### 8.1 Grouping

- `fragment_pair_precision / recall`：同组 fragment pair 与 GT 同容器 pair 的比较；
- `false_merge_count`：一个输出 group 含多个 GT 容器 fragment；
- `false_split_count`：一个 GT 容器被多个非弃权输出 group 分裂；
- `unassigned_fragment_ratio`：未归属高置信 fragment / 高置信 fragment；
- `unique_assignment_rate`：只属于一个输出关联的高置信 fragment / 高置信 fragment；
- `cross_container_merge_count`：跨真实容器的非弃权 merge 数。

### 8.2 Container / Support

- `container_iou`：仅对另行具备 pixel-accurate GT 的 R1 explicit/implicit container；R0 禁用；
- `boundary_f1`：仅对另行具备 pixel-accurate GT 与冻结容差带的 R1 计算；R0 禁用；
- `full_seed_coverage`：输出区域覆盖完整 GT fragment 区域的比例，即使 S2 删除的 fragment 也由 evaluator 检查；
- `container_leakage_ratio`：仅在具备 pixel-accurate GT 时计算；R0 只判断是否跨冻结的 coarse container topology 泄漏；
- `support_envelope_validity`：free-text support 是否位于人工最小/最大 envelope 之间；
- `virtual_boundary_correctness`：异容器是否被正确分开、同容器是否没有伪造 ridge，并记录虚拟边界 band 命中；
- `manual_region_correctness`：盲评者对“合理完整且无危险泄漏”的二元结论。

### 8.3 Abstention / 系统级

- `abstention_correctness`：预期不确定/负例是否输出 `REVIEW_REQUIRED/SKIP`；
- `false_low_risk_candidate_count`：GT 为跨容器不确定、not-text、复杂艺术字、严重结构粘连，却输出低风险关联候选的数量；
- `risk_coverage_curve`：按置信阈值展示覆盖率与 false-low-risk risk；
- `low_risk / review_required / skip` 数量；
- `decision_flip_rate`：S1 到 S2/S3 后从 review/skip 错翻为 low-risk 的比例；
- P2 相对 P1 的 uncertain-subset 增益与安全回退数量。

像素 text precision/recall、soft-edge recall、protected overlap、residual text 不属于本 Spike，不得伪造这些指标。

## 9. 门禁

### 9.1 Harness 有效性门禁

- R0 六类具有冻结的 semantic labels、container topology 与 A coarse target-region reference；
- 当前最小 R0 Spike：R1 最低 37 region 不适用；若未来启动 expanded validation，必须在该轮重新启用此门禁；
- calibration/evaluation 与类别间重复为 `0`；
- source hash 运行前后相同；
- GT 未进入算法输入；
- 旧 difference/supplement mask 未被当作 GT；
- S0/S1/S2/S3 与 B0/B1/P1/P2 运行矩阵无 silent skip；
- 输出、参数、随机种子和失败均可追踪。

任一项失败，本次结果无效，不得给算法 verdict。

### 9.2 P1 主门禁

在 S0 与 S1 上同时满足：

```text
关键接触气泡回归集 false merge = 0
hard-09 cross-container merge = 0
明显字符/fragment 被 ROI 或 region 边界裁断 = 0
跨集合重复 = 0
高置信 fragment 单一归属率 >= 98%
人工判断正确的 container/support region >= 90%
```

并且：

- 同一气泡多列文字不得被虚拟边界拆成多个低风险容器；
- 跨容器不确定、not-text、复杂艺术字、严重结构粘连必须 `REVIEW_REQUIRED` 或 `SKIP`；
- P1 必须相对 B0/B1 至少在接触/断裂边界安全上显示实际收益，且不能增加新的 hard-gate 失败；否则复杂度没有成立依据。

### 9.3 S2 / S3 安全门禁

```text
false_low_risk_candidate_count = 0
review/skip → low-risk 的危险 decision flip = 0
```

允许 coverage、IoU 或 recall 下降；不允许在证据变差时更自信。漏 seed、FP 或无法解释 fragment 必须反映为 uncertainty、unassigned evidence 或 abstention。

### 9.4 P2 保留门禁

P2 不决定主 Spike 是否通过。只有在预先由 P1 标记的 uncertain subset 上：

- 至少修正一个真实边界/支持区错误；
- 不新增 false merge、false split、false-low-risk 或危险 decision flip；
- 不改变 confident P1 case；

才保留为后续候选。否则明确拒绝 P2，P1 保持主路径。

## 10. Verdict

### `GO_TO_PIXEL_TEXT_MASK_SPIKE`

Harness 有效，P1 主门禁与 S2/S3 安全门禁全部通过；P1 相对基线有安全收益。只允许规划后续 pixel text mask Spike。

### `FURTHER_SPIKE`

Harness 有效，但 P1 仍有可定位、可修正且未造成不可接受低风险输出的问题；或样本/标注不足以给结论。

### `NO_GO`

在有效 Harness 上，hard-09/接触气泡持续跨容器合并、同容器多列持续错误拆分、S2/S3 产生 false-low-risk，或 P1 不优于简单基线且无法通过 abstention 控制风险。

无论 verdict 为何，均不得启用实际 Cleaning、CleanerProvider、Workflow integration 或 `AUTO_ACCEPT`。

## 11. 停止条件

运行或实现过程中出现以下任一条件，立即停止，不继续调参：

1. 来源文档出现新的未解决冲突；
2. GT container assignment、expected decision 或 reviewer verdict 泄漏到算法输入；
3. 原图、既有报告、既有 CSV 或本地 source 被修改；
4. 发现跨集合重复、错误配对、incomplete text instance 或 crop 截字；
5. 旧 difference mask / supplement mask 被当作 GT；
6. 当前最小 Spike 的 R0 六类或冻结 calibration 资产无法满足；未来 expanded validation 才重新启用 R1 最低样本条件；
7. 任一方法/seed 条件被 silent skip，或 evaluator 对不同方法使用不同规则；
8. final evaluation 后仍根据结果调参；
9. hard-09 在 P1/P2 上均产生非弃权跨容器 merge；
10. S2/S3 出现 false-low-risk candidate；
11. 需要引入禁止算法、实际 Cleaning、Provider/Workflow 或依赖升级才能继续；
12. 输出越过允许目录或 source hash 改变。
