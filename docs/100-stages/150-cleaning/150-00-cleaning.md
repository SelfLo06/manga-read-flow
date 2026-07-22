# 150 Cleaning

## 1. 阶段目标

Cleaning 在不覆盖原图的前提下，对已经获得正式授权的文字实例生成候选 cleaned artifact。

Cleaning 的目标不是“尽量清除页面上的文字”，而是：

- 只处理已建立正式关联的文字实例；
- 只在可解释的 required、protected、uncertainty 和 safe-edit 证据范围内写入；
- 保留候选生成过程、写入范围和来源信息；
- 将候选交给 CleaningCheck；
- 由 Workflow Loop 决定接受、复核、重试、跳过或阻塞。

Cleaner 不决定：

- 实例是否 eligible；
- 是否 skip；
- 是否 fallback；
- 是否 accept；
- 是否更新 active pointer；
- 是否创建或解决 QualityIssue。

原图永不覆盖。

## 2. 当前状态

当前主线处于 **M1 — Single-Page Visual Closure**。

现有实验已经证明部分受限机制可运行，包括：

- topology 与实例归属；
- pixel evidence 计算；
- real cleaner 的局部写回；
- 部分页面和容器上的 fail-closed 行为。

这些结果尚未证明通用单页 Cleaning 能力。

当前 physical-boundary capability 仍未关闭：

- 最新诊断中的 A1、A2、A5 均为 `NO_GO`；
- g002、g004 仍为 `BLOCKED_PENDING_CAPABILITY`；
- 最新相关 Spike 中 `ACTUAL_CLEANING=NOT_RUN`。

当前继续采用 protected/uncertainty fail-closed，不通过缩小 required、扩大 safe、放宽全局阈值或添加单 case 规则制造通过。

详细信息见：

- [已知问题](150-10-known-problems.md)
- [实验索引](150-20-experiments.md)
- [CleaningCheck](150-40-cleaning-check.md)

## Physical Boundary Handoff

PhysicalBoundaryEvidence 位于 Visual Contract preparation、CleaningEligibility 和 Cleaning 之前。Slice 1E 已实现正式只读 Grouping-input selector：它从唯一 Grouping pointer exact-read acceptance/check/snapshot、stale facts、Detection/OCR/Profile/source/producer bindings 与 artifacts，成功时返回未来 Physical Boundary attempt 可持久化的 immutable binding，失败时结构化拒绝且不启动 producer。Physical Boundary producer、candidate/revision、Check、acceptance 与 active pointer 仍未实现。

runtime Check 不读取 oracle，也不决定 accept/retry/fallback/skip/block。实验 `PhysicalBoundaryBenchmarkEvaluator` 只能位于 `tools/experiments/150-cleaning/`，读取 frozen candidate/oracle manifest，输出实验 metrics/verdict，不创建正式 QualityIssue、revision、Visual Contract 或 active pointer。

Physical Boundary 的 accepted revision 必须拥有独立的 `active_physical_boundary_evidence_revision_id`（未来 metadata/UoW extension）。只有 WorkflowLoopEngine 决策和 UoW acceptance transaction 才能推进该 pointer；VisualContractRevision 必须绑定 exact accepted evidence revision。当前仓库没有真实 Physical Boundary state，因此 Slice 1E replacement 没有可同步失效的 exact-bound 下游 pointer，也未伪造该状态。Cleaning 只消费未来完成该 binding 的 Visual Contract，当前 physical-boundary capability 仍未通过，M1 仍阻塞。

## 3. Canonical Processing Path

Cleaning 的正式处理链路是：

```text
已接受的 Page 与上游 active results
→ 正式 Detection / OCR / Grouping 结果
→ 当前关联与容器构造链路
→ 正式文字实例、容器和证据对象
→ required / protected / uncertainty / safe-edit evidence
→ eligibility 与 route 决定
→ Cleaner 生成候选 cleaned artifact
→ ArtifactService 登记候选 artifact
→ CleaningCheck 产生 metrics、evidence 和 IssueDrafts
→ WorkflowLoopEngine 决定 accept / retry / fallback / skip / block
→ UoW / Repository 原子持久化 result、decision、QualityIssues
  并推进 active_cleaned_artifact_id
```
