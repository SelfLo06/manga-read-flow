# Text-Seeded Container Association Spike — Retired v0.2 Freeze Record

版本：v0.2
状态：`SUPERSEDED / REOPENED`，仅保留历史记录
冻结日期：2026-07-15

## 0. Reopening Notice

项目维护者于 2026-07-15 明确指出 v0.2 的样本范围过窄、冻结过早，并授权扩大 `data/local` 筛选。因此本文的 R0 source/ROI、boundary 数值、S1 final selection、calibration/evaluation asset split 与阈值网格均不再具有冻结效力。

核心算法思想和安全边界仍由 GOAL/HARNESS 保留；本文以下内容只能作为历史候选与审计线索，不能作为实现、校准或评估输入。当前有效进度见 `CANDIDATE-EXPANSION.md`。

## 1. 冻结范围

本文曾在 v0.2 尝试冻结四项，现均已重新开放复核：

1. R0 六类回归实例的 source、ROI、语义与预期安全决策；
2. visible / virtual boundary 的 GT 容差带与 P1 预测不确定带定义；
3. S1 的 Detection/OCR 与 Grouping 上游 run；
4. `P_same_container` 只能使用 calibration 子集确定阈值的协议、搜索空间和安全约束。

本文不实现 association 算法，不生成像素文字 Mask、safe edit region 或 cleaned image，不生成 benchmark manifest，不接入 CleanerProvider / Workflow，也不启用 `AUTO_ACCEPT`。

## 2. R0 实例冻结

ROI 统一使用原图坐标 `[x, y, width, height]`。ROI 只固定评估上下文，不等于 container GT、support GT 或 edit region。

| R0 ID | Source / SHA-256 / 尺寸 | 冻结 ROI | 冻结语义 | 预期安全决策 |
| --- | --- | --- | --- | --- |
| `R0-contact-hard09` | `data/local/(C78) [真珠貝 (武田弘光)] YUITAま (ToLOVEる -とらぶる-) [カラー化]/(C78) [真珠貝 (武田弘光)] YUITAま (ToLOVEる -とらぶる-) [カラー化]/yuitama_09.png`；`aa34d4743036c040348c68066bd07b38df4de32d04539bc2193c26ceb9c0c77c`；`1120×1600` | `[0, 1020, 300, 430]` | 左下相邻、局部接触的两个不同气泡；旧 `hard-09` crop 只覆盖其中一部分，因此本冻结扩大 ROI。 | 必须保持两个 container；不得 merge。若边界证据不足，只能 `REVIEW_REQUIRED`。 |
| `R0-same-container-multicol` | `local_samples/real/black2.webp`；`95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb`；`1280×1698` | `[800, 300, 440, 620]` | `black2_r02`，一个连通气泡、七个竖排 fragment / 多列文字；原 GT bbox `[864, 370, 298, 482]`。 | 必须保持一个 container；不得因竞争传播产生内部虚拟分界。 |
| `R0-broken-boundary` | `local_samples/real/gura.webp`；`318bec1ff1147645f48bec491d6e0e6811f8ee5d2610252bb36ce5757e5f8647`；`800×1136` | `[0, 700, 300, 436]` | `gura_r09`，容器被页面左/下边界截断；原 GT bbox `[50, 773, 169, 363]`。 | `implicit_container`；可见轮廓与页面边界共同限制传播。边界不能闭合时为 `REVIEW_REQUIRED`，不得向页面背景无界泄漏。 |
| `R0-free-text` | `local_samples/real/gura.webp`；同上；`800×1136` | `[100, 310, 190, 110]` | `gura_r04` 的 `00:02:14` 摄像时间戳；S1 group bbox `[144, 350, 87, 26]`；无气泡、无旁白框。 | `container_mask = null`；只输出有限 `support_region`。因其为非对白 overlay，固定为 `REVIEW_REQUIRED`，不得借 support region 暗示可清字。 |
| `R0-not-text` | `data/local/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)/_023.jpg`；`a31442650c6f84d5f3f15bf4daf25a109ec968e4728ee73e10a075a7a3502444`；`1406×2000` | `[980, 80, 160, 140]` | 独立视觉复核确认旧 `hard-12` 候选是网点/结构变化，不是文字；旧 candidate mask 不作为 GT。 | `SKIP`；不得生成低风险 container/support。该实例只用于 S0 人工误种子与 S3 FP 注入，不把旧差异 mask 当 detector 输出。 |
| `R0-textured-risk` | `local_samples/generated/synthetic_04_complex_background_skip.webp`；`33c9ae0922a559f2a187e312e55ac90597c367f7c377371a50dadddd68652d69`；`1000×1500` | `[540, 410, 400, 260]` | `s04_r02`，倾斜文字位于透明/渐变标签上，底层为重复纹理；原 GT bbox `[585, 460, 315, 165]`。 | 容器类型或边界只要不稳定即 `REVIEW_REQUIRED`；不得进入低风险关联候选。 |

