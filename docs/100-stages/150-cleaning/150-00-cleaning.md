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
→ CleaningCheck
→ Workflow Loop 决定 accept / review / retry / skip / block
→ ArtifactService 执行正式 artifact 登记与 active 切换