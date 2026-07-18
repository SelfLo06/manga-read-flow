# Boundary-to-text false-positive review

审查范围：仅审查 Stage A 的 maintainer lock、评估结果和 A1/A2/A5 现有实现；不产生 Cleaner candidate，也不改动任何冻结证据。

## 结论

`g004` 的人工确认边框共 70 px，在 A1、A2、A5 中均未被分类为 `required_text`：`false_boundary_to_text_pixels = 0`。因此，在**已标注的 70 px 争议范围内**，三个候选都没有发生“真实气泡边框 → 文字 required evidence”的误判。

这不是 Stage B 的充分条件。所有方法仍将这 70 px 标为 `unresolved_uncertain`，而非 `proven_non_text_boundary`；A1 还将 `g002::unsafe::10` 的 2 个维护者标为 `UNCERTAIN` 的像素错误认证为 `required_text`。故目前的零 false-positive 只证明一次受限 abstain 成功，不能证明具有可泛化、可写的 physical-boundary correction 能力。

## 证据核验

锁定一致：`stage-a-evaluation-lock.json` 中的 summary、human review、evaluation SHA-256 分别与当前文件相符（`da6ad279…c6f17d`、`c4c1e372…ba8955`、`ff9564c3…6633db`）。评估范围明确为“maintainer-labelled disputed components only”，不能外推到整页。

| 人工事实 | A1 | A2 | A5 | 审查判断 |
| --- | ---: | ---: | ---: | --- |
| `g004` BUBBLE_BOUNDARY 70 px | required_text 0；unresolved 70 | 0；70 | 0；70 | 三法均未把已确认边框认证为文字；false boundary-to-text 为 0。 |
| `g002` TEXT_EDGE 708 px | 认证 288；未决 420 | 0；708 | 0；708 | 文字证据仍不完整，不能据此清字。 |
| `g002` UNCERTAIN 2 px | 认证 2 | 未决 2 | 未决 2 | A1 的 core-connectivity 单独不足以把 uncertainty 提升为 required_text。 |
| `proven_non_text_boundary` | 0 | 0 | 0 | 无方法自动产出可从旧 required 中安全移除的边框证据。 |

上述数字来自 `stage-a-summary.json`、`human-review-lock.json` 和 `stage-a-evaluation.json`。`g004` 两个组件分别为 45 px 和 25 px，三个方法均为 `required_text = 0`；因此 70 px 的零值不是舍入结果。

## A1 的 2 px uncertainty 误放行

`g002::unsafe::10` 是 2 px、`uncertainty_only_pixels = 2`，人工标签为 `UNCERTAIN` / `ALLOW_AS_REQUIRED_TEXT = NO`。A1 却给出 `required_text = 2`、`unresolved = 0`；A2/A5 均保留为未决。

实现原因是 A1 的可达域排除了 `protected` 与 ridge，却没有排除 `uncertainty`：它把包含高置信 core 的旧 required 连通分量整体归为 `required_text`。所以这 2 px 没有成为 safe 像素，也没有触发任何真实写入（Stage A 不运行 Cleaner，且 protected 仍不可写）；但它们被错误地升级为“required 文字证据”。若把 A1 结果作为后续 correction 的输入，该升级会抹去应有的 fail-closed 阻断，因此必须在 Stage B 前修正或明确禁止采用 A1 对 uncertainty 的认证。

## 为何 `false boundary-to-text = 0` 仍不足以进入 Stage B

1. 该值只覆盖人工标注的 g004 70 px，且三个方法采取的是 unresolved abstain，不是通用边框证明；没有已验证的 `proven_non_text_boundary` 规则。
2. g002 仍有 420 个已确认 TEXT_EDGE 像素被 A1 留为未决，A2/A5 则为全部 708 px；并且 g002 组件 01/02 的 103 个 protected px 均属于维护者确认的 TEXT_EDGE。protected 不可写，不能以重分标签绕过。
3. A1 对 2 个 `UNCERTAIN` 像素的误认证说明“core 连通”不是充分证据；对一组 boundary 的零误报不能抵消这项 fail-closed 缺口。
4. Stage A 没有证明对所需控制矩阵的泛化能力。特别是评估文件明确否定“generic control-validated rule”，不能将 g004 的人工结论转化为算法规则。

## 决策与建议

维持 `NO_GO`：当前事实只支持保留 g004 为不可写的 `unresolved_uncertain`，保留 g002 的 protected/uncertain 文字冲突，不支持放宽全局阈值或把人工分类直接写入算法结果。

被拒绝的替代方案：

- 将 g004 的 70 px 因人工标签直接改为 `proven_non_text_boundary`：这是 target-specific 人工特判，不能证明通用方法。
- 把 A1 的 core 连通视为 uncertainty 的充分证据：已被 2 px `UNCERTAIN` 反例否定。
- 因 false-positive 为零而放宽 physical corridor 或 protected：会绕过 protected 非写入不变量，也不能解决 g002 已确认文字落在 protected 中的事实。

## 风险、验证与开放问题

风险：宏观 component 标签将每个组件的像素统一赋类；当前评估不能证明组件内每个像素的细粒度语义，更不能作为整页 precision/recall。A1 的 2 px 反例还表明其“不跨 protected/ridge”不等于“所有 required_text 都是可采纳文字证据”。

已执行验证：核对 evaluation lock 的三项 SHA-256；运行 `pytest -q -p no:cacheprovider tests/spikes/cleaning/physical_boundary`，结果 `7 passed`。这些测试验证分类分割、protected 非 required 和评估计数，不证明新的 correction capability。

开放问题：若继续研究，应先定义一种不依赖 target/颜色名称的像素级 physical-boundary 证明，并在控制矩阵上验证其同时满足边框不误报、文字完整性及 uncertainty fail-closed；在此之前，Stage B 不应接收 A1 的 uncertainty 认证，也不应生成写入候选。

## 审查后修复记录

当前 A1 已将 `uncertainty` 纳入 hard barrier，且聚焦回归断言 A1/A2/A5 均不得把 uncertainty 认证为 `required_text`。`stage-a-run-v0.2`、其 FORM 与 evaluation lock 仍是不可变历史证据，不回写也不重新裁决；该修复只消除未来只读 evidence replay 的已知 fail-closed 缺口，不能弥补 A1 的 420 px 文字未决、g004 的 70 px boundary 无自动 proof 或缺少控制矩阵的事实。因此 Stage B 仍为禁止，Gate 仍为 `NO_GO`。
