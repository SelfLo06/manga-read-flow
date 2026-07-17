# Typesetting Input Contract & Validator Grounding — REPORT

## 裁决

`PENDING_HUMAN_REGION_AND_MAPPING_REVIEW`

自动合同已通过，但本 Goal 尚未关闭。只有人工确认 `case-71/72` 的 region 与文字段落映射后，才能决定是否进入字号、换行、留白和光学居中优化。

本报告不证明自动嵌字质量，不批准正式 Workflow 集成，也不扩大 E1 Cleaning 的能力边界。

## 输入与范围

- 仅使用冻结的 `case-71`、`case-72`。
- Detection/Grouping、Goal 6 association diagnostics 和 E1-only 清字图均为冻结复用。
- OCR 使用真实 MangaOCR；Translation 使用真实 Page-level API，不使用 probe text。
- Translation 采用既有 P0 合同：每页一次、`ja → zh-Hans`、空 glossary、无 previous context。
- 输出为本地忽略产物：`data/local/typesetting-input-contract-v0.1/run-v0.4/`。

## 已确认事实

| 项目 | 结果 |
|---|---:|
| 页面 | 2 |
| source fragment | 31 |
| fragment 可追踪覆盖 | 31/31（100%） |
| segment | 14 |
| E1 eligible typesetting block | 9 |
| 明确 excluded block | 5 |
| safe-inside 正例 | 全部通过 |
| overflow / boundary-touch / wrong-container 负例 | 全部拒绝 |

`case-71__g002` 没有再被压成一段：7 个 fragment 被保真拆为两个 segment，各自拥有 OCR、译文与同一 container 的映射。

`case-72` 的 E3/E2 context 没有静默消失：5 个 segment 以 `excluded + reason` 留在 ledger；只有 3 个 E1 block 进入 typesetting region。

真实翻译请求均通过 block 数量与 ID 映射校验，且未触发结构 repair。本轮译文仅用于验证输入合同，不构成翻译质量 Gate。

## Region grounding

初版“亮像素连通域”在 `case-71` 将白色页面背景与多个气泡串为一个 1,482,338 px 区域，触发面积门禁。这是代码级确认的 region 构造错误，不是简单阈值不足。

修正后使用：

```text
深色线稿 → 膨胀为屏障 → group seed 选择封闭浅色内部 → 向内腐蚀
```

该方法不读取 Cleaning safe/effective mask，也不从 overlay 反推 region。自动生成 8 个 region candidate：`case-71` 5 个、`case-72` 3 个。是否都代表真实气泡内部仍由人工表单裁决。

## Validator grounding

Validator 对每个 candidate 绑定 `region_id + region_sha256`，计算：

- `overflow_pixels` / `overflow_ratio`；
- `minimum_inner_margin`；
- `boundary_touch`。

每个 region 的安全内部点均通过；人为加入的越界点、边界接触点和其他 container 点均被拒绝。因此，上一轮“错误 region 上自洽而视觉假通过”的问题在机制上已被隔离：先冻结真实 region，再允许指标评价 glyph。

这不表示 validator 已覆盖真实中文字形、整行排版或复杂边界；它只证明正负例合同不再忽略显式越界。

## 临时 workflow 耗时

正式累计口径由 `run-v0.2` 已完成上游 checkpoint 与 `run-v0.4` 下游恢复组成。所有时间均为 `time.perf_counter` 单调 wall time。

| Stage | 状态 | 耗时 |
|---|---|---:|
| Detection | frozen reused | 0 ms |
| Grouping | frozen reused | 0 ms |
| Association | Goal 6 reused | 0 ms |
| Cleaning | Goal 6 reused | 0 ms |
| Input load/hash | completed | 104 ms |
| MangaOCR model init | completed prior attempt | 11,750 ms |
| OCR（14 segments） | completed prior attempt | 1,359 ms |
| Page Translation（2 pages） | completed prior attempt | 29,043 ms |
| Provenance | completed prior attempt | 1 ms |
| Region construction | completed | 270 ms |
| Validator | completed | 514 ms |
| Visualization/form | completed | 775 ms |
| **累计 pipeline 总耗时** |  | **43,816 ms（43.816 s）** |
| 恢复尝试自身 wall time |  | 1,673 ms |

翻译占累计时间约 66.3%，OCR 模型初始化约 26.8%。冻结复用阶段的 0 ms 不能解释为真实产品端到端耗时为零。

失败尝试单独保留，不计入正式累计值：

- `run-v0.2` 的 region 构造失败用于定位亮背景串联；其已完成 OCR/Translation/provenance 成为 hash 锁定 checkpoint。
- `run-v0.3` 在 Translation 遇到 Provider `empty_response`，35.273 s 后安全停止；这是外部失败证据，不是算法耗时样本。

## 决策与理由

1. 冻结 fragment → group → segment → OCR → translation → container → cleaning decision → typesetting block/exclusion 的显式 ledger。
   - 理由：禁止“OCR 看见了，但后续无从解释文字去哪了”。
2. 一个 container 允许对应多个 segment。
   - 理由：`case-71` 已证明 container 与段落不是一对一。
3. Typesetting region 必须是独立 artifact candidate。
   - 理由：Cleaning mask 只描述可修改像素，不等于可排版内部。
4. 先验证 region 身份，再计算视觉安全指标。
   - 理由：错误 region 上的 `overflow=0` 没有产品意义。
5. 支持 hash 锁定的断点恢复并分开累计/本次耗时。
   - 理由：Provider 瞬时失败不应强迫重复 OCR/付费翻译，也不能被混入算法性能。

## 淘汰/拒绝的做法

- 使用 hardcoded probe text 评价真实输入完整性；
- 一个 container 只允许一段文本；
- 用 TextBlock bbox、Cleaning safe mask 或调试 overlay 冒充气泡 region；
- 在错误 region 上继续调字号与换行；
- fragment 被 merge/exclude 后不留原因；
- 为跑通而放宽 18% 面积熔断。

## 风险与待证事项

- 当前 group 内段落拆分只由冻结两页支持，尚未形成全局 grouping 规则。
- 深色线稿屏障法可能在开口气泡、彩色边框、低对比度边界上失败。
- 人工尚未确认 8 个绿色 region 的语义正确性。
- Validator 尚未使用真实整段 glyph mask 做压力测试。
- Translation Provider 本轮出现一次 `empty_response`，正式 Loop 仍需拥有 retry/fallback；本 Spike 不实现该职责。
- 仍未证明字号、换行、留白、光学居中或最终嵌字图可接受。

## 人工审查入口

填写：`data/local/typesetting-input-contract-v0.1/run-v0.4/FORM.md`

主要查看：

- `overlays/case-71-regions-and-provenance.png`
- `overlays/case-72-regions-and-provenance.png`
- FORM 中每个 segment 的真实 OCR/译文、container、E1/E2/E3 和 eligible/excluded 状态。

## Open questions

1. 8 个绿色区域是否都确实位于对应真实气泡内部？
2. `case-71/container-002` 的两个 segment 是否符合视觉上的上下两段？
3. OCR/译文是否存在跨气泡串块，而不只是字符串错误？
4. 人工确认后，是进入真实 glyph validator 压力测试，还是仍需先修 region/segment？