### 2.1 冻结理由

- `hard-09` 保留维护者指定的接触气泡回归意图，同时修正旧 crop 只覆盖局部的问题；
- `black2_r02` 已有 Detection/OCR 与 Grouping 证据，能直接验证“同容器多列不得 false split”；
- `gura_r09` 的页面截断是可复现的 implicit-container 边界缺失；
- `gura_r04` 是真实、简单、无容器文字，适合验证“support 而非假气泡”；
- `hard-12` 经视觉复核确为非文字结构，适合作为 abstention 负例；
- `s04_r02` 同时包含透明、纹理、倾斜和低对比证据，适合验证风险识别而非追求覆盖。

### 2.2 明确不继承的旧证据

- `hard-09`、`hard-12` 的旧 mask、difference component、expected disposition 不进入算法输入；
- 旧 crop 不是本轮 ROI GT；
- 现有 bbox 只用于定位和完整性检查，不等于 pixel mask 或 safe region；
- R0 实例冻结不代表其精确 container boundary GT 已完成。精确 GT 仍须按第 3 节双人标注。

## 3. Boundary Uncertainty Band 冻结

### 3.1 尺度

对每个 ROI，令 `h_ref` 为 S0 人工确认 fragment 的中位字符高度。冻结基础半宽：

```text
delta = clip(round(0.15 * h_ref), 2, 8) pixels
```

该尺度随文字分辨率变化，同时通过 `2..8 px` 限制极小字和大字的容差膨胀。

### 3.2 GT band

两名标注者独立画 boundary centerline，不看算法输出。

```text
visible_boundary_band = dilate(visible_centerline, delta)
virtual_boundary_band = dilate(virtual_centerline, 2 * delta)
```

页面裁断或遮挡端点使用 `2 * delta`。标注者 centerline 的分歧区域并入 `gt_boundary_uncertainty_band`。

若出现以下任一情况，该 region 固定为 `GT-uncertain`，只验证 abstention，不进入 boundary F1 / IoU 精确门禁：

- boundary topology 不一致；
- 超过 `20%` 的 centerline 长度无法在对方 `2 * delta` band 内匹配；
- 同一位置存在两个以上同样合理的虚拟闭合路径；
- free-text 的 support 最大 envelope 无法达成 reviewer 共识。

### 3.3 P1 geodesic prediction band

对每个像素或 superpixel，令 `D1 <= D2` 为最小和次小 source geodesic distance，冻结归一化竞争 margin：

```text
m(x) = (D2(x) - D1(x)) / (D2(x) + D1(x) + 1e-6)
```

初始冻结：

```text
virtual_ridge_core: m(x) <= 0.05
boundary_uncertainty_band: m(x) <= 0.15
```

此外，SLIC target scale 做 `-20% / nominal / +20%` 三点扰动；归属标签或 ridge topology 发生变化的区域并入 `boundary_uncertainty_band`。

规则：

- uncertainty band 只能扩大 `REVIEW_REQUIRED`，不能提升 low-risk 置信；
- 预测 core 落入 GT band 才计 confident boundary hit；
- 仅 uncertainty band 与 GT band 相交不计 confident correct，但正确弃权可计入 abstention；
- 上述 `0.05 / 0.15` 在 final evaluation 前不得因 evaluation case 调整；若未来需要调整，只能使用第 5 节 calibration assets，并产生新的冻结版本。

## 4. S1 Detection / Grouping Run 冻结

S1 固定使用下列 cold chain：

| 层 | 冻结值 |
| --- | --- |
| Detection/OCR run | `20260710T091753Z-0676c2` |
| cycle | `cold` |
| Detection `results.json` SHA-256 | `ed545db771e8d75403e01921e5256b6c8ddf6f3ee200cfa6d680f6328e60f7f4` |
| Detection `regions.csv` SHA-256 | `3c8aad5abb04f2439d55b66cddd2fd307ea2d875e353eb94e0dc6168f71c8d8c` |
| Detection GT SHA-256 | `e5f189c199d6e8b1c1a07197acae8cd9fcd25ea9baf47a54c6b3d34e23e8be21` |
| Detection 参数 | `oracle_union_padding_px=8`；`prediction_coverage_threshold=0.5`；oracle 参数只属于既有 evaluator，不得进入 association 输入 |
| Grouping run | `20260710T142823Z-b08c9c` |
| Grouping source run | `20260710T091753Z-0676c2` |
| Grouping cycle | `cold` |
| Grouping `results.json` SHA-256 | `565f85e2002c5069b67cf12856b3741b9c616d96fea981f9ec3f1116986b8a5b` |
| Grouping `groups.csv` SHA-256 | `bab66e736218ab08df51ce664b004f203b229bc808825669ab5a55c7d1cf567e` |
| Grouping `summary.json` SHA-256 | `941d68c6d5742222e1a103bbbb83d4efa3b228cdeb10fd8e704d628594d7e5bd` |
| Grouping 参数 | `orientation_ratio=1.25`；`projection_overlap_ratio=0.15`；`gap_relative_limit=0.35`；`gap_min_px=16` |
| 已知结论 | Detection/OCR `CONDITIONAL_GO`；Grouping `PASS_WITH_LIMITATIONS`；9 个 real extra groups 必须保留 |

