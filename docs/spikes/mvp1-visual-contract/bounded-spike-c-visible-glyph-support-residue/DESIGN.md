# Spike C 设计说明（实现前）

## 主候选方案

`visible_support_candidate = text_core` 的有限局部扩张，扩张只保留与 core 同连通域邻近、
或相对 local background 具有足够 Lab 对比的像素。背景用 instance 内安全 ring 的 Lab
中位数/MAD 估计，避免把白色/浅灰气泡中的浅色描边因绝对亮度过高漏掉。

清理 control output 的 residue 是：位于 source support 或有限邻域、相对 local background
有足够对比、并形成最小连通结构的像素组件。完整字符/关键笔画 control 直接验证组件
结构；孤立小斑点与普通背景变化必须不触发 issue。

## QualityIssue 边界

本轮只生成可被未来 `QualityCheckService` 消费的 immutable issue draft。它含根因、segment/
instance binding、mask/component/hash/contrast/completeness 证据；不创建数据库记录，不更新
状态，也不决定 retry/fallback/skip/block。未来 `WorkflowLoopEngine` 才拥有这些决策。

## 拒绝的替代方案

- 单一 luminance 阈值：已被 Spike B 的浅色 halo 反例否定；
- 仅扩大固定 dilation：会把普通背景吞入 residue，不能处理局部灰白差异；
- 用 real Cleaner 测试：扩大授权范围，且会把 mask、重建和 Validator 失败混在一起；
- 人工 overlay 直接作为 candidate：造成 oracle 泄漏。

## 风险与停止

颜色/扫描噪声可能使 local contrast 与字形结构混淆。本轮只允许一个主候选和一次聚焦修订；
若 B/C/D 与 E 无法同时成立，停止为 `CHANGES_REQUIRED`，不继续阈值搜索。

## 允许文件

- `docs/spikes/mvp1-visual-contract/bounded-spike-c-visible-glyph-support-residue/**`
- `tools/spikes/mvp1_visual_contract/spike_c.py`
- `tests/unit/test_mvp1_visual_contract_spike_c.py`
- `data/local/mvp1-visual-contract-spike-c-v0.1/**`（忽略，不提交）

其他文件禁止修改；如需生产修改，停止并报告。
