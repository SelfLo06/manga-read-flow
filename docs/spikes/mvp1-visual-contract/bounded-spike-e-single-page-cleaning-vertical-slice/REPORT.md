# MVP-1 Visual Contract Bounded Spike E — 实现报告

## 结论

```text
FORMAL_PAGE = case-71
LOCAL_CLEANING_CANDIDATE = PASS
APPLY_SCOPE = PASS
BLOCK_REASON_BINDING = PASS
WORKFLOW_GATE_BEHAVIOR = PASS
PAGE_CLEANING_COMPLETENESS = NOT_ACHIEVED
OVERALL = ACCEPT_BLOCKED_REVIEW
```

本轮证明：在一个真实 `case-71` 页面上，已获准的 `g002/s01` BubbleInstance 能通过正式 Provider、ArtifactService、Repository、QualityCheck 和 decision transaction 生成可审计候选；同页 `g002/s02` 输入不完整时，系统能登记候选与 evidence、创建 blocking QualityIssue，并保持 `active_cleaned_artifact_id=NULL`。它没有证明 case-71 已完成整页清字。

## 正式范围与 disposition

case-71 共保存 6 个 TextSegment、6 个独立 BubbleInstance 和唯一 assignment：

| Segment | Cleaning disposition | 结果 |
|---|---|---|
| `g002/s01` | `E1 / COMPLETE / spike_d_pass` | 执行真实 Cleaner，局部结果通过 |
| `g002/s02` | `E1 / INCOMPLETE_REVIEW` | 不执行；`required_text_not_safely_editable` 阻塞 |
| `g001/s01`、`g003/s01`、`g004/s01`、`g005/s01` | `OUT_OF_SLICE / NOT_EVALUATED` | 无冻结 pixel-cleaning 证据，明确不扩大写回授权 |

`g002/s01` 与 `g002/s02` 属于同一 ContactBubbleCluster，但保持两个独立 BubbleInstance；Cleaner 和 Validator 均未使用 parent cluster mask。

## 正式执行证据

本地 run：

```text
data/local/mvp1-single-page-cleaning-slice-v0.1/case-71-run-v0.3/
```

关键结果：

- `g002/s01` ActualChangedPixelMask：4,530 pixels；
- residue、outside-safe、protected、uncertainty、instance-boundary damage：均为 0；
- background difference：0；seam delta：1.0；
- 原图 SHA-256 前后均为 `95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb`；
- workflow attempt：Provider 成功；
- workflow decision：`block / cleaning_input_or_output_blocked`；
- blocking issue 精确绑定 `case-71__g002__s02`、validation evidence、attempt、input hash 和 config hash；
- Page 状态：`review_required`；
- `active_cleaned_artifact_id=NULL`。

人工 FORM 直接嵌入 original、candidate、重算的 ActualChangedPixelMask overlay 和 blocking-instance overlay。人工选择为：

```text
PASS_LOCAL_CLEANING
PASS_APPLY_SCOPE
PASS_BLOCK_REASON
ACCEPT_BLOCKED_REVIEW
```

## 实现能力

- project migration v2：visual revision、BubbleInstance/TextSegment revision、assignment、eligibility、Cleaning result history 与 Page 当前 visual revision；
- ArtifactService：有界、合法 UTF-8 JSON evidence 登记；
- CleanerProvider：`candidate ∩ safe-edit ∩ instance - protected - uncertainty` 的局部 border-sampled fill；
- 独立 Cleaning validator：从 source/output bytes 重算 ActualChanged、residue、structure damage、background difference 与 seam evidence；
- QualityCheck：生成实例/TextBlock 绑定的 blocking issue；
- decision transaction：Cleaning result、issue、decision、attempt、task 和 active pointer 原子收口；
- PASS reuse：只在当前 visual revision、active pointer 与 artifact integrity 均一致时复用；
- BLOCK：候选保持正式可审计，但不 selected。

## 性能

正式临时 workflow 总耗时约 `612.355 ms`：

| 阶段 | 耗时 |
|---|---:|
| contract artifact + persistence | 96.413 ms |
| Provider + output promotion | 177.282 ms |
| Validator + evidence promotion | 319.987 ms |
| Quality classification | 0.127 ms |
| Decision transaction | 6.030 ms |

该数据只覆盖冻结输入后的 Cleaning vertical slice，不包含 Detection、OCR、Grouping、Association 或 Translation。

## 已知限制与后续问题

1. `g002/s02` 只有 6 个 required-support 像素落在 safe-edit 外，现合同仍正确阻塞整个实例；这说明虚拟实例边界 / safe-edit derivation 需要 text-aware correction，不能通过放宽 blocking Gate 掩盖。
2. 其余四个实例只有 topology/eligibility 候选，没有冻结的 pixel-cleaning evidence；本轮不得宣称整页覆盖。
3. 当前 run 证明局部正式路径和安全拒绝，不证明 E2/E3、复杂背景、全页、Batch、Typesetting 或产品 `AUTO_ACCEPT`。
4. 下一轮若修正 `g002/s02`，必须保持两个 BubbleInstance 独立，并验证 required support 完整、边界无损伤和相邻实例无泄漏。

## 验证

- 定向正式回归：`69 passed`；
- 扩展测试（排除三个既有收集阻塞项）：`300 passed, 1 failed`；唯一失败为既有 Goal 2 frozen harness hash mismatch，与本轮文件无关；
- 完整收集另受两个同名 `test_core.py` 和缺少 `psutil` 的既有问题阻塞；
- `git diff --check` 通过；
- 报告生成时未 commit、未 push；后续由独立、经测试的提交收口，当前版本状态以 Git 历史为准。
