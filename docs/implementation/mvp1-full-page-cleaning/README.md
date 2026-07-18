# MVP-1 整页清字实施包

本目录承载整页清字台账详细设计获批后的三 Slice 实施记录。设计权威源是 [整页清字台账设计包](../../design/full-page-cleaning-ledger/README.md)；本目录不得反向修改设计基线。

## 当前状态

| Slice | 状态 | 说明 |
| --- | --- | --- |
| [01——台账基础](slices/01-ledger-foundation/README.md) | `ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS` | v3 migration、ledger persistence、recovery 和边界测试已完成 |
| [02——组合、验证与原子验收](slices/02-composition-validation-acceptance/README.md) | `NEXT_ALLOWED_SLICE` | 尚未实现；唯一允许更新 active cleaned pointer 的 Slice |
| [03——case-71 收口与 case-72 泛化](slices/03-real-page-closure/README.md) | `NOT_STARTED` | 尚未运行真实整页收口和泛化 Gate |

`FULL_INTEGRATION_SUITE = ENVIRONMENT_BLOCKED`，原因是当前 Windows/UNC 测试环境缺少 `cv2`，并存在 SQLite 文件句柄锁。该项不是 PASS。

## 三 Slice 边界

1. Slice 1 只建立持久化 ledger、归属、supersession、correction reservation、recovery 和 unaccepted-run stale operation。
2. Slice 2 增加 combined member、确定性 composition、page validation、issue lifecycle、stale propagation 和 atomic acceptance。
3. Slice 3 使用同一 Slice 1/2 合同分别执行 case-71 与 case-72 Gate，不允许增加 case-specific schema、threshold 或特殊逻辑。

Slice 1 不允许临时 `CLEANED_PASS`，也不允许修复非空 active cleaned pointer。Slice 2/3 的范围文档不代表其实现已经开始。

## 版本化规则

本目录的 `README.md`、各 Slice `README.md`、`REPORT.md` 和 `GATE.md` 是可追溯实施记录。命中 `.gitignore` 的 `PLAN.md` 属于本地过程产物，不是本目录的权威入口。
