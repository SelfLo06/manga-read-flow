# Case-72 Full-page Cleaning Generalization Diagnosis v0.1

## 1. Executive summary

本报告只读分析 Slice 3 `case-72` 的既有 `run-v0.3`。未启动 Cleaner、Composer、acceptance 或新的 Spike；未修改数据库、FORM、REPORT、GATE、现有运行产物或实现。

结论为 **DIAGNOSIS_D（混合问题）**：

- `g003` 是已确认的 eligibility false negative。当前 runner 没有执行 Spike B 要求的 text-mask / protected / uncertainty 判定，而是读取并广播 Spike A 的旧 `candidate_risk=E3`。这属于 `RUNNER_INTEGRATION_BUG`、`ELIGIBILITY_RULE_REGRESSION` 和 `DESIGN_TO_IMPLEMENTATION_GAP`。正确的近期落点是 `REVIEW`，不是自动 E1：Spike B 仍明确禁止将其提升为可实际 Cleaning。
- `g002`、`g004` 的 blocker 不是 silent omission，也不是 Cleaner/validator 失败。它们在 Cleaner 前因 `support_completeness=INCOMPLETE_REVIEW` 被阻止。两者 100% unsafe support 都位于真实 BubbleInstance 的 protected/uncertainty boundary corridor；现有 Slice F planner 只修正**两个相邻实例之间的虚拟边界**，两目标均无该输入条件。因此“未调用 Slice F”是事实，但不是已实现通用 correction 的 wiring bug。当前批准的算法能力不覆盖它们；是否存在安全的通用修正，现有材料不能证明，需另立有界 Spike。
- `g001/g006` 的 E1 清字、独立 validator、candidate membership 均正确。其余 6 个 target 全部有 durable disposition/issue，故没有 silent omission。page validator、block transaction、`official_unselected` candidate 和 `active pointer=NULL` 都忠实执行了当前 ledger，安全阻塞正确。

```text
LEDGER_CORRECT = YES
SAFETY_BLOCK_CORRECT = YES
GENERALIZATION_QUALITY_ACCEPTABLE = NO
SLICE_3_CAN_PASS_AS_IS = NO
CURRENT_SLICE_3_FIX_POSSIBLE = PARTIAL
NEW_ALGORITHM_SPIKE_REQUIRED = ONLY_FOR_SPECIFIC_TARGETS

FINAL_CLASSIFICATION = DIAGNOSIS_D
```

这里的 `LEDGER_CORRECT=YES` 指 durable facts、唯一归属、candidate/validation/block 关系正确记录实际执行结果；不表示 `g003=E3` 的业务分类正确。

## 2. Scope 与限制

- 诊断对象仅为既有 case-72 Slice 3 `run-v0.3`。
- 优先级依次为 project.db durable facts、hash-locked JSON/mask/artifact、WorkflowAttempt/ToolRunLog、源码调用链；stdout/stderr 未作为业务事实来源。
- 所有 review-material lock 项均以 `sha256sum -c` 验证为 `OK`。
- `FORM.md` 保持空白；报告不构成 Human Gate，也不改变 `BLOCKED_WITH_COMPLETE_LEDGER` 语义。
- “unsafe 是否确为可安全编辑的抗锯齿像素”没有像素 GT 或新的受控运行，均按 `NOT_PROVABLE_FROM_CURRENT_EVIDENCE` 处理。

## 3. Preflight：branch、HEAD 与 dirty state

| 项 | 值 |
| --- | --- |
| branch | `main` |
| HEAD | `a943ee96f4bc168fbf3d4cb9691d0608fc184b1d` (`a943ee9 docs(cleaning): record Linux full integration pass`) |
| preflight `git diff --check` | 无输出，PASS |
| preflight dirty state | 3 个未跟踪文件，均未触碰：`src/manga_read_flow/application/full_page_cleaning_harness.py`、`tests/integration/test_full_page_cleaning_harness.py`、`tools/mvp1/run_full_page_cleaning_slice3.py` |

