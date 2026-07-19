# 160 Typesetting

Typesetting 以 active translation、BubbleInstance/layout slot、已接受 cleaned artifact 和字体配置为输入，生成版本化 typeset artifact；不覆盖 cleaned image 或原图。TypesettingCheck 应基于 renderer 实际 glyph 占用验证溢出、遮挡、留白、对齐与可读性。

当前输入合同/region grounding 仅为 GO_WITH_CHANGES，历史输出整体为 NO_GO；尚无产品级普通气泡完整输出。M1 需要在冻结单页上完成实际视觉检查，复杂拟声词和艺术字明确后置。

拒绝仅用预估文本 bbox 代替实际 glyph、跨容器排字或在 Cleaning 未接受时继续。风险包括字体缺失、中文断行、竖排/旋转、溢出和视觉中心偏移。验证覆盖短长文本、空译文、多 segment、字体回退、实际 glyph mask、局部重嵌和 stale propagation；字体集与阈值待 M1 校准。
