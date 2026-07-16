# Goal 4 — Focused Association Correction Report v0.1

状态：`COMPLETE`

结论：`B1_STRONG_BASELINE_ONLY`

## 1. Executive Summary

Goal 4 使用与 R0 完全隔离的 8 个 calibration crop，实现并冻结了以下 focused correction：

- upstream group 级的 same/different 证据聚合；
- 有限 support envelope 与 geodesic stop；
- 单 seed 与 merged-container 分离的动态面积上限；
- uncertain isolated seed、极端跨度 seed 与无 seed 的 regionless abstention。

这些改动解决了部分安全和泄漏问题：R0 case-01 能 regionless SKIP，case-02 得到不触边的有限 free-text support，case-04 的背景泄漏显著下降。可是它没有改善关键 container topology：corrected P1 仍为 2/3，与 B1 相同；case-03 的省略号与正文仍 false split。更重要的是，case-05/06 的 corrected region 退化为文字邻域 support，明显不如 B1 对真实气泡 coarse scope 的贴合。

因此不选择 corrected P1，不宣称 container association 已解决，也不进入 Pixel Text Mask 或 Cleaning。B1 仅被冻结为后续研究中的强基线，不是生产实现或自动接受路径。

## 2. Frozen Calibration Evidence

### 2.1 Scope and isolation

```text
Calibration S1 run:        20260715T114410Z-7b216b
Calibration results hash: 1596a7fbd336ab00f3afc949852b8debff2bcb2073f58d5db6bbae52a193b128
Calibration spec hash:    fec0210c9e7e03f78fa8d93aae157812c472c795a091765bcaf1b5dfa9411ba1
Maintainer FORM hash:      7cd3ffeff3a632c83d33c4e8592074573c77051489c931917dc9b12f061ec9b7
Labels hash:               6feab4b51e3a11b6ce0cef2ee63c03bc54b3c569d61f1031abb54f2379263b1c
Calibration lock hash:     2daf93a246b971e36c59b6cdde182b91927d16673843e2098cca25fe9c30248c
Focused module hash:       585c88828b53809fd3f6bdd2e0cdacc4701f733ec7333ee8224c26b002280bf4
Base harness hash:         bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11
R0 source overlap:         0 / 8
r0_asset_accessed:         false
pixel boundary GT used:    false
```

八例来自 8 张不同 source image、6 个 source bucket。G4-01 冻结 cross-group different，G4-04 冻结 cross-group same；G4-02 只作为“至少两个容器”的输出 gate，不把未明确的全部 group pair 擅自写成 different。

### 2.2 Selected calibration values

```text
T_different:                         0.30
T_same:                              0.85
max_geodesic_cost:                  12.0
support_padding_scale:               0.25
single-seed max support area ratio:  0.20
merged max support area ratio:       0.35
extreme span ratio:                  0.90
extreme seed bbox area ratio:        0.20
```

两个冻结 group pair 均明确且正确，abstention gap 为 `0.55`。1008 个 support candidate 中 192 个通过强化后的 8/8 calibration gate；选择规则先要求全部 gate 通过，再最大化 bubble-case bounded support、最小化 free-text support，并在同分时选择更紧的传播参数和更保守的 extreme-seed 触发值。

### 2.3 Calibration cases

| Case | Frozen role | Selected result |
| --- | --- | --- |
| G4-01 | 两个不同容器 | 2 个非空 component，PASS |
| G4-02 | 至少两个容器 | 3 个非空 component，PASS |
| G4-03 | 中央多列同容器 | 中央 group 完整，全部 region 非空，PASS |
| G4-04 | 两个 upstream group 同容器 | 1 个非空 merged region，PASS |
| G4-05 | 标题/装饰高风险 | regionless extreme-span SKIP，PASS |
| G4-06 | 无气泡 SFX | 19.5% ROI 有限 support、不触边、REVIEW，PASS |
| G4-07 | no seed / not text | SKIP，PASS |
| G4-08 | false uncertain seed | regionless SKIP，PASS |

## 3. Calibration Findings and Corrections

### 3.1 Fragment-level union was rejected

最初 fragment scorer 在 G4-01 的同一 group pair 中同时产生一个高分和一个低分。如果按任一 fragment 高分 union，会跨越两个接触气泡错误合并。corrected P1 因而改为以 upstream group 为竞争源：组内 fragment 先合并，跨组分数取候选成员对的保守最小值。

### 3.2 Global white-component connectivity was rejected

曾验证“白色背景连通”是否可作为同容器证据。G4-01 的接触气泡可经裁切外部白区连通，该假设被 calibration 直接证伪并移除。最终只保留排除文字框后的局部分隔走廊证据。

### 3.3 One global area cap was rejected

`0.15` 的全局 cap 能拒绝 G4-05 标题，却会把 G4-06 合法 SFX support 一并清空；放宽又会保留标题。最终使用动态规则：极端跨度且大面积的单 seed regionless；普通单 seed 使用 20% cap；已由多 fragment 合并的 container candidate 使用独立的 35% cap。

### 3.4 A topology-only calibration lock was rejected

第一次通过的 lock 允许 G4-04 topology 正确但 `mask=null`。该 lock 被保留为 `rejected-insufficient-nonnull-gate`，未用于 R0。正式 gate 增加 G4-01～04 相关 region 必须非空后重新冻结。

