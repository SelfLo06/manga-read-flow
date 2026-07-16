# Detection + OCR Real Tool Spike — REPORT

状态：`DONE`

最终结论：`CONDITIONAL_GO`

## 1. Executive Summary

- run_id：`20260710T091753Z-0676c2`
- 运行时间：`2026-07-10`
- 样本：8 assets / 27 scored regions
- 最终结论：`CONDITIONAL_GO`
- 核心理由：Detection 对核心 real regions 的召回足够，但 line-level fragmentation 很重；manga-ocr 在干净 crop 上可用，复杂/竖排/彩色场景仍有明显误差，真实集成前需要容忍 grouping 缺口和人工回退。

## 2. Environment

| Item | Value |
|---|---|
| OS | Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| Python / Conda | Python 3.12.13 / `manga-read-flow` |
| GPU / Driver / CUDA | NVIDIA GeForce RTX 4060 Laptop GPU / 566.26 / 12.6 |
| PyTorch | 2.13.0+cu126 |
| Paddle / PaddleOCR | PaddleOCR 3.7.0 / paddlepaddle-gpu 3.3.1 |
| manga-ocr | 0.1.14 |
| Pillow / OpenCV | Pillow 12.2.0 / opencv-python-headless 5.0.0.93 + opencv-contrib-python 4.10.0.84 |

`pip check` 摘要：`paddlepaddle-gpu 3.3.1` 与已安装 NVIDIA CUDA 组件存在精确版本冲突（`nvrtc`、`cudnn`、`cusparselt`、`nccl`），但本轮真实实验仍能完成。

## 3. Input Integrity

- GT validator：通过
- ground-truth hash before / after：一致
- image hashes unchanged：一致
- 实际计分 regions：27
- 排除的 auxiliary regions：18 real auxiliary pending；其中 15 个 unmatched prediction 已手工归类为 `auxiliary_text`，其余辅助/装饰内容不纳入核心评分

## 4. Experiment A — Pure OCR

| Split | Regions | Exact rate | Median CER | Mean CER | CER <= 0.25 |
|---|---:|---:|---:|---:|---:|
| Synthetic | 11 | 0.7273 | 0.0 | 0.1298 | 10 |
| Real core | 16 | 0.5625 | 0.0 | 0.1591 | 12 |

主要失败案例：

| Asset / Region | Expected | Actual | CER | Evidence tags |
|---|---|---|---:|---|
| synthetic_03 / s03_r01 | どうしてそんなことをまだ終わっていない | どうしてそんなことをまだ終わってとをいない | 0.1053 | ocr_substitution; scenario: small_text |
| synthetic_03 / s03_r02 | 本当に大丈夫なのか | 本当に大丈夫な | 0.2222 | ocr_substitution; scenario: small_text |
| synthetic_04 / s04_r03 | どうしてそんなことを | そういうことですか．．． | 1.1 | detection_miss, ocr_substitution; scenario: complex_background, low_contrast, skewed_text, small_text |
| black1 / black1_r04 | はー!? 何その連携 ハメじゃん！ このっ・・・ サメのくせに！ | はー？何その連携ハメじゃん！このっ．．．サメのくせに！ | 0.1786 | ocr_substitution, detection_fragmented; scenario: vertical_text |
| black1 / black1_r06 | シッポ フリフリすなー むかつくー!! | シッポフリフリすなーむかつくー！！ | 0.1176 | ocr_substitution, detection_fragmented; scenario: vertical_text |
| gura_color / gura_color_r04 | へぇー | えー | 0.6667 | ocr_substitution; scenario: color_text, vertical_text |
| gura_color / gura_color_r08 | えっ!? | えっ！？ | 0.5 | ocr_substitution; scenario: color_text, vertical_text |
| gura / gura_r06 | お！ 中から人の声が 聞こえていますよ！ | おー中から人の声が 聞こえていますよ！ | 0.0556 | ocr_substitution, detection_fragmented; scenario: vertical_text |
| black2 / black2_r02 | はぁ？ こういうのは 普通兄が 上だろ？ それにお前 寝相わるいし 落ちちゃうぞ | はぁ？こういうのは普通兄が上だろ？それにお前落ちちゃうぞ | 0.1471 | ocr_substitution, detection_fragmented; scenario: vertical_text |
| black2 / black2_r05 | はぁ・・・ 仕方ないなぁ | はぁ．．．仕方ないなぁ | 0.2727 | ocr_substitution, detection_fragmented; scenario: vertical_text |

## 5. Detection-only

| Split | GT | Hit | Miss | Recall | Fragmented | Clear FP |
|---|---:|---:|---:|---:|---:|---:|
| Synthetic | 11 | 10 | 1 | 0.9091 | 3 | 0 |
| Real core | 16 | 16 | 0 | 1.0 | 13 | 0 |

