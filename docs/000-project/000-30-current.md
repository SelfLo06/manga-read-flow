# 当前状态

更新时间：2026-07-19。

## 一句话结论

M0 Architecture Proof 已关闭；M1 Single-Page Visual Closure 是当前主线，但尚未形成可交付的完整单页中文漫画结果。

## 已确认事实

- 后端已证明 Repository/UoW、ArtifactService、Provider Adapter、Workflow Loop、QualityIssue、active pointer、恢复/幂等和 export readiness 的核心机制。
- topology eligibility、pixel evidence、visible glyph residue、real cleaner 和单页 Cleaning 纵向切片已有受限证据；它们只证明明确样本和条件。
- 最新 physical-bubble-boundary Stage A 诊断已完成。A1/A2/A5 当前均为 NO_GO；g002/g004 保持 `BLOCKED_PENDING_CAPABILITY`；没有运行本 Spike 的实际 Cleaning。
- g002 的 page marker 是 basin/unsafe 位置的因果贡献因素但不是安全修复；g004 的水平候选只解释 70 个 boundary 像素中的 1 个。颜色没有被证明为主要或唯一根因。
- Typesetting 历史输出为 NO_GO；输入合同/region grounding 仅为 GO_WITH_CHANGES。最小 Web 入口尚未实现。

## 已冻结决定

原图不覆盖；不以放宽阈值绕过 protected/uncertainty；人工标签只作评估 oracle；Provider 拒绝不绕过；M1 不吸收 M2/M3 的语义和规模化范围。仓库编号不改变 Workflow 语义。

## 最近下一步

1. 设计独立的 `PhysicalBoundaryEvidence v0.2` 候选：带 provenance 的 bubble/panel/page-edge/unknown boundary graph，并预先冻结 controls。
2. 通过独立 gate 后才申请新的 evidence revision 与 Stage B；在此之前不创建 Cleaner candidate 或 active-pointer 更新。
3. physical-boundary 能力成立后，继续单页 Cleaning/Typesetting 视觉闭环和最小产品入口。

## 风险与开放问题

主要风险是把“当前 arms NO_GO”误写成研究方向 NO_GO、把受控消融误当安全修复、或把 no-write 指标误报为 Cleaning PASS。开放问题包括 BubbleInstance 持久化表达、M1 验收样本、physical-boundary 通用证据和 actual-glyph TypesettingCheck 阈值。
