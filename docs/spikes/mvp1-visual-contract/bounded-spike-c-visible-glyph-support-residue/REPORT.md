# MVP-1 Visual Contract Bounded Spike C — REPORT

## 最终裁决

```text
VISIBLE_GLYPH_SUPPORT_CONTRACT = PASS_WITH_LIMITS
CONTROLLED_RESIDUE_VALIDATOR = PASS
INSTANCE / REVISION_BINDING = PASS
SPIKE_B_REGRESSION_MATRIX = PASS
ACTUAL_CLEANING = NOT_EXECUTED / NOT_GO
SPIKE_C = GO_FOR_BOUNDED_REAL_CLEANER_SPIKE
```

这不是对真实清字质量、整页清字或产品 Workflow 的 GO。它只允许下一轮在同样窄的普通气泡范围内，使用真实 Cleaner 输出验证这份像素证据合同。

## 运行与证据边界

最终运行：

```text
data/local/mvp1-visual-contract-spike-c-v0.1/run-v0.7/
```

- candidate snapshot SHA-256：`4bd8233247f4f68cb7a0cd75115f5e512559603f8e4fc25b9cfb24e55ff1740b`；
- candidate snapshot 在解析 fixture oracle decision 前写入；输入锁明确记录 `oracle_hash_read_before_candidate_snapshot=true` 与 `candidate_generation_oracle_decision_access=false`。也就是说，候选生成前为可复现性读取 oracle 文件字节计算 hash，但没有读取或使用预期 decision 内容；
- 输入锁包含 Spike A/B snapshot、Spike B FORM、当前 Spike C harness、fixture oracle 与 profile 的 hash；
- 没有调用 Cleaner、Provider、Workflow、数据库或产品 artifact 生命周期；`actual_cleaner_executed=false`；
- 控制输出是确定性背景填充，不是 inpainting 成功样张。

`run-v0.4/FORM.md` 是人工填写的 FORM。为补齐 H 的完整 Spike B 回归矩阵并消除 oracle 字段歧义，最终代码产生了 `run-v0.5` 至 `run-v0.7`。已逐项核对：v0.4 与 v0.7 的四个真实 segment 的 source、text-core、visible-support、safe-edit、local-background、residue、cleaned-control artifact content hash 以及 decision 全部相同；六项 control evidence overlay 与 observed decision 也完全相同。故该人工审查可作为 v0.7 **相同可视证据**的审查结果；它不替代 v0.7 的 hash-lock，也不倒灌修改 v0.4。

## 证据合同

| 对象 | 本轮语义 | 不代表什么 |
|---|---|---|
| `text_core` | 高置信深色字芯候选 | 完整可见字形 GT |
| `visible_support_candidate` | 受实例约束、局部 Lab 背景对比筛选后的有限字形支持候选 | 跨字体、特效文字的一般化真值 |
| `safe_edit` | 可安全写回的独立 mask | required/visible support 的替代品 |
| `protected` / `uncertainty` | 上游风险边界；不得并入 required support | 可自动忽略的风险 |
| `local_background_sampling` | 实例内、core 外 ring 的 Lab median/MAD 采样 artifact | 全页统一亮度阈值 |
| `residue_candidate` | support 内相对局部背景有足够对比、且形成最小连通组件的残留 | 真实清字的背景/结构质量结论 |

每个真实 segment ledger 均保留 page/segment、instance/revision/region hash、source/output hash、上述 mask artifact、局部背景统计、连通组件、局部对比、required/safe completeness、decision、issue code 与 reason codes。大 mask 只作为文件 artifact 保存；JSON 不含 ndarray，也没有以 `text_core_pixels` 偷换 visible support 计数。

失败时，`cleaning_residue_issue_draft` 只输出未来 `QualityCheckService` 可使用的根因证据：affected segment、实例绑定、residue mask/component、local contrast、required coverage、unsafe ratio 与 reason codes。它不包含 retry、fallback、skip 或 block 策略；这些仍属于未来 `WorkflowLoopEngine`。

## 控制结果

| Control | 预期 | 观察 | 结果 |
|---|---|---|---|
| A：完整移除 visible support | PASS | PASS | PASS |
| B：只移除深色 core，保留浅色 halo | BLOCK / `cleaning_residue` | BLOCK | PASS |
| C：灰白气泡中保留近白可辨字形 | BLOCK / `cleaning_residue` | BLOCK | PASS |
| D：恢复完整字符或关键笔画组件 | BLOCK / `cleaning_residue` | BLOCK | PASS |
| E：普通背景变化/小噪声 | PASS | PASS | PASS |
| F：required support 与 safe-edit 不完整重合 | `INCOMPLETE_REVIEW` | `INCOMPLETE_REVIEW` | PASS |

B/C/D 还各自输出了结构化 `cleaning_residue` issue draft；A/E 不会误造 issue；F 不会混入 Cleaning PASS control。

## 真实样本与人工审查

审查范围固定为 case-71 接触实例的两个 segment，以及 case-72 的两个普通实例。

- case-71 `g002/s01`、case-72 `g001/s01`、case-72 `g006/s01`：required support 完整落入 safe-edit，受控移除后 residue 为 PASS；
- case-71 `g002/s02`：6 个 required-support 像素不安全，强制 `INCOMPLETE_REVIEW`，即使其受控输出检测到 residue 也不能伪称 Cleaning PASS；
- 人工审查确认：case-71 接触实例的 support / safe / local-background / residue 没有跨实例合并；固定样本未见明显可辨字形落在紫色 support 外；B/C/D 检出、A/E 不误报；根因字段足够绑定到 instance/revision，且 Validator 没有越权做 Loop 决策。

人工 Overall：`PASS_WITH_LIMITS`。

## Spike B 不退化

v0.7 重新运行了以下拒绝/约束矩阵，全部为 true：

```text
missing
duplicate
wrong-instance
glyph-overflow
glyph-boundary-touch
validator-region-binding-mismatch
one correction reservation
second automatic correction rejection
```

这只验证 Spike B 的局部 Validator 合同仍被调用和拒绝；不把 Spike C 解释为重新验证或替换 Spike B 的真实清字结论。

## 限制、风险与下一步

1. visible support 仍是启发式 candidate，只在固定样本经人工确认；没有证明不同分辨率、粗描边、发光/阴影、强压缩、复杂彩色文字或背景文字的完整性。
2. 局部背景 ring 可能被复杂纹理或相邻文字污染，且当前没有显式排除 protected/uncertainty 像素；本轮只覆盖白/浅色普通气泡和轻微灰白差异。
3. E 只证明 support 外单个小噪点不会误报，不能证明 support 内复杂纹理、扫描噪声或灰阶不均也不会误报。
4. 控制填充不检验真实 inpainting 的背景连续性、边界损伤或实际残字分布。
5. `INCOMPLETE_REVIEW` 是事实分类，不是自动 retry/skip 产品策略。
6. 允许的下一步仅是 bounded real Cleaner Spike：对 COMPLETE support 的少量普通气泡运行真实清理，然后以本合同验证残字、结构损伤和背景一致性；仍不得接入正式 Workflow/API/UI/Provider/数据库。
