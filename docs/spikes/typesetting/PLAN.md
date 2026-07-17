# 自动嵌字可行性 Spike：PLAN

1. 冻结两页、8 个 E1 context、字体哈希和占位句，不再调 Cleaning/association；明确 cleaning safe edit mask 与 typesetting region 不是同一语义，消费冻结 overlay 而不重跑 B1。
2. 运行 R0/R1/R2，生成整页对照和机器指标。
3. 先检查硬合同：源图哈希、context 数、越界和 `no_fit`。
4. 用户仅对对照图填写选择题式审查表。
5. 按 GOAL 门禁裁决：进入 P0 Typesetter 详细设计、保留为手动功能，或停止当前路线。

本轮不接 Workflow。若 GO，下一轮才定义正式输入 DTO、TypesetterProvider 输出候选、QualityCheckService 规则和 WorkflowLoopEngine 的缩字/重排/回退动作。

## 开放问题

- 正式输入应使用独立 `typesetting_region`，还是从 container/safe edit region 派生？
- 最小字号应按图片分辨率、气泡高度还是阅读缩放比例定义？
- 默认字体的许可、打包方式和缺字回退链如何冻结？
- R2 的样式继承是否有足够收益，还是 MVP 只保留 R1？
