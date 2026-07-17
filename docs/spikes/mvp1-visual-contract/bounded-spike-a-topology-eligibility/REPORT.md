# MVP-1 Visual Contract Bounded Spike A — REPORT

## 当前裁决

```text
AUTOMATIC_CONTRACT = PASS
DELIBERATE_NEGATIVES = 4/4 REJECTED
HUMAN_REVIEW = PASS_WITH_CHANGES
EXIT_GATES = 10 PASS / 0 PENDING / 0 FAIL
SPIKE_A = GO_TO_SPIKE_B_WITH_GUARD
```

本报告不批准 migration、正式 Workflow、Cleaning、Typesetting 或产品实现。它只
允许进入受限的 Spike B；`case-72__g003__s01` 的 protected-overlap 假阴性必须在
actual text-mask / safe-edit evidence 层被证伪或关闭后，才可能讨论实际 Cleaning。

## 冻结运行

正式候选：

```text
data/local/mvp1-visual-contract-spike-a-v0.1/run-v0.4/
```

关键锁：

- snapshot content SHA-256：`61d5e375e83cd0fcc368d07096327d9914885d1da42834c938bf0a287c2f68ae`；
- snapshot file SHA-256：`2a571f2a7f30303974bc74be10749e1048ae1f25dfbe8a5509e3d80e6bcdabff`；
- Visual Contract、Spike module、Goal 7 association module、S1、provenance、OCR、Goal 5 lock、Goal 6 evidence 均记录 hash；
- candidate snapshot 先生成并冻结，之后才加载 evaluation oracle；
- oracle 未进入候选生成；
- snapshot 是本 run 唯一关系事实来源。

## 方法

每个冻结 Goal 5 candidate 先作为 `ContactBubbleCluster` 候选。每个 TextSegment bbox 中心形成独立传播 marker；在候选 Mask 内计算两 marker 之间的 maximum-bottleneck path：

```text
saddle_ratio = widest_path_min_boundary_clearance
               / min(left_seed_clearance, right_seed_clearance)
```

固定通用规则：

```text
saddle_ratio >= 0.90 → same BubbleInstance
saddle_ratio <  0.90 → different BubbleInstance
```

`same` 关系的连通分量形成实例，因此实例数可为 1、2、3 或更多。该阈值只是本 bounded Spike 的可证伪假设，不是全局产品阈值。

Eligibility 在实例级重算背景、segment grounding、protected overlap ratio 与 supported-scope evidence。历史 Goal 6 risk 只作为对照，不向 cluster 成员广播。

## case-71

整页保持：

```text
6 TextSegment
5 source cluster candidate
6 BubbleInstance
6/6 segment unique assignment
```

旧 `container-002` 的结果：

```text
case-71__g002__s01 → independent BubbleInstance
case-71__g002__s02 → independent BubbleInstance
saddle_ratio = 0.836526
threshold = 0.90
decision = different
```

两个实例获得独立 Mask、revision、qualification 与 eligibility assessment。其余单气泡没有被连带拆分。

## case-72

历史口径完整保留：

```text
7 BubbleInstance
8 TextSegment
historical eligible = 3
historical excluded = 5
```

逐实例重放结果：

| Segment | Historical | Candidate | 主要证据 |
|---|---|---|---|
| `g001/s01` | E1 | E1 | 明亮、低方差、无 overlap |
| `g002/s01` | E3 | E1 candidate | overlap `4/10453 = 0.0383%`；背景 244.74 / std 2.20；bbox grounding 80.75% |
| `g003/s01` | E3 | E3 | overlap `112/650 = 17.23%`，超过 5% |
| `g004/s01` | E1 | E1 | 明亮、低方差、无 overlap |
| `g005/s01` | E2 | E3 | 无可用 background sample，证据不足时 abstain |
| `g006/s01` | E1 | E1 | 明亮、低方差、无 overlap |
| `g007/s01+s02` | E2 | E3 | 大面积复杂 SFX/free-text candidate；背景 std 46.33 |

`g002/s01` 的变化只说明旧“任意 overlap 即整实例 E3”规则存在明确假阴性候选；它不批准清字，也不证明 Pixel Text Mask 已安全。

