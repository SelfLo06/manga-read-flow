# Goal 2 — Minimal B0/B1/P1 Harness and Calibration Lock v0.1

状态：`COMPLETE / READY_FOR_GOAL_3`

## 1. Goal 与边界

本 Goal 只实现用于技术 Spike 的最小 `B0/B1/P1` Harness，并只用 Goal 1 冻结的 `cal-01/cal-02` 资产校准 `P_same_container`。它不运行 R0、不形成算法 verdict，也不实现 Cleaning、像素文字 Mask、safe edit region、P2、Provider、Workflow 或 benchmark manifest。

本地 calibration 输入：

```text
S1 run:       20260715T075556Z-7bb156
results hash: 195230ecd63191d64621b251b9c1adbc9c6efd6b3366cdfab5bf4438f066a621
spec hash:    9162a4314f5b2d71c5bdf80e89a90d02b23852f7d0df2ca85452ae9833074d99
assets:       cal-01, cal-02
```

## 2. 决策

### 2.1 Initial source 与 scorer

- 每个冻结的 S1 detector fragment 是一个 atomic propagation source；
- S1 group membership 只作为 scorer prior，不直接等同于最终 container；
- pair label 只在 calibration evaluator 层读取，`score_same_container` 的接口不接受 label；
- crop-edge partial fragments 不生成 calibration pair，但仍保留在 calibration sanity run 的真实 S1 输入中；
- OCR 字符串与 detector score 均未伪造：本轮不使用 OCR，冻结输入中的 `score=null` 原样保留。

固定 scorer 特征与权重：

| Feature | Weight |
| --- | ---: |
| same upstream group | 0.40 |
| orientation compatibility | 0.15 |
| scale similarity | 0.15 |
| normalized proximity | 0.15 |
| edge corridor | 0.15 |

权重、feature set 与网格均在实际 calibration 分数产生前写入测试和实现。当前最小网格为：

```text
T_different ∈ {0.40, 0.45, 0.50, 0.55, 0.60}
T_same      ∈ {0.70, 0.75, 0.80, 0.85, 0.90}
minimum empirical same/different margin = 0.20
```

选择规则为：先要求 calibration pair 的 false merge/split 均为零，再取最大 abstention gap；若无法形成安全 separation，则 `force_all_uncertain=true`。`FREEZE.md` 中的 v0.2 网格已经由其 reopening notice 明确退役，不用于本轮。

### 2.2 B0 / B1 / P1

| Method | Goal 2 最小实现 |
| --- | --- |
| B0 | 冻结 S1 group 的 union bbox + character-scale padding；重叠或缺乏容器证据时 review。 |
| B1 | 相同初始 group seeds 上的 gradient priority-flood seeded watershed；竞争 ridge 只作为基线边界，不获得 P1 scorer。 |
| P1 | dependency-free SLIC RGBXY superpixels、superpixel graph、hard/soft edge cost、多源 geodesic propagation；先按 `P_same_container` 合并 source，再生成 virtual boundary；不确定 pair 必须 abstain。 |

当前测试环境没有 OpenCV，且 Goal 边界禁止依赖升级。因此 B1 和 SLIC 由 NumPy 自包含实现，图像读取只用既有 Pillow；没有改变 P1 的 SLIC + graph + multi-source geodesic 设计。

输出仅包含 container/support association 候选、RLE region、virtual boundary、same-container decision、诊断与 abstention。没有 cleaned image、pixel text mask 或 safe edit region。

## 3. Calibration pair 与结果

Pair-generation rule 冻结后共得到 5 个不重复 atomic-fragment pair：

- `cal-01`：2 个 `different` pair；排除右侧 crop-edge partial container；
- `cal-02`：3 个 `same` pair；排除左下 crop-edge partial container。

实际分数：

| Pair | Label | Score |
| --- | --- | ---: |
| `cal-01:p0003:p0004` | different | 0.329203 |
| `cal-01:p0003:p0005` | different | 0.305373 |
| `cal-02:p0002:p0003` | same | 0.864460 |
| `cal-02:p0002:p0004` | same | 0.755386 |
| `cal-02:p0003:p0004` | same | 0.841176 |

