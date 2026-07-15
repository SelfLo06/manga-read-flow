# Text-Seeded Container Association Spike — PLAN

版本：v0.3
状态：Goal 3 R0 Validation Complete / Verdict FURTHER_SPIKE

## 1. 目标与执行原则

未来实现只验证 `text seed → container/support association → abstention`。先冻结样本、GT、接口、对照、参数与随机种子，再写测试和 Spike 代码；不边看 final 结果边改规则。

Round 1 已完成 GOAL / HARNESS / PLAN。Round 2 的 v0.2 freeze 曾因范围过窄被重开；v0.3 已完成扩大候选选择、A/B 独立选择题与分层裁决。R0 semantic labels、container topology 及 A coarse target-region reference 已冻结；pixel-accurate boundary GT、双人边界一致性和 uncertainty-band 数值未冻结。当前仍不执行 association。

维护者于 2026-07-15 将执行范围收窄为三个长周期 Goal：输入冻结、最小实现与 calibration、R0 运行与 verdict。下文原完整 Phase 设计仅保留为未来 expanded validation 参考；当前不扩建 R1、不生成 benchmark manifest，也不要求完整百分比 × 多随机种子的压力矩阵。

## 2. 当前工作文档

当前设计工作集包含：

```text
docs/spikes/cleaning/followups/text-seeded-container-association/GOAL.md
docs/spikes/cleaning/followups/text-seeded-container-association/HARNESS.md
docs/spikes/cleaning/followups/text-seeded-container-association/PLAN.md
docs/spikes/cleaning/followups/text-seeded-container-association/FREEZE.md  # retired v0.2 record
docs/spikes/cleaning/followups/text-seeded-container-association/CANDIDATE-EXPANSION.md
docs/spikes/cleaning/followups/text-seeded-container-association/R0-SELECTION-v0.3.md
docs/spikes/cleaning/followups/text-seeded-container-association/R0-ADJUDICATION-v0.3.md
docs/spikes/cleaning/followups/text-seeded-container-association/S1-INPUT-FREEZE-v0.1.md
docs/spikes/cleaning/followups/text-seeded-container-association/GOAL2-HARNESS-CALIBRATION-v0.1.md
```

当前三个 Goal 的状态：

1. Goal 1 — R0 / calibration 输入与 S1 freeze：`COMPLETE`；
2. Goal 2 — 最小 B0/B1/P1 Harness 与 calibration-only threshold lock：`COMPLETE`；
3. Goal 3 — 冻结 R0 上的一次轻量 B0/B1/P1 运行、人工宽容差评分与 verdict：`COMPLETE / FURTHER_SPIKE`。

Goal 3 的结果见 `GOAL3-R0-VALIDATION-REPORT-v0.1.md` 与 `GOAL3-GATE-v0.1.md`。当前不得进入 Pixel Text Mask；继续前需新开 focused association correction Goal。

4. Goal 4 — Focused Association Correction：`COMPLETE`；最终冻结 `B1_STRONG_BASELINE_ONLY`，corrected P1 未被选择，不进入 Pixel Text Mask 或 Cleaning。详见 `GOAL4-FOCUSED-CORRECTION-REPORT-v0.1.md` 与 `GOAL4-GATE-v0.1.md`。

## 3. 后续经评审授权后的允许范围

仅在维护者批准本设计并另行授权实现后，允许：

```text
docs/spikes/cleaning/followups/text-seeded-container-association/**
tools/spikes/text_seeded_container_association/**
tests/unit/test_text_seeded_container_association*.py
local_samples/...  # 仅 Git 忽略的 fixture、GT、preview、run output
```

约束：

- `tools/spikes/**` 只含独立 Spike 逻辑，不形成正式 Provider；
- `tests/unit/**` 只测试纯函数、评分、门禁与可重复性；
- 本地输出必须位于 Git 忽略目录；
- 原图和已有本地 artifact 只读；
- 新 REPORT / GATE 仅在真实运行完成后生成，不预写结论。

