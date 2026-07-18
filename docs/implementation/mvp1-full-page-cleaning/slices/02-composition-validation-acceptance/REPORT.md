# Slice 2——组合、验证与原子验收报告

## 已交付范围

Slice 2 保留 foundation migration `project_full_page_cleaning_ledger_v3` 的 id、DDL 与 checksum，并新增独立 completion migration `project_full_page_cleaning_acceptance_v3`。逻辑 `project_metadata.project_schema_version` 仍为 `project_full_page_cleaning_ledger_v3`。

completion migration 新增：combined candidate、规范化 members、page validation、专用 cleaning issue relations、accepted `CLEANED_PASS` selection 和 page acceptance record，以及 accepted candidate/validation 唯一索引与 `CLEANED_PASS` trigger guard。Repository/UoW 新增 candidate/validation ledger、issue lifecycle、block transaction、atomic acceptance、acceptance recovery 和 active pointer stale repair。

纯 composer 从同一 original 按 canonical key 重放各 member 的 ActualChangedPixelMask，不串行在上一 candidate 上继续编辑。页 validator 重算 inventory attribution、missing/duplicate、pairwise overlap、wrong-instance write、outside-safe、protected、uncertainty、boundary、residue、combined delta union、source/combined integrity 与 freshness。Preparation Service 在图像计算完成后先经 ArtifactService promotion，再写 candidate/member 与 validation facts；外部计算期间不持有 SQLite write transaction。

## 关键裁决与不变量

- Fresh Project 固定记录 foundation→completion；foundation-only Project 先返回 `PROJECT_MIGRATION_REQUIRED`，显式 migration 在独立 transaction 内补齐 completion，保留既有 ledger 数据。
- Full v3 readiness 同时校验两条 marker/checksum、所需 table/index/trigger、completion 列集合和关键约束；同名 malformed table 不会获得成功 marker。
- `CLEANED_PASS` 使用 completion-owned accepted disposition relation，只能由 `accept_page_cleaning_atomically` 在 candidate members 与 PASS validation 同时转为 accepted 后创建；数据库 trigger 拒绝绕过。
- acceptance 重新检查 visual/original/active pointer/task/attempt CAS、run/candidate/validation、member attribution、artifact metadata hash/state、freshness 和 unresolved blocking issue。任一失败回滚全部 issue/decision/selection/Page 与 TextBlock summary/pointer/task/retry-budget 写入。
- block transaction 保存 issue、typed relations、decision、run/task terminal facts，但不更新 active pointer。
- stale repair 要求 accepted run 与 expected active artifact 精确匹配，在同一 transaction 清空 pointer，并将 run/result/disposition/candidate/member/validation/acceptance/correction/related issue 标为 stale。
- Provider 无数据库和验收依赖；composer/validator 无 persistence 依赖；`SinglePageCleaningService` 未被扩成 full-page orchestrator。

## 迁移标识

```text
LOGICAL_SCHEMA_VERSION = project_full_page_cleaning_ledger_v3
FOUNDATION_MIGRATION = project_full_page_cleaning_ledger_v3
FOUNDATION_CHECKSUM = 9d6f88ecacb7ecf2cfd4ae8aed15b1a939d5eb94ee9d0d69522040c6184d1290
COMPLETION_MIGRATION = project_full_page_cleaning_acceptance_v3
COMPLETION_CHECKSUM = 541912e65133320e6b9a123823a840bf3895c7872ea816273093050a1f047569
```

foundation id、checksum 与既有 DDL 未改写；没有 v4。

## 验证证据

- Slice 2 migration：`8 passed`；覆盖 fresh、foundation-only、幂等、两条 checksum、DDL rollback、malformed shape、future schema。
- Slice 2 acceptance：`13 passed`；覆盖 normalized membership、validation guard、issue resolve/block、atomic acceptance、非法 `CLEANED_PASS`、CAS/rollback、artifact integrity/freshness、stale repair。
- composition/validator：`3 passed`；覆盖 canonical replay、PASS 和 missing/duplicate/cross-write/safety/integrity/freshness 失败。
- 架构边界：`3 passed`；覆盖 accept/block owner、ArtifactService promotion 顺序、Provider/composer/SinglePage 边界。
- 聚合定向与 ProjectStore 非删除回归：`57 passed, 2 deselected`。
- Slice 1 foundation focused：包含于聚合回归；单独最终回归命令见 Gate 交付记录。
- 最宽可行 integration（忽略缺 `cv2` 的 `test_single_page_cleaning_slice.py`，排除两个 Windows 删除探针）：`112 passed, 2 deselected`。
- Slice 2 变更 Python 文件 Ruff：`All checks passed`；compileall：PASS；`git diff --check`：PASS。全仓 Ruff 另检出 33 个既有 Spike/测试风格问题，未修改无关文件。

完整 integration suite 在收集 `test_single_page_cleaning_slice.py` 时因 `ModuleNotFoundError: cv2` 阻塞。完整 unit suite 同样因九个既有视觉 Spike/Typesetting 测试导入 `cv2` 而阻塞。两个 ProjectStore 删除数据库测试在当前 Windows/UNC 解释器下因 SQLite 文件句柄锁失败；这些均记录为环境限制，不记为 PASS。

## 风险与范围确认

ArtifactService physical integrity check 发生在 acceptance transaction 之前；事务内再次校验 durable artifact id/hash/storage state 和 expected guards。文件在检查与事务之间发生外部篡改时，后续 preview/export integrity gate 仍会触发 stale/block；跨进程 workspace 锁仍属于后续产品级并发能力。

本 Slice 没有运行真实 case-71 或 case-72 Cleaning，没有实现 Slice 3，没有执行 Combined Code Health Review，也没有改写旧 frozen run、旧 FORM、Spike E/F 报告或 Slice 1 REPORT/GATE。

## 最终裁决

`SLICE_2 = ACCEPTED_WITH_RECORDED_ENVIRONMENT_LIMITS`。下一允许任务为 Slice 3。
