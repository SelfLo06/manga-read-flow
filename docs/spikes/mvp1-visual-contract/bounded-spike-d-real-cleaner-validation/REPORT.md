# Spike D Report — Real Cleaner Output Validation

## 结论

```text
REAL_CLEANER_OUTPUT_VALIDATION = PASS_WITH_LIMITS
REAL_CLEANER_OUTPUT_ON_FROZEN_SCOPE = PASS
SPIKE_D = GO_FOR_SINGLE_PAGE_CLEANING_SLICE
FULL_PAGE / BATCH / AUTO_ACCEPT / PRODUCT INTEGRATION = NOT_APPROVED
```

本结论只证明一个真实、局部的 `border_sampled_fill` 候选在三个冻结的低风险普通气泡 segment 上通过残字、结构损伤和背景一致性验证。它不推翻既有 Cleaning 全页覆盖、eligibility 或复杂对象仍未获证的结论。

## 目标与边界

本轮复用 Spike C 的 `visible-support / residue` 合同，对真实 Cleaner 输出而非合成 clean-negative 作验证。范围仅限：普通白色或浅色气泡、`required_safe_completeness=COMPLETE`、低 protected/uncertainty 风险。未接入 Workflow、API、UI、数据库、ArtifactService、Provider、全页或 Batch；不涉及 OCR、翻译或排版。

## 输入、实现与可复现性

- 运行：`data/local/mvp1-visual-contract-spike-d-v0.1/run-v0.5/`
- candidate snapshot SHA-256：`90b6465c8beb87cc7401dd02e572193a0126e54908d17bb975011b3895fa50f5`
- 冻结上游：Spike A `run-v0.4`、Spike B `run-v0.7`、Spike C `run-v0.7`。
- 固定真实 segment：`case-71__g002__s01`、`case-72__g001__s01`、`case-72__g006__s01`。`case-71__g002__s02` 仍为 `INCOMPLETE_REVIEW`，未进入真实 Cleaner。
- 唯一 Cleaner：Goal 6 风格的局部 `border_sampled_fill`；从 instance-local、protected/uncertainty 排除的读取环采样 RGB 中位数，只向 `visible_support ∩ safe_edit - protected - uncertainty` 写回。
- `ActualChangedPixelMask` 从 source/output RGB 差异重新计算；Cleaner 不访问数据库、不登记正式 artifact、不创建正式 QualityIssue，也不决定 retry/skip/block。

候选快照在读取 fixture oracle 的期望 decision 前写入；仅预先记录 oracle 文件 hash。该预读 hash 是可审计的隔离限制，不是读取 oracle decision。

## 真实输出结果

| Segment | Instance | Changed pixels | 残字 | 越出 safe / protected / uncertainty / boundary | 背景差异 | 人工审查 | 结果 |
|---|---|---:|---|---|---|---|---|
| `case-71__g002__s01` | 独立接触 BubbleInstance | 4,530 | 0 residue component | 全为 0 | 无差异 mask；seam Δ=1.000 | PASS | PASS |
| `case-72__g001__s01` | 普通气泡 | 4,248 | 0 residue component | 全为 0 | 无差异 mask；seam Δ=2.236 | PASS | PASS |
| `case-72__g006__s01` | 普通气泡 | 2,532 | 0 residue component | 全为 0 | 无差异 mask；seam Δ=2.449 | PASS | PASS |

三条记录均保存 source、required support、safe-edit、protected、uncertainty、Cleaner candidate、ActualChangedPixelMask、真实输出、residue mask、local-background sampling、structure-damage 和 background-difference artifact 及 hash。完整字段在该 run 的 `summary.json` 和 `real-cleaner-snapshot.json`。

## Controls 与 Gate

五个确定性失败 control 全部获得预期 `BLOCK`：

| Control | 必须阻断的原因 | 结果 |
|---|---|---|
| 原图未修改 | `cleaning_residue` | BLOCK |
| 仅清深色 core | halo / visible residue | BLOCK |
| safe-edit 外写回 | `outside_safe_edit` | BLOCK |
| 修改 protected | `protected_structure_damage` | BLOCK |
| 错误黑色背景填充 | residue / `background_inconsistency` | BLOCK |

真实 Cleaner 三条 PASS 与上述合成 controls 严格分开记录：controls 仅证明 Gate 的故障检测，不构成真实 Cleaner 成功证据。

## 人工审查与审计

人工 FORM：`data/local/mvp1-visual-contract-spike-d-v0.1/run-v0.5/FORM.md`。它复用 `run-v0.3` 的人工结论，因为 v0.5 和 v0.3 的三条 source、所有核心 mask、cleaned output、诊断图与自动 decision 的 SHA-256 全等；v0.5 只新增 background seam evidence 并修正 PASS 不生成伪 QualityIssue draft。三条图片均人工 PASS，Overall 为 `PASS_WITH_LIMITS`。

独立只读审计：`reviews/final-evidence-review.md`。审计确认：未把 controls 当作真实输出成功；无 mask 外写回或 protected/uncertainty/boundary 损伤；未发现固定样本的 residue/background false negative、oracle decision 泄漏、字段语义污染，且人工与自动结果一致。

## 已知限制与下一步边界

- `visible-support` 仍是 Spike C 的启发式候选，只在固定样本得到人工覆盖确认。
- 单色中位数填充与 seam 指标不适用于纹理、渐变、网点、发光/阴影艺术字、自由拟声词或背景文字。
- 本轮不证明 Cleaning eligibility、页面覆盖率、接触簇以外对象或整页质量；更不证明自动接受。

因此可进入的仅是带 guard 的 single-page Cleaning vertical slice：沿用 complete/safe/instance binding、保留 QualityIssue evidence、局部失败安全回退原图；不得扩大为全页、Batch 或 `AUTO_ACCEPT`。

## 验证

```text
/home/selflo/miniconda3/bin/python -m pytest -q \
  tests/unit/test_mvp1_visual_contract_spike_a.py \
  tests/unit/test_mvp1_visual_contract_spike_b.py \
  tests/unit/test_mvp1_visual_contract_spike_c.py \
  tests/unit/test_mvp1_visual_contract_spike_d.py

32 passed
```

`git diff --check` 通过。未运行完整仓库 pytest：其会收集 `data/local/vendor/yolo-world` 的第三方测试，并缺少该 vendor 的可选依赖；该路径与本 Spike 无关。
