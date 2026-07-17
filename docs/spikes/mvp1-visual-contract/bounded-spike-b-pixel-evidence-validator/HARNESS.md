# MVP-1 Visual Contract Bounded Spike B — HARNESS

## 输入锁与事实来源

候选运行必须先写入 `input-lock.json`，至少锁定：

- Spike A snapshot content/file hash、evaluation lock hash、FORM hash；
- 原图、instance mask、source TextSegment/translation provenance 的 hash；
- renderer module、validator module、font file、profile 与 fixture oracle hash；
- source `instance_id`、instance revision、region artifact hash、segment revision。

候选生成完 `PixelEvidenceSnapshot` 后才可读取 evaluation oracle。候选和 Validator 只能
消费 snapshot/child-artifact refs；oracle 仅能评价结果。

## 事实对象

| 对象 | 必填事实 | 不可替代项 |
|---|---|---|
| `RequiredTextEvidence` | segment/instance/revision、text-core mask、source image、coverage、mask hash | OCR bbox、coarse cluster、overlay |
| `SafeEditEvidence` | effective mask、protected mask、uncertainty mask、交集和扣除后 coverage | instance-level overlap ratio |
| `PostCleaningResidueReport` | required component、test output、component coverage、threshold/profile、decision | changed-pixel count |
| `ActualChangedPixelMask` | input/output hash、recomputed mask、writeback mask comparison | provider 自报改动数 |
| `RenderedGlyphEvidence` | full-canvas alpha/coverage、write mask、segment/instance/region binding、glyph count | 先裁剪后的 output |
| `CorrectionReservation` | contract id、root issue、ordinal、idempotency key、decision | in-memory retry counter |

## 场景矩阵

| # | 场景 | 输入 | 预期结果 |
|---:|---|---|---|
| B1 | case-71 接触实例 | 两个已拆分 instance 的真实 segment | 各自 evidence/glyph 独立，不能借 parent cluster 通过 |
| B2 | case-72 E1 evidence | 冻结 E1 candidate | RequiredTextEvidence、safe-edit、clean negative 可重放 |
| B3 | case-72 `g003` | 历史 E3 / 人工 false-negative | 输出 protected/uncertainty 与 text-mask 相交分解；不作 Cleaning 批准 |
| B4 | clean negative | B2 同输入的受控无 required-text 输出 | residue = pass |
| B5 | deliberate residue | B2 输出恢复 required component | `cleaning_residue` blocking |
| B6 | changed-mask mismatch | writeback claim 与实际 input/output 差不同 | blocking |
| B7 | actual glyph normal | 真实整段译文、全画布未裁剪 alpha | exact-region binding 与空间检查通过 |
| B8 | missing / duplicate | 缺 glyph 或同 segment 两 glyph | 分别拒绝 |
| B9 | wrong-instance | segment=A、glyph region=B | `wrong_instance_rendering` blocking |
| B10 | overflow / touch | glyph alpha 穿出或接触 exact region | 分别拒绝或按 uncertainty 明确 review，不能静默通过 |
| B11 | wrong validator region | renderer=A、validator=parent/B | preflight binding blocking，空间数值不参与放行 |
| B12 | correction reservation | 同 root stage 的 replay/second request | 0→1 一次；重放幂等；第二次自动 reservation 拒绝 |

## 自动门禁与停止条件

自动 Gate 必须逐项报告 B1–B12 所用 artifact refs/hashes、issue code、预期与实际结果。
任一 deliberate negative 未被拒绝，或 negative 只能靠隐藏 case mapping 才被拒绝，立即
`NO_GO`。以下也停止：

- residue 正反例无法从冻结输入重放；
- glyph evidence 只有裁剪后的 mask；
- validator 使用了 parent / bbox / 错 revision；
- correction 需要 ordinal 2 才能通过；
- 必须扩展到 E2/E3、SFX、批处理或正式 Workflow 才能完成验证。

## 人工审查

自动 Gate 通过后，只对真实页 overlay/报告填写 FORM：

1. case-71 两个实例的 required text / glyph 是否仍分离；
2. `g003` 的 protected 与 uncertainty 证据是否可解释，且没有借此伪称可以清字；
3. residue-positive/overflow/错 region 的可视化是否确实展示了被拒绝的错误；
4. 本轮结论是否保持“Validator 合同通过”而非“Cleaning/Typesetting 已可用”。
