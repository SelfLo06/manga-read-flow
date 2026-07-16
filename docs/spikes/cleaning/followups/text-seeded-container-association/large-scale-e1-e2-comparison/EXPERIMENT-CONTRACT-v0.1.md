# 40 页 E1 与 E1+E2 激进清字对比实验：实验契约 v0.1

状态：用户授权执行；仅用于评估，非产品策略变更。

## 目的

在同一本、同一批 40 页原图上，比较当前冻结的 `E1-only` 与实验性
`E1+E2` 自动应用的可见效果、覆盖量和耗时。它回答“E2 值不值得继续扩大
验证”，不回答“E2 已可作为 MVP 自动清字策略”。

## 固定输入与共同上游

输入为 `data/local/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)` 的全部 40 个 JPG，按文件名排序。

共同上游为：Paddle 检测 fragment、冻结的 Grouping、Goal 5 路由与关联锁、
Goal 6 `P0_conservative` mask。当前关联算法只消费文字几何/分组先验；不消费
OCR 字符串。因此本实验的 “OCR+清字” 指文字区域检测/分组到清字链路，**不**把
manga-ocr 字符串识别伪装成会影响 E1/E2 决策的步骤。

## 对比臂

| 臂 | 应用规则 | E2 含义 |
| --- | --- | --- |
| `E1_ONLY` | 仅在 E1 context 的 `M_effective` 内作 border-sampled fill | 不应用 |
| `E1_PLUS_E2_AGGRESSIVE_COMPARISON` | E1 同上；E2 context 的 `M_effective` 内自动作 Telea radius=2 | 仅本次实验允许的激进比较臂 |

E3、bounded support、regionless abstention、topology uncertain 和无有效 mask 的 context
在两臂中均保持原样。任何像素都不得在 `M_effective` 外变化。

## 与既有冻结结论的关系

既有锁定结论是：E1 可生成供人工审查的候选；E2 仅比较，E3 不自动清。这与本次
“自动应用 E2”表面冲突。该冲突由维护者本轮针对**隔离实验**的明确授权解决；本
契约不改写算法锁、不创建 `AUTO_ACCEPT`、不接入 `CleanerProvider` 或 Workflow，
也不生成产品 artifact 或 export。

## 输出与度量

每页输出原图副本、四层 mask 应用语义 overlay、两臂候选和四联缩略图。汇总记录：

1. 检测/分组总耗时；
2. 关联和 mask 构建耗时；
3. 两臂各自的实际写回耗时与 changed pixels；
4. E1/E2/E3 context 数、无 seed 页数、路由与 abstain 原因；
5. `changed_outside_effective = 0` 的逐页断言；
6. 供人工审阅的整书缩略对照总览。

不产出像素准确率、清字“准确率”、自动采纳率或发布级质量声明；没有人工标注就
不存在这些真值指标。

## 停止条件

任一条件触发即停止该页并将整次 run 标记 `STOPPED`：源文件 hash 变化、输入页数
不是 40、检测/关联失败、mask 跨 context 重叠、候选在有效 mask 外改像素、或输出
目录已存在。已完成页保留为诊断证据，但不宣称实验通过。

运行中追加的资源安全事实：`case-10` 的两个超大检测 seed 是拟声词/装饰候选，最大
单 seed 面积约为页面 12.7%，旧 priority-flood B1 在此输入上被系统 OOM 终止。为保证
40 页批处理的失败隔离，本 runner 在进入 B1 前对单 seed 面积超过 10% 的页面做
`REGIONLESS_ABSTENTION / oversized_fragment_seed`。这不是阈值调参或 E2 放宽：两臂
都不写入该页，且该原因会在矩阵中单独计数。

## 人工审查结论

运行后只需判断：E2 是否在足够多的普通 E2 气泡中降低残字，且没有系统性结构伤害。
若未达到，维持 E2 comparison-only；若表现良好，下一步仍是扩大独立标注验证，而非
直接升级 MVP 自动策略。
