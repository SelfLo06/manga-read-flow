# Detection + OCR Real Tool Spike — GOAL

## 1. 目标

验证以下组合是否值得进入最小 Provider Adapter 设计：

```text
PaddleOCR Detection + manga-ocr Recognition
```

本轮必须分别判断：

- PaddleOCR 对漫画文本区域的检测能力；
- manga-ocr 在人工 GT crop 上的纯 OCR 能力；
- Detection 输出参与裁剪后的端到端表现；
- 横排、竖排、小字、彩色文字、复杂背景、弱对比、倾斜文字的失败模式；
- 初始化时间、单图耗时、稳定性与环境风险。

## 2. 实验范围

计分范围：

- synthetic：11 regions；
- real core dialogue：16 regions；
- 合计：27 regions。

18 个 auxiliary pending regions 不计入核心分数，只记录是否被检测。

## 3. 必须分开的实验

### 实验 A：纯 OCR

```text
GT container bbox -> crop -> manga-ocr -> OCR 指标
```

用于排除 Detection 误差。

### 实验 B：Detection + OCR

```text
完整图片 -> PaddleOCR Detection -> 几何匹配/分组 -> crop -> manga-ocr
```

用于区分：漏检、误检、碎片化、分组错误、阅读顺序错误和 OCR 错误。

## 4. 非目标

本 Spike 不负责：

- 实现正式 DetectorProvider / OCRProvider；
- 修改 `src/manga_read_flow/**`；
- 接入 WorkflowLoopEngine、ArtifactService、Repository 或 SQLite；
- 创建正式 artifact、QualityIssue 或 WorkflowDecision；
- 实现 API、UI、Batch、Export；
- 训练模型、自动调参或完整 container grouping 算法。

## 5. 强制边界

- 原图和 ground truth 只读；
- 模型输出不得用于生成或修正 ground truth；
- expected text 不得参与框匹配、裁剪或分组；
- 所有输出写入 `local_samples/spike_outputs/{run_id}/`；
- 不修改依赖；
- 不 commit，不 push。

## 6. 退出结论

最终只允许：

- `GO`
- `CONDITIONAL_GO`
- `FURTHER_SPIKE`
- `NO_GO`

结论必须基于逐样本结果、定量指标、失败类型、性能、环境稳定性和 MVP 影响。
