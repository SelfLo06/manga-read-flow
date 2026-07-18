# 整页清字台账设计包

本目录是 MVP-1 整页清字的已接受详细设计包。最终独立 Harness 审查结果为 `PASS_WITH_OPEN_QUESTIONS`；该结果只表示设计足以进入分 Slice 实施，不表示 case-71 收口或 case-72 泛化已完成。

## 阅读顺序

1. [GOAL.md](GOAL.md)：设计目标、范围和硬边界。
2. [HARNESS.md](HARNESS.md)：设计必须表达的场景和 Gate。
3. [final/full-page-cleaning-ledger-dd-v0.1.md](final/full-page-cleaning-ledger-dd-v0.1.md)：最终详细设计基线。
4. [final/schema-outline.md](final/schema-outline.md)：持久化结构轮廓。
5. [final/migration-decision.md](final/migration-decision.md)：迁移裁决。
6. [final/open-questions.md](final/open-questions.md)：不阻塞当前实施的开放问题。

`proposals/`、`reviews/` 和本地 `PLAN.md` 是设计过程材料，不高于 `final/`，也不应作为后续实施的唯一依据。

## 当前实施状态

- [Slice 1 — Ledger Foundation](../../implementation/mvp1-full-page-cleaning/slices/01-ledger-foundation/README.md)：`ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`。
- Slice 2——组合、验证与原子验收：下一允许任务，尚未实现。
- Slice 3——case-71 收口与 case-72 泛化：尚未实现。

Slice 1 不得创建临时 `CLEANED_PASS`，不得更新或清理非空 active cleaned pointer。这些是实现切片边界，不修改本目录 `final/` 中的设计基线。
