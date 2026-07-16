# Goal 6 — Minimal Human-Reviewed Cleaning Plan v0.1

状态：`COMPLETED`

## Plan

1. 已复核 Goal 5 hash、branch/worktree、SRS/HLD 与清字 algorithm lock；无阻断冲突。
2. 已冻结本 Goal 的允许/禁止范围、风险分流、人工 review 表与四层语义 overlay。
3. 已实现纯本地 text-mask / protected-mask / safe-region harness，并覆盖 containment、fragment trace、different-container isolation、case-54 skip。
4. 已完成 6–8 个 targeted calibration source/ROI、补充 S1 与 review bundle；初始 `cal-51..54` 只保留 reopen 证据。
5. 已在补充 calibration 上冻结 `P0_conservative`；E2 保持 comparison-only。
6. 已以 P0 对 `case-51..54` 完成唯一一次 independent evaluation，且没有读取 evaluation 标签或调参。
7. 已完成维护者人工 review：case-51/52 为 ACCEPTABLE，case-53/54 正确 abstain。
8. 已生成 [`GOAL6-FINAL-REPORT-v0.1.md`](GOAL6-FINAL-REPORT-v0.1.md)，裁决为 `GO_TO_EXPANDED_CLEANING_VALIDATION`。
9. 已完成相关回归与 gate audit；历史 Goal 6 资产将按独立提交保存，不 push。该 Plan 的扩展验证方向已被后续 Goal 7 的 semantic-qualification 阻断结论限缩。

## Execution constraints

- Goal 5 router、其 calibration lock、S1、ROI 与 case source 在 Goal 6 中只读。
- Goal 6 可以真实生成本地候选清字图，但每项仍是人工审查产物，不更新 active pointer 或原图。
- 一次 evaluation 前后均不读取/改写人工 review；正式输出目录不得覆盖。
- 最终交付必须有少量图片与表格；图片不替代 hash/containment/abstention 门禁。
