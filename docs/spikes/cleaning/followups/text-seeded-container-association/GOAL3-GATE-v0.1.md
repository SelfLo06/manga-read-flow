# Goal 3 — R0 Container Association Gate v0.1

## Verdict

```text
GOAL 3 VERDICT = FURTHER_SPIKE
GO_TO_PIXEL_TEXT_MASK_SPIKE = NO
ACTUAL CLEANING ALLOWED = NO
```

## Gate Matrix

| Gate | Result | Evidence |
| --- | --- | --- |
| 六例 R0 × B0/B1/P1 完整 | PASS | 18/18 JSON + 18/18 overlays；hash 全部匹配。 |
| R0 source 未修改 | PASS | `source_hashes_unchanged=true`。 |
| Calibration/evaluation 隔离 | PASS | 算法 runner 无 evaluator input；`ground_truth_accessed=false`。 |
| R0 后无调参 | PASS | `parameter_updates_after_r0=false`；阈值保持 `0.40/0.75`。 |
| Safety decision | PASS | B0/B1/P1 均 6/6；全部风险输出 review。 |
| False-low-risk | PASS | 三种方法均为 0。 |
| P1 same/different topology | PARTIAL / FAIL TO ADVANCE | 2/3；case-03 false split。 |
| P1 container type | FAIL TO ADVANCE | 2/6；NOT_TEXT、free text、explicit 均误判。 |
| P1 coarse target-region quality | FAIL | 0/5 可接受 coarse match；普遍背景泄漏或错误内部边界。 |
| P1 相对 B1 收益 | FAIL | topology 相同；case-05/06 的 B1 coarse bubble 明显更好。 |
| Strict pixel boundary metrics | NOT AVAILABLE | A only coarse reference；B overlay unavailable。 |
| Cleaning / pixel text mask | NOT RUN | 明确越界禁止。 |

## Stop and Next Decision

本轮在 verdict 后停止，不修改当前 P1、scorer、阈值或 R0 输出。任何继续工作必须新开 focused association correction Goal，并只使用新的 calibration 资产冻结新版本。当前不得进入 Pixel Text Mask 或实际 Cleaning。

## Validation

```text
python -m py_compile \
  tools/spikes/text_seeded_container_association/harness.py \
  tools/spikes/text_seeded_container_association/calibrate_same_container.py \
  tools/spikes/text_seeded_container_association/run_r0_matrix.py \
  tools/spikes/text_seeded_container_association/evaluate_r0_matrix.py

python -m pytest \
  tests/unit/test_text_seeded_container_association_harness.py \
  tests/unit/test_text_seeded_container_calibration.py \
  tests/unit/test_text_seeded_container_s1_freeze.py \
  tests/unit/test_text_seeded_container_r0_matrix.py \
  tests/unit/test_text_seeded_container_r0_evaluator.py -q
```

```text
32 passed in 7.25s
```
