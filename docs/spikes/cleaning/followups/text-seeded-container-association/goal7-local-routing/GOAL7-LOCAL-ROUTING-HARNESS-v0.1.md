# Goal 7 — Local Association Routing Harness

状态：`FROZEN_FOR_PHASE_A`

## 输入锁

唯一输入是：

```text
data/local/text-seeded-container-association/large-scale-e1-e2-comparison-v0.1/
  S1-INPUT-SPEC.local.json
  s1-runs/s1-book-40-v0.1/results.json
  images/case-01.jpg ... case-40.jpg
```

必须记录并验证 S1/result/source hash。不得重跑 detector/grouping，不得读取 E1/E2 候选
决定 route。

## Phase A contract

每个 cluster 输出：

```text
page_id
cluster_id
group_ids
fragment_ids
local_bbox
local_roi
local_topology = single | same | different | unresolved
route = LOCAL_B1_CANDIDATE | LOCAL_REVIEW_REQUIRED | LOCAL_ABSTENTION
reason
estimated_roi_pixels
queue_budget
working_memory_budget_mb
would_run_b1
```

Page 只汇总 cluster；不得存在 page-level extreme/topology route。

固定安全要求：

```text
page-global extreme abstention = 0
单个异常 seed 连带丢弃其他 cluster = 0
单个 uncertain pair 阻塞整页 = 0
false-low-risk = 0
```

Phase A 不声称 `LOCAL_B1_CANDIDATE` 已找到 container；它只是进入局部传播的资格。

## 人工冻结包

从 Phase A 输出选择少量 cluster，人工选择：

- 内容角色：普通对白 / caption-label / SFX-decoration / not-text / uncertain；
- 预期空间任务：coarse container / bounded support / local skip / uncertain；
- topology：same / different / n/a / uncertain；
- 是否进入 Phase B。

Phase B 至少冻结：6–8 个普通对白、2 个接触气泡、2 个 SFX/异常 seed、2 个 uncertain。
若 frozen pack 无法满足，停止并扩大人工样本，不得猜标签。

## Phase B 资源 contract

```text
max_roi_pixels <= 262144
max_queue_entries <= 500000
max_working_memory < 512 MB / ROI
p95 runtime < 2 s / ROI
OOM = 0
worker crash = 0
超限只 local abstain
```

B1 只在局部 ROI 的 L1 分辨率运行，结果可映射回原图坐标。至少输出：source crop、
seed/group overlay、local ROI、B1 coarse region、route/decision。

## Phase C 门禁

参数冻结后只运行一次 40 页复放：

| Gate | 要求 |
| --- | ---: |
| page-global extreme abstention | 0 |
| abnormal seed collateral page loss | 0 |
| uncertain pair page-wide block | 0 |
| human-confirmed ordinary dialogue non-empty candidate | >= 80% |
| OOM / worker crash | 0 / 0 |
| per-ROI peak memory | < 512 MB |
| per-ROI p95 runtime | < 2 s |
| visible ordinary-dialogue coarse candidates | >= 8 |
| false-low-risk / AUTO_ACCEPT | 0 |

若仍看不到至少 8 个普通对白 coarse container 候选，当前 B1/text-first 组合停止，不得
进入 Pixel Text Mask。

## 停止条件

S1/source hash 变化、需要重跑 Detection、需要 E1/E2 或 Pixel Mask 才能判断、出现整页
联锁、资源预算不可执行、人工标签不足、或 Phase C 后要求调参时立即停止。
