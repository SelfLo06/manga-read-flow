# 150 Cleaning 已知问题

| ID | 问题 | 当前证据与影响 |
| --- | --- | --- |
| CLN-150-001 | physical boundary 缺少通用可证明语义 | g002 的 page marker 影响 basin 但不是安全修复；g004 的水平候选只解释 1/70。未知边界必须阻断写入。 |
| CLN-150-002 | text support 与 protected/uncertainty 冲突 | g002 的 708 个确认文字中 A1 只认证 288，420 unresolved；阈值放宽可能伤害边界或文字。 |
| CLN-150-003 | 容器 topology 在接触气泡/跨结构场景不稳定 | 错误 grouping 会让 mask、Cleaner 和 Typesetting 在错误实例上工作。 |
| CLN-150-004 | 局部正例不能泛化为完整页面 | case-71 的允许段可清除，但同簇另一段因 safe-edit 不足阻塞；不能宣称整页成功。 |
| CLN-150-005 | 实际视觉残字、边界损伤和背景接缝仍需统一 gate | 自动像素指标与人工可读性可能不一致；需在冻结 controls 上校准。 |

处理原则：问题必须由独立 controls、像素级 GT 和 provenance 证据关闭；人工标签仅作 oracle。若证据不足，保留原图并产生可解释 QualityIssue。开放问题是 boundary graph 分类、truncated-by-page 表达和支持范围的最小 GT 组成。