注意：Slice 3 runner/harness 本身是未跟踪工作区文件，不属于 HEAD。它们是本次既有 run 的实际源码证据，但不应被误称为已提交产品基线。

## 4. Current run identity 与路径

| 项 | 值 |
| --- | --- |
| run 根目录 | `data/local/mvp1-full-page-cleaning-v0.1/slice-3/run-v0.3/case-72/` |
| Project DB | `workspace/projects/77176b56-6cb1-47b9-8fa6-aad59cd34705/project.db` |
| summary | `summary.json` |
| review lock | `review-material-lock.json` |
| visual contract evidence | `work/visual-contract-evidence.json` |
| FORM | `FORM.md`（未填写） |
| PageCleaningRun | `run::case-72::bb33ac2c-97f6-4029-95d4-917f563c5fd2` |
| combined candidate | `candidate-full-page-db9b41d7-f24b-4280-b844-0353fc764a8b` |
| PageCleaningValidation | `validation-full-page-81af9d9d-514f-4b1e-96d8-6de3a3b11327` |
| WorkflowDecision | `decision::case-72::block` |
| config hash | `662c628133eaaafe71845b9b45152324f96ca59336c8161bbad314fd0bf02da8` |
| correction chain / reservation | 均不存在（两表 0 rows） |

run 的 `source_hash=6518cbe...3069c9`、所有 relevant artifact hash、current visual-contract revision 和 dependency fingerprint 均无 stale 标记。

## 5. Inspected evidence

已读取并交叉核对：

- 当前 `summary.json`、review lock、visual-contract evidence、FORM、6 个 disposition JSON；
- 原图、combined candidate、side-by-side、absolute diff、actual-changed overlay；所有 8 个 target 的 original/candidate/required-change/evidence crop；
- 8 个 target 的 instance/visible(required)/safe/protected/uncertainty mask；
- 两个 Cleaner evidence、两个 independent validator evidence、对应 artifact metadata；
- PageCleaningRun、inventory、result、disposition、QualityIssue/relations、candidate/member、validation、decision、WorkflowAttempt、ToolRunLog、active pointer、correction tables；
- Spike A/B/C/D/E/F 的正式 GOAL/HARNESS/REPORT/GATE，full-page ledger detailed design/HARNESS，Slice 1/2/3 文档；
- Spike A/B classifier/evidence 函数、Slice F planner、Slice 3 runner/harness、full-page composition/validation 源码及其 focused tests。

历史基线的关键材料为：Spike A `run-v0.4/visual-contract-snapshot.json`（threshold `mvp1-spike-a-topology-eligibility-v1`）和 Spike B `run-v0.7/pixel-evidence-snapshot.json`。

## 6. Durable ledger summary

| # | target | eligibility / support | durable final fact | blocking |
| ---: | --- | --- | --- | --- |
| 1 | g001 | E1 / COMPLETE | validated instance result，candidate member | 否 |
| 2 | g002 | E1 / INCOMPLETE_REVIEW | `BLOCKED_UNSAFE_REQUIRED` / `required_text_not_safely_editable` | 是 |
| 3 | g003 | E3 / COMPLETE | `UNSUPPORTED_E3` / `visual_contract_e3` | 是 |
| 4 | g004 | E1 / INCOMPLETE_REVIEW | `BLOCKED_UNSAFE_REQUIRED` / `required_text_not_safely_editable` | 是 |
| 5 | g005 | REVIEW / INCOMPLETE_REVIEW | `BLOCKED_UNSAFE_REQUIRED` | 是 |
| 6 | g006 | E1 / COMPLETE | validated instance result，candidate member | 否 |
| 7 | g007/s01 | REVIEW / COMPLETE | `INCOMPLETE_REVIEW` / historical exclusion | 是 |
| 8 | g007/s02 | REVIEW / COMPLETE | `INCOMPLETE_REVIEW` / historical exclusion | 是 |

所有 inventory row 恰有一个成员归属或 current disposition；`missing_attribution_count=0`、`duplicate_attribution_count=0`，因此 **silent omission=0**。6 条 blocking QualityIssue 分别与 run 和对应 inventory item 建立关系，并由 block decision 的 `decided_by` relation 收口。

