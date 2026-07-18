# Physical Bubble Boundary Spike 交接 v0.1

## 1. 交接目的与 blocker

本交接为当前 Slice 3 的受控能力缺口建立独立、有限的 Spike。它不授权修改 Slice 3 的 acceptance、阈值、protected/uncertainty guard 或任何已有 migration。

当前 blocker 是：两个普通对白 target 的 required text support 在真实物理 BubbleInstance 边界走廊内与 protected/uncertainty 相交。现有安全合同正确阻止 Cleaner，因此它们不能成为组合成员；没有证据证明这些像素可安全删除。

## 2. 冻结事实

| target | required | safe | unsafe required | required∩protected | required∩uncertainty | 当前结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| g002 | 15,802 | 15,092 | 710 | 103 | 710 | `BLOCKED_UNSAFE_REQUIRED` |
| g004 | 13,133 | 13,063 | 70 | 34 | 70 | `BLOCKED_UNSAFE_REQUIRED` |

两者全部 unsafe support 位于真实 BubbleInstance 的 boundary corridor；这是已冻结观察，不是“可以安全放行”的证明。两者 source、visual revision、现有 required/safe/protected/uncertainty evidence 均须保持可复现。

## 3. Physical boundary 与 Slice F virtual boundary 的差异

Slice F 的 text-aware planner 仅处理两个互斥、相邻 BubbleInstance 之间的**虚拟分界**：它拥有 primary/neighbor instance、shared virtual boundary，以及只在该虚拟走廊内转移 uncertainty 的明确定义。

本交接对象是单个实例的**真实物理气泡轮廓**。其中部分 required support 已与真实 protected outline 重合；不存在可替代的相邻实例或 virtual separator。把 protected physical boundary 伪装成 Slice F virtual boundary 会改变 planner 的前提并违反其 guard。

## 4. 为什么现有 Slice F planner 不适用

1. 缺少 mutually exclusive primary/neighbor instance 对与 shared virtual boundary 输入。
2. `required∩protected` 非零，违反 planner 不移动 protected/visible 像素的安全语义。
3. 当前 evidence 无法逐像素证明 unsafe support 是文字抗锯齿而不是真实气泡轮廓。
4. 仅以 unsafe 比例、实例名称、页面、坐标或人工修图放行均不构成通用证据。

因此当前 Slice 3 不得创建 correction reservation、调用 Slice F planner 或调用 Cleaner 处理这些 blocker。

## 5. 禁止事项

- 不使用 case/page/target id、文件名或坐标作为规则输入。
- 不扩大 safe mask，不缩小 required support，不降低 protected/uncertainty guard。
- 不按 unsafe 比例自动放行，不手工修图，不使用第二次自动 correction。
- 不改 schema、migration/checksum、page validator 或 acceptance predicate。
- 不把 Spike 结果直接写为 `CLEANED_PASS` 或更新 active pointer。

## 6. Spike Goal

验证是否存在通用的 physical-bubble-boundary evidence 或一次性 correction，使候选文字边缘与真实 bubble outline 可被区分，并且在不写 protected physical boundary、不中断 required evidence、通过独立 validator 的前提下，重建可安全编辑的 support。

若不能证明，Spike 必须明确 `NO_GO`，保留当前 blocker；“更保守”或“看起来可能可清”都不是通过条件。

## 7. Spike HARNESS

Spike 需要：

1. 冻结 source hash、visual revision、instance/segment revisions、required/safe/protected/uncertainty masks、配置与依赖 fingerprint。
2. 使用至少一个非目标页或合成控制样本验证规则不是 target-specific。
3. 生成 candidate evidence 前后数值对照：required、safe、protected、uncertainty、交集、actual changed、residue、boundary damage、outside-safe write。
4. 若存在自动 correction，只能创建一个 durable `CorrectionChain` / `CorrectionReservation`，ordinal 必须为 1；provider/validator 不消耗预算。
5. Provider 不能访问数据库；图像工作不能持有 SQLite write transaction；validator 只返回事实，workflow 决定 block/accept。

## 8. 需要研究的问题

- 如何区分文字边缘与真实 bubble outline；
- 是否能在不写 protected boundary 的前提下重建 safe-edit；
- visible-support evidence 是否需要通用改进；
- 是否存在通用 physical-boundary correction；
- 如何保证 required evidence 不缩小；
- 如何保持 one automatic correction；
- 如何独立验证 residue、boundary damage 与 outside-safe write。

## 9. 成功与失败标准

### GO

- 对冻结与控制样本都不依赖 page/target/坐标分支；
- required support 原样保留，protected physical boundary 零写入；
- 独立 validator 的 protected、uncertainty、boundary、outside-safe、residue predicate 全部通过；
- correction（如有）可 durable replay，ordinal 不超过 1；
- 视觉和数值证据可复验，且无 active pointer 更新。

### NO_GO

任一条件不能证明，或需要放宽 guard、缩小 required、手工修图、第二次 correction、schema 变更、新的 page-specific rule，即为 `NO_GO`。返回 Slice 3 后继续保留完整 blocker，不得伪造成功。

## 10. 可修改范围

独立 Spike 可新增其自身的 `GOAL.md`、`HARNESS.md`、局部实验代码、局部测试、局部 REPORT/GATE 和 gitignored evaluation evidence。除非后续 Spike Gate 明确授权，禁止修改 Slice 3 runner 的既有 acceptance/block 合同、Slice 1/2 migration、final detailed design 或现有冻结 run。

## 11. 必需视觉与数值证据

- original / candidate / side-by-side / absolute diff；
- required、safe、protected、uncertainty 与 actual-changed overlay；
- 每实例 crop 与 boundary corridor overlay；
- candidate 与 evidence hash lock；
- 像素交集、连通域、boundary distance 分布；
- independent validator summary 与负例控制；
- correction reservation/replay（若适用）。

## 12. 返回 Slice 3 的集成 Gate

只有独立 Spike 的 Gate 为 `GO`，且证明通用规则、完整证据、一次 correction、独立 validator 与 source preservation 后，才允许回到当前 Slice 3 集成。该 Gate 不自动接受 case-72；集成后仍须创建新的 immutable run、重新验证并完成新的人工 FORM。
