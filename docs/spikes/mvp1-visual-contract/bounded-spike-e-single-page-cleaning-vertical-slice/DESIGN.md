# MVP-1 Visual Contract Bounded Spike E — Single-Page Cleaning Vertical Slice

状态：`IMPLEMENTED_WITH_BLOCKED_REVIEW`

正式切片页：`case-71`

## 1. 目标与范围

把 Spike D 已验证的 `border_sampled_fill` 接入正式单页工作流，且仅覆盖固定可信页面中的低风险、普通白色/浅色气泡。正式路径为：

```text
可信 page input
→ BubbleInstance / TextSegment revision
→ eligibility
→ CleanerProvider（临时输出）
→ ArtifactService（正式 artifact）
→ CleaningCheck（issue draft）
→ workflow decision transaction
→ active_cleaned_artifact 或 blocked/review
```

不实现 Typesetting、OCR/翻译改进、API/UI、Batch、复杂区域、全页覆盖率优化或多级 fallback。

正式切片只覆盖 `case-71` 的接触气泡簇 `g002`：

```text
case-71__g002__s01 -> COMPLETE / E1 / Spike D PASS
case-71__g002__s02 -> INCOMPLETE_REVIEW / required_text_not_safely_editable
```

它必须生成前者的真实候选并保留后者的阻塞证据。由于同页普通支持对象仍不完整，正式人工 Gate 预期为 `BLOCKED_REVIEW`，候选不得更新 `active_cleaned_artifact_id`。这不是 Cleaner 失败，也不宣称 case-71 已完成整页清字。

最终正式 run 与人工审查均符合该预期。`g002/s02` 的阻塞行为通过当前安全合同，但其 6 个 unsafe required-support 像素暴露了虚拟实例边界 / safe-edit derivation 的覆盖缺口；该缺口进入后续 bounded correction，不在本切片内放宽门禁。

## 2. 已确认约束

- 只有 ArtifactService 可将图片、mask 或 JSON evidence 变为正式 artifact；原图永不覆盖。
- Provider 只接收只读 artifact ref/path 与实例级 mask，输出 attempt temp files；不得访问 SQLite、登记 artifact、创建 QualityIssue 或决定状态。
- QualityCheckService 只分类和归因；WorkflowLoopEngine 决定 continue、一次 correction 或 block。
- 正式 integration 不可继续以 run-local manifest 作为 active relation 的事实来源；需要 SQLite relation/revision 与 migration。
- `active_cleaned_artifact_id` 是 Page 的唯一 selected cleaned output；候选 artifact 即使正式登记，在 decision 未 accept 前仍为 unselected。
- supported 范围内 incomplete/unsafe/无解释 exclusion 不能静默跳过；必须保留 disposition 和 evidence，并阻断本切片的 acceptance。

## 3. Schema review 与决策

### 3.1 现有能力

M0 已有 `pages.active_cleaned_artifact_id`、`processing_artifacts`、`workflow_attempts`、`workflow_decisions`、`quality_issues` 与原子 acceptance transaction。它不足以表达：实例 revision、segment 唯一归属、eligibility/disposition、mask/evidence 与 candidate 的依赖关系。

### 3.2 最小新增持久化事实

新增一个 per-project migration，且仅新增本切片所需的关系：

| 记录 | 必要字段 | 用途 |
|---|---|---|
| `visual_contract_revisions` | revision/page/source artifact/input hash/status | Page 级 coherent revision，作为本轮 relation 的根。 |
| `bubble_instance_revisions` | instance/revision/page/contract revision/region hash/mask artifact refs | 实例级区域、边界和安全约束。 |
| `text_segment_revisions` | segment/revision/page/source TextBlock/contract revision/order | 可信文字输入的稳定身份。 |
| `segment_instance_assignments` | segment revision/instance revision/disposition/reason/evidence artifact | 唯一 assignment 或显式 exclusion；不得双源。 |
| `cleaning_eligibility_records` | instance revision/eligibility/required-safe completeness/risk reason/evidence artifact | E1 与 excluded/review 的可解释事实。 |
| `cleaning_result_records` | contract revision/attempt/cleaned artifact/actual-changed & validator evidence refs/input+config hash/decision | 从候选到 active selected image 的完整依赖链。 |

大 mask、overlay、图片与 JSON evidence 均在文件系统，由 `processing_artifacts` 保存 metadata/hash；SQLite 只保存 artifact ref、identity、hash 与约束字段。`TextSegment` 在本切片可 1:1 映射到现有 `TextBlock`，但不把 `TextBlock` 重命名为 `TextSegment`，从而不破坏 OCR/Translation active pointer。

### 3.3 Migration

`MIGRATION = REQUIRED_NOW`。理由是该切片会正式更新 active cleaned pointer、参与跨重启 decision/reuse，且需要 Repository 可查询/原子约束的 revision、assignment、issue 和 expected-state。现有 baseline 只会判定 migration required，未提供递增 runner；实现必须同时提供幂等、checksum-locked 的 project migration runner，并保持旧 project 在迁移前为 `PROJECT_MIGRATION_REQUIRED`，绝不静默写入旧 schema。

### 3.4 Artifact 类型与保留

| 内容 | Artifact 类型 | owner | 保留 |
|---|---|---|---|
| 清字图 | `cleaned_image` | Page | `active_result`（accept 后） |
| required/safe/protected/uncertainty/candidate/changed/residue/damage/bg mask | `mask_image` | BubbleInstance revision 或 Page | `successful_payload` |
| instance/segment/eligibility/result manifest、local-background 统计 | `validation_evidence`（JSON） | revision/result | `successful_payload` |
| block/review 时的 candidate 与诊断 | 同上 | attempt/revision | `failed_attempt_payload` |