### 4.1 S1 输入规则

- 只读取 cold detector fragment geometry、score、方向、group、alternative/uncertainty 与 fragment ID；
- OCR 字符串只允许作为弱先验或诊断字段，不得用 expected text；
- extra / auxiliary / empty-OCR / unmatched seed 不得静默删除；
- 不读取 GT bbox、GT container assignment、expected decision 或旧 Cleaning mask；
- 同一输入 hash 不得混入 warm cycle 结果。

### 4.2 覆盖限制与扩展门禁

该 run 覆盖 `black2`、`gura`、`synthetic_04`，因此覆盖当前 R0 的 `4/6`：

```text
covered:
  R0-same-container-multicol
  R0-broken-boundary
  R0-free-text
  R0-textured-risk

not covered:
  R0-contact-hard09
  R0-not-text
```

不得把旧 difference mask 拼接进 S1。正式 S1 全 R0/R1 矩阵前，必须用相同 Detector/Grouping 版本与参数对 `yuitama_09.png` 和 `_023.jpg` 生成一个定向 extension run，并在生成后单独冻结其 run ID 与 hashes。extension 尚未存在，因此当前只允许：

- 对 `R0-contact-hard09` 运行 S0；
- 对 `R0-not-text` 运行 S0 人工误种子与 S3 注入；
- 对其余 4 个 R0 使用冻结 S1；
- 不得声称 S1 已覆盖完整 R0。

## 5. Calibration / Evaluation 资产隔离

### 5.1 Calibration assets

以下四个 asset 是唯一允许选择 `P_same_container` 阈值和调整 boundary margin 的资产：

| Asset | SHA-256 |
| --- | --- |
| `local_samples/generated/synthetic_01_clean_dialogue.webp` | `671ae61e0c573079e21814b49d97983862b27e2d802eeb29e75efe2ac42f11ad` |
| `local_samples/generated/synthetic_02_narration_boxes.webp` | `250284db93d7b99e461daeeaa2d43368ed0aa9d2221a980558544de93411a2ac` |
| `local_samples/real/black1.webp` | `abb689f3a8e442e55bbe8b2c5fb56ea531fe7ddfec8724ba63e48a5740720231` |
| `local_samples/real/gura_color.webp` | `6518cbe64699a9d6e878c066d828babbcf48c6d7b26332b72408bc692a3069c9` |

### 5.2 Evaluation-only assets

以下资产不得用于阈值、权重、SLIC 尺度或 feature selection：

| Asset / case | SHA-256 |
| --- | --- |
| `local_samples/generated/synthetic_03_small_bubble_overflow.webp` | `330055f0c646f8f3a7b37df29c6c95a07473f6c4b02586161a64856cd7e5d3ab` |
| `local_samples/generated/synthetic_04_complex_background_skip.webp` | `33c9ae0922a559f2a187e312e55ac90597c367f7c377371a50dadddd68652d69` |
| `local_samples/real/black2.webp` | `95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb` |
| `local_samples/real/gura.webp` | `318bec1ff1147645f48bec491d6e0e6811f8ee5d2610252bb36ce5757e5f8647` |
| `R0-contact-hard09` source | `aa34d4743036c040348c68066bd07b38df4de32d04539bc2193c26ceb9c0c77c` |
| `R0-not-text` source | `a31442650c6f84d5f3f15bf4daf25a109ec968e4728ee73e10a075a7a3502444` |

R0 六例全部为 evaluation-only；即使某 R0 失败，也只能影响 verdict，不能回流调参。

## 6. `P_same_container` Threshold Freeze Protocol

### 6.1 为什么当前不伪造数值阈值

当前尚无 P1 scorer，也没有 calibration asset 上的 `P_same_container` 分数。此时直接写死 `0.8/0.2` 或其他数值不是 calibration，而是无证据猜测。故本次冻结的是唯一合法的阈值产出协议；数值只能由未来 calibration-only run 一次性产出。

在数值冻结前：

```text
all P_same_container decisions = uncertain
recommended_decision = REVIEW_REQUIRED
```

### 6.2 Calibration pair 门禁

