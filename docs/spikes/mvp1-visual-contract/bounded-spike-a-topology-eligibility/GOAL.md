# MVP-1 Visual Contract Bounded Spike A — GOAL

状态：`COMPLETE — GO_TO_SPIKE_B_WITH_GUARD`

## 目标

用真实、可哈希锁定的证据验证以下合同是否可执行、可证伪：

```text
DetectionFragment
→ TextGroup
→ TextSegment
→ ContactBubbleCluster
→ BubbleInstance
→ SegmentDisposition
→ InstanceQualification
→ CleaningEligibilityAssessment
```

本轮只验证气泡实例拓扑、文字段唯一去向和逐实例 Cleaning eligibility。它不生成清字图，不实现 Typesetting，不接入正式 Workflow。

## 固定问题

1. `case-71` 的接触区域是否输出两个独立 `BubbleInstance`；
2. `case-72` 是否保留 7 个实例、8 个 segment，并逐实例解释历史上的 3 eligible / 5 excluded；
3. N≥3 接触簇是否不被硬编码成二分；
4. 单气泡多列、多段是否不会被过度拆分；
5. merge、split、unassigned、wrong-instance 负例是否全部被拒绝；
6. eligibility 是否不广播 cluster 最坏风险；
7. 每个 E2/E3 是否具有 rules、features、threshold version 和 evidence。

## 输入

- 冻结 Visual Contract v0.1；
- 冻结 case-71/72 S1 Detection/Grouping；
- 冻结 Typesetting Input Contract provenance ledger；
- Goal 5 container candidate 与 Goal 6 历史风险证据；
- 本目录显式、版本化的 evaluation oracle。

Oracle 只用于生成候选后的 Gate 评价，禁止进入候选生成或 eligibility 规则。

## 输出

- run-local、schema-versioned、hash-locked `VisualContractSnapshot`；
- cluster/instance/segment disposition/qualification/eligibility JSON；
- cluster 与 instance 二值 Mask artifact；
- topology/eligibility overlay；
- deliberate-negative 验证结果；
- 自动合同检查；
- `FORM.md`、`REPORT.md`、`GATE.md`。

## 允许

- Spike 专属 Python 工具与测试；
- stable ID、immutable revision；
- marker competition、virtual boundary candidate 和 same-container qualification；
- per-instance eligibility evidence；
- 本地 JSON、PNG、FORM。

## 禁止

- migration、正式数据库 schema、active pointer；
- Repository、Workflow、ArtifactService 正式集成；
- CleanerProvider、TypesetterProvider；
- 实际 Cleaning、字号/换行、glyph rendering；
- UI/API、40 页实验；
- OCR、翻译、性能优化；
- 使用 oracle、case ID、目录顺序或 legacy `container-*` 序号驱动候选算法。

## 裁决

十项退出门禁均已通过。`case-72__g003__s01` 的人工 `FALSE_NEGATIVE` 不否定
BubbleInstance 拓扑或逐实例证据合同；它冻结为 Spike B 的必测反例：不得再以
BubbleInstance 级 protected-overlap ratio 单独批准或否决实际写回。

任一 deliberate negative 被接受，或必须加入样本专属规则，均为 `NO_GO`。
