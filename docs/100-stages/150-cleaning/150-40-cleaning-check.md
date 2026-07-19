# 150 CleaningCheck

CleaningCheck 检查候选输出是否只修改已授权像素、完整覆盖声明处理的 required text、保持 protected/uncertainty/outside-safe 不写、没有跨实例写入，并评估残字、边界损伤、背景接缝和原图 hash。它只产生 QualityIssue drafts，不接受结果或推进 active pointer。

当前 fail-closed 条件：任何 unknown physical boundary、unresolved support、protected/uncertainty 写入、required text 遗漏、跨实例修改或 artifact/hash 不一致都阻断该实例。允许 skip 时必须保留原图内容并解释原因，不能把正文静默清空。

拒绝用“输出文件存在”、平均像素变化或单个人工 PASS 代替合同。风险是 validator 未观察 Cleaner 实际写入、GT 泄漏到规则和阈值对当前 case 过拟合。验证覆盖全通过、部分实例阻断、空 mask、越界 mask、残字、边界损伤、重复执行、崩溃和原图不变；通用 physical-boundary gate 尚未通过。
