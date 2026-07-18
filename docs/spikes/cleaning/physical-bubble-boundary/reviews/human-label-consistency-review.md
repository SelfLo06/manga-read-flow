# Stage A Human-label Consistency Review

审查范围：仅审查 `stage-a-run-v0.2` 的人工 FORM、其锁定材料与已冻结诊断；不裁决候选、Stage B 或最终 Gate。

## 结论

人工标签完整、内部一致，并与维护者补充复核一致：g002 的争议 support 主要是文字主体／字缘，g004 的两个争议组件是高风险的真实气泡边框；g002 的最后 2 px 仍为 `UNCERTAIN`。这使现有 `fail-closed` blocker 的归因更精确，但**不**授权写入任一 protected 像素，也不能单凭本轮标签放行 Stage B。

颜色不是本轮 blocker 的已证明根因。深蓝、橙色与抗锯齿分层只能作为 evidence/reporting strata；不能据此放宽全局阈值、宣称 A5 已获益，或扩展至 speaker attribution／typesetting policy。

## 审查输入与完整性

- `FORM-stage-a.md` 有 12 个唯一组件 ID；每个均填有允许的 `HUMAN_CLASS`、`BOUNDARY_DAMAGE_RISK`、`ALLOW_AS_REQUIRED_TEXT`、非空 `NOTES`，并附加 `COLOR_STRATUM`。
- g002：10 个组件、710 px。9 个 `TEXT_EDGE`（708 px），均为 `LOW` / `YES`；component-10 为 2 px `UNCERTAIN`、`LOW` / `NO`。
- g004：2 个组件、70 px，均为 `BUBBLE_BOUNDARY`、`HIGH` / `NO`。
- 填表前的 111 项图像／mask／summary 由 `review-material-lock.json` 锁定；人工填写使旧清单中的 FORM 摘要预期失配。`human-review-lock.json` 将该 pre-label lock 的 SHA-256 与当前 FORM SHA-256 `4a57b262…d8757d` 一并锁定，并逐项镜像 12 条人工结果。审查时二者与磁盘一致。

## 与冻结诊断及维护者复核的一致性

| 目标 | 人工结论 | 一致性判断 | 仍然有效的安全约束 |
| --- | --- | --- | --- |
| g002 | 708 px 为深蓝字形／抗锯齿字缘，2 px 不确定；组件 01/02 虽有 protected overlap，人工仍确认其文字归属。 | 与“文字 evidence 总体正确、左页缘导致边界形状敏感、阻塞来自 protected/uncertainty corridor”一致。 | 文字归属不等于可写性；任何 required text 落入 protected 或 unresolved uncertainty 时仍不得由现有 safe-only 路径清除。 |
| g004 | 45 px 与 25 px 均为连续黑色对白框斜边及其抗锯齿带。 | 与“窄的局部物理边界冲突、非橙色字体问题”一致。 | 必须保留为 physical boundary；不得因 component 很小、邻近橙色或 unsafe ratio 很低而转为 required_text。 |
| g003 | 本 FORM 无 g003 项。 | 不影响既定 `REVIEW`；不得据此升级为 E1。 | 继续保持既有 eligibility 结论。 |

## 候选可／不可证明的事项

1. A1 在 g002 的部分文字组件保留 required_text，但还把 component-10 的 2 px（人工 `UNCERTAIN`）标为 required_text；所以它不能以该输出声明全部人工标签一致，也不能作为安全放行依据。
2. A2 与 A5 对全部 12 个 unsafe 组件均保守地输出 `unresolved_uncertain`，没有把人工确认的 g004 边框变为 required_text；它们满足“未见 boundary-to-text 误放行”的必要观察，但不满足 `unresolved_uncertain = 0`，不能进入 Cleaner。
3. 人工标签可证明组件级的视觉归属，不能替代逐像素 ground truth、候选的 text-edge precision/recall，或 `required_text` 全在 safe-edit 的证明。尤其 g002 的 103 个 protected-overlap px 仍要求受限 physical-boundary capability；本审查不允许把它们移出 required 或改为 safe。
4. 因此 Stage A 可据此继续做候选／控制的定量一致性审查；本审查本身不构成 Stage A GO，亦不授权 Stage B。

## 颜色证据边界

- 标签记录了 g002 两个 `DEEP_BLUE` 字形组件、若干 `ANTIALIAS_EDGE`，及 g004 的 `ANTIALIAS_EDGE` 边框；g004 注释明确橙色仅是组件外邻接背景。
- 当前人工集没有“橙色文字”的正样本，也不是像素级颜色真值；`stage-a-summary.json` 内 A5 的分层 precision/recall 仍是 `PENDING_HUMAN_LABELS` 的 pre-label 输出。不能从“g002 多为深蓝文字、g004 邻近橙色”推出颜色导致 blocker，或用这些标签替代深蓝、橙色、抗锯齿的 precision/recall 计算。
- 后续若报告颜色指标，须从已锁定的人工标签和同配置正／负控制重新计算，显式报告样本缺失与不确定性；不得按色名、case、target、坐标建立阈值或路径。

## 风险与后续检查

- 最大风险是将人工 `ALLOW_AS_REQUIRED_TEXT=YES` 误读为“可越过 protected 写入”。该字段只确认文字 evidence，不能覆盖 protected、uncertainty 或 validator 合同。
- g002 的左缘几何敏感性和 g004 的窄边框都支持受限 physical-boundary 研究，不支持全局阈值放宽。
- 下一审查应以同一算法配置核算 candidate-vs-human 的 component／像素映射、false boundary-to-text、unresolved 数量、控制样本和 case-specific branch audit。只有满足零边框误放行及完整 safe-edit evidence 后，才可讨论 Stage B。

## 验证记录

- 字段计数：6 类字段各 12/12；组件 ID 为 12 个唯一值。
- 人工像素汇总：g002 `708 TEXT_EDGE + 2 UNCERTAIN = 710`；g004 `70 BUBBLE_BOUNDARY`。
- Hash：pre-label lock 的 110 项非 FORM 材料均匹配；旧 FORM 摘要失配是人工填写后的预期状态。post-label `human-review-lock.json` 同时匹配当前 FORM 和 pre-label lock 文件。

未决问题：本人工 FORM 不提供逐像素标签，亦不覆盖橙色文字正样本；这些限制必须保留到后续指标和 Gate，不能静默补全。