## 7. Candidate、validation 与 block

- candidate 是同一 original 的确定性组合，只含 g001、g006 两个 validated result；status=`official_unselected`，两个 member 都是 `proposed`。
- page validation 的所有像素安全谓词均为 0 / true：pairwise overlap、wrong-instance write、outside-safe、protected、uncertainty、boundary damage、residue 均为 0；combined delta=member union，source/combined integrity 与 freshness 也都通过。
- `inventory_complete=true`，但 `dispositions_unique=false` 的准确语义是 `validate_full_page_cleaning()` 把**blocking disposition**视为不可接受的 prospective final pass（`full_page.py:169-190`），不是 row 重复。故 validation=`fail` 正确。
- `block_page_cleaning_atomically()` 写入 `decision::case-72::block`，run status=`blocked`，page status=`review_required`，`active_cleaned_artifact_id=NULL`。这与 ledger/acceptance contract 一致。

## 8. g002 diagnosis

### 8.1 当前事实链

| 字段 | 值 |
| --- | --- |
| segment / revision | `case-72__g002__s01` / `::slice3-v1` |
| instance / revision | `instance::ee0be8d915b46b599bb8` / `instance-revision::ebc77b36d3ed026384b3::slice3-v1` |
| current eligibility | E1 |
| historical → Spike A candidate | `E3::SKIP` → E1；old overlap `4/10453=0.038267%`，background mean/std `244.736725/2.203342` |
| support completeness | INCOMPLETE_REVIEW |
| reason / disposition | `required_text_not_safely_editable` / `BLOCKED_UNSAFE_REQUIRED` |
| QualityIssue | `issue-full-page-cleaning-801c12a8-dbec-4b9b-84b9-f3feeeb12b77`，open/blocking |
| dependency fingerprint | `d756f400...7e82b` |
| evidence/policy | dark-core luminance `<=180`、visible dilation=2px、boundary band=4px；Slice 3 config hash 如 §4 |

### 8.2 Pixel evidence

| 指标 | 值 |
| --- | ---: |
| required / safe / required∩safe | 15,802 / 15,092 / 15,092 |
| unsafe required / ratio | 710 / 4.493102% |
| required∩protected | 103 |
| required∩uncertainty | 710 |
| unsafe∩protected | 103 |
| unsafe∩uncertainty-only | 607 |
| unsafe outside protected∪uncertainty | 0 |
| connected components / max | 10 / 275 px（sizes: 275,247,51,39,30,26,20,10,10,2） |
| unsafe→instance boundary distance (min/p25/p50/p75/p95/max) | 0/1/3/4/5/5.6 px |
| unsafe→protected distance（同分布） | 0/1/3/4/5/5.6 px |
| in 4px/6px boundary corridor | 710/710（100%） |

unsafe 不分散在正文中心；它们完全落在真实物理 bubble boundary 的保守带。`visible` 是 `dilate(text_core,2) ∩ instance`，因此这证明这些像素来自该候选 support 的形态学生长与边界带冲突；但不能据此证明每个 unsafe 像素都是可安全删除的文字抗锯齿，结论为 `NOT_PROVABLE_FROM_CURRENT_EVIDENCE`。

### 8.3 Correction routing

没有 correction eligibility 评估记录、CorrectionChain、reservation、replay、planner 调用或异常降级。Cleaner/validator attempt 仅对应 g001/g006。

直接原因：runner `_build_targets()` 仅在 `case_id == "case-71"` 时构造 correction（`tools/mvp1/run_full_page_cleaning_slice3.py:157-165`）。随后 g002 因 COMPLETE=false 进入 `_record_blocking_target()`；harness 的 `is_composition_eligible` guard 是 `eligibility == E1 and support_completeness == COMPLETE`（`full_page_cleaning_harness.py:67-69,201-211`）。

