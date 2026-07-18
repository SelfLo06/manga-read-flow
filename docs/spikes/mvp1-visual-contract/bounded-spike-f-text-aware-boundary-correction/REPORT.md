# MVP-1 Visual Contract Bounded Correction Slice F — 实现报告

状态：`ACCEPTED_BOUNDED_CORRECTION`

## 自动结论

```text
FORMAL_PAGE = case-71
G002_S02_TEXT_AWARE_CORRECTION = AUTOMATION_PASS
G002_CONTACT_CLUSTER_CLEANING = PASS
CASE_71_FULL_PAGE_CLEANING = NOT_ACHIEVED
ACTIVE_CLEANED_POINTER = NOT_UPDATED
COMBINED_CODE_HEALTH_REVIEW = PENDING
```

冻结 artifact 是本轮事实来源。旧 Spike E 文本中的 `6` 与当前 hash-lock artifact 不一致；本轮按用户裁决使用实际 `23` 个 unsafe required pixels，且未修改旧 run 或旧报告。

## 有界 correction

- 仅处理 `case-71 / g002 / s02`；`s01` 只重验，不重做清字。
- 输入绑定：旧两实例、required support、protected、uncertainty、source SHA-256。
- 仅在旧 virtual-boundary uncertainty 周围的 `6px` corridor 内处理。
- `required support + 1px guard` 为 virtual boundary 的不可穿越区；`1px` 是该样本唯一不触及 protected structure 的最小固定 guard。`2px` 控制输入保持 block。
- safe-edit 从新 instance/protected/virtual-boundary/uncertainty 重新派生，不从 required support 膨胀；实例 identity、assignment 与像素互斥保持不变。
- correction budget：`ordinal=1`，`budget_after=0`；ordinal 2 被单元测试拒绝。

## 自动证据

本地 run：`data/local/mvp1-single-page-cleaning-correction-v0.1/case-71-g002-s02-run-v0.1/`

- unsafe required：`23 → 0`；
- instance overlap：`0`；
- g002/s02 实际 Cleaner 写回：`7,863` pixels；
- g002/s02 通过正式 `SinglePageCleaningService`，但因其余四个实例仍 `OUT_OF_SLICE`，决策为 `block`，`active_cleaned_artifact_id=null`；
- g002/s01 使用新 instance revision 重跑独立 validator：residue/outside-safe/protected/uncertainty/boundary damage 均为 `0`；
- 原图 SHA-256 前后：`95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb`；
- combined candidate 仅组合 g002/s01 既有候选与本轮 s02 实际变化；其他四个实例没有被写入。

## 人工 Gate

`data/local/mvp1-single-page-cleaning-correction-v0.1/case-71-g002-s02-run-v0.1/FORM.md` 已填写：

```text
PASS_TEXT_AWARE_BOUNDARY
PASS_REQUIRED_COVERAGE
PASS_LOCAL_CLEANING
PASS_INSTANCE_ISOLATION
ACCEPT_BOUNDED_CORRECTION
```

人工确认内部斜向分界没有损伤可见气泡轮廓、连接区域或周边结构；s02 无可辨残字、halo 或漏清，s01 未退化且无跨实例污染。该接受仅覆盖 g002 contact cluster。

## 验证

```text
python -m pytest -q tests/unit/test_text_aware_boundary.py \
  tests/integration/test_single_page_cleaning_slice.py \
  tests/unit/test_mvp1_visual_contract_spike_b.py \
  tests/unit/test_mvp1_visual_contract_spike_c.py \
  tests/unit/test_mvp1_visual_contract_spike_d.py
# 27 passed
```

```text
python -m pytest -q tests/integration/test_single_page_cleaning_slice.py \
  tests/integration/test_project_store_init.py \
  tests/integration/test_import_and_artifactservice.py \
  tests/integration/test_repository_uow_core.py \
  tests/integration/test_workflow_happy_path.py \
  tests/integration/test_fakeprovider_stageexecutor.py \
  tests/integration/test_quality_issues_and_readiness.py \
  tests/unit/test_mvp1_visual_contract_spike_d.py \
  tests/unit/test_text_aware_boundary.py \
  tests/unit/test_mvp1_visual_contract_spike_b.py \
  tests/unit/test_mvp1_visual_contract_spike_c.py
# 90 passed
```

完整 pytest 未作为本轮通过声明：它仍受既有同名 `test_core.py`、缺少 `psutil` 与 Goal 2 frozen harness hash mismatch 阻塞。

## 限制

这不是整页完成、E2/E3 推广、通用气泡分割或自动接受。旧 blocking issue 的原始审计证据仍在旧 run；本独立 run 以新的 page-scope incomplete issue 保持 page block。人工 Gate 必须确认本地视觉效果、边界与实例隔离。
