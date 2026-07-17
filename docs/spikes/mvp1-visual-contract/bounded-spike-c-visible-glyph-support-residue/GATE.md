# MVP-1 Visual Contract Bounded Spike C — GATE

## 当前状态

```text
PASS_WITH_LIMITS — GO_FOR_BOUNDED_REAL_CLEANER_SPIKE
ACTUAL_CLEANING — NOT_GO
```

| # | 门禁 | 状态 | 证据 |
|---:|---|---|---|
| C1 | A–F 确定性 controls 符合预期 | PASS | `run-v0.7/summary.json` |
| C2 | 浅色 halo、近白字形、关键笔画残留均被拒绝 | PASS | B/C/D 均为 `BLOCK / cleaning_residue` |
| C3 | 普通背景噪声不误报 | PASS | E 为 PASS |
| C4 | unsafe required support 不进入 Cleaning PASS | PASS | F 与 case-71 `g002/s02` 为 `INCOMPLETE_REVIEW` |
| C5 | 接触 BubbleInstance 的 support/residue/binding 不跨实例 | PASS | case-71 overlay + FORM |
| C6 | 缺失、重复、错误实例、越界、边界触碰、错误 validator region、一次 correction 均不退化 | PASS | v0.7 regression matrix |
| C7 | candidate generation 与 fixture oracle decision 隔离 | PASS_WITH_LIMITS | snapshot 先于 decision parse；oracle hash 为可复现性预读，已显式记录 |
| C8 | 当前样本中 support 外无明显可辨字形 | PASS_WITH_LIMITS | FORM 人工审查；固定样本限定 |
| C9 | residue failure 可形成无 Loop 决策的 QualityIssue 证据草案 | PASS | B/C/D `quality_issue_draft` |
| C10 | 没有把合成 control 宣称为真实清字成功 | PASS | run 元数据与 REPORT 明确 `actual_cleaner_executed=false` |

## 允许事项

仅允许开始一个新的、独立的 bounded real Cleaner Spike，且必须：

- 限于 COMPLETE support 的普通浅色/白色气泡；
- 逐 segment 保存 source/output、support/safe/protected/uncertainty、局部背景、residue 与结构损伤证据；
- 实际残字失败产出 `cleaning_residue` root-cause evidence；
- `INCOMPLETE_REVIEW` 保持不自动清理；
- 以少量固定样本、有限策略和明确停止条件运行。

## 仍然禁止

```text
PRODUCT WORKFLOW INTEGRATION = FORBIDDEN
API / UI / DATABASE / MIGRATION = FORBIDDEN
PROVIDER INTEGRATION = FORBIDDEN
FULL-PAGE OR BATCH CLEANING = FORBIDDEN
AUTO_ACCEPT = FORBIDDEN
TREATING THIS AS PRODUCT CLEANING GO = FORBIDDEN
```