这不是可直接复用 Slice F planner 的漏接线：`correct_text_aware_virtual_boundary()` 要求 mutually exclusive primary/neighbor instances、current virtual boundary、及只在该虚拟分界 corridor 内移动 uncertainty；g002 是单 segment、单实例的真实物理边界保护，不存在相邻 instance / virtual separator。将 physical `protected` 冒充 virtual boundary 会触发 `guard_conflicts_visible_or_protected` 或违反该 planner 的语义。

```text
G002_ROOT_CAUSE = EVIDENCE_CONSTRUCTION_TOO_CONSERVATIVE + CURRENT_CAPABILITY_SCOPE_LIMIT
G002_CORRECTION_ROUTING = NOT_ROUTED; EXISTING_SLICE_F_GUARD_NOT_SATISFIED
G002_REAL_CAPABILITY_LIMIT = YES
```

此处 YES 仅指当前已批准能力；不是“任何通用算法都不可能安全处理”的断言。

## 9. g003 diagnosis（最高优先级）

### 9.1 完整 eligibility 决策链

| 维度 | 历史 / 当前值 |
| --- | --- |
| historical classification | `E3::SKIP` |
| Spike A automatic | E3；`R_PROTECTED_OVERLAP_RATIO=112/650=17.230769% > 5%` |
| Spike A human decision | `FALSE_NEGATIVE`：普通白色气泡、文字位于内部，不能把实例邻近关系广播为整体 E3 |
| Spike B mandatory regression | actual required=909、safe=909、protected overlap=0、uncertainty overlap=0；status `REVIEW_ONLY_G003` |
| current automatic | E3 / COMPLETE / `UNSUPPORTED_E3` |
| instance area | 9,188 px，area ratio=0.00388637 |
| background mean / variance proxy | mean=239.231857，std=2.078966，sample=790 |
| grounding | center inside；bbox overlap=0.97754386 |
| current actual text∩protected / uncertainty | 0 / 0 |
| current required support completeness / safe-edit completeness | COMPLETE / 909 of 909 |
| current reason / disposition creator | `visual_contract_e3` / `_build_targets()` then `_record_blocking_target()` |
| classifier/policy version | source snapshot threshold `mvp1-spike-a-topology-eligibility-v1`; runner stores no separate classifier policy version，only config hash in §4 |

`Spike A` 的 `assess_instance()` 使用历史 `core_protected_overlap_pixels/core_pixels`（`spike_a.py:291-298,323-327,360-363`）。Spike B 的 `build_safe_edit_evidence()` 明确规定 `decision_basis=PIXEL_INTERSECTION_NOT_INSTANCE_RATIO`（`spike_b.py:98-123`），且 B GOAL/GATE 明定 g003 不得再因 instance-level ratio 静默 E3。

但 Slice 3 runner 不是调用当前 classifier：它从 frozen Pixel Snapshot 取 `eligibility_snapshot.candidate_risk`（runner `:149-155`），只重新算 required completeness；之后直接把 `risk` 映射成 `eligibility`（`:169-179`）。因此 g003 的 COMPLETE pixel evidence 没有参与 eligibility，旧 E3 被原样写入 visual contract、inventory、disposition 和 issue。

```text
HISTORICAL_HUMAN_DECISION = FALSE_NEGATIVE; prohibit instance-level ratio as final E3
CURRENT_AUTOMATIC_DECISION = E3 / UNSUPPORTED_E3
CURRENT_RULE_PATH = Spike B snapshot.eligibility_snapshot.candidate_risk
                    -> runner _build_targets risk mapping
                    -> _record_blocking_target
DIVERGENCE_POINT = no text-mask/protected/uncertainty eligibility decision is invoked
```

没有 revision/hash mismatch：source hash 与 Spike B record 相同；current masks 还重现了 B 的 909/909/0 计数。故这不是 stale artifact reuse。也没有 default exception/fallback：代码为确定性风险映射，两个 ToolRunLog 仅为 g001/g006 success。

`g003` 尚不能被称为 E1 或候选 Cleaner 成功：Spike B 的正式结论仍是 `REVIEW_ONLY_G003`，且 RequiredTextEvidence 是 candidate，不是完整可见字形 GT。正确近期行为应是保留 source、明确 review/block，不能是 `UNSUPPORTED_E3`。