只从第 5.1 节资产的 cold S1 fragments / initial conservative groups 生成 pair。pair 生成规则在看分数前冻结，并至少满足：

- `same_container` pair `>= 10`；
- `different_container` pair `>= 10`；
- 两类都至少覆盖 `2` 个 asset，其中至少 `1` 个真实 asset；
- pair 不得来自 evaluation-only asset；
- pair label 只在 evaluator 中可见；
- 相同 fragment pair 不得重复计数。

不足门禁时，不冻结数值阈值，所有 pair 保持 uncertain。

### 6.3 冻结搜索空间

```text
T_different ∈ {0.05, 0.10, 0.15, 0.20}
T_same      ∈ {0.80, 0.85, 0.90, 0.95}
```

决策：

```text
P_same <= T_different  → different-container candidate
P_same >= T_same       → same-container candidate
otherwise              → uncertain / REVIEW_REQUIRED
```

任何 hard/soft evidence 冲突、alternative grouping 接近、未分配高置信 fragment 或 boundary instability 都可把 candidate 降为 uncertain，但不得越过阈值提升置信。

### 6.4 选择目标

在 calibration subset 上按以下字典序选择唯一阈值对：

1. `false_merge_count = 0`；
2. `false_split_count = 0`；
3. 最大化 decisive pair coverage；
4. 最大化 abstention gap `T_same - T_different`；
5. 若仍并列，选择更高 `T_same`；
6. 若仍并列，选择更低 `T_different`。

若没有阈值对同时满足前两项，数值阈值不得冻结，Spike 进入 `FURTHER_SPIKE`；禁止通过 evaluation case 反向找阈值。

### 6.5 一次性冻结与评估隔离

未来 calibration run 必须先输出：

```text
calibration asset hashes
pair-generation config hash
P_same scorer/version hash
all candidate threshold metrics
selected T_different / T_same
selection reason
```

选中后只允许写一次新的 calibration lock 记录；随后 final evaluation 只读这些值。evaluation 失败只能改变 verdict，不能修改阈值。任何阈值变更都必须新开版本并重新运行完整 calibration，旧 evaluation 不得参与。

## 7. 当前门禁状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| R0 identity / ROI / semantics | `FROZEN` | 六例全部已固定。 |
| Exact R0 boundary GT | `PENDING_ANNOTATION` | 必须按第 3 节双人标注。 |
| Boundary uncertainty definition | `FROZEN` | GT 与 P1 prediction band 均已固定。 |
| S1 base run | `FROZEN_PARTIAL_COVERAGE` | 4/6 R0；不得宣称完整覆盖。 |
| S1 targeted extension | `REQUIRED_BEFORE_FULL_MATRIX` | 尚未运行，不得伪造 run ID。 |
| Calibration/evaluation asset split | `FROZEN` | R0 全部 evaluation-only。 |
| P_same threshold protocol | `FROZEN` | 搜索空间、门禁和目标已固定。 |
| P_same numeric thresholds | `PENDING_CALIBRATION_RUN` | scorer 尚不存在；当前全部 uncertain。 |

## 8. 风险与停止条件

- `hard-09` 扩大 ROI 后若双人复核认定并非两个不同接触容器，立即停止并报告 R0 证据冲突，不替换为方便样本；
- R0 ROI 内如发现字符被裁断，先修订冻结版本，不调算法；
- calibration pair 数不足时不得降低门槛或借用 evaluation；
- targeted S1 extension 与 base run 的工具版本/参数不一致时不得合并统计；
- boundary `0.05/0.15` 或 P_same 阈值若在 evaluation 后修改，当前 verdict 作废；
- 任一旧 difference mask / expected text / GT assignment 泄漏到算法输入，结果作废；
- 任何实际 Cleaning、CleanerProvider、Workflow、benchmark manifest 或 `AUTO_ACCEPT` 仍禁止。

## 9. 验证记录

本次仅完成只读验证：

- 视觉检查 `hard-09`、`hard-12`、`hard-13`、`black2`、`gura`、`synthetic_04`；
- 检查 source 尺寸、SHA-256、既有 GT bbox 与 Grouping 输出；
- 检查 Detection/OCR 与 Grouping run 的链路、cycle、参数和文件 hash；
- 确认 base S1 对 R0 只有 `4/6` 覆盖；
- 未运行 Detector/OCR/Grouping 新任务；
- 未运行 container association、Cleaning 或测试；
- 未创建或修改任何 benchmark manifest。

## 10. 剩余开放项

1. R0 精确 boundary / support GT 的双人标注及 hash；
2. `hard-09` 与 `hard-12` 的 S1 targeted extension run ID / hashes；
3. P1 scorer 实现后，在 frozen calibration assets 上产出的实际 `T_different / T_same`；
4. R1 最低 37 region 的完整冻结，仍不属于本次 R0 freeze。
