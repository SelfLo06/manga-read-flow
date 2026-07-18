# Safety / Abstention 审查

## 结论

支持 `NO_GO`，并确认 Stage B 必须保持 `DENIED`。当前证据只支持
Stage A 的只读分类和 abstain；不支持将任何人工标签、A1/A2/A5 输出或
局部颜色证据转化为 physical `protected` 走廊中的写权限。

## 审查范围与证据

已审查 `GOAL.md`、`HARNESS.md`、`evidence.py`、`run_stage_a.py`、
`evaluate_stage_a.py`、完成的人工锁、自动评估锁及 `GATE.md`。本审查对应的
本地 evidence hash 为：

| 输入/输出 | SHA-256 |
| --- | --- |
| `stage-a-summary.json` | `da6ad2799610f2c597688ad2a20441ba4f52d9de40db19581138218091c6f17d` |
| `human-review-lock.json` | `c4c1e372677df950302a61bb83e52696ea41f4cf4a5083eaaac343a6cfba8955` |
| `stage-a-evaluation.json` | `ff9564c3a9d0c199cf76406d147bd540d4da927bfa7494342cf68d48c16633db` |

## 不变量核对

| 不变量 | 结论 | 依据 |
| --- | --- | --- |
| 旧 `required` 完整分类 | PASS | `Classification.validate()` 强制四类 mask 与 `old_required` 精确分区。 |
| `protected` 不得认证为文字 | PASS | A1/A2/A5 均将 `protected` 排除在可达/candidate 之外；聚焦测试断言所有 arm 的 `required_text & protected == 0`。 |
| `uncertainty` 不得认证为文字 | PASS（当前代码） | A1 将其置为 traversable barrier，A2/A5 在最终 `required_text` 排除；聚焦测试同样断言零交集。 |
| 不可证实即 abstain | PASS | 三个 arm 的 `proven_non_text_boundary` 均恒为空；争议像素保留 `unresolved_uncertain`，不会缩小 `required` 或扩大 `safe`。 |
| 原图及 Slice 3 冻结输出不变 | PASS（工具范围） | runner 只读冻结 source/evidence，且拒绝覆盖既有 evidence；只向该 Spike 的 ignored run root 写入 mask、overlay、FORM 和锁。未发现 Cleaner、Composer、candidate、pointer 或 acceptance 调用。 |
| 人工标签不成为写授权 | PASS | FORM 仅由 `freeze_human_review()` 读取并锁定，评估器仅据其计算指标；没有回写 `visible`、`safe`、`protected` 或 `uncertainty` 的路径。`ALLOW_AS_REQUIRED_TEXT=YES` 只是 oracle 标记，不能绕过 `protected`。 |

## 关键发现

1. g002 的 708 个已标注文字边缘中，A1 历史 evidence 仅认证 288 个，仍有
   420 个 unresolved；其中 103 个落在 frozen `protected`。即使人工确认文字，
   也没有安全路径把这些物理边界走廊像素写入。
2. g004 的 70 个高风险 physical boundary 像素在所有 arm 均为 unresolved；
   没有 arm 给出 `proven_non_text_boundary`。这避免了 boundary-to-text 误认证，
   但并未建立可供 correction 使用的通用边界证明。
3. 当前 `evidence.py` 已把 `uncertainty` 纳入 A1 的硬 barrier。冻结 v0.2
   evidence 中 A1 曾将 2 个后来标为 `UNCERTAIN` 的像素认证为文字；这份历史
   evidence 不能被改写，也正是维持 `NO_GO` 的充分反例。当前回归测试阻止该
   现象在后续只读评估中复发，但不构成 Stage B 的正向授权。
4. A5 的 Lab 色差只在 seed-connected、`protected`/ridge barrier 之后参与
   证据判断。没有把蓝色、橙色、case、target 或坐标变成规则分支；其当前
   recall 为 0，故更不能以颜色假说放宽 physical guard。

## Stage B 裁定

`NO_GO` 是唯一安全结论。进入 Stage B 会要求至少一项本轮没有得到的授权：

- 覆盖 g002 已确认文字且仍受 protected 限制的像素；或
- 将 g004 的 physical boundary 自动证明为可调整/可写；或
- 用人工标签直接改写保护状态。

三者均违反本 Spike 的 fail-closed 合同。因此不得创建 correction budget、
correction reservation、Cleaner candidate 或新的 Slice 3 run。

## 风险与后续条件

风险不在于少量 g004 冲突看似狭窄，而在于它仍是未被自动证明的 physical
boundary。也不能将 g002 的左缘几何或深蓝观察转化为全局/样本专用阈值。

若未来另行授权研究，前置条件应为独立的通用 physical-boundary ground truth
与控制矩阵，且必须证明在不触碰 `protected`、不缩小 `required`、不扩大 `safe`
的前提下，同时满足文字完整性和 boundary proof；本轮人工 FORM 不可复用为
产品写策略。

## 验证

执行 `pytest -q -p no:cacheprovider tests/spikes/cleaning/physical_boundary`：
`7 passed`。该测试仅验证 Stage A 的 mask/guard/replay/evaluation 不变量，
不代表 Cleaning、Stage B 或 Slice 3 acceptance 通过。