## 4. Single R0 Re-evaluation

```text
R0 run id:              goal4-r0-corrected-v0.1
R0 matrix hash:         075c232a8da60550daa275d12a0bd3d8c2651775c07f5cbb0939bf3357f1fa15
R0 runner hash:         0c80f3836b8a86dbd3fa883e4f40ef07794b377b8c430fd0da8419cd93243b41
Evaluation hash:        aef9440dae19a22a090e8cfb3f47f3c8914f75f7ffbb0d59f92d092cc33855e8
Evaluator hash:         c26ac58e993ff2736ea52831cf3580295d4cefe9f266d3748ef94c1deae09e70
Manual review hash:     750e443ed2c4a3b9fbdf2bf1ed430a25f01311514cd09f8e91a5f345ae4ddcb8
source hashes unchanged: true
ground truth accessed:    false
evaluator accessed:       false
post-R0 parameter update: false
cleaning performed:       false
```

这是 Goal 4 唯一一次成功的 R0 corrected run。B1 没有重跑，而是读取 Goal 3 已冻结的 matrix/evaluation 作为强基线。

## 5. Automated Results

| Metric | B1 | corrected P1 |
| --- | ---: | ---: |
| Safety decision | 6/6 | 6/6 |
| Topology | 2/3 | 2/3 |
| Target region availability | 未单独统计 | 4/5 |
| Container type | baseline unsupported | 2/6 |
| Excluded/false-seed non-null regions | 未按 nullable contract 统计 | 2 |

corrected P1 没有产生 false low-risk candidate。所有风险输出仍为 SKIP 或 REVIEW_REQUIRED。

## 6. Tolerant Coarse Review

| Case | corrected P1 outcome | Relative to B1 |
| --- | --- | --- |
| case-01 | false seed 变为 regionless SKIP | corrected 更好 |
| case-02 | 有限 free-text support，面积 12.9%，不触边 | corrected 更好 |
| case-03 | 省略号与正文仍 false split；另有 excluded seed 非空 region | 未获得 container association 收益 |
| case-04 | 泄漏显著收窄，但一个 target=null，false seed 仍非空 | mixed |
| case-05 | topology 正确；矩形 support 越出/漏掉气泡 scope | B1 明显更好 |
| case-06 | topology 正确；两个 region 只是文字邻域，不是两个气泡 scope | B1 明显更好 |

该复核只相对 Annotator A coarse reference 作宽容差判断。Annotator B 无 overlay，因此不计算双人边界一致性；没有 pixel IoU、boundary F1 或冻结 uncertainty-band 数值。

## 7. Decision and Rationale

### Selected

`B1_STRONG_BASELINE_ONLY`：B1 在 case-05/06 对真实气泡 scope 的 coarse association 仍是本 Spike 最强信号。它被冻结用于比较和未来研究，不授权自动 Cleaning。

### Not selected: corrected P1

corrected P1 对 false/free-text 风险有局部收益，但没有修复 case-03，也没有在 case-05/06 保持 B1 的 container-shaped scope。它实际更接近“安全的文字邻域 support”，不能冒充已解决的 container association。

### Rejected: advance to Pixel Text Mask

目标容器关联尚不稳定。此时生成 pixel text mask 只会掩盖上游 association 缺陷，且无法证明 safe edit region 属于正确容器。

### Rejected: NO-GO for the entire direction

B1 在 explicit/contact bubble 上仍有 2 个清晰 coarse match；corrected P1 也证明 regionless abstention 与有限 support 可行。方向本身未被完全证伪，但当前 corrected 方案不足以成为下一阶段输入。

## 8. Risks and Expected Failure Modes

- 短列/省略号与正文属于同一气泡时，局部分隔走廊会把它们 false split；
- B1 对 free text、false seed 和复杂纹理会扩散到大面积背景；
- corrected P1 的紧 envelope 会把真实气泡降格为文字邻域矩形；
- 单 seed 极端跨度规则可能对合法大字产生保守 abstention；
- false seed 若方向明确且尺寸普通，仍可能获得非空 support；
- 自包含全图 SLIC 很慢：8 个 calibration case 约 4–5 分钟，6 个 R0 case 约 14.7 分钟；不适合作为交互式实现；
- R0 只有六例，结论是技术 Spike verdict，不是泛化精度声明。

## 9. Open Questions

- 若未来重开研究，是否应将“container search”和“free-text bounded support”拆成两个明确 method，而不是共享一个 mask contract？
- 是否需要用显式 contour/closed-region evidence 替代走廊启发式，专门解决 case-03 类同容器短列？
- 是否有必要在进入任何 Pixel Text Mask 前新增独立、盲评的 container-scope calibration，而不是继续增加 R0 后启发式？

当前这些问题不构成继续 Goal 4 的授权。

## 10. Validation

最终验证覆盖 calibration/R0 hash isolation、nullable region contract、group-level conservative aggregation、dynamic cap、regionless abstention、R0 runner 无 evaluator 输入、artifact hash、source immutability 和 post-R0 no-tuning。

```text
45 passed in 5.98s   # R0 前冻结回归
```

最终完整回归结果见 Gate 文档。
