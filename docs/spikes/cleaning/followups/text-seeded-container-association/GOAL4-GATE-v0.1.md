# Goal 4 — Focused Association Correction Gate v0.1

## Verdict

```text
GOAL 4 VERDICT = B1_STRONG_BASELINE_ONLY
CORRECTED_P1_SELECTED = NO
GO_TO_PIXEL_TEXT_MASK_SPIKE = NO
ACTUAL_CLEANING_ALLOWED = NO
```

## Gate Matrix

| Gate | Result | Evidence |
| --- | --- | --- |
| 8 个 calibration case 与 R0 隔离 | PASS | 8 source hashes 与 R0 overlap=0；`r0_asset_accessed=false`。 |
| Maintainer FORM 完整冻结 | PASS | 8/8 单选、全部高信心；FORM hash 已写入 lock。 |
| Group-level same/different 可分 | PASS ON CALIBRATION | G4-01 different=0.163；G4-04 same=0.861；阈值 `0.30/0.85`。 |
| Calibration support/abstention gate | PASS | 正式 lock 8/8；G4-01～04 region 非空；G4-05/07/08 SKIP；G4-06 bounded。 |
| 单次 R0 完成且无调参泄漏 | PASS | 6/6 outputs；GT/evaluator 未访问；post-R0 tuning=false；source unchanged。 |
| Safety decision | PASS | corrected P1 6/6；无 false low-risk。 |
| Topology improvement over B1 | FAIL TO SELECT | corrected P1=2/3，B1=2/3；case-03 仍 false split。 |
| Target region availability | PARTIAL | corrected P1=4/5；case-04 有 target=null。 |
| False/excluded seed suppression | PARTIAL | case-01 与 case-05 的 excluded seed regionless；case-03/04 仍有 2 个非空 excluded region。 |
| Free-text leakage correction | PARTIAL PASS | case-02 明显改善；case-04 改善但不完整。 |
| Preserve B1 container scope | FAIL TO SELECT | case-05/06 corrected region 为文字邻域矩形，B1 coarse bubble 更好。 |
| Pixel-accurate boundary metric | NOT AVAILABLE | A only coarse reference；B overlay unavailable。 |
| Pixel Text Mask / Cleaning | NOT RUN | 明确禁止。 |

## Frozen Choice

`B1_STRONG_BASELINE_ONLY` 的含义：

- B1 保持为 explicit/contact bubble association 的强比较基线；
- 不把 B1 声称为生产算法；
- 不允许 B1 自动触发清字；
- corrected P1 保留为未选中的实验实现；
- 当前不启动 Pixel Text Mask、safe edit region 或 Cleaning preview。

## Stop Condition

Goal 4 在此停止。不得使用本次 R0 结果继续调整 scorer、阈值、padding、area cap 或 abstention 规则；任何新算法尝试必须是新的、明确授权的 Goal，并使用新的 calibration evidence。

## Validation

```text
python -m pytest \
  tests/unit/test_text_seeded_container_association_harness.py \
  tests/unit/test_text_seeded_container_focused_calibration.py \
  tests/unit/test_text_seeded_container_goal4_r0.py \
  tests/unit/test_text_seeded_container_goal4_evaluator.py \
  tests/unit/test_text_seeded_container_calibration.py \
  tests/unit/test_text_seeded_container_s1_freeze.py \
  tests/unit/test_text_seeded_container_r0_matrix.py \
  tests/unit/test_text_seeded_container_r0_evaluator.py -q
```

禁止项复核：未使用 LaMa、Diffusion、ControlNet、FFT 网点重建；未执行实际 Cleaning；未接入 CleanerProvider/Workflow；未生成 benchmark manifest；未使用 AUTO_ACCEPT；未 push。
