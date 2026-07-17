# MVP-1 Visual Contract Bounded Spike B — GOAL

状态：`COMPLETE — PASS_WITH_CHANGES / NOT_GO_FOR_REAL_CLEANING`

## 目标

在完全 run-local、hash-locked 的受限 harness 内，验证像素证据与实际 glyph
Validator 是否能证伪错误结果。它承接 Spike A 的 `VisualContractSnapshot`，但不重算
BubbleInstance topology，也不把任何结果接入产品。

本轮只验证：

```text
RequiredTextEvidence
→ safe-edit / protected-pixel evidence
→ PostCleaningResidueReport
→ ActualChangedPixelMask
→ un-clipped RenderedGlyphEvidence
→ reconciliation / spatial validator
→ one correction reservation
```

核心问题是：系统能否用不可变像素和 identity 证据拒绝“看似通过、实际残字、越界、
跨实例、漏渲染或验证了错误区域”的候选。

## 固定输入与范围

- Spike A `run-v0.4` 的 `visual-contract-snapshot.json`、input/evaluation lock、FORM；
- case-71/72 的冻结原图、TextSegment、BubbleInstance mask、翻译 provenance；
- case-72 `g003/s01`：protected-overlap 假阴性的 mandatory regression case；
- 少量 schema-versioned synthetic controls，只用于 deliberate negative，不替代真实页；
- 已安装的本地 Pillow/OpenCV/Numpy 能力。

真实 case 必须至少覆盖：case-71 的两个接触 BubbleInstance、case-72 的 E1 候选及
`g003`。复杂 SFX、E2/E3 和全页批处理不扩入范围。

## 关键裁决

1. `RequiredTextEvidence` 是每个 eligible TextSegment 的像素级要求，不得由 OCR bbox、
   cluster mask、overlay 或 changed-pixel 计数替代；
2. `ActualChangedPixelMask` 从受控 input/output 像素差重新计算，是事后事实；
3. residue 的 clean-negative 与 deliberate-residue-positive 必须使用同一冻结输入和同一
   evidence contract；
4. glyph coverage 必须先以完整 page canvas 渲染、再验证；禁止先裁剪到 region 后把裁剪
   结果当作“无 overflow”的证据；
5. renderer 与 validator 的 exact BubbleInstance region ID/revision/hash 必须相同；
6. `g003` 只能用 text-mask / safe-edit pixel 与 protected / uncertainty evidence 判断，
   不得回退到 instance-level protected-overlap ratio；本轮不把它提升为可实际清字；
7. 一次 correction reservation 只验证合同的 exactly-once/replay 语义，不调用 Workflow。

## 允许

- Spike 专属、run-local Python 工具和测试；
- 文件 hash、immutable JSON、PNG mask、JSON ledger、overlay、FORM、自动 Gate；
- 冻结原图的受控像素副本、deterministic compositing 与 deliberate residue controls；
- 全画布未裁剪 glyph alpha/render evidence；
- deterministic synthetic mutation 与 correction-reservation simulation。

这里的受控像素副本仅用于证明 Validator 合同，**不是** CleanerProvider、实际清字算法、
产品 preview 或可用清字结果。

## 禁止

- migration、正式数据库 schema、active pointer；
- Repository、Workflow、ArtifactService、QualityCheckService 正式集成；
- CleanerProvider、TypesetterProvider、任何生产清字或产品候选图；
- 字号搜索、换行优化、样式优化、OCR/翻译优化；
- UI/API、40 页实验、Batch、性能优化；
- 使用 case ID、目录顺序、overlay 像素或人工隐藏映射驱动候选/Validator 通过。

## 退出门禁

1. 每个 Spike B active segment 都有带 source/revision/hash/coordinate 的 RequiredTextEvidence；
2. clean-negative 通过，deliberate-residue-positive 必须产生 `cleaning_residue`；
3. actual changed mask 与 writeback evidence 可复算，且不能代替 residue 判定；
4. `g003` 能输出 text-mask、safe-edit、protected 与 uncertainty 分解证据；不得因
   instance-level ratio 静默 E3，也不得被本轮误批准为实际 Cleaning；
5. 每个 eligible segment 有未裁剪的整段 glyph evidence，且在精确 instance region 内验证；
6. missing、duplicate、wrong-instance、empty glyph、overflow、confirmed boundary touch、
   wrong-validator-region 全部被拒绝；
7. renderer/validator region binding mismatch 在空间检查前阻塞；
8. correction reservation 只允许 ordinal 0→1；重放不重复消耗，第二次自动 correction
   必须拒绝；
9. snapshot/ledger 是关系事实来源；不需要 parent bbox、目录顺序、overlay 或人工隐藏
   映射；
10. 任一 deliberate negative 被接受、evidence 无法重放、或为通过而写入样本专属规则，
    本轮 `NO_GO`。

## 非目标与后续

本轮已证明受限的 Pixel Evidence / Validator 合同可拒绝指定反例，但人工审查确认真实
Cleaner 的完整 residue 仍无证据。它不证明清字视觉质量、typesetting 美学、真实 OCR/
翻译质量或产品 Workflow，也不授权进入真实 Cleaning 或正式集成。