人工审查确认 `g002/s01` 的 E1 candidate 合理：它是浅色、低方差普通气泡，且仅有
`4/10453 = 0.0383%` 的 protected overlap，应保留安全像素而不是整实例弃权。
人工同时裁决 `g003/s01` 为 `FALSE_NEGATIVE`：视觉上它仍是边界清晰、文字位于内部的
普通白色气泡，当前 `112/650 = 17.23%` 的 BubbleInstance 级 overlap ratio 仍过于
粗糙。该发现不改变本轮“原因可审查”的门禁结论；它冻结了下一轮的必要反例：风险必须
检查实际 text mask / safe-edit pixels 与 protected structure 的交集，并保留 boundary
uncertainty band，不能把实例级邻近关系直接广播成整体 E3。

## 合同反例

| 反例 | 结果 |
|---|---|
| N≥3 接触簇 | 3 instances，PASS |
| 单气泡多列 | 1 instance / 2 segments，PASS |
| 单气泡两段 | 1 instance / 2 segments，PASS |
| mixed-risk contact cluster | 同 cluster 内 E1 与 E2 并存，PASS |
| deliberate merge | rejected |
| deliberate split | rejected |
| deliberate unassigned | rejected |
| deliberate wrong-instance | rejected |

## 耗时

run-v0.4：

| Stage | 耗时 |
|---|---:|
| 冻结输入读取与 Goal 5 association 重放 | 22,687 ms |
| topology、eligibility、snapshot、Mask、overlay | 1,654 ms |
| 自动合同与负例评价 | 177 ms |
| **总耗时** | **24,518 ms** |

该耗时只描述当前临时 Spike；没有重新运行 Detection/OCR/Translation，也不是完整产品端到端性能。

## 自动验证

```text
43 passed
```

覆盖 Spike A 12 项测试、既有 association harness、routed association、Goal 7 local routing 与 Typesetting Input Contract。另两组既有 Goal 7 Phase B/C 测试在当前 Miniconda 环境因缺少既有 `psutil` 于收集阶段停止；本轮未安装或升级依赖，也未把它们误记为算法失败或通过。

## 限制

- N≥3、多列、两段和 mixed-risk 目前是 synthetic contract fixture，不是泛化质量样本；
- case-71/72 已参与问题定义，因此本轮证明合同和反例机制可执行，不证明 topology 阈值全局泛化；
- source cluster Mask 仍是 coarse candidate，不是 pixel-accurate bubble GT；
- BubbleInstance partition 是 topology evidence，不是 safe edit mask；
- eligibility candidate 不执行 Cleaning；
- 数值阈值未进入正式产品 profile。

## 人工入口

填写：

```text
data/local/mvp1-visual-contract-spike-a-v0.1/run-v0.4/FORM.md
```

主要查看：

```text
overlays/case-71-topology-eligibility.png
overlays/case-72-topology-eligibility.png
gate-matrix.json
visual-contract-snapshot.json
```

## 最终人工审查

`run-v0.4/FORM.md` 已完成，裁决为 `PASS_WITH_CHANGES`：

- case-71：旧 `container-002` 正确拆为两个 BubbleInstance，两个 segment 唯一归属；
  对角虚拟边界只可作为拓扑近似，不能升格为 pixel-accurate safe-edit boundary；
- case-72：7 BubbleInstance / 8 TextSegment，`g007` 两段仍属于同一自由拟声词实例；
- `g001`、`g004`、`g006` 的 E1 与 `g005`、`g007` 的 E3 均获接受；
- `g002` 从历史 E3 到本轮 E1 获接受；`g003` 仍是人工确认的 eligibility 假阴性；
- 未发现静默 segment 丢失、重复归属、错误 merge/split，或依赖 case ID / 样本专属
  候选行为。

因此 Spike A 的拓扑、唯一去向与逐实例 evidence 合同成立；未解决的 `g003` 不得被
表述为 E1 已获批准，也不得带入实际 Cleaning。它是 Spike B 的 mandatory regression
case，而非本轮的样本专属阈值调参目标。
