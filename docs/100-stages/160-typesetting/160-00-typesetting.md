# 160 Typesetting

Typesetting 以 active translation、BubbleInstance/layout slot、已接受 cleaned artifact 和字体配置为输入，生成版本化 typeset artifact；不覆盖 cleaned image 或原图。TypesettingCheck 应基于 renderer 实际 glyph 占用验证溢出、遮挡、留白、对齐与可读性。

## Implementation Status

```text
Historical output verdict: NO_GO
Input contract / region grounding: GO_WITH_CHANGES
Real product renderer: NOT IMPLEMENTED / NOT PROVEN
Actual-glyph product Check: NOT CLOSED
Real accepted Translation + Cleaning integration: NOT IMPLEMENTED
M1: NOT COMPLETE
```

当前只有历史实验和 FakeProvider typesetting artifact/pointer lifecycle；FakeProvider persistence 不构成真实排版能力。尚无产品级普通气泡完整输出，也没有从 accepted Translation、accepted Cleaning 和 accepted container/layout binding 进入真实 renderer 的正式调用链。M1 需要在冻结单页上完成实际视觉检查，复杂拟声词和艺术字明确后置。

拒绝仅用预估文本 bbox 代替实际 glyph、跨容器排字、在 Cleaning 未接受时继续，或把 FakeProvider 图片提升为真实排版证据。风险包括字体缺失、中文断行、竖排/旋转、溢出和视觉中心偏移。验证需覆盖短长文本、空译文、多 segment、字体回退、实际 glyph mask、正式入口、局部重嵌和 stale propagation；字体集与阈值待 M1 校准。
