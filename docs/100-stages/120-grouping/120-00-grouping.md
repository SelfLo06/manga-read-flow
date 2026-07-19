# 120 Grouping

Grouping 将 Detection/OCR 的文字片段关联到 BubbleInstance 或等价文本容器，并产出可追踪的 segment、container、layout slot 与 topology 关系。它是语义输入与 Cleaning/Typesetting 写入边界之间的桥梁。

text-seeded association、局部 routing 和视觉合同已有可复用 harness 与受限正例；它们没有授权全自动 association、mask 或 Cleaning。接触气泡、跨画格/页边结构和 merge/split 仍可能造成容器归属不确定。

当前选择 fail-closed：证据不足的实例进入 REVIEW/BLOCKED，不跨未知 physical boundary。拒绝按最近 bbox 或单阈值把所有片段强行归组，因为会扩大错误写入。验证覆盖单气泡、多 segment、接触气泡、旁白框、跨画格候选、局部编辑和 provenance 对账。BubbleInstance 是否先作为持久化实体仍开放。