## 4. 禁止文件与操作

禁止修改或新增：

```text
src/manga_read_flow/**
任何 CleanerProvider / Provider Adapter 正式实现
任何 Workflow / WorkflowLoopEngine / StageExecutor 集成
任何 Repository / SQLite / ArtifactService 正式代码
docs/SRS-v1.0.md
docs/HLD.md
docs/PROJECT-PLAN.md
docs/spikes/cleaning/algorithm-lock-v0.1.md
已有 REPORT / GATE / ratings / benchmark pilot CSV
benchmark-manifest.jsonl 或其他正式 benchmark manifest
依赖文件、lockfile、环境配置
```

算法与能力禁止：

```text
LaMa
Diffusion
ControlNet
FFT screentone reconstruction
GrabCut
Active Contour
CRF
实际 fill / inpaint / Cleaning
像素文字 Mask / safe edit region 实现
AUTO_ACCEPT
```

操作禁止：

- 未经授权的 commit / push / pull / rebase；
- 覆盖原图；
- 修改现有 GT、REPORT、GATE 或失败证据；
- 将 local outputs、缓存、日志或临时 AI 文件纳入 Git；
- 为单个 asset 写隐藏特判。

## 5. 实施阶段

### Phase 0：Preflight 与证据冻结

1. 重新检查 branch、working tree 与允许文件范围；
2. 记录权威文档版本和输入 source hash；
3. 确认旧 REPORT 重复文件内容一致，且不修改已有文件；
4. 读取 `FREEZE.md` 的 reopening notice 与 `CANDIDATE-EXPANSION.md`，确认没有把历史候选误当 final freeze；
5. 若来源出现未解决冲突，停止。

输出：只读 preflight 记录；不得生成算法结果。

### Phase 1：Fixture 资格审查与人工 GT

1. 已完成：维护者填写 `r0-candidate-review-v0.2/FORM.md`，六类均为唯一高信心主选项；
2. 已完成：检查六个主候选的来源分散性，冻结六张不同源图的 source/ROI/crop identity；
3. 已完成：生成随机 case 编号的 Annotator A/B 独立标注包；
4. 已完成：A/B 独立选择题与 coordinator 裁决，冻结 semantic labels 与 container topology；
5. 已完成：A overlay 冻结为 coarse target-region reference；B 无 overlay，因此 inter-annotator boundary agreement 与 pixel-accurate boundary GT 明确不可用；
6. 已完成：R0 verdict 为 `PASS_FOR_CONTAINER_ASSOCIATION_SPIKE`，不重开六例；
7. 已完成：冻结新的六例统一 S1 run，不拼接历史 `black2` chain 与无法证明同版本的 extension；
8. 已完成：冻结两个与 R0 隔离的最小 calibration backup crop；Goal 1 不生成 pair、不选择阈值；
9. 已完成：检查 source/crop hash、blind input、运行可重复性与 provenance；
10. 当前最小 Spike 明确延后 R1 37-region 扩展、正式 evaluation split 与 benchmark manifest。

门禁：采用 HARNESS 9.1 的当前最小 R0 适用项；R1 条目只在未来 expanded validation 重新启用。

### Phase 2：输入/输出与评分契约

先写测试，冻结：

- fragment / group / ROI 数据结构；
- 四种方法统一输出结构；
- `LOW_RISK_ASSOCIATION_CANDIDATE / REVIEW_REQUIRED / SKIP`；
- grouping、container、boundary、support、abstention 指标；
- GT 隔离检查；
- source mutation 检查；
- duplicate / crop truncation / silent skip 检查；
- S2/S3 deterministic perturbation；
- risk–coverage 汇总。

测试至少覆盖正常、边界、失败、幂等与错误输入；禁止调用正式产品代码。

### Phase 3：B0 几何基线

实现并冻结：

```text
geometry-aware conservative grouping
→ group union bbox
→ character-scale dilation
→ overlap/conflict detection
→ confidence / abstention
```

