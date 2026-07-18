# 漫画阅读流程——新对话交接（2026-07-18）

> 历史快照：本文记录 Slice 1 开始前的交接状态。Slice 1 后续已经完成并通过 Gate；当前状态请从 [`docs/README.md`](../../README.md) 进入。本文不得作为当前任务授权。

## 项目与当前任务

项目处于 MVP-1「高质量单页视觉闭环」。M0 架构验证已完成；当前不做 Batch、UI、Typesetting 或 OCR/Translation 质量优化。下一实际工作是实现 Full-page Cleaning Ledger 的最小持久化切片，之后才恢复 case-71 Closure 与 case-72 generalization。

## Git：先保留，不得清理

- branch：`main`；HEAD：`6b2d12facb07c88b2f5f42c29fe3f0507ac280b1`。
- 已提交 Slice E：`6b2d12f feat(mvp1): add bounded single-page cleaning slice`。
- 未提交但已人工验收的 Slice F：`clean_single_page.py`、`quality/__init__.py`、`text_aware_boundary.py`、对应 tests、工具脚本和 Spike F REPORT/GATE。
- 未提交设计文档：`docs/design/full-page-cleaning-ledger/{GOAL,HARNESS}.md` 与 `final/*`。
- 不得 reset/stash/checkout/rebase/clean；先识别 Slice F、设计文档和后续新改动。

## 已冻结事实

- Slice E 证明正式 Provider→ArtifactService→Repository/UoW→QualityCheck→decision 路径，但服务强制恰好一个 E1，不能构成全页。
- Slice F：case-71 `g002/s02` correction 通过，unsafe required `23→0`，并重验 `g002/s01`；overlap/cross-write=0。其他四项缺 pixel ledger，page 仍 block、pointer 为 null。
- case-71 有 6 segment；只有 g002/s01、g002/s02 有完整局部 PASS evidence。
- case-72：g002 unsafe=710、g004 unsafe=70、g003 review/E3；g005/g007 仍缺完整 ledger。
- 普通对白/旁白不得因 E2/E3/missing evidence 静默变成 non-blocking skip；只有明确范围外且保留原文的 SFX/free-text/non-text 可 non-blocking。

## 已完成设计（尚未实现）

必读：

- `docs/design/full-page-cleaning-ledger/GOAL.md`
- `docs/design/full-page-cleaning-ledger/HARNESS.md`
- `docs/design/full-page-cleaning-ledger/final/full-page-cleaning-ledger-dd-v0.1.md`
- `docs/design/full-page-cleaning-ledger/final/schema-outline.md`
- `docs/design/full-page-cleaning-ledger/final/migration-decision.md`
- `docs/design/full-page-cleaning-ledger/final/open-questions.md`

冻结决策：新 `PageCleaningRun`；immutable inventory 与独立 disposition ledger；per-instance immutable result；从同一 original 确定性组合的 member/candidate；页级 validator；一次 durable correction reservation；规范化 issue relations；仅 atomic acceptance 可更新 pointer；stale/缺失/hash mismatch 时 guarded UoW 清空 pointer；schema 为 additive `project_full_page_cleaning_ledger_v3`，不回填旧 Spike E/F。

最终独立 Harness review=`PASS_WITH_OPEN_QUESTIONS`：30/30 场景可由设计表达，不代表实现或 Closure 已通过。proposal/review 被 `.gitignore` 忽略，final 文档未忽略。

## 新对话应做什么

先做新的窄实现 Goal：**Full-page Cleaning Ledger Persistence Slice 1**。范围仅：v3 migration、named repository/UoW、run/inventory/disposition、correction reservation 与 focused migration/repository tests。禁止本 slice 做 Cleaner 算法、全页 composition、case-71 Closure、case-72、Typesetting/API/UI/Batch。

开始前：检查 Git；完整阅读 AGENTS、SRS、HLD、PROJECT-PLAN、上列 Goal/Harness/final 文档及 Slice E/F REPORT/GATE；核查 schema/repositories；若无冲突，再先写实现 Goal/HARNESS/PLAN，不能直接编码。

## 可用技能

- 实现获授权且需测试先行：`tdd`。
- 具体失败诊断：`diagnose`。