ArtifactService 必须增加 JSON 的安全登记能力；JSON 不能以图片 API 绕过、也不能直接由 Repository 写文件。

## 4. 职责与一次有界 Loop

```text
SinglePageCleaningService
  ├─ Repository：载入冻结 revision、创建 task/attempt reservation
  ├─ WorkflowLoopEngine：执行一次主路径；仅一次 correction reservation 或 block
  ├─ CleanerProvider：产生 temp cleaned image + block-level evidence
  ├─ ArtifactService：promote image/mask/JSON artifacts
  ├─ QualityCheckService.CleaningCheck：产生 issue drafts
  └─ workflow decision transaction：写 issue/decision/attempt，且仅 PASS 更新 active pointer
```

主路径只接受 COMPLETE 的 E1 instance。unsupported 对象保留 `unsupported_but_explainable_skip`；supported incomplete、ordinary false exclusion、`cleaning_residue`、`structure_damage`、`background_inconsistency` 均为 blocking。唯一 correction 仅允许在明确的 input-contract/validator binding 故障下重建同一局部 revision；它不是 Cleaner 自行 retry。一次 correction 后仍失败即 block。

## 5. 关键事务、重跑与 stale

1. **准备**：Repository 原子写 visual revision、instances、segments、assignment、eligibility 与 processing task；未产生 active pointer。
2. **执行**：attempt reservation 成功后调用 Provider；崩溃前的 temp files 不是正式事实。
3. **候选登记**：ArtifactService 先登记所有 child artifact，再登记 JSON evidence manifest；失败 artifact 保留但不 selected。
4. **决策事务**：以 Page active pointer、visual revision 和 task/attempt 状态为 expected state，原子写 `cleaning_result_record`、QualityIssue lifecycle、WorkflowDecision、attempt terminal status 与 task progress。仅 PASS 写 `active_cleaned_artifact_id`。
5. **重跑/复用**：相同 source + visual revision + Cleaner config hash + artifact integrity 且已 PASS 时复用 selected result，不重新调用 Provider。任一输入/revision/hash 改变时旧 cleaned artifact 可保留历史但对该 revision stale，不能 export-effective。
6. **恢复**：重启时仅依赖 committed attempt/decision/artifact/result record；未决 reservation 恢复为可重试或明确 block，绝不覆盖 original 或凭 temp 文件切 active pointer。

## 6. QualityIssue 映射

| 检查 | issue_type / error_code | 默认 |
|---|---|---|
| 可辨残字 | `cleaning_residue` / `cleaning_residue` | blocking |
| safe 外或 protected/uncertainty/boundary 修改 | `structure_damage` / 具体 damage code | blocking |
| 背景差异、白块或接缝 | `background_inconsistency` / `cleaning_background_inconsistency` | blocking |
| required support 不完整 | `cleaning_input_incomplete` / `required_support_unsafe` | blocking |
| 普通支持气泡无充分依据被排除 | `ordinary_bubble_false_exclusion` / `cleaning_eligibility_unexplained` | blocking |
| 明确不支持对象 | `unsupported_but_explainable_skip` / role-specific | non-blocking，但本切片不作为 PASS 样本 |

每个 draft 关联 page、TextBlock（若有）、attempt、主要 evidence artifact、input/config hash 和 dedupe key。QualityCheck 不直接创建 DB row 或决定 retry。

## 7. 拒绝的替代方案

- **继续使用 Spike JSON snapshot 作为正式事实**：无法原子约束 active pointer、assignment 与恢复，拒绝。
- **只把一个 page-level cleaned image 存入现有 schema**：丢失 instance/segment/provenance，无法解释 exclusion，拒绝。
- **让 CleanerProvider 直接写 workspace 或 DB**：违反 Provider/Artifact/DAO 边界，拒绝。
- **无 migration 地修改 baseline CREATE TABLE**：旧 project 无法安全升级，拒绝。
- **成功后才保存 evidence**：block/review 失去可追溯性，拒绝。

## 8. 实现前 Harness

1. 通过固定 `case-71` 创建 revision；`g002/s01` 与 `g002/s02` 唯一绑定到接触簇内两个独立 BubbleInstance，前者 COMPLETE/E1，后者 incomplete 且显式 blocking。
2. Provider 只在 attempt temp root 写输出；ArtifactService 登记 cleaned image、mask 和 JSON evidence。
3. 正式 `case-71` 运行登记 `g002/s01` 候选，但因 `g002/s02` incomplete 产生 blocking QualityIssue，保持 `active_cleaned_artifact_id=NULL`；FORM 直接嵌入原图、候选、实际应用 mask 与阻塞实例图。
4. 隔离的 all-complete 集成 fixture 产生 selected `active_cleaned_artifact_id`，且 original hash 不变；该 fixture 只证明事务路径，不冒充 case-71 整页产品成功。
5. source unchanged、halo、outside-safe、protected change、wrong background 均产生对应 blocking QualityIssue；不得更新 active pointer。
6. 相同输入重跑复用已有 PASS，不增加 Provider call；改 config 或 region revision 则新结果不能与旧 active 混用。
7. candidate artifact 已登记但在决策前崩溃：重启后不更新 active pointer，仍可审计或安全重建。
8. migration 前旧 project 返回 migration-required；迁移后保留旧数据且 schema checksum 正确。

## 9. 风险与开放问题

- 现有迁移机制仅有 baseline gate，增量 runner 是本切片的工程风险，必须单独测试 upgrade 与幂等。
- `TextSegment=TextBlock` 仅是本切片的适配；多段/多列 cardinality 扩展前需要重新审查。
- 一次 correction 的具体触发条件仅收敛为 input/validator binding；不将视觉质量不佳自动重跑。
- 清字 PASS 只代表固定普通气泡，不扩大到整页或复杂对象。
