# 110 Detection

Detection 从不可变页面 artifact 产生版本化文本区域候选及 provenance，为 Grouping/OCR 提供几何输入。Adapter 只返回候选，不访问数据库或决定接受；QualityCheckService 检查空结果、越界、重叠和明显漏检证据。

## Implementation Status

Primary text detection candidate 是 PaddleOCR 3.7.0，当前已缓存 detector asset 为 `PP-OCRv6_medium_det`。Paddle 在目标链路中主要承担文字 Detection；正式产品 profile/config、Provider Adapter 和真实 DetectionCheck 接入仍需在实现时完成。

当前 `ProcessPageService` 使用 FakeProvider；`AcceptedDetectionEvidenceSet`、artifact、acceptance provenance 和下游 exact binding lifecycle 已实现，但 `src/` 中没有真实 Paddle Detection Adapter。现有 Paddle 代码位于 `tools/experiments/`，只能标记为 `EXPERIMENT_ONLY`；FakeProvider acceptance 只能证明 lifecycle，不能证明 real Detection。

历史 YOLO 与真实样本 Spike 只证明工具可运行和局部输入形态，不构成产品质量门禁。Detection 的主要候选工具不再笼统视为完全开放，但正式模型配置、阈值、产品支持范围与 M2 系统性验收仍未关闭。

拒绝把模型输出直接提升为 active 结果或将模型缓存混入源数据。风险是普通正文漏检被 warning 掩盖、区域越界和 reading order 误推断。验证需覆盖空页、多区域、边界框裁剪、Provider refusal、版本复用和从正式入口到 accepted evidence 的真实调用链；M2 系统性验收集仍开放。
