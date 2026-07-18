# Final Scope-Leakage / Slice 3 Integration Readiness 审查

## 结论

**通过范围隔离审查；不具备 Slice 3 integration readiness，维持 `NO_GO`。**

本审查只确认本轮产物没有越权修改既有系统或冻结事实；它不把范围隔离
误解为能力通过。`GATE.md` 的 `PHYSICAL_BOUNDARY_CAPABILITY = NOT_PROVEN`
和 `Stage B = DENIED` 是当前唯一允许的后续状态。

## 审查证据

审查时执行：

```text
git status --short
git diff --name-only
git diff -- src docs/design/cleaning/slice-3
git diff --check
```

结果如下。

| 项目 | 结果 | 依据 |
| --- | --- | --- |
| 产品代码 `src/` | PASS | 无 Git diff；Spike 工具仅位于 `tools/spikes/cleaning/physical_boundary/`。 |
| schema / migration / DAO | PASS | 无受跟踪文件变更；工具中的 JSON `schema` 字段仅标识本地 lock 格式，不是数据库 schema。 |
| Slice 3 文档与 acceptance | PASS | `git diff -- docs/design/cleaning/slice-3` 为空；未修改 acceptance、visual contract 或 ledger。 |
| case-72 冻结输入 | PASS（静态工具审计） | `run_stage_a.py` 只从 `case-72/run-v0.5` 读取 source、summary 和 evidence；其所有写入均在独立的 gitignored Spike run root。 |
| active pointer / artifact metadata | PASS | 未发现 pointer、repository、ArtifactService 或元数据写路径。 |
| Stage B / Cleaner / candidate | PASS（禁止状态） | 工具不调用 Cleaner、Composer、validator 或 acceptance；Gate 明确拒绝 correction reservation 和 candidate。 |
| 原图 | PASS（工具范围） | Stage A 仅读取 source bytes，输出为 mask、overlay、FORM 和 hash lock。 |
| 工作树范围 | PASS，交付前须保持 | 未跟踪内容仅为本 Spike 的 docs、tests 与 tools；没有受跟踪文件 diff。 |

`run_stage_a.py` 的固定 `case-72` 路径和默认 g002/g004 target 是受限实验的
fixture selector；分类函数不接收 target/case/坐标身份，也不据此写入或改变
Slice 3 状态。该判断与 case-specific tuning 审查一致。

## 与 Gate 的一致性

本审查复核 [`GATE.md`](../GATE.md)：g002 仍有 protected/uncertainty
冲突，g004 尚无自动 physical-boundary proof，A1/A2/A5 均未证明通用能力。
所以即使范围已隔离，也不得：

- 生成 Stage B correction、Cleaner candidate 或新的 Slice 3 run；
- 修改 case-72 `run-v0.5`、其 block decision 或 active pointer；
- 将本地 FORM、人工标签或颜色分层接入产品规则；
- 将 `NO_GO` 表述为 case-72 acceptance，或把 g003 从 `REVIEW` 升级。

## 拒绝的替代方案

- **以范围审查通过替代能力 Gate。** 它不能补足 physical-boundary 的逐像素证明。
- **将 Stage A 工具迁入 `src/` 或 Slice 3。** 这会在 `NO_GO` 时引入无授权的产品耦合。
- **把 frozen `case-72` 目录当作输出目录。** 这会破坏可重放的 baseline 和原有 block 证据。

## 风险与交付条件

当前未跟踪的测试/工具目录含运行产生的 `__pycache__/`。它们不是 Spike
交付物，若维护者按 Gate 授权建立独立提交，必须只暂存 `.py`、`.md` 等
有意产物，排除缓存、`data/` 本地 evidence 及其他 ignored 文件。

若未来另行授权新研究，需先获得新的通用 ground truth/control 依据并重新
通过能力 Gate；本审查不提供 Stage B 或 Slice 3 集成授权。
