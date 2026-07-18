# Final GO/NO_GO Evidence Review

## 独立裁决

**`STAGE_A = NO_GO`，`STAGE_B = DENIED`。**

该裁决证据充分，且正确落实了维护者人工复核：g002 的主要争议像素是文字
evidence，但其中受 frozen physical protected/uncertainty corridor 限制的像素
仍不可写；g004 的窄冲突是高风险真实气泡边界，尚无通用自动证明。结论不是把
问题归因于彩色字体，也不是放宽全局阈值，更不允许将 g003 从 `REVIEW` 升级。

审查范围为 `GOAL.md`、`HARNESS.md`、`REPORT.md`、`GATE.md`、完成的本地
Stage A 锁/评估、既有 human-label、boundary-to-text、safety/abstention、
case-specific-tuning 与 final-scope/integration 审查；只作证据审查，不生成
candidate 或修改冻结材料。

## 证据链核验

本地文件的 SHA-256 与 `stage-a-evaluation-lock.json` 一致：

| 产物 | SHA-256 | 审查结果 |
| --- | --- | --- |
| `stage-a-summary.json` | `da6ad279…c6f17d` | 匹配 |
| `human-review-lock.json` | `c4c1e372…ba8955` | 匹配 |
| `stage-a-evaluation.json` | `ff9564c3…6633db` | 匹配 |
| 完成的 `FORM-stage-a.md` | `4a57b262…d8757d` | 与 human lock 匹配 |

人工 FORM 覆盖 12/12 个争议组件：g002 为 708 px `TEXT_EDGE` 与 2 px
`UNCERTAIN`；g004 为 70 px `BUBBLE_BOUNDARY`，均标为 high risk / 不允许
作为 required text。FORM 是评估 oracle，不是 protected/safe/required 的写入
授权；这与维护者“文字 evidence 总体正确、实际 blocker 是 physical boundary
conflict”的复核一致。

| Gate 所需事实 | 锁定评估结果 | 裁定 |
| --- | --- | --- |
| 不将已标注边界当文字 | A1/A2/A5 对 g004 70 px 的 `required_text` 都是 0 | 必要条件满足，但仅为 abstain |
| 完整覆盖确认文字 | A1 recall=`0.40677966`，420 px unresolved；A2/A5 recall=`0` | 失败 |
| 自动证明 physical boundary | 三个 arm 的 `proven_non_text_boundary` 均为 0；g004 70 px 均 unresolved | 失败 |
| uncertainty fail-closed | 历史 v0.2 A1 曾认证 2 px 人工 `UNCERTAIN`；当前代码已加 barrier，但历史 evidence 不重写 | 历史反例仍支持 NO_GO |
| 通用能力/控制 | 锁定评估明确尚未证明 required control matrix | 失败 |

颜色指标也不构成反向放行：A1 对深蓝分层 recall 为 `0.54597701`、抗锯齿边缘
为 `0.01612903`；A2/A5 均为 0；本 FORM 中没有橙色文字正标签，橙色 recall
为 `null`。因此不应宣称 A5 已解决颜色问题，也不应把颜色观察扩展至 speaker
attribution 或 typesetting policy。

## 决定与理由

维持 `NO_GO` 的独立充分理由是：任一 arm 都没有同时建立完整的文字 support、
无 uncertainty/boundary 误认证、以及可泛化的 physical-boundary proof。g002
中的人工文字归属不能越过 103 px frozen protected overlap；g004 的少量像素也
不能因规模小而获得写权限。故 Stage B 所需的 correction budget、reservation、
Cleaner candidate、validator 或 Slice 3 integration 均无授权基础。

以下替代方案应拒绝：

- 将人工 `BUBBLE_BOUNDARY` 直接转成 `proven_non_text_boundary`；这是针对目标的人工特判。
- 以 g002 左缘、g004 窄冲突、蓝/橙色或坐标修改阈值；这违反通用性与 no case-specific tuning 约束。
- 以 `false_boundary_to_text = 0` 代替 boundary proof；该值来自 unresolved abstain。
- 将当前 A1 uncertainty barrier 的回归修复回填到 v0.2 evidence，或据此重开 Stage B；修复不抹除冻结实验的覆盖与 proof 缺口。

## 范围与风险

范围审查确认没有产品 `src/`、Slice 3 acceptance、case-72 frozen run、active
pointer 或原图写入；Stage A 只产出本地 evidence/FORM/lock。该隔离结论不等于
能力通过。主要剩余风险是将“人类看出文字/边框”误解为“算法已能安全授予写
权限”，或把 fail-closed 的 no-write 误报为清字成功。

## 验证与开放问题

- 已重新运行：`pytest -q -p no:cacheprovider tests/spikes/cleaning/physical_boundary`，`8 passed`。该结果只验证 Spike 的分类、guard、可重放及控制不变量，不代表 Cleaning 或 Slice 3 acceptance。
- 已复核锁值、人工组件数量、分层 recall 和 Gate 结论；与此前五份审查无实质矛盾。早期审查中记录的 `7 passed` 为当时快照，当前最终复跑结果以 `8 passed` 为准。
- 若未来另行授权，应先建立不依赖 target、颜色名称或人工标签反灌的 physical-boundary 像素级 ground truth/control matrix，并重新证明文字完整性、boundary proof 和 uncertainty guard；本审查不提供任何 Stage B 或 Slice 3 集成授权。
