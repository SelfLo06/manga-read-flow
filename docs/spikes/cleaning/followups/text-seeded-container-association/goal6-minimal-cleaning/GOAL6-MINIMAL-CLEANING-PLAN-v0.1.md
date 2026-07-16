# Goal 6 — Minimal Human-Reviewed Cleaning Plan v0.1

状态：`IN_PROGRESS`

## Plan

1. 复核 Goal 5 hash、branch/worktree、SRS/HLD 与清字 algorithm lock；记录冲突或前置条件。
2. 冻结本 Goal 的 GOAL/HARNESS/PLAN、允许/禁止范围、风险分流与人工 review 表。
3. 实现纯本地、只读的 text-mask / protected-mask / safe-region harness，并为 source/hash、fragment trace、region containment、different-container isolation、case-54 skip 先写测试。
4. 在 `cal-51..54` 运行有限 mask/fill policy grid，生成 calibration review bundle；冻结单一 policy 和实现 hash。
5. 以冻结 policy 对 `case-51..54` 进行唯一一次 evaluation；输出可视化 comparison，不读取 evaluation review 结果。
6. 生成只读人工 review 包与填写说明；等待维护者完成 review。
7. 读取 review，计算门禁，生成 REPORT/GATE 和少量最终效果图；只给出 `GO_TO_EXPANDED_CLEANING_VALIDATION`、`KEEP_AS_MINIMAL_MANUAL_REVIEW_SPIKE` 或 `NO_GO`。
8. 运行相关回归，检查 path-limited diff；仅在本 Goal 已明确允许时做独立 commit，不 push。

## Execution constraints

- Goal 5 router、其 calibration lock、S1、ROI 与 case source 在 Goal 6 中只读。
- Goal 6 可以真实生成本地候选清字图，但每项仍是人工审查产物，不更新 active pointer 或原图。
- 一次 evaluation 前后均不读取/改写人工 review；正式输出目录不得覆盖。
- 最终交付必须有少量图片与表格；图片不替代 hash/containment/abstention 门禁。