结果：

```text
status:                  FROZEN
T_different:             0.40
T_same:                  0.75
empirical score margin:  0.42618291751598514
force_all_uncertain:     false
harness hash:            bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11
calibration runner hash: 9d04937e8c5e20e35aa89a550682f5a418fa540ec159e4fd31441aa436f92853
pair-key hash:           8a8945ec4ea3aee0d866ccb7ddb1e6eb66cc4e586d30ec94e7300ab39493c4bb
calibration lock hash:   5ad91445bdf8bc29ba1ba3d4c48ac9f6f4838dd06601a3bc5a80310744e1f1cc
```

本地只读 lock：

```text
data/local/text-seeded-container-association/calibration-v0.1/
  calibration-runs/goal2-v0.1/calibration-lock-v0.1.json
  calibration-runs/goal2-v0.1/harness-sanity/*.json
```

六个 sanity outputs 均为 `REVIEW_REQUIRED`：B0 明示无容器证据，B1 明示无 same-container model，P1 明示 implicit boundary 需要复核。这是保守输出的 sanity evidence，不是 R0 成败结论。

## 4. 理由与拒绝替代

| 决策 | 理由 | 拒绝替代 |
| --- | --- | --- |
| atomic fragment 作为 source | 保留高召回位置与多源竞争，避免把上游 group 当成真实容器。 | 一个 S1 group 永久绑定一个 container。 |
| 上游 group 只作 prior | 利用方向/完整性证据，同时允许 Goal 3 检验错误 grouping。 | 完全忽略 grouping；或把 group label 当 GT。 |
| 无 separation 时全 uncertain | 小样本上安全性优先。 | 借 R0 反向调阈值；强制给 pair 分类。 |
| 自包含 NumPy/Pillow | 当前环境可复现，且不升级依赖。 | 为 Spike 修改 dependency/lockfile。 |
| R0 与 calibration 严格隔离 | 避免 final evaluation 泄漏。 | 查看 R0 结果后改权重、网格或 pair。 |

## 5. 风险与限制

- 只有 5 个 pair、2 个 calibration crop；阈值仅适用于本次最小 R0 Spike，不能宣称统计泛化；
- same pairs 都继承同一 upstream group，group prior 的贡献较大；Goal 3 必须观察真实错误 grouping 是否触发 abstain，而不能据此宣称 group 可靠；
- 自包含 SLIC 是最小实现，没有生产级 connectivity repair 或性能优化；
- pixel-accurate boundary GT、严格 IoU/boundary F1、双人 boundary agreement 与 uncertainty-band 数值仍未冻结；
- calibration sanity 保留 crop-edge partial fragments，因此 region 数量不是人工 container-count metric；
- P1 当前只证明流程可运行，是否优于 B0/B1 必须由 Goal 3 的冻结 R0 轻量矩阵决定。

## 6. Validation

```text
python -m pytest \
  tests/unit/test_text_seeded_container_association_harness.py \
  tests/unit/test_text_seeded_container_calibration.py -q

16 passed
```

验证覆盖：scorer 禁止 label 参数、separator evidence、asset leakage/duplicate pair 拒绝、hash lock、无 separation 全 uncertain、B0 coverage、B1 disjoint competition、P1 merge-before-propagation、different/uncertain pair 行为、RLE contract，以及只生成 `cal-01/cal-02 × B0/B1/P1` 六个 sanity output。

## 7. Goal 3 前的冻结项与开放项

Goal 3 只读以下内容：Harness 代码、上述 scorer/weights/grid、`T_different=0.40`、`T_same=0.75`、Goal 1 的 R0 S1 run 与 R0 分层人工证据。Goal 3 不得根据 R0 结果重调。

开放项：R0 上的分类、container count、same/different topology、跨容器泄漏、正确 abstain，以及相对 A coarse reference 的宽容差评估。仍禁止 pixel-accurate segmentation、精确 boundary F1、双人 boundary agreement 或 uncertainty-band 数值声明。
