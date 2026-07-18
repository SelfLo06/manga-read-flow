# 整页清字台账——数据库结构轮廓 v0.1

无 SQL/DDL；所有表均在 project.db，`project_id` 是 scope key。大图、mask、overlay、validator 原始 payload 一律只存 `ProcessingArtifact` 引用。

## 新增实体（完整 project schema v3）

逻辑 schema 版本 `project_full_page_cleaning_ledger_v3` 由 foundation 与 completion 两条不可变物理 migration record 共同组成。阶段列表示实体首次由哪条 record 创建；completion 不是可选扩展。详见 [迁移分期修订 v0.1.1](migration-staging-amendment-v0.1.1.md)。

| 表 / 实体 | 物理 migration record | 字段组与关系 | 约束 / immutable 规则 |
|---|---|---|---|
| `page_cleaning_runs` | foundation | id；page、visual revision、source artifact/hash、profile/config snapshot；status；supersedes；inventory/acceptance refs | 输入 immutable；run 只能追加 lifecycle；一个 page 可有多 run |
| `page_cleaning_inventory_items` | foundation | id；run；TextSegmentRevision、assignment/instance revision、target/support class、eligibility、dependency fingerprint、inventory evidence | immutable；`UNIQUE(run_id, text_segment_revision_id)`；不存 final disposition |
| `segment_cleaning_dispositions` | foundation | id；inventory item；code/reason/root/blocking-at-decision；result/member/evidence refs；supersedes；rule snapshot | append-only；每 item 最多一条 current final（partial unique / 等价原子 guard） |
| `instance_cleaning_results` | foundation | id；run/instance revision；covered target relation；attempt/provider/config/fingerprint；candidate + required/safe/protected/uncertainty/visible-support/actual/residue/boundary/background artifact refs；数值和 validator decision | immutable；0..N/result；artifact hash/fingerprint 均持久化 |
| `instance_result_inventory_targets` | foundation | result 到 inventory item 的显式覆盖/attribution | `UNIQUE(result_id, inventory_item_id)`；不可用 TextBlock/bbox 推断 |
| `cleaning_correction_chains` / `cleaning_correction_reservations` | foundation | chain identity、scope、source/target fingerprints；reservation ordinal、idempotency key、attempt/decision、status、budget_after | 每 chain 只允许 ordinal=1；replay 返回同一 reservation；状态可恢复 |
| `combined_cleaning_candidates` | completion | id；run/source hash；combined artifact/hash；combined delta artifact/hash；composition config/member-set fingerprint；status/supersedes；accepted validation ref | immutable；run 0..N；至多一个 accepted candidate |
| `combined_cleaning_candidate_members` | completion | candidate、instance result、instance revision、composition key、actual-write artifact/hash；accepted selection | `UNIQUE(candidate_id, instance_result_id)`；`UNIQUE(candidate_id, instance_revision_id)`；成员顺序只来自 canonical key |
| `page_cleaning_validation_records` | completion | id；run/candidate；inventory、attribution、overlap、cross-write、outside-safe、protected、uncertainty、boundary、residue、source/hash、combined-hash、freshness 判定、计数和 artifact refs；accepted selection | immutable；candidate 0..N validation revisions；acceptance 明确引用一条 PASS |
| `cleaning_quality_issue_relations` | completion | issue 到 run、inventory item、instance result、candidate、validation、reservation、decision 的显式 typed FK columns | append-only；不是 JSON/EAV；允许一个 issue 多个对象关系 |

## 既有表的使用

- `visual_contract_revisions`、segment/instance/assignment/eligibility 是上游 visual identity；不复制为第二关系源。
- `workflow_attempts` 记录工具调用；不替代 run。`workflow_decisions` 记录 Loop 决策；不替代 disposition。
- `quality_issues` 保存 lifecycle；关系由新 link 表表达。
- `cleaning_result_records` 保留为 Slice E 历史，不能作为 full-page ledger 或 reuse/acceptance 来源。
- `pages.active_cleaned_artifact_id` 是唯一 current effective output pointer；stale/缺失/hash mismatch 的 guarded UoW 必须清空它。

## 索引与 artifact 引用

索引：`run(page_id,status)`、inventory(run,segment revision)、current disposition、result(run,instance revision,fingerprint)、candidate(run,status)、validation(candidate,status)、reservation(chain/idempotency/status)、issue relation(issue/run/inventory)。所有 artifact ref 均要求 `ProcessingArtifact` present + hash-valid；overlay 仅诊断，不可作为 geometry 或 acceptance truth。
