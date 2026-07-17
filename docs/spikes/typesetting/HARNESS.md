# 自动嵌字可行性 Spike：HARNESS

## 输入合同

复用 Goal 6 已冻结的 S1、Goal 5 association lock、P0 cleaning mask lock 和 E1-only 清字页。输入源文件仅校验和读取，不覆盖。

Goal 6 的 `safe` 是清字写回区域，会主动挖掉结构和不确定像素，不能直接当作文字可占用区域。当前没有独立 `safe text region` 产物，因此首轮按优先级回退到 coarse container mask 向内收缩 8 px。旧结果没有单独持久化 coarse mask；harness 从 Goal 6 全量 context overlay 的像素差恢复 union，再用冻结 S1 group seed 做确定性归属，且不得重跑 B1。该适配器只用于复用旧证据；正式实现必须直接持久化 typesetting region。

系统字体通过命令行注入并记录 SHA-256；仓库不分发字体文件。首轮使用本机 Noto Sans SC 常规/粗体。占位句只覆盖排版长度与标点形状，不得解释为译文。

## 三臂对照

| 臂 | 空间约束 | 换行/字号 | 样式 |
|---|---|---|---|
| R0 | safe region bbox | 字符级 DP、矩形内拟合 | 黑字、单字体、无描边 |
| R1 | 腐蚀后的 safe region Mask | 中文禁则、自适应字号、近似视觉居中 | 黑字、单字体、无描边 |
| R2 | 同 R1 | 同 R1 | 原文字色回退、条件描边、对白/强调 |

R0 仍允许字号拟合，避免用必然溢出的基线夸大 R1；R1/R2 的额外证据只来自 Mask 和样式。

## 输出

每页生成：`source.png`、`cleaned-input.png`、`r0.png`、`r1.png`、`r2.png`、`comparison.png`、`result.json`。根目录生成 `matrix.json`。所有产物位于 `data/local/`，不进入版本历史。

## 指标

- `font_size`、`line_count`；同一字号允许比较多种目标行宽，避免单一换行方案迫使字号无谓缩小；
- `overflow_ratio` 必须为 0，`minimum_inner_margin` 至少 2 px，`boundary_touch` 必须为 false；
- `contrast_ratio`、`style`、`stroke_width`；
- 每臂成功布局数与 `no_fit`；
- 原图前后 SHA-256。

人工评价优先于单一分数：`ACCEPTABLE / REVIEW / REJECT`，并记录可读性、越界/边缘接触、居中、换行、字号和样式。

## 风险与已拒绝方案

- `safe` 是现阶段最可靠的有限区域，但不是正式 typesetting region GT；因此结论仅限可靠 E1 输入。
- 从诊断 overlay 恢复 mask 是历史资产适配，不得成为产品接口。
- 两页不能代表整书分布；本轮只判断“值得继续”，不冻结全局阈值。
- 暂不直接移植第三方项目，避免把其职责边界和依赖带入当前架构。
- 暂不做字体识别；中文字体授权、字形覆盖和风格映射留到实现前单独冻结。

## 验证场景

- 短句、中句、长句；问号、逗号、括号、感叹号；
- 椭圆/不规则安全区域；多个独立容器同页；
- 彩色原字的高/低置信度回退；
- 无法拟合时不写入该 context。