先在 calibration 子集定参数。B0 不得获得 GT container assignment 或 P1 的 same-container 图像证据。

### Phase 4：B1 Watershed 基线

实现同 ROI、同 seed 下的 seeded watershed；输出 basin、ridge、冲突和不确定度。B1 只作简单图像边界基线，不用 P1 的 geodesic graph 或 GT-informed merge。

### Phase 5：P1 主候选

按固定顺序实现：

```text
局部特征图
→ SLIC superpixels
→ superpixel graph
→ hard barrier / soft cost
→ initial multi-source propagation
→ P_same_container evidence
→ merge-and-rerun / keep-competition / abstain
→ geodesic Voronoi ridge
→ explicit / implicit / free_text / uncertain
→ confidence + reasons
```

必须保留 alternative grouping、unassigned fragment、boundary uncertainty 与每项置信证据。禁止用资产 ID 或 GT 修复个别失败。

### Phase 6：P2 条件细化

只对 P1 在算法输出阶段已标记的 uncertain boundary band 运行 Random Walker。不得在看到 GT 后选择 P2 case，不得修改 confident P1 case，不得把 uncertainty 强制改为 low-risk。

### Phase 7：S0–S3 正式矩阵

运行顺序固定：

```text
R0 smoke regression
→ calibration sanity run
→ freeze parameters
→ S0 × B0/B1/P1/(conditional P2)
→ S1 × B0/B1/P1/(conditional P2)
→ S2{1%,3%,5%} × 5 seeds × methods
→ S3{1%,3%,5%} × 5 seeds × methods
→ final evaluation once
```

每项必须记录成功、弃权或失败，禁止 silent skip。

### Phase 8：人工审查与 Verdict

为每个关键案例生成只读 overlay：

- source + fragment seeds；
- GT（仅 evaluator/reviewer 图层）；
- B0/B1/P1/P2 区域；
- visible/virtual boundary；
- leakage / missed fragment；
- same-container decision；
- uncertainty band 与 abstention reason；
- S1/S2/S3 差异对照。

reviewer 不修改代码、参数、GT 或输出，只给 `correct / incorrect / uncertain` 与失败 taxonomy。根据 HARNESS 9 节决定 `GO_TO_PIXEL_TEXT_MASK_SPIKE / FURTHER_SPIKE / NO_GO`。

### Phase 9：报告与收尾

真实运行后才允许新增：

```text
docs/spikes/cleaning/followups/text-seeded-container-association/REPORT.md
docs/spikes/cleaning/followups/text-seeded-container-association/GATE.md
```

报告必须包含：输入完整性、环境、R0/R1、B/S 全矩阵、指标、盲评、失败模式、停止事件、限制、verdict 与下一步。无论结论如何，都不得开始 pixel text mask 或 Cleaning 实现，必须先由维护者评审。

## 6. 单元与 Harness 验证场景

至少预先覆盖：

1. 单一规则气泡的正常归属；
2. hard-09 相邻/接触容器；
3. 同容器多列文字；
4. broken boundary；
5. free-text support；
6. not-text false seed；
7. S2 删除关键 fragment；
8. S3 注入结构线/纹理 FP；
9. alternative grouping 与 uncertain；
10. hard barrier 不可穿越；
11. soft barrier 可在高代价下传播但降低置信；
12. P2 不改 confident P1 case；
13. 重复输入得到相同输出与指标；
14. GT 泄漏检测；
15. source hash 改变时失败；
16. duplicate / crop truncation / silent skip 时 gate 失败；
17. malformed geometry、空 seed、越界 polygon 的显式错误或弃权。

本 Spike 不涉及数据库恢复、Provider refusal、file cleanup、soft delete 或 export blocking；这些系统级场景因明确禁止 Workflow/Provider 集成而不适用，不能伪造验证结果。

## 7. 预期失败模式