```text
G003_FALSE_NEGATIVE_CONFIRMED = YES
G003_ROOT_CAUSE = RUNNER_WIRING
```

## 10. g004 diagnosis

### 10.1 当前事实链

| 字段 | 值 |
| --- | --- |
| segment / revision | `case-72__g004__s01` / `::slice3-v1` |
| instance / revision | `instance::dba2d44b5f3db67bc083` / `instance-revision::e20d53321f61034ce12e::slice3-v1` |
| eligibility | E1（history 与 Spike A 一致） |
| history evidence | mean/std=244.228226/1.495235，instance=54,211 px，protected ratio=0 |
| support / reason / disposition | INCOMPLETE_REVIEW / `required_text_not_safely_editable` / `BLOCKED_UNSAFE_REQUIRED` |
| QualityIssue | `issue-full-page-cleaning-f543fb20-0bbd-4863-b846-ec6a5f2bb262` |
| dependency fingerprint | `c6591248...e7bc4e` |

### 10.2 Pixel evidence

| 指标 | 值 |
| --- | ---: |
| required / safe / required∩safe | 13,133 / 13,063 / 13,063 |
| unsafe required / ratio | 70 / 0.533008% |
| required∩protected / uncertainty | 34 / 70 |
| unsafe∩protected / uncertainty-only | 34 / 36 |
| unsafe outside protected∪uncertainty | 0 |
| connected components / max | 2 / 45 px（45、25） |
| unsafe→boundary min/p25/p50/p75/p95/max | 0/0/1/1.4/2.197/2.8 px |
| unsafe→protected（同分布） | 0/0/1/1.4/2.197/2.8 px |
| in 4px/6px boundary corridor | 70/70（100%） |

70 px 的确只落在 narrow corridor：34 px 和 protected 重合，余下 36 px 仅在 uncertainty；并非正文中心的分散遗漏。它们属于 `dilate(text_core,2)` 所形成的 visible-support candidate，但现有 artifact 不能证明其逐像素为文字抗锯齿边缘，也不能证明删除不会损伤真实 bubble outline：`NOT_PROVABLE_FROM_CURRENT_EVIDENCE`。

### 10.3 Correction routing

g004 与 g002 相同：无 correction record/reservation/planner/attempt，且 COMPLETE=false 先被 composition guard 阻止。它是单实例、单 segment、独立 cluster，不具备 Slice F 的相邻实例和 virtual boundary。Slice F 的 rule 也明确禁止移动 `visible/protected` 像素，g004 有 34 required pixels 与真实 protected 重合，故其并不满足 Slice F 的 generic preconditions。

```text
G004_ROOT_CAUSE = EVIDENCE_CONSTRUCTION_TOO_CONSERVATIVE + CURRENT_CAPABILITY_SCOPE_LIMIT
G004_CORRECTION_ROUTING = NOT_ROUTED; EXISTING_SLICE_F_GUARD_NOT_SATISFIED
G004_REAL_CAPABILITY_LIMIT = YES
```

## 11. Other targets

| target | current state | historical/formal scope check | conclusion |
| --- | --- | --- | --- |
| g001 | E1/COMPLETE；5089 changed；validator all safety flags false；member | Spike D real-cleaner PASS sample | 执行正确，无 omission/case-specific evidence |
| g005 | REVIEW/INCOMPLETE；963 unsafe；block | visual crop 是场景内小矩形标牌/文字区域，历史 `E2::E2_COMPARISON_ONLY`，并非已证实普通对白 | 保留原文符合 review；runner 把所有 target 固定为 `ordinary_dialogue`，因此是否可非阻塞 scope exclusion 为 `NOT_PROVABLE_FROM_CURRENT_EVIDENCE` |
| g006 | E1/COMPLETE；2716 changed；validator all safety flags false；member | Spike D real-cleaner PASS sample | 执行正确，无 omission/case-specific evidence |
| g007/s01,s02 | REVIEW/COMPLETE；无 Cleaner；explicit review issue | Spike A: 同一自由 SFX/free-text instance；history `E2::E2_COMPARISON_ONLY` | 原文保留符合 MVP-1 exclusions；当前 profile 未提供可验证的 non-blocking unsupported policy，所以 block 仍是保守正确 |

