# Goal 5 — Routed Spatial Association Harness v0.1

状态：`FROZEN_FOR_IMPLEMENTATION`

## HARNESS

### 数据隔离

- calibration：`cal-51` 至 `cal-54`；evaluation：`case-51` 至 `case-54`。
- 8 个 crop 来自 8 个不同 source image；与 R0、Goal 4 source hash 重叠为 0。
- calibration/evaluation source hash 重叠为 0；只使用冻结 S1 Detection/Grouping run。
- evaluator labels 只在输出完成后读取；算法 run payload 必须记录 `ground_truth_accessed=false`。

### 三路输出 contract

| Route | 必须输出 | 必须为空 | 决策限制 |
| --- | --- | --- | --- |
| `COARSE_CONTAINER_SEARCH` | 一个或多个 B1 coarse region、seed trace、container evidence | pixel text mask / safe edit region | topology decisive 才可 `goal6_trial_eligible=true` |
| `BOUNDED_SUPPORT` | 紧凑、有限、不触 ROI 边的 support | container assertion | 只表示局部计算支持，不表示气泡 |
| `REGIONLESS_ABSTENTION` | reason、unassigned/风险证据 | spatial region | 必须 `SKIP`，不得进入 Goal 6 |

统一输出字段：

```text
asset_id
route
route_confidence
input_fragment_ids
input_group_ids
container_regions_or_null
support_regions_or_null
topology = same | different | uncertain | not_applicable
topology_evidence
recommended_decision = REVIEW_REQUIRED | SKIP
goal6_trial_eligible
abstention_reasons
diagnostics
```

本轮不存在 `LOW_RISK` 或 `AUTO_ACCEPT`。`goal6_trial_eligible` 只是人工试验入选条件。

### 冻结样本矩阵

| Split | ID | 预期 route | topology contract |
| --- | --- | --- | --- |
| calibration | cal-51 | coarse container | same |
| calibration | cal-52 | coarse container | different |
| calibration | cal-53 | bounded support | not applicable |
| calibration | cal-54 | regionless abstention | not applicable |
| evaluation | case-51 | coarse container | same |
| evaluation | case-52 | coarse container | different |
| evaluation | case-53 | bounded support | not applicable |
| evaluation | case-54 | regionless abstention | not applicable |

标签是 coarse semantic/topology contract，不是 pixel boundary GT。不得计算 pixel IoU、boundary F1 或 uncertainty-band 数值。

### Calibration

router 只允许从预先声明的有限网格选择：container boundary evidence、最大/最小 basin area、compact-support padding/area、extreme span/area、complex-group count 与 topology decisive margin。选择顺序固定：

1. calibration 4/4 route；
2. cal-51/cal-52 topology 正确且 decisive；
3. bounded support 非空、不触边、面积受限；
4. abstention regionless；
5. 同分选择更保守阈值。

无 4/4 可行组合则停止，禁止查看 evaluation 后扩网格。

### 指标与门禁

| 指标 | Gate |
| --- | ---: |
| calibration route correctness | 4/4 |
| evaluation route correctness | 4/4 |
| topology correctness（适用 4 例） | 4/4；不得错误确认 |
| container count correctness | 适用例全部正确或安全 abstain |
| cross-container leakage | 0 个非弃权错误 |
| bounded support validity | 2/2 非空、有限、不触边 |
| regionless abstention | 2/2 |
| false-low-risk / dangerous flip | 0 |
| source/hash/GT isolation | 全部 PASS |

### 停止条件

发现来源冲突、GT 泄漏、source mutation、crop 截断关键文字/容器、跨 split/source 重复、S1 silent skip、calibration 无可行参数、evaluation 后要求调参、错误确认 topology、跨容器非弃权泄漏，立即停止。需要实际 Cleaning、禁止算法、正式 Provider/Workflow、benchmark manifest 或依赖升级才能继续时同样停止。

### 预期失败模式

- B1 把分镜/人物轮廓当容器边界；
- 接触气泡被合并或同容器多列被拆分；
- bounded support 吞入分镜、人物或整片背景；
- 大型/复杂 SFX 被误判为普通 support；
- 无 seed 或低质量 seed 仍产生非空 region；
- route confidence 在证据变差时反而升高；
- topology 不确定却被标为 Goal 6 eligible。