| ID | 失败模式 | 可观察证据 | 期望处理 |
| --- | --- | --- | --- |
| F01 | 接触气泡跨容器 merge | 一个 group/region 含多个 GT container seed；hard-09 失败 | hard gate fail；若证据不够应 abstain。 |
| F02 | 同容器多列 false split | 同一 GT container 出现多个低风险输出或伪 virtual ridge | 合并重跑或 abstain；不得强切。 |
| F03 | broken boundary 泄漏 | IoU 下降、leakage 上升、region 沿低代价背景扩散 | 降置信并 review；检查 soft cost/ROI，不扩大硬墙特判。 |
| F04 | 强线稿被误当 container boundary | 容器被人物/背景线稿切碎 | 结构证据降为 soft penalty 或 abstain。 |
| F05 | 真实容器边界被当可穿越软边 | 跨气泡、跨分镜传播 | hard barrier 置信错误；hard gate fail。 |
| F06 | SLIC 尺度敏感 | 参数微变导致 boundary/assignment 大幅翻转 | 标记 boundary uncertainty；不得选择只对单图有利的尺度。 |
| F07 | same-container 循环振荡 | merge/split 迭代不收敛或标签反复 | 有界迭代后 `uncertain`；记录 history。 |
| F08 | 虚拟边界位置不稳定 | geodesic ridge 在重复/微扰 run 中漂移 | 输出 uncertainty band；必要时条件 P2，否则 review。 |
| F09 | free text 被伪造成气泡 | 输出非空 container_mask 或 support 追随假轮廓 | contract fail；free text 只能有 support。 |
| F10 | free-text support 吞入结构 | support 超出最大 envelope、碰到人物/分镜 | review/skip；不得用扩大 dilation 修复 coverage。 |
| F11 | not-text FP 生成虚假候选 | hard-12/13 或 S3 FP 输出 low-risk support | S3 safety gate fail。 |
| F12 | 漏 seed 后错误高置信 | S2 中缺失 fragment，但 region 仍声称完整低风险 | false-low-risk；必须 review/skip。 |
| F13 | extra/auxiliary group 静默消失 | S1 输入 fragment 不在输出或 unassigned 列表 | harness invalid；所有输入需可追踪。 |
| F14 | ROI/crop 裁断字符 | GT fragment 被 ROI 边界截断 | fixture/harness fail，先修样本，不调算法。 |
| F15 | GT/旧 mask 泄漏 | 结果异常贴合旧 difference mask 或代码读取 GT 字段 | 结果作废并停止。 |
| F16 | P2 掩盖 P1 普遍失败 | 大量 confident/普通 case 被送入 Random Walker | 违反条件运行；P2 结果作废。 |
| F17 | 置信度与风险反向 | seed 变差后 low-risk coverage 上升 | calibration/decision fail；停止 final verdict。 |
| F18 | 简单基线同样有效 | P1 无安全收益或更差 | 拒绝复杂化，结论为 further/no-go。 |

## 8. 停止条件

采用 HARNESS 第 11 节全部停止条件。特别强调：

- `hard-09` 在 P1/P2 上仍发生非弃权跨容器 merge；
- S2/S3 产生任一 false-low-risk candidate；
- 发现 GT 泄漏、source mutation、重复或 incomplete text instance；
- 需要实际 Cleaning、禁止模型、正式 Provider/Workflow、benchmark manifest 或依赖升级才能继续；
- final evaluation 后提出针对单例的调参或 asset-specific rule。

停止后只保留失败证据并写明 `FURTHER_SPIKE` 或 `NO_GO`，不得绕过门禁。

## 9. 交付要求

最终交付必须报告：

- 修改文件；
- 决策与拒绝替代；
- R0/R1 与输入完整性；
- B0/B1/P1/P2、S0/S1/S2/S3 全矩阵；
- 指标、门禁、停止事件与 verdict；
- 预期/实际失败模式；
- 未解决问题；
- 测试或替代验证及其真实结果；
- 未运行、未验证的事项。

未经单独授权，不 commit、不 push。
