# MVP-1 Visual Contract Bounded Spike D — 设计

## 固定范围

本轮只验证三个 Spike C `COMPLETE` 的普通实例：

```text
case-71__g002__s01
case-72__g001__s01
case-72__g006__s01
```

`case-71__g002__s02` 是 `INCOMPLETE_REVIEW`，不得运行 Cleaner。没有全页、Batch、OCR、翻译、排版或产品集成。

## Cleaner

唯一主策略是已锁定的 Goal 6 E1 `border_sampled_fill`：从 `candidate_mask` 外、`safe_edit` 内、排除 text/protected/uncertainty 的局部 ring 取 RGB 中位数，写入 `candidate_mask`。

```text
candidate_mask = visible_support_candidate ∩ safe_edit
                 − protected − uncertainty
```

Cleaner 的输入是 source、candidate mask 和可采样 ring；输出只是内存候选图。它不访问数据库、不登记正式 artifact、不创建 QualityIssue，也不作 retry/skip/block 决策。

## 独立证据

- `ActualChangedPixelMask` 从 source/output RGB 差分重新计算；任何 `changed ∩ ~safe_edit`、`changed ∩ protected` 或 `changed ∩ uncertainty` 都是结构损伤 BLOCK。
- 残字沿用 Spike C 的 visible-support/local-background/connected-component 合同；另记录 support 外源字形候选，人工检查 support coverage。
- 边界损伤以 instance boundary 与相邻 protected/uncertainty 的差分检查；不得以 Cleaner 自报计数替代。
- 背景一致性同时记录 candidate 内相对 local-background 的 Lab 色差统计、candidate 边界内外的 Lab 接缝差，以及 background-difference mask；明显人工白/灰块或接缝可推翻数值 PASS。

Validator 只输出 `PASS` / `BLOCK` / `INCOMPLETE_REVIEW`、issue code 与 evidence draft。未来 QualityCheckService 可消费 `cleaning_residue`、`outside_safe_edit`、`protected_structure_damage`、`background_inconsistency`，但本轮不持久化它们，也不调用 WorkflowLoopEngine。

## Controls 与 oracle 隔离

生成 run-local candidate snapshot 后才读取固定 oracle。确定性 controls 与真实 Cleaner 输出分别标记：

1. 原图不改；
2. 只清 core、保留 halo；
3. 故意在 safe-edit 外改一个像素；
4. 故意改 protected 像素；
5. 用明显错误的背景色填充；
6. 真实 `border_sampled_fill` 输出。

前五项只证明 Gate 能拒绝错误，绝不计作 Cleaner 成功。

## 停止条件

本轮最多一个策略；仅允许一次有明确证据依据的局部修订。任一真实 candidate 出现 support 外可辨残字、Validator 与人工冲突、越界写回、protected/uncertainty 损伤或明显背景不协调，即冻结 `CHANGES_REQUIRED`，不试第二套策略。

## 允许文件

```text
docs/spikes/mvp1-visual-contract/bounded-spike-d-real-cleaner-validation/**
tools/spikes/mvp1_visual_contract/spike_d.py
tests/unit/test_mvp1_visual_contract_spike_d.py
data/local/mvp1-visual-contract-spike-d-v0.1/**  (ignored run only)
```

禁止修改生产 Workflow、Repository、ArtifactService、Provider、API、UI、schema、Spike A/B/C 冻结资料和既有本地 run。
