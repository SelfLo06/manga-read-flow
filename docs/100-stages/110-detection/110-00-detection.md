# 110 Detection

Detection 从不可变页面 artifact 产生版本化文本区域候选及 provenance，为 Grouping/OCR 提供几何输入。Adapter 只返回候选，不访问数据库或决定接受；QualityCheckService 检查空结果、越界、重叠和明显漏检证据。

历史 YOLO 与真实样本 Spike 只证明工具可运行和局部输入形态，不构成产品质量门禁。M1 可用可信输入隔离视觉后半链路；系统性 Detection 质量提升属于 M2。

拒绝把模型输出直接提升为 active 结果或将模型缓存混入源数据。风险是普通正文漏检被 warning 掩盖、区域越界和 reading order 误推断。验证需覆盖空页、多区域、边界框裁剪、Provider refusal 和版本复用；模型选择与 M2 验收集仍开放。
