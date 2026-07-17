# 自动嵌字可行性 Spike 首轮门禁

## 结果

```text
Verdict: NO_GO
Scope: current Typesetting input and validation chain
Automatic typesetting direction: remains open
```

## 未通过项

- [ ] 每个 source fragment 到 typesetting block 的去向可追踪。
- [ ] 同容器多文字组/多段输入不会静默压缩为一条字符串。
- [ ] 使用真实、冻结且可审查的 `typesetting_region`。
- [ ] 明显越过真实气泡边界的候选被 validator 拒绝。
- [ ] 所有 excluded / merged / unassigned context 带原因进入结果。
- [ ] 当前页面的 E1-only 范围足以支持完整页面嵌字结论。

## 已通过但不足以放行的项

- [x] 8 个已选 E1 context 均能生成 R0/R1/R2 候选。
- [x] 原图未被覆盖。
- [x] 渲染与指标在 harness 使用的 region 内部自洽。
- [x] R2 能展示颜色/字重继承路径。

这些项目不抵消 region 语义错误和 provenance 缺失。

## 下一门禁

只有同时满足以下条件，才允许恢复换行/字号优化：

1. 选定样本中 100% source fragment/text group 有最终去向或明确排除原因；
2. `typesetting_region` 为独立、可视化、冻结输入，不从诊断 overlay 恢复；
3. 人工构造的越界、触边、错误容器三类负例全部被自动 validator 拒绝；
4. 同容器两段文字能够保持身份、顺序和独立布局约束；
5. 机器 overlay 与人工观察对 region 边界一致。

未通过时停止，不扩大样本、不接 Workflow、不做整书实验。
