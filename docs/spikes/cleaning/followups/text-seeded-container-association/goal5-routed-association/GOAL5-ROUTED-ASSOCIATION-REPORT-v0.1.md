# Goal 5 — Routed Spatial Association Validation Report v0.1

状态：`COMPLETE`

## 1. 结论

```text
GOAL 5 VERDICT = GO_TO_GOAL6_MINIMAL_CLEANING_TRIAL
ROUTED SPATIAL ASSOCIATION = PASS ON MINIMAL INDEPENDENT EVALUATION
PIXEL TEXT MASK / CLEANING QUALITY = NOT TESTED
PRODUCTION OR WORKFLOW INTEGRATION = NOT AUTHORIZED
```

Goal 5 支持继续保留 text-first association，并把空间任务显式拆成三路：

1. 有足够局部边界证据时，进入 `COARSE_CONTAINER_SEARCH`；
2. 文字 seed 有效但缺少容器证据时，进入 `BOUNDED_SUPPORT`；
3. 无 seed、极端 seed 或 contract 失败时，进入 `REGIONLESS_ABSTENTION`。

正式 evaluation 的 4 个独立 case 全部命中冻结 contract，且没有错误确认 topology、跨容器非弃权泄漏或伪低风险输出。该结果只放行 Goal 6 的人工审查最小清字试验；不证明 coarse region 是精确气泡边界，也不证明能安全清字。

## 2. 实际算法选择

本轮选择的不是单一 `B1/P1`，而是以下可弃权分流架构：

```text
S1 Detection / Grouping fragments
  → seed geometry safety check
  → B1-style preliminary local propagation + boundary evidence
      ├─ boundary evidence ≥ 0.50
      │    → group-pair same/different evidence
      │    → decisive same: merge component and rerun coarse propagation
      │    → decisive different: preserve competing components
      │    → uncertain: preserve uncertainty; Goal 6 ineligible
      ├─ weak boundary + compact valid seed
      │    → texture-adaptive bounded support
      └─ no seed / extreme geometry / support contract failure
           → regionless abstention
```

OCR 字符串不参与路由。使用的先验只有 fragment 的位置、尺度、方向、upstream group、score 与局部图像梯度。`COARSE_CONTAINER_SEARCH` 输出是 B1-style coarse basin；`BOUNDED_SUPPORT` 只是局部计算域，不宣称存在气泡；所有非弃权输出仍为 `REVIEW_REQUIRED`。

## 3. 数据与隔离

| Split | Case | S1 fragments / groups | 预期任务 |
| --- | --- | ---: | --- |
| calibration | cal-51 | 4 / 2 | explicit same-container |
| calibration | cal-52 | 2 / 2 | explicit different-container |
| calibration | cal-53 | 1 / 1 | bounded support |
| calibration | cal-54 | 3 / 2 | regionless abstention |
| evaluation | case-51 | 6 / 2 | explicit same-container |
| evaluation | case-52 | 3 / 3 | explicit different-container |
| evaluation | case-53 | 1 / 1 | bounded support |
| evaluation | case-54 | 0 / 0 | regionless abstention |

- 8 个 crop 来自 8 个不同 source image；calibration/evaluation source overlap 为 0。
- 与 R0、Goal 4 source denylist overlap 为 0。
- 全部 source/crop hash 在 run 前后保持不变。
- calibration lock 明确记录 `evaluation_labels_accessed=false`、`evaluation_assets_scored=false`、`pixel_boundary_gt_used=false`。
- evaluation matrix 明确记录 `ground_truth_accessed=false`、`evaluation_labels_accessed=false`、`parameter_updates_after_evaluation=false`、`cleaning_performed=false`。
- 本地 identity、标签、run output 位于 Git 忽略目录 `data/local/text-seeded-container-association/goal5-routed-v0.1/`，不是 benchmark manifest。

S1 使用 PaddleOCR `3.7.0` 的 `PP-OCRv6_medium_det` 与冻结 grouping 参数。环境的 `pip check` 仍报告 Paddle GPU CUDA 组件版本不完全匹配；本轮 S1 已成功完成且输入 hash 未变化，但该环境漂移是后续复现风险，不能隐去。

## 4. Calibration lock

仅在 `cal-51..54` 上搜索 12 个预声明组合，其中 8 个通过全部 contract。固定选择规则为：全部 contract 通过后，优先更高的 container/topology 证据阈值与更小 support padding。

冻结参数：

| 参数 | 值 |
| --- | ---: |
| container boundary threshold | 0.50 |
| extreme seed span ratio | 0.85 |
| extreme seed area ratio | 0.65 |
| max support group count | 2 |
| support padding scale | 0.15 |
| support max area ratio | 0.20 |
| topology different threshold | 0.20 |
| topology same threshold | 0.85 |
| topology same minimum member pairs | 2 |

Calibration 结果：

| Case | Route | Topology | Regions | Goal 6 eligible | Result |
| --- | --- | --- | ---: | --- | --- |
| cal-51 | coarse container | same | 1 container | yes | PASS |
| cal-52 | coarse container | different | 2 containers | yes | PASS |
| cal-53 | bounded support | n/a | 1 support | yes | PASS |
| cal-54 | regionless abstention | n/a | 0 | no | PASS |

