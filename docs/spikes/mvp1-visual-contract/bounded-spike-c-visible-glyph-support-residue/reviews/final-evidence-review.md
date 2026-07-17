# Spike C 独立最终证据审查

审查时间：2026-07-17。审查者只读检查；未修改 harness、run、FORM、REPORT 或 GATE。

## 审查范围与可复核证据

- 当前 `tools/spikes/mvp1_visual_contract/spike_c.py`、Spike C 单测，以及 Spike B 的对应回归测试；
- hash-locked `data/local/mvp1-visual-contract-spike-c-v0.1/run-v0.6/`；
- 人工填写的 `run-v0.4/FORM.md`，以及它到 v0.6 的视觉/语义等价性；
- Spike B 的冻结输入和本轮 `FIXTURE-ORACLE-v0.1.json`。

已独立复算：v0.6 candidate snapshot SHA-256 为
`32b07f3d25e170bb2ed8274c5da1c277dba895f5a7d6b7ad313210c1dc13a2bd`，与
summary 一致；其 `spike_c_module_sha256` 为
`40fa96812f317da0e50614cbc69259fde9ca75655b3d2a1644ef349acc9b2cc6`，与审查时
当前源码一致。4 个真实 record 和 6 个 control 的所有记录 artifact file hash 均复核一致。

定向测试：

```text
pytest -q tests/unit/test_mvp1_visual_contract_spike_a.py \
          tests/unit/test_mvp1_visual_contract_spike_b.py \
          tests/unit/test_mvp1_visual_contract_spike_c.py
28 passed
```

仓库根目录的无参数 `pytest -q` 会误收集 `data/local/vendor/yolo-world-v2.1` 的第三方
测试，且本环境缺少其 `torch/mmcv/mmdet` 等依赖；这不是 Spike C 定向测试失败。

## 结论

**可支持 `PASS_WITH_LIMITS / GO_FOR_BOUNDED_REAL_CLEANER_SPIKE`，不是 Real Cleaning GO。**

该结论只允许一个有界的下一阶段：用新的真实清理候选验证已冻结的 visible-support / residue
合同。它不允许 `AUTO_ACCEPT`、产品 Workflow 接入、全页清字、或宣称真实背景重建已经成功。

## 逐项审查

### 1. false negative

通过的有界证据：

- B（仅去深色 core、保留 halo）、C（灰白气泡的近白残字）、D（关键笔画）均为
  `BLOCK / cleaning_residue`；对应 component 分别为 72、48、12 像素。
- A（完整移除）为 `PASS`；F 正确为 `INCOMPLETE_REVIEW`，没有进入 PASS control。
- case-71 的接触 BubbleInstance、case-72 的两处固定样本经人工 FORM 审查，未见明显可辨
  字形落在紫色 support 外；instance/revision binding 未跨实例合并。

限制：support 只是在固定样本上经人工确认的启发式候选。2px 扩张、Lab contrast 6 和最小
3 像素连通组件没有证明对不同分辨率、粗描边、强压缩、发光/阴影或复杂彩色文字泛化。
因此不得把本轮 PASS 表述为“所有可见原文均能检测”。

### 2. false positive

E 的非字形小噪点为 `PASS`；residue 仅在 required support 内、达到局部 Lab contrast 并形成
最小连通组件时才会触发。当前样本没有观察到误报。

但 E 是很小且在 support 外的斑点，不能证明在 support 内的复杂背景纹理、扫描噪声或气泡
灰阶不均同样不会误报；局部背景 ring 也没有把 protected/uncertainty 作为显式排除输入。
这不是本轮 bounded 门禁的 blocker，却是 real Cleaner Spike 必须保留的 false-positive 风险与
扩样方向。

### 3. oracle 隔离

`build_run` 先写入 `CANDIDATE_FROZEN_BEFORE_ORACLE` snapshot，再解析 oracle 的预期
decision；候选 support、真实 record 和 mask 不按 oracle 分支，B--D 的 QualityIssue draft 也
在 v0.6 中可追踪。未发现 oracle 用于调阈值或修改 candidate 的证据。

一个术语级限制：snapshot 前会读取 oracle 文件的字节以计算 `oracle_sha256`，虽然不解析或使用
预期标签。因此 `candidate_generation_oracle_access=false` 应理解为“没有 oracle **decision/content
semantic access**”，而不能作绝对的文件读取否认。建议后续将字段改名为
`candidate_generation_oracle_decision_access`，或在 snapshot 后再登记 oracle hash；本轮无结果级
oracle 泄漏证据。

