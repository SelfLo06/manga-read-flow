# 120 Grouping

Grouping 将 accepted Detection fragments 与 accepted OCR evidence 组织为可追踪的 text-group identity、fragment-to-group membership、M1 ordering、membership provenance、proposal geometry 和 unresolved relation。text group 是语义关联事实，不是 BubbleInstance、physical container 或最终 layout boundary；Grouping 仍是语义输入与 Cleaning/Typesetting 写入边界之间的桥梁。

text-seeded association、局部 routing 和视觉合同已有可复用 harness 与受限正例；它们只提供 proposal/supporting evidence，没有授权全自动 association、BubbleInstance、mask 或 Cleaning。接触气泡、跨画格/页边结构和 merge/split 仍可能造成 text-group membership 及其后续物理实例映射不确定。

当前选择 fail-closed：证据不足的 relation 显式 unresolved/abstained，不依据未经证明的视觉分隔 proposal 跨越疑似或未知分隔强制归组。拒绝按最近 bbox 或单阈值把所有片段强行归组，因为会扩大错误写入。验证覆盖单气泡、多 segment、接触气泡、旁白框、跨画格候选、局部编辑和 provenance 对账。BubbleInstance、bubble/panel/page-edge/contact/separator evidence 由后续 Physical Boundary 职责拥有，不是 Grouping snapshot 输出。

Slice 1A 已完成 Detection 正式交接：正式 Detection acceptance 会生成 canonical `accepted-detection-evidence-set.v1` manifest，经 ArtifactService 登记，并在同一 UoW transaction 中保存 immutable set metadata、exact member bindings 与 acceptance provenance。未来 Grouping 必须按 exact `detection-set-v1:<sha256>` 读取该依赖；不得从页面全部 `text_blocks`、文件存在性或时间戳推断 accepted membership，也不得新增 Detection active pointer。

Slice 1B 已实现 `FrozenGroupingEvidenceSnapshot` candidate path：正式独立 application entry exact-read Slice 1A Detection set、冻结其成员对应的 active immutable OCR results、原图 bytes/hash 与 `ProcessingProfileSnapshot`，通过显式注入的纯 producer port 生成结构候选，登记 canonical `frozen-grouping-evidence-manifest.v1` artifact，并保存 immutable snapshot metadata、exact OCR bindings 和 generation outcome provenance。当前没有默认或生产 Grouping producer，自动 post-OCR orchestration 未启用。

Slice 1C 已实现正式 `CheckGroupingCandidateApplicationService`、oracle-free `GroupingCheck`、immutable `GroupingCheckResult`、`grouping-check-evidence.v1` artifact、正式 QualityIssue persistence 和 check execution provenance。Repository 的 historical exact-read 只审计 candidate 自身保存的 immutable rows/bindings；当前 Detection/OCR/Profile/source/producer compatibility 由 application use case 单独解析并进入 check input fingerprint。OCR active revision 变化不会隐藏历史 candidate，而会产生 root stage 为 `grouping` 的 blocking dependency issue。相同 check identity 复用 CheckResult/evidence/QualityIssue，并追加独立 execution provenance。

Slice 1D 已实现页面级 `page_grouping_state.active_grouping_snapshot_id`、immutable Grouping acceptance、WorkflowDecision 和 pointer/version CAS。Slice 1E 在同一正式 UoW 中加入 immutable stale facts 与 `CLEAR_ON_STALE`：新的 accepted Detection/OCR dependency 会 append exact stale facts 并 CAS 清空 pointer；不同 snapshot replacement 会 append 旧 snapshot superseded fact、原子切换 A→B 并只递增一次 version；legacy dependency mismatch 可由正式 recovery CAS repair。Profile 与 source 当前没有 applicable mutation application，因此只由 explicit selector/current-usability 校验保护。完整合同见 [FrozenGroupingEvidenceSnapshot Contract](120-30-frozen-grouping-evidence.md)。

## Physical Boundary Frozen Handoff

当前产品代码已有 immutable `FrozenGroupingEvidenceSnapshot` candidate、GroupingCheckResult、正式 QualityIssue、Workflow/UoW acceptance、immutable acceptance/stale facts 和 `page_grouping_state.active_grouping_snapshot_id`。Slice 1E 的正式 Physical Boundary Grouping-input selector 只返回 pointer-selected、accepted、not-stale、dependency/artifact-valid、无 blocker 的 exact immutable binding；失败返回结构化 rejection，不调用 producer。实验 association/harness 结果仍不属于产品 source of truth。

该 snapshot 至少绑定 `project_id`、`page_id`、immutable source artifact/hash、Detection/OCR dependencies、fragment/text-group membership、fragment geometry、full-page coordinate space、provenance、producer/profile identity、manifest artifact/hash 和 dependency fingerprint。大型 manifest/geometry 通过 ArtifactService 保存，SQLite 只保存 metadata、relations 和 hash。

Detection/OCR bbox、routed association、bbox union 或其他几何结果只能作为 proposal/supporting evidence，不能直接升级为 BubbleInstance 或 physical boundary。snapshot 缺失、stale、provenance 不完整或跨未知边界时，Grouping 必须 abstain，Physical Boundary 后续链路只能产生 blocking/review-required issue。

## Implementation Status

```text
Slice 1A — AcceptedDetectionEvidenceSet: IMPLEMENTED
Slice 1B — Grouping candidate: IMPLEMENTED
Slice 1C — GroupingCheck / QualityIssue: IMPLEMENTED
Slice 1D — Workflow acceptance / active pointer: IMPLEMENTED
Slice 1E — stale / reuse / exact Physical Boundary binding: IMPLEMENTED
Grouping product implementation overall: PARTIAL
Production Grouping algorithm: NOT IMPLEMENTED / NOT VALIDATED
Physical Boundary: NOT IMPLEMENTED
M1: NOT COMPLETE
```
