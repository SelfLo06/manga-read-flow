# Goal 7 — Local Association Routing Correction Final Report v0.1

状态：`COMPLETE_WITH_LOCAL_ASSOCIATION_EVIDENCE`

范围：仅 Text-Seeded Container Association Spike。没有重跑 Detection/Grouping，没有生成 Pixel Text Mask 或 safe edit region，没有执行 Cleaning、E1/E2、CleanerProvider 或 Workflow。

## 裁决

```text
PAGE_GLOBAL_ASSOCIATION = REJECTED
LOCAL_GROUP_CLUSTER_ROUTING = PASS_FOR_SPIKE
BOUNDED_LOCAL_B1_RESOURCE_READINESS = PASS_FOR_SPIKE
COARSE_CONTAINER_AUTOMATION = NOT_PROMOTED
PIXEL_TEXT_MASK_AND_CLEANING = BLOCKED
```

Goal 7 保留了 text-first 方向，但只证明：普通对白可以在整页环境中独立进入有界局部 B1，并产出供人工审查的 coarse candidate。它没有证明所有非空 region 都是正确容器，更不构成像素级边界或清字证据。

## 冻结输入与阶段

唯一上游输入为冻结 S1：

```text
data/local/text-seeded-container-association/
  large-scale-e1-e2-comparison-v0.1/
  s1-runs/s1-book-40-v0.1/results.json
```

| 阶段 | 结果 |
| --- | --- |
| A：静态局部分流 | 40 页、366 group → 311 local cluster；255 `LOCAL_B1_CANDIDATE`、55 `LOCAL_REVIEW_REQUIRED`、1 `LOCAL_ABSTENTION` |
| B：人工冻结 + bounded local B1 | 12 个普通对白 group 中 10 个确认可见 candidate（83.3%）；接触/相邻气泡 topology 2/2 正确；4 个负控/uncertain 均保持 local skip |
| C：一次性 40 页复验 | 255/255 local B1 完成且非空；38/40 页有候选；未运行 55 个 topology 待审 cluster 与 1 个 oversized cluster |

## 门禁结果

| 门禁 | 结果 | 裁决 |
| --- | ---: | --- |
| page-global extreme abstention | 0 | PASS |
| abnormal seed collateral page loss | 0 | PASS |
| uncertain pair page-wide block | 0 | PASS |
| 人工确认普通对白非空 candidate | 10/12 = 83.3% | PASS |
| 可见普通对白 coarse candidate | 10 | PASS |
| 接触/相邻气泡 topology | 2/2 正确 | PASS |
| OOM / worker crash / timeout | 0 / 0 / 0 | PASS |
| 单 ROI 峰值 RSS | 165.5 MB | PASS（<512 MB） |
| 单 ROI p95 B1 runtime | 0.657 s | PASS（<2 s） |
| false-low-risk / AUTO_ACCEPT | 0 / 0 | PASS |

资源结果只证明有界局部执行稳定；`255/255 non-empty` 不是语义正确率。

## 可见证据与限制

Phase B 人工审查中，8 个单组普通对白有 5 个 `CORRECT`、1 个 `PARTIAL`、2 个 `WRONG_OR_LEAK`；两个多组相邻气泡为 1 个 `CORRECT`、1 个 `PARTIAL`。错误或泄漏项均被人工标为 `PhaseC=NO`，没有被自动提升。

Phase C 抽样同样显示标题、SFX 和复杂画面会生成非空粗区域，部分会越出目标对象。这是现阶段 local route 尚未具备 content-role qualification 的直接证据。因此：

```text
LOCAL_B1_CANDIDATE != confirmed container
non-empty coarse region != safe edit region
```

## 冻结决策

1. page-global geometry、page-global topology 和 full-page B1 被拒绝；
2. per-group / 小型 local cluster routing 是后续唯一允许的 association 粒度；
3. B1 只允许在有 ROI、L1 像素/队列/内存/时间预算的隔离 local worker 中运行；
4. `LOCAL_REVIEW_REQUIRED` 不可自动运行后续 Pixel Text Mask 或 Cleaning；
5. 所有 local B1 输出继续是 `REVIEW_REQUIRED`，禁止 `AUTO_ACCEPT`；
6. Pixel Text Mask、safe edit region、E1/E2 自动清字仍被阻断。

## 拒绝的替代项

- 继续用全页 union bbox 判断 extreme：已证明会把普通漫画页误弃权；
- 任意全页 pair uncertain 阻塞全页：已证明会产生 page-wide collateral loss；
- full-page Python priority-flood：已有约 14 GB OOM 证据；
- 用 255 个非空 B1 region 宣称 association correctness：与 Phase B 的 `WRONG_OR_LEAK` 反例冲突；
- 在本结果后直接生成 mask 或清字：缺少 confirmed-container 与保护结构证据。

## 建议的下一 Goal

`Goal 8 — Local Candidate Qualification Spike`：在已冻结的 local route + bounded B1 上，验证如何将 explicit bubble、bounded support、SFX/not-text 与 uncertain 分开，并以人工语义样本评估 coarse candidate 的正确性/泄漏。它必须继续复用冻结 S1/Goal 7 artifacts；不接入 Pixel Text Mask 或 Cleaning，除非新的 qualification gate 单独通过。

## 证据路径

```text
data/local/text-seeded-container-association/goal7-local-routing-v0.1/
  phase-a-v0.1/PHASE-A-MATRIX.json
  phase-b-v0.1/PHASE-B-HUMAN-REVIEW.json
  phase-c-v0.1/PHASE-C-FROZEN-CONFIG.json
  phase-c-v0.1/run-v0.1/PHASE-C-RESULTS.json
  phase-c-v0.1/run-v0.1/SAMPLE-CONTACT-SHEET.png
```