## 5. 一次性 evaluation

冻结 lock 和实现 hash 后运行一次 `case-51..54`；先生成无答案 matrix，之后才由 evaluator 读取标签。

| Case | 实际 Route | Topology | Regions | Goal 6 eligible | Result |
| --- | --- | --- | ---: | --- | --- |
| case-51 | coarse container | same | 1 container | yes | PASS |
| case-52 | coarse container | different | 3 containers | yes | PASS |
| case-53 | bounded support | n/a | 1 support | yes | PASS |
| case-54 | regionless abstention (`no_seed`) | n/a | 0 | no | PASS |

| 指标 | 结果 | Gate |
| --- | ---: | ---: |
| route correctness | 4/4 | 4/4 |
| topology correctness | 2/2 | 全部适用例正确 |
| container count correctness | 2/2 | 全部适用例正确 |
| bounded support validity | 1/1 | 1/1 |
| regionless abstention | 1/1 | 1/1 |
| false low-risk candidates | 0 | 0 |
| cross-container leakage violations | 0 | 0 |

这里的 “cross-container leakage” 只表示 coarse topology/count contract 没有把不同容器非弃权合并；不是 pixel leakage 指标。

## 6. 决策、理由与拒绝方案

### 决策

- 保留三路架构，进入 Goal 6 最小试验。
- Goal 6 只接收 `goal6_trial_eligible=true` 且 topology 非 uncertain 的冻结输出。
- `REGIONLESS_ABSTENTION` 不产生空间 fallback，也不进入 Goal 6。
- Goal 5 输出不能直接用于实际产品或自动清字。

### 理由

单独 B1 会在无气泡/错误 seed 上扩散；统一 corrected P1 已在 Goal 4 显示会把部分真实气泡退化为文字邻域。三路分流在最小独立 evaluation 上同时保住了 explicit container、free-text support 与无效 seed abstention，且没有用扩大 coverage 换取通过。

### 拒绝方案

- 拒绝把 bounded support 伪装成 bubble/container；
- 拒绝把 uncertain topology 强制变为 same 或 different；
- 拒绝在 evaluation 后调阈值、扩大网格或增加 asset-specific rule；
- 拒绝在 Goal 5 提前实现 Pixel Text Mask、safe edit region 或 Cleaning；
- 拒绝使用 OCR 字符串、人工标签或 evaluator verdict 作为 router 输入。

## 7. 风险与实际/预期失败模式

本轮未观察到 gate 级失败，但样本只有 4 个 calibration + 4 个 evaluation，不能推断广泛泛化能力。仍需保留：

- 画风变化使 0.50 边界阈值失效；
- 分镜线、人物轮廓或网点被当作容器边界；
- 接触气泡被合并，或同容器多列被错误拆分；
- 单个错误但紧凑的 seed 被送入 bounded support；
- 大气泡/大字号对话被 extreme geometry 错误弃权；
- member-pair 最大分数造成偶然 same 判定；
- coarse basin 包含非文字像素，Goal 6 局部 mask 生成仍可能失败；
- S1 漏检导致安全 abstain，但也会损失可处理覆盖率。

任何 topology 不确定、support 触边/超面积、seed 极端或 Goal 6 局部 mask 证据不足的 case 都应继续 `SKIP/REVIEW_REQUIRED`，不能靠强制清字修复。

## 8. 验证

```text
python -m pytest \
  tests/unit/test_text_seeded_container_association_harness.py \
  tests/unit/test_text_seeded_container_calibration.py \
  tests/unit/test_text_seeded_container_focused_calibration.py \
  tests/unit/test_text_seeded_container_goal4_r0.py \
  tests/unit/test_text_seeded_container_goal4_evaluator.py \
  tests/unit/test_text_seeded_container_r0_matrix.py \
  tests/unit/test_text_seeded_container_r0_evaluator.py \
  tests/unit/test_text_seeded_container_s1_freeze.py \
  tests/unit/test_text_seeded_container_routed_association.py \
  tests/unit/test_text_seeded_container_routed_calibration.py -q
```

结果：`56 passed`。Goal 5 routed 专项测试结果：`9 passed`。此外已检查 calibration/evaluation source 隔离、hash 不变、GT access guard、one-shot output guard 与 route contract 互斥。

证据复核时发现首版 evaluator 将 false-low-risk 数量写为常量 0。冻结的四个结果本身全部为 `REVIEW_REQUIRED/SKIP`，但为避免 gate 依赖人工观察，评分器已改为逐例读取结果并验证 decision；它还把 route、topology、container count、support 与 abstention 分开计数。随后仅对同一批不可变 result hashes 生成 `evaluation-verified.json`，结果仍全部通过；router、lock、资产、S1 与 case output 均未修改或重跑。

## 9. 未解决问题与 Goal 6 边界

未解决的是：如何在冻结 coarse container/support 内生成保守的 Pixel Text Mask 与 safe edit region，以及用何种最小 fill 方法得到可视化清字结果。Goal 6 才允许对这些问题做人工审查试验。

Goal 6 必须提供少量“原图 / seed 与空间域 overlay / Pixel Text Mask / 清字后”效果图，同时保留指标表；不得把可视化观感替代安全门禁。Goal 5 本身不生成清字效果图。
