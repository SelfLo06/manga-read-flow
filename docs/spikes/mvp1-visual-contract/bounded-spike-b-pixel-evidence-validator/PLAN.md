# MVP-1 Visual Contract Bounded Spike B — PLAN

状态：`COMPLETE — PASS_WITH_CHANGES`

## Phase 0：冻结与设计检查

- 阅读 SRS、HLD、Visual Contract 详细设计与 Spike A Gate；
- 锁定 run-v0.4 与人工 FORM；
- 建立本目录 GOAL/HARNESS/PLAN、oracle 和输入清单；
- 明确受控像素 fixture 不等于正式 Cleaning。

## Phase 1：先写可证伪测试

- RequiredTextEvidence / safe-edit / residue 正反例；
- actual changed mask 对照与 mismatch；
- 完整 glyph、missing、duplicate、wrong-instance、overflow、touch、wrong-region；
- correction reservation 的一次性与重放。

## Phase 2：实现 run-local harness

- canonical mask/image hashing；
- immutable `PixelEvidenceSnapshot`、child artifact 与 ledger；
- controlled pixel output 与 residue evaluator；
- full-canvas glyph evidence 和 validator；
- gate matrix、overlay、FORM、timings。

## Phase 3：运行与收口

- 生成新的 versioned run，不覆盖 Spike A；
- 自动合同、测试、diff/encoding 检查；
- 读取人工 FORM 后更新 REPORT/GATE；
- 未获维护者授权前不 commit、不进入产品集成。

结果：`run-v0.7` 已完成。bounded Validator contract 为 `PASS_WITH_CHANGES`；真实
Cleaning residue completeness 为 `CHANGES_REQUIRED`，本轮不扩展到真实 Cleaner。