## 6. Experiment B — Detection + OCR

### Oracle container group

| Split | Regions | Misses | Exact rate | Median CER | CER <= 0.30 |
|---|---:|---:|---:|---:|---:|
| Synthetic | 11 | 1 | 0.7273 | 0.0 | 9 |
| Real core | 16 | 0 | 0.6250 | 0.0 | 14 |

### Native fragments

| Split | Regions | Fragmented | Exact rate | Median CER | Order failures |
|---|---:|---:|---:|---:|---:|
| Synthetic | 11 | 3 | 0.9091 | 0.0 | 0 |
| Real core | 16 | 13 | 0.4375 | 0.0866 | 0 |

## 7. Failure Attribution

| Failure source | Count | MVP impact |
|---|---:|---|
| Detection miss | 1 | One complex-background synthetic block was missed entirely. |
| Fragmentation / grouping | 16 | The dominant issue on real pages; per-line fragments are frequent, especially vertical dialogue. |
| OCR on valid crop | 3 | Direct OCR remains strong on clean crops but degrades on color, low contrast, and some vertical text. |
| Reading order | 0 | No separate order failure was isolated in this first run; most issues are fragmentation/crop-level. |
| Runtime / environment | 0 | No crash/OOM; GPU cold start was stable. |

## 8. Scenario Analysis

| Scenario | Result | Failure mode | MVP implication |
|---|---|---|---|
| Horizontal | Mixed but usable | One synthetic miss; otherwise mostly strong on clean horizontal text. | Usable with fallback and user review on edge cases. |
| Vertical | Good detection, fragile OCR | Fragmentation and substitutions on vertical dialogue. | Needs grouping tolerance and review path. |
| Small text | Weak | Small/overflow risk crops lose characters. | Warning/skip/manual correction required. |
| Color text | Mixed | Colorized dialogue introduces substitutions. | Not a fully solved mainline case. |
| Complex background | Weak | One outright miss and several noisy crops. | Must allow skip / manual intervention. |
| Low contrast | Weak | CER worsens on faint text. | Keep as warning path. |
| Skewed text | Mixed | Angled blocks fragment and can miss. | Needs future grouping/geometry work. |

## 9. Performance

| Metric | Cold | Warm p50 | Warm max |
|---|---:|---:|---:|
| Paddle initialization | 2.03s | 0s | 0s |
| manga-ocr initialization | 8.13s | 0s | 0s |
| Detection per page | 5.95s | 7.50s | 9.63s |
| OCR per crop | covered in region timings | covered in region timings | covered in region timings |
| End-to-end per page | 5.95s p50 | 7.50s p50 | 9.63s max |

稳定性与资源情况：cold/warm 两次完整 run 都成功完成；GPU 维持高负载但未 OOM。`pip check` 存在 NVIDIA 版本冲突，属于已知环境风险。

## 10. Architecture / MVP Impact

回答：

- PaddleOCR 输出更像 line-level prediction，不是 semantic container；核心 real pages 需要独立 grouping/归因。
- 需要独立 line-to-container grouping 或至少 oracle-style grouping 作为中间验证层。
- manga-ocr 适合作为主 OCR 候选，但对竖排、彩色、低对比和碎片拼接很敏感。
- 需要备用 OCR 或手工回退路径，尤其是复杂背景/小字/倾斜块。
- 明确需要 warning、manual correction、skip 三条路径。
- 不建议在本 spike 里继续拆环境；当前 GPU 环境能跑通，但 `pip check` 冲突要保留为风险记录。

## 11. Exit Decision

```text
CONDITIONAL_GO
```

证据：

- Detection：real core 16/16 hit，但 fragmentation 13/16，unmatched 15 个主要是 auxiliary_text。
- Pure OCR：synthetic 11/11 中 10/11 CER<=0.25；real core 16/16 中 12/16 CER<=0.25，median CER=0.0。
- Detection + OCR：oracle group real 14/16 CER<=0.3；native fragments real 14/16 CER<=0.3，但 exact 仅 7/16。
- Performance：warm page p50 7.50s，max 9.63s，低于 10s 门槛。
- Environment：GPU 可用，cold/warm 稳定完成；`pip check` 存在 NVIDIA 组件版本冲突。
- MVP impact：可以进入最小 Provider Adapter 设计，但必须把 grouping 缺口、竖排碎片和复杂背景 skip 视为一等问题。

## 12. Next Step

只选择一个：

- 进入最小 DetectorProvider / OCRProvider 设计；
- 追加针对性 Spike；
- 替换某个候选工具；
- 先做环境拆分 Spike；
- 停止当前工具组合。
