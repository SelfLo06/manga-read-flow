# Goal 5 — Routed Spatial Association Plan v0.1

状态：`COMPLETE / GO_TO_GOAL6_MINIMAL_CLEANING_TRIAL`

## PLAN

1. 冻结 4 calibration + 4 evaluation 的 source、ROI、crop hash 与 coarse contract。
2. 对 8 crop 运行一条统一的 Detection/Grouping S1 chain，检查 seed 可追踪性与 source hash。
3. 先写 route contract、GT 隔离、nullable region、topology uncertainty 与幂等测试。
4. 实现只读 router：B1 coarse container、corrected bounded support、regionless abstention。
5. 仅在 `cal-51..54` 搜索有限参数网格；无 4/4 组合立即停止。
6. 冻结 calibration lock 和实现 hash 后，只运行一次 `case-51..54` evaluation。
7. 冻结 Goal 6 输入接口；只让 route 正确、空间输出非空且 topology 非 uncertain 的人工试验候选进入。
8. 生成 REPORT/GATE，运行目标单测与相关回归，检查 path-limited diff 后独立提交；不 push。

## 执行约束

- evaluation 运行前不得读取 evaluator labels；运行后不得改 router、参数、crop 或 S1 输入。
- overlay 只作内部审计，不作为 Goal 5 最终效果展示，也不升级为 boundary GT。
- 任何单例特判、asset ID 规则、OCR 字符串规则或手工改写 route 都使结果作废。
- Goal 5 完成后停下等待维护者确认；不得自动开始 Goal 6。

## 验证

至少覆盖正常、无 seed、越界 geometry、重复 fragment、nullable region、container/support 互斥、topology uncertain、hash mismatch、GT access guard、重复运行一致性与 evaluation one-shot guard。

## 完成记录

- 4 个 calibration case 已完成有限网格校准并冻结 lock；evaluation labels 未访问。
- 4 个 evaluation case 已按冻结实现和参数运行一次；运行后未修改 router、参数、crop 或 S1 输入。
- 正式结果：route `4/4`、topology `2/2`、container count `2/2`、bounded support `1/1`、regionless abstention `1/1`。
- `false_low_risk_candidate_count=0`，`cross_container_leakage_violation_count=0`。
- 结论与 Goal 6 输入 contract 见 `GOAL5-GATE-v0.1.md` 和 `GOAL5-GOAL6-INPUT-CONTRACT-v0.1.md`。