`g005/g007` 的 historical missing pixel ledger 已被明确表达为 reason/evidence；没有被静默丢弃。运行时确有过宽 target class（runner `:201` 固定 `ordinary_dialogue`），这是未来 policy plumbing 风险，不改变此次安全 block 的正确性。

## 12. Correction routing trace

```text
_prepare
  -> _build_targets
       -> Spike B text_core / visible / boundary_and_uncertainty / safe / completeness
       -> only if case-71: correct_text_aware_virtual_boundary + correction metadata
       -> g002/g004: COMPLETE=false -> formal blocker target
  -> FullPageCleaningHarnessService.prepare
       -> before_execution(reserve_correction) [no-op for case-72]
       -> !is_composition_eligible -> _record_blocking_target
       -> E1+COMPLETE only -> StageExecutor -> Cleaner -> validator
```

`cleaning_correction_chains` 与 `cleaning_correction_reservations` 为 0 row，说明没有 reservation 被拒绝、replay 或异常吞掉；是未被构造。Slice F 的 `correct_text_aware_virtual_boundary()`（`quality/text_aware_boundary.py:46-123`）的 hard guards 是 ordinal=1、两 instance 互斥、required 位于 primary、guarded required 不与 visible/protected 冲突、且只在 virtual-boundary/uncertainty corridor 更新。g002/g004 不满足该模型，不可把 `if case_id == case-71` 的现状泛化为“应无条件调用 planner”。

## 13. Eligibility decision trace

```text
Spike A old classifier
  historical core-protected ratio > 5% -> g003 E3

Spike B formal regression
  actual text/protected=0; actual text/uncertainty=0; safe=required=909
  -> REVIEW_ONLY_G003, not actual-cleaning approval

Slice 3 actual runner
  pixel snapshot eligibility_snapshot.candidate_risk (= old E3)
  -> E3 -> UNSUPPORTED_E3
```

这条 path 违反 Spike A Gate 与 Spike B GOAL 所冻结的“不得用 instance-level protected overlap 作为 g003 或同类最终整体 E3”要求。历史人工裁决不只是对话记忆：它存在于 Spike A REPORT/GATE，且 Pixel-level replacement 规则与数据存在于 Spike B GOAL/HARNESS/REPORT/GATE 和 `spike_b.py`；缺失的是 runner 的正式接线。

## 14. Code path trace

| 职责 | 实际函数 / 文件 |
| --- | --- |
| Slice 3 entry | `_prepare`, `_build_targets`, `reserve_correction` — `tools/mvp1/run_full_page_cleaning_slice3.py` |
| visual contract builder/persist | `FullPageCleaningHarnessService._register_visual_contract` — `application/full_page_cleaning_harness.py` |
| historical classifier | `assess_instance` — `tools/spikes/mvp1_visual_contract/spike_a.py` |
| pixel evidence | `text_core_from_bbox`, `expand_visible_text_support`, `boundary_and_uncertainty`, `evaluate_required_text_completeness` — `spike_b.py` |
| safe-edit | `build_safe_edit_evidence` — `spike_b.py` |
| correction planner | `correct_text_aware_virtual_boundary` — `quality/text_aware_boundary.py` |
| reservation | `reserve_or_replay_cleaning_correction`, `mark_cleaning_correction_executing`, `complete_cleaning_correction` — runner + ledger UoW |
| Cleaner | `FullPageCleaningHarnessService._execute_target` -> `StageExecutor.execute` -> `BorderSampledFillCleanerProvider` |
| instance validator | `validate_cleaning_output` — `quality/cleaning_validation.py` |
| disposition/issue | `_record_blocking_target` — harness `:575-626` |
| candidate/member & page validator | `FullPageCleaningPreparationService.prepare` -> `compose_full_page_cleaning` / `validate_full_page_cleaning` |
| atomic block | `block_page_cleaning_atomically` — acceptance UoW |