### 4. 字段语义与职责边界

通过。ledger 以 `required_support_pixels`、`required_support_hash`、`safe_edit_pixels`、
`unsafe_required_*`、`residue_component_count`、`max/mean_local_contrast` 等明确字段保存证据，
未发现将 visible-support 像素伪写为 `text_core_pixels` 的污染。

B/C/D 的 draft 包含 page/segment/instance/revision/region hash、source/output hash、residue
hash、组件、contrast、coverage、unsafe ratio 和 reason codes；未包含 retry/fallback/skip/block 的
Workflow 决策。它足以作为未来 `QualityCheckService` 的输入，而不越过
`WorkflowLoopEngine` 边界。

### 5. Spike B 回归

v0.6 的 `spike_b_regressions` 八项均为 true：missing、duplicate、wrong-instance、overflow、
boundary-touch、wrong-validator-region、一次 correction 保留、第二次 correction 拒绝。此前
v0.4 只记录其中四项，**不得再作为完整 H 的依据**；本审查只以 v0.6 为准。

## v0.4 人工 FORM 是否可引用到 v0.6

**可以，且不是 blocker；但 REPORT/GATE 必须明确写出 carry-forward 依据。**

独立比较结果：

- v0.4 与 v0.6 的 4 个真实 record、6 个 controls 的 decision、issue、reason、completeness 与
  residue evidence 均相同；共同 artifact 的 content hash 均相同。
- FORM 中三个直接展示给人工的 overlay 文件字节 SHA-256 相同：
  - `controls-grid.png`：`ec6e10320b07133af29878ac438dd2d5f06f3f6d4dfa249ca8d738a0f2f2043a`
  - `case-71-contact-evidence.png`：`2798ccfcaa1ccc5792359afcc78f805e198cb0986cfc8b633cda643544902198`
  - `case-72-evidence.png`：`68e98e27757e5a8b649de0391b5fa8136fe6e6ea863c69279433d88476e601fc`
- v0.6 新增的是完整 H 记录和 B/C/D 的结构化 QualityIssue draft；未改变人工看到的图、题目、
  control decision 或真实 record。

因此，v0.4 FORM 的 PASS_WITH_LIMITS 可作为 v0.6 的人工审查结论；不要求重复人工填写。FORM
标题仍写 `run-v0.1` 是可追溯性瑕疵，最终报告必须用实际路径和 run ID 消除歧义，不能再引用该标题。

## 必须保留的结论边界

1. 本轮没有运行真实 Cleaner；`cleaned-control` 是合成验证对象。
2. `PASS_WITH_LIMITS` 不代表真实 Cleaning residue completeness 已证明，更不代表 E1/E2 自动清字
   获批。
3. 允许的下一步仅是 bounded real Cleaner Spike：固定对象、保留 instance binding、支持不完整即
   `INCOMPLETE_REVIEW`、残字即生成 `cleaning_residue` evidence，不由 Validator 决定 loop 行为。
4. 一旦真实结果出现 support 外可辨残字、support 内背景误报，或 protected/uncertainty 污染局部
   背景估计，必须停在 `CHANGES_REQUIRED`，不能靠本轮合成 control 覆盖。

## v0.7 oracle 字段语义复核（追加）

已复核最终 `run-v0.7`：candidate snapshot SHA-256
`4bd8233247f4f68cb7a0cd75115f5e512559603f8e4fc25b9cfb24e55ff1740b` 与 summary 一致，且其
module hash 与当前源码一致。`input_lock` 现明确区分
`oracle_hash_read_before_candidate_snapshot=true` 和
`candidate_generation_oracle_decision_access=false`；这准确表达了候选冻结前为输入锁读取 oracle
字节求 hash、但未读取/使用 oracle decision 的事实，关闭了先前的字段语义缺口。

我也独立比对了 v0.4→v0.7：4 个真实 record、6 个 controls 的 decision、issue、reason、
completeness、residue evidence 及共同 artifact content hash 均相同；三张人工 overlay 的字节 hash
也完全相同；H 八项均为 true，定向 A/B/C 测试仍为 `28 passed`。因此 v0.4 FORM 对 v0.7 的
carry-forward 结论继续成立，且不构成 oracle 泄漏 blocker。
