# MVP-1 整页清字实施包

本目录承载整页清字台账详细设计获批后的三 Slice 实施记录。设计权威源是 [整页清字台账设计包](../../design/full-page-cleaning-ledger/README.md)；本目录不得反向修改设计基线。

## 当前状态

| Slice | 状态 | 说明 |
| --- | --- | --- |
| [01——台账基础](slices/01-ledger-foundation/README.md) | `ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS` | v3 migration、ledger persistence、recovery 和边界测试已完成 |
| [02——组合、验证与原子验收](slices/02-composition-validation-acceptance/README.md) | `ACCEPTED` | completion migration、组合、验证、issue lifecycle、原子验收和 stale repair 已完成；Linux 全量 integration 已通过 |
| [03——case-71 收口与 case-72 泛化](slices/03-real-page-closure/README.md) | `NEXT_ALLOWED_SLICE` | 尚未运行真实整页收口和泛化 Gate |

Slice 2 已在 Linux `manga-read-flow` Conda 环境重验：`FULL_INTEGRATION_SUITE = PASS`（`117 passed`）。Slice 1 的历史 Gate 保持原记录，不因后续环境验证而改写。

## 三 Slice 边界

1. Slice 1 只建立持久化 ledger、归属、supersession、correction reservation、recovery 和 unaccepted-run stale operation。
2. Slice 2 以不可变 `project_full_page_cleaning_acceptance_v3` completion record 补齐完整逻辑 v3，再增加 combined member、确定性 composition、page validation、issue lifecycle、stale propagation 和 atomic acceptance。
3. Slice 3 使用同一 Slice 1/2 合同分别执行 case-71 与 case-72 Gate，不允许增加 case-specific schema、threshold 或特殊逻辑。

Slice 1 不允许临时 `CLEANED_PASS`，也不允许修复非空 active cleaned pointer。Slice 2/3 的范围文档不代表其实现已经开始。

## 版本化规则

本目录的 `README.md`、各 Slice `README.md`、`REPORT.md` 和 `GATE.md` 是可追溯实施记录。命中 `.gitignore` 的 `PLAN.md` 属于本地过程产物，不是本目录的权威入口。

逻辑 schema v3 的两条物理 migration record 分期见[迁移分期修订 v0.1.1](../../design/full-page-cleaning-ledger/final/migration-staging-amendment-v0.1.1.md)。