g002/g004 actual path terminates at `is_composition_eligible` and `_record_blocking_target`; g003 follows the same path due E3; g001/g006 alone reach cleaner and validator. Focused integration test only injects preclassified targets (`test_full_page_cleaning_harness.py:_target`) and asserts an E3 blocker; it never exercises runner `_build_targets()` or g003 regression. Thus test path and current runner policy path are materially disconnected.

## 15. Hypothesis matrix

| Hypothesis | Status | Evidence / counterevidence / implication |
| --- | --- | --- |
| H1 g003 eligibility rule regression | CONFIRMED | Current E3 comes from old candidate risk; B actual intersection is 0/0 and B forbids that E3 rationale. Implies g003 must not be represented as unsupported E3. |
| H2 g003 correction only in docs | REJECTED | It is in formal A/B GOAL/GATE/REPORT and `spike_b.py`; however not wired into runner. Implies implementation/productization gap, not documentation-only gap. |
| H3 g002/g004 correction wiring missing | REJECTED as root cause | No call exists, but existing Slice F only supports virtual shared boundary and its guards do not fit these single physical-boundary targets. |
| H4 g002/g004 fail correction guard | CONFIRMED | no neighbor/virtual separator; unsafe intersects real protected pixels (103/34) and uncertainty. Implies current planner must not be invoked. |
| H5 safe-edit too conservative | INCONCLUSIVE | 100% unsafe lies in boundary corridor, consistent with conservatism; support is itself candidate and no GT proves safety of the excluded pixels. |
| H6 revision/fingerprint mismatch | REJECTED | source hash/mask counts match B; current DB has no stale field. The error is semantic rule selection, not stale identity. |
| H7 real algorithm capability gap | CONFIRMED for current approved capability | existing safe-only cleaner and Slice F cannot handle g002/g004; intrinsic solvability remains unproven. |

## 16. Root-cause classification

| Classification | affected targets | severity / Slice 3 block | repair / Spike |
| --- | --- | --- | --- |
| `RUNNER_INTEGRATION_BUG` | g003 | high; semantic eligibility corruption, currently blocks | code fix in Slice 3 |
| `ELIGIBILITY_RULE_REGRESSION` | g003 | high; false unsupported classification | existing-rule integration, no new algorithm |
| `DESIGN_TO_IMPLEMENTATION_GAP` | g003; tests | high; formal regression absent from real runner | code + focused tests |
| `EVIDENCE_CONSTRUCTION_TOO_CONSERVATIVE` | g002,g004 (hypothesis only) | medium/high; produces blockers | needs proof, not threshold relaxation |
| `REAL_ALGORITHM_CAPABILITY_GAP` | g002,g004 | high; cannot finish supported ordinary dialogue | new bounded Spike required |
| `EXPECTED_MVP_SCOPE_LIMIT` | g007; likely g005 | low/medium; source preserved | policy classification plumbing, not unsafe bypass |
| `INSUFFICIENT_EVIDENCE` | exact anti-alias/safe removability for g002,g004; whether g005 can be non-blocking | explicit | obtain new formal evidence, not guess |

## 17. Safety behavior assessment

安全行为是正确的：unsafe required 不会因少量像素、候选图存在或 Cleaner 未报错而通过；g002/g004 没有触发 Cleaner；g003 没有因 pixel completeness 被误自动清字；g001/g006 的 actual writes 均没有 protected/uncertainty/outside-safe/boundary/residue violations；最终 pointer 未更新。没有发现异常捕获后把错误隐藏为 block，也没有 provider refusal。

## 18. Generalization quality assessment

不合格。8 条可解释 ledger 表明“可审计、安全失败”已经泛化；但视觉产物只清除了 2/8 个 target，普通对白 g002/g004 未能处理，g003 被错误降格为 unsupported。它不是可用的完整全页清字结果，不能以 candidate 已生成或 all pixel safety counters=0 掩盖。

## 19. Slice 3 impact

