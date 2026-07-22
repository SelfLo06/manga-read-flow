# 当前状态

更新时间：2026-07-22。

## 一句话结论

M0 Architecture Proof 已关闭；M1 Single-Page Visual Closure 尚无真实用户产品闭环。当前仓库的架构生命周期、部分阶段生命周期和实验能力领先于真实产品调用链，开发主线改为按用户产品路径逐边关闭真实能力。

## 当前实际存在的链路

当前并存三条未串联链路：

```text
1. Import
   → FakeProvider 全阶段循环
   → ready_for_export

   只证明 M0 生命周期机制；不证明真实 Provider；不生成实际用户导出文件。

2. accepted Detection + accepted OCR
   → Grouping candidate
   → GroupingCheck
   → Workflow acceptance
   → active Grouping

   Grouping 生命周期较完整；没有 production Grouping producer；未自动接入 process_page。

3. 调用方提供 VisualContract 和 masks
   → real Cleaner
   → CleaningCheck
   → accepted cleaned artifact

   Cleaner 真实；权威视觉输入仍由测试或 runner 手工构造；尚未来自正式 Physical Boundary 产品链。
```

## 当前 Reality Summary

状态词区分正式集成、部分产品能力、仅生命周期、仅 FakeProvider、仅实验、仅设计和未实现，不能相互替代。

| 能力 | 当前状态 | 事实边界 |
| --- | --- | --- |
| Import backend | `FORMAL_PATH_INTEGRATED` | `ImportPageService`、ArtifactService 和 Project persistence 已接通 |
| 用户 Import / API / Web | `NOT_IMPLEMENTED` | 无上传、预览或用户操作入口 |
| Detection | `FAKEPROVIDER_ONLY` | accepted evidence 生命周期存在；真实 Paddle Adapter 未进入产品代码 |
| OCR | `FAKEPROVIDER_ONLY` | result/pointer 生命周期部分存在；真实 crop/Adapter/OCRCheck/编辑闭环未接入 |
| Grouping | `PRODUCT_PARTIAL` | Slice 1A–1E 已实现；production producer 和 post-OCR orchestration 不存在 |
| Translation | `FAKEPROVIDER_ONLY` | 真实 LLM Adapter、正式输入装配和 real-provider Check 未实现 |
| Physical Boundary | `PRODUCT_PARTIAL` | 正式 Grouping input selector 已有；producer、Check、revision 和 pointer 未实现 |
| Cleaning | `PRODUCT_PARTIAL` | real Cleaner、Check 和接受路径存在；正式上游未提供 VisualContract/masks |
| Typesetting | `FAKEPROVIDER_ONLY` | artifact/pointer lifecycle 存在；真实 renderer 仅有 `EXPERIMENT_ONLY` 历史 `NO_GO`，actual-glyph acceptance 未关闭 |
| Export | `LIFECYCLE_ONLY` | readiness/blocker 机制存在；writer、record、manifest 和用户文件不存在 |
| Review / Edit | `LIFECYCLE_ONLY` | 目标版本语义存在；正式编辑入口和完整原子 stale 传播未关闭 |
| Workflow / Recovery | `FORMAL_PATH_INTEGRATED` | M0 FakeProvider 路径及部分独立阶段机制已验证，不等于真实全链恢复 |
| API / Web | `NOT_IMPLEMENTED` | 无 FastAPI/Next.js 产品入口 |

## 当前开发原则

每个产品能力采用 Capability Closure Loop：

```text
最小代码与合同核实
→ 只验证必要的高风险假设
→ 立即实现正式 extension point
→ 接入正式入口
→ Check
→ Workflow decision
→ accepted/current result
→ direct downstream
→ 用户可见结果
```

设计、必要实验和正式实现必须围绕同一 capability 连续收敛。实验结果不能替代产品 source of truth，也不能在没有 Productization Exit 时长期横向展开。

## 当前主线

沿产品顺序关闭最早未完成的正式边。最新全链审查显示，用户 Import 入口和 real Detection 是最早断点。

首个候选纵向切片：

```text
单页输入
→ ImportPageService
→ immutable source artifact
→ real Paddle Detection
→ DetectionCheck
→ Workflow acceptance
→ accepted Detection evidence
→ 用户可见 Detection 状态/预览
```

最终切片范围仍需在开始实现前根据最新代码完成 Preflight；本文不展开完整任务清单。

## 已冻结决定

原图不覆盖；不以放宽阈值绕过 protected/uncertainty；人工标签只作评估 oracle；Provider 拒绝不绕过；M1 不吸收 M2/M3 的系统性语义、跨页和规模化范围。仓库编号不改变 Workflow 语义。

## 风险与开放问题

主要风险包括：把 FakeProvider 生命周期误报为真实 Provider；把实验 runner 误报为产品入口；lifecycle 已实现但 producer 缺失；把 `ready_for_export` 误报为实际 Export；用手工构造的下游输入掩盖真实上游断裂；继续横向实验但没有 Productization Exit；以及 OCR/Translation replacement 后完整、原子的 stale propagation 尚未证明。

Physical Boundary 的 A1/A2/A5 `NO_GO`、Typesetting 历史 `NO_GO` 和受限 Cleaning 证据仍然有效，但它们不再单独定义最近产品主线。开放问题还包括 M1 冻结验收样本、最小用户入口合同、真实 Provider profile、BubbleInstance 产品表达和 actual-glyph TypesettingCheck 阈值。
