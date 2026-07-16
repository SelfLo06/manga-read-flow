# Goal 5 — Routed Spatial Association Gate v0.1

## Verdict

```text
GOAL 5 VERDICT = GO_TO_GOAL6_MINIMAL_CLEANING_TRIAL
THREE-ROUTE ARCHITECTURE = SELECTED FOR MINIMAL HUMAN-REVIEWED TRIAL
PIXEL-ACCURATE SEGMENTATION CLAIM = NO
ACTUAL CLEANING COMPLETED = NO
```

## Gate Matrix

| Gate | Result | Evidence |
| --- | --- | --- |
| 8 个资产与 R0/Goal 4 隔离 | PASS | 8 个 source hash 两两不同；denylist overlap=0。 |
| calibration/evaluation 隔离 | PASS | 4+4；source overlap=0；calibration 未访问 evaluation labels/assets。 |
| S1 完整性 | PASS | 8/8 有显式记录；case-54 的 0 seed 是有效 abstention 输入，不是 silent skip。 |
| calibration route contract | PASS | 4/4；12 组有限网格中 8 组全通过。 |
| evaluation route correctness | PASS | 4/4，一次性运行后无调参。 |
| evaluation topology | PASS | same/different 2/2；无错误确认。 |
| evaluation container count | PASS | 2/2；same=1，different=3。 |
| bounded support | PASS | 1/1 非空、有限、不触边。 |
| regionless abstention | PASS | 1/1，无 seed 时无空间输出。 |
| cross-container leakage violation | PASS | 0；仅按 coarse topology/count contract 评价。 |
| false low-risk / AUTO_ACCEPT | PASS | 0；所有候选仍为 `REVIEW_REQUIRED`。 |
| source mutation / GT leakage | PASS | source hash unchanged；run 时 GT/evaluation labels 未访问。 |
| Pixel Text Mask / Cleaning | NOT RUN | Goal 5 明确禁止。 |
| pixel IoU / boundary F1 | NOT AVAILABLE | 没有 pixel-accurate boundary GT，不得宣称。 |

## Frozen Choice

Goal 5 选择以下组合，不选择统一容器算法：

- `COARSE_CONTAINER_SEARCH`：B1-style 局部传播 + decisive topology merge/preserve；
- `BOUNDED_SUPPORT`：独立的 texture-adaptive 有界支持域；
- `REGIONLESS_ABSTENTION`：无 seed、极端或失败证据不生成 region；
- uncertain topology：不得进入 Goal 6。

## Authorization Boundary

本 gate 只建议维护者启动 Goal 6 最小清字试验。Goal 6 必须另行冻结 GOAL/HARNESS；不得直接接入 CleanerProvider、Workflow 或生产路径，不得使用 `AUTO_ACCEPT`，不得把 Goal 5 coarse region 当作 Pixel Text Mask。

## Stop Record

Goal 5 在一次 evaluation 和本 gate 后停止。不得使用 evaluation 结果继续修改 router、阈值、asset、ROI 或 S1 run。后续发现的路由问题应作为新证据记录，不能回写 Goal 5 成功结果。

禁止项复核：未使用 LaMa、Diffusion、ControlNet、FFT 网点重建；未执行实际 Cleaning；未接入 CleanerProvider/Workflow；未生成 benchmark manifest；未使用 AUTO_ACCEPT；未 push。