- 当前 Slice 3 README 仍为 `NOT_STARTED`，而实际 runner/harness 是未跟踪文件；本次 run 不能成为已完成 Slice 3 的提交基线。
- case-72 保持 blocked；不得填 FORM、恢复 acceptance、更新 pointer 或重写 disposition。
- g003 可通过受控的现有规则/接线修复其 eligibility representation，但这一修复本身不授予真实 Cleaning。
- g002/g004 需要先有新的通用安全证据与明确 planner scope；不能将 4.49%/0.53% unsafe ratio 作为放宽门槛理由。

## 20. Minimal repair recommendations（不实施）

### A. Wiring / integration fix（当前 Slice 3 内）

1. 让 runner 使用一个版本化、可持久化的 eligibility decision interface；不得从 historical `candidate_risk` 直接映射 disposition。
2. 把 g003 的 pixel-level intersection 输出接入该 interface；在已有 Spike B 证据下输出 `REVIEW`/明确 reason，而不是 `UNSUPPORTED_E3`。
3. 添加 end-to-end focused test：同一 g003 pixel evidence 为 909/909、protected/uncertainty intersection=0 时，runner 不得写 E3；测试应调用 `_build_targets()` 或等价正式接口，而非手工注入 E3 target。
4. 显式持久化 classifier/policy version 与 evidence source revision，避免只保存 aggregate config hash。

### B. Existing-rule correction（当前 Slice 3 内，但仅 g003）

Spike A/B 已正式支持：以 actual text-mask 与 protected/uncertainty actual intersection 取代 instance-level protected-overlap broadcast。它只能把 g003 从错误 `UNSUPPORTED_E3` 改为正确 review 阶段，不得伪装为 E1 pass 或自动跑 Cleaner。

### C. New algorithm capability（不得伪装为 bug fix）

对 g002/g004 新立一个通用、非 case-id 的 physical-bubble-boundary evidence/correction Spike：先定义怎样区分真实可见 bubble outline 与 required text edge、何时可在物理 boundary corridor 重新构建 safe edit；保持 required evidence 不缩小、protected structure 不可写、single automatic reservation、独立 validator 与 source preservation。禁止坐标/target/page hard-code、阈值下调、手工修图或第二次自动 correction。

## 21. Whether a new Spike is required

```text
NEW_ALGORITHM_SPIKE_REQUIRED = ONLY_FOR_SPECIFIC_TARGETS
TARGETS = g002, g004
NOT_REQUIRED_FOR = g003 eligibility representation/routing
```

原因不是背景 inpainting 的失败，而是当前正式 planner 没有处理真实 physical boundary conflict 的输入/guard/验证合同。是否最终需要新的算法或仅新的通用 evidence derivation，必须由该 Spike 证明。

## 22. Unresolved facts

- `g002/g004` 的每一个 unsafe pixel 是否为可安全删除的文字抗锯齿/描边：`NOT_PROVABLE_FROM_CURRENT_EVIDENCE`。
- 在不写 protected physical boundary 的条件下，是否存在可通过 validator 的通用 correction：`NOT_PROVABLE_FROM_CURRENT_EVIDENCE`。
- g005 是否应由明确 profile 作为 non-blocking sign/review exclusion：`NOT_PROVABLE_FROM_CURRENT_EVIDENCE`；目前 runner 的 `ordinary_dialogue` 固定 target class 不能作该证明。
- g003 若改为 REVIEW 后，完整 RequiredTextEvidence 与真实 Cleaner 是否足以获得 E1 validated result：`NOT_PROVABLE_FROM_CURRENT_EVIDENCE`。

## 23. Final recommendation

维持现有 `BLOCKED_WITH_COMPLETE_LEDGER`，不接受 candidate、不更新 pointer。先在 Slice 3 以最小集成修复把 g003 的旧 E3 风险路径替换为已有的 pixel-level review rule，并加真实 runner seam 的测试；随后对 g002/g004 单独启动新的、通用 physical-boundary capability Spike。完成后才允许重新运行 case-72。不得引入 case-specific 分支、坐标、阈值下调、手工图像或 blocker 隐藏。
