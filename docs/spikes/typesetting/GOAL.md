# 自动嵌字可行性 Spike：GOAL

## 目标

回答一个有限问题：在已有人工认可的 E1 清字页和容器安全区域上，规则式自动嵌字是否足以支撑 MVP 的普通对白基础排版。

本 Spike 不评价翻译质量，不证明 Cleaning 或 association 的整页覆盖率，也不接入 Workflow。

## 冻结范围

- 输入：Goal 6 的 `case-71`、`case-72`，仅 8 个 E1 context。
- 文字：预先声明的短、中、长中文排版探针；不是原文翻译。
- 输出：R0 / R1 / R2 整页候选、对照图、机器指标和人工审查表。
- R0：矩形 bbox、单字体、黑字、无描边、字符级换行。
- R1：coarse container mask 向内收缩、中文禁则、自适应字号、光学近似居中、4×渲染；现有 cleaning safe edit mask 不冒充 typesetting safe region。
- R2：R1 加高置信度原文字色继承、条件描边、对白/强调两种样式。

## GO / NO-GO

GO 只表示值得实现 P0 Typesetter：

- 8 个 context 中至少 6 个由 R1 或 R2 达到 `ACCEPTABLE`；
- 所有被接受候选无可见越界、不可读小字或严重遮挡；
- R1 相对 R0 在非矩形容器中有可见收益，或至少不退化；
- 失败可由 `no_fit`、overflow、低对比度等指标解释并安全跳过。

任一原图被覆盖、跨 context 写入、字体缺字或多数普通对白无法排入，立即 NO-GO/STOP。

## 明确排除

- SFX、自由文字、竖排中文、路径文字、透视变形、艺术字重绘；
- OCR、翻译、Cleaning、association 的重新训练或调参；
- Provider、ArtifactService、QualityIssue、WorkflowLoop 集成；
- 自动接受或产品准确率声明。
