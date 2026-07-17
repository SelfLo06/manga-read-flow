# MVP-1 Visual Contract Bounded Spike C — HARNESS

## Candidate / oracle 隔离

候选生成只读取 hash-locked Spike A snapshot、Spike B run-v0.7、冻结 source/translation
provenance 和本 run profile。先写入 immutable `ResidueEvidenceSnapshot`，之后才加载
evaluation oracle。oracle、case ID、目录顺序、overlay、人工标记均不得驱动候选。

## 局部背景与 residue 规则

1. 从 instance 内、visible support 外、远离 protected/uncertainty/boundary 的 ring 采样；
2. Lab 中位数为 local background；MAD/分位差记录背景不确定性；
3. output 像素与该背景的 Lab 对比度达到 profile 阈值，且落在 source support 或有限邻域，
   才成为 residue candidate；
4. candidate 必须形成最小连通组件，或命中关键笔画/完整字符 control；孤立背景噪点 PASS；
5. Required support 与 safe-edit 不完整相交时，先给 `INCOMPLETE_REVIEW`，不进入
   Cleaning PASS control。

## 必测 controls

| ID | Control | 预期 |
|---|---|---|
| A | 完整清除 visible support | PASS |
| B | 只清 text core，留 halo/描边 | `cleaning_residue` BLOCK |
| C | 灰白气泡留接近白色但相对背景可辨字形 | `cleaning_residue` BLOCK |
| D | 恢复完整字符或关键笔画组件 | `cleaning_residue` BLOCK |
| E | 只有背景亮度变化、压缩噪声/小斑点 | PASS |
| F | required support/safe-edit 不完整 | `INCOMPLETE_REVIEW` |
| G | case-71 contact instances | support/residue/binding 不跨实例 |
| H | Spike B glyph/correction mutations | 全部仍拒绝 |

## 每 segment ledger 字段

`page_id`、`segment_id`、`instance_id`、`region_revision_id`、`region_hash`、source/output
hash、text core/support/safe/protected/uncertainty artifact、local-background evidence、residue
mask/component evidence、max/mean local contrast、required/safe completeness、decision、issue
code、reason codes。

未来 QualityCheckService 可将 `cleaning_residue` draft 映射为 QualityIssue。Spike C 只输出：

```text
root_issue = cleaning_residue
affected_segment_id
instance binding
residue mask hash / component count / residual support pixels
max / mean local contrast
required support coverage / unsafe required ratio / reason codes
```

不得输出 retry/fallback/skip/block 的 workflow 决策。
