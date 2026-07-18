# Slice 3 Report——Correction Checkpoint A

## 状态

`SLICE_3 = IN_PROGRESS`。本报告记录 eligibility 与 runner 接线修正；它不是最终 Slice 3 报告，不构成 case-72 人工 Gate 或最终提交。

## 已完成

- case-71 已保持其既有正式 acceptance；本轮没有打开其数据库、改写其 run 或更新其 active pointer。
- 新增版本化 `FullPageEligibilityDecision` 接口。输入包含 target class、历史 classifier signal、required/safe/protected/uncertainty 像素计数、support completeness、实例/segment revision、evidence revision、policy/profile/config identity；输出 eligibility、reason、policy/decision version、evidence summary 与 dependency fingerprint。
- runner 不再把历史 `candidate_risk` 直接映射为最终 disposition。历史 E3 且当前 required=safe、required∩protected=0、required∩uncertainty=0 时，结论为 `REVIEW/pixel_level_evidence_requires_review`，不是 E1。
- target class 从 frozen visual contract 的正式 assessment reason codes 派生：普通对白、sign/scene review、SFX/free text 不再统一写为 `ordinary_dialogue`。
- eligibility decision 通过 visual-contract evidence artifact 和 blocker evidence artifact 持久化；无 schema/migration 修改。

## Case-72 Checkpoint run

权威 checkpoint 输出：`data/local/mvp1-full-page-cleaning-v0.1/slice-3/run-v0.5/case-72/`。

| 项 | 结果 |
| --- | --- |
| PageCleaningRun | `run::case-72::e624cf03-5b07-4be0-a1ba-b2d1ee088e2f` |
| source hash | `6518cbe64699a9d6e878c066d828babbcf48c6d7b26332b72408bc692a3069c9` |
| inventory | 8；silent omission=0 |
| candidate | `candidate-full-page-cc97a726-523e-45ea-a426-f5cfd1e64721`，`official_unselected` |
| candidate hash | `59166b28d5978f1cd43b4a0643c8008212e6c0819cc1c3b1e5e6a5cf61f0f0e0` |
| validation | `fail`；block transaction=`BLOCKED` |
| active pointer | `NULL` |
| Cleaner / validated results | 仅 g001=5,089 changed、g006=2,716 changed |
| recovery | candidate=`official_unselected`、validation=`fail`，可重建 block 事实 |

g003 现在是 `REVIEW` + `INCOMPLETE_REVIEW/pixel_level_evidence_requires_review`：未调用 Cleaner、不是 candidate member、不是 `UNSUPPORTED_E3`。g002/g004 分别保留 710/70 unsafe required 的 `BLOCKED_UNSAFE_REQUIRED/physical_boundary_capability_requires_review`。g005 为 `sign_or_scene_text_review`，g007/s01、g007/s02 为 `sfx_or_free_text`，均保守阻塞且无 silent omission。

本 checkpoint 未生成新的 case-72 FORM，未接受 candidate，未更新 pointer。先前 `run-v0.4` 因自动生成了不应存在的 checkpoint FORM 而未作为权威 evidence；其内容未被覆盖或提交。

## 验证

- Slice 1 foundation、Slice 2 migration/acceptance/composition/stale、Spike E/F 定向、eligibility、harness 与真实 runner seam 聚焦回归：`66 passed`。
- 完整 integration suite：`122 passed`。
- 最宽 unit suite：`234 passed, 2 failed`；失败均与本 Slice 无关：环境缺少 `skimage` 的 Goal-7 watershed 测试，以及冻结 Goal-2 harness hash 与本地已冻结 lock 不匹配。它们未被写为本 Slice PASS。
- changed-file Ruff：环境未安装 `ruff`，记录为 `ENVIRONMENT_LIMITED`；`py_compile` 已通过。
- review-material lock 的每个受锁文件均通过 `sha256sum -c`。
- 真实 seam 覆盖 g003 review regression、真实 pixel E3、正式 target class、g002/g004 不调用 virtual-boundary correction、case-id 无关的 policy decision，以及 checkpoint 不生成 case-72 FORM。

本阶段尚未裁决最终 Slice 3 Gate。

## 后续

必须先执行 [Physical Bubble Boundary Spike 交接](../../diagnostics/physical-bubble-boundary-spike-handoff-v0.1.md)。仅当其 Gate=`GO`，才可回到本 Slice 处理 g002/g004、创建新的 case-72 run 和人工 FORM。
