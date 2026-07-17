# MVP-1 Visual Contract v0.1 — Open Questions

状态：`NON_BLOCKING_FOR_DESIGN_BASELINE`
说明：本文件只保留不阻塞 Visual Contract v0.1 的后续决策。若实现前仍影响 schema、contract 或 Gate，必须在相应 bounded Spike / schema review 中关闭。

| # | 问题 | 当前边界 | Owner / 关闭时点 |
|---:|---|---|---|
| 1 | `TextSegment` 最终是否 1:1 收敛到现有 `TextBlock`，还是成为独立持久化实体？ | 每个 segment 现在必须有恰好一个 immutable `ContentOwnerRef`；不得双 active owner | Persistence/Data Model review；正式 migration 前 |
| 2 | purpose-specific relation/revision 最小物理表如何拆分？ | 正式 DB 必须可查询/约束 active visual revision、instance lineage、assignment/exclusion、evidence refs 与 decision；不要求每个 slot/glyph 独立表 | Schema review；正式 Workflow 前 |
| 3 | topology split/merge 时如何自动判断“同一实例新 revision”或“新实例 identity”？ | 边界局部修正保 identity；语义 split/merge 新 identity；算法未冻结 | Topology bounded Spike |
| 4 | BubbleInstance/polygon/binary mask/glyph alpha 的 canonical encoding、坐标约定与 hash 是什么？ | identity/revision/hash/coordinate space 必填；overlay 不可替代 | Artifact contract + bounded Spike |
| 5 | residue score 与 required-text coverage 的数值阈值是什么？ | RequiredTextEvidence/PostCleaningResidueReport schema和缺证据blocking已冻结；阈值只可写入版本化 profile | Cleaning calibration 子集 |
| 6 | occupancy、relative margin、visual center、orphan、contrast、touch margin 的数值阈值是什么？ | actual glyph重算字段、hard safety与profile binding已冻结；不得用case-71/72两页直接冻结全局值 | Typesetting calibration 子集 |
| 7 | `simple_label` 是否属于 MVP-1 supported profile？ | 普通对白/旁白明确支持；复杂 SFX/艺术字明确 unsupported；simple label 暂不自动并入 | 产品范围复核 + bounded sample |
| 8 | superseded/failed mask、glyph、manifest 和 correction evidence 的 retention TTL？ | active、open issue、accepted decision 与 required replay evidence不可清理 | Artifact retention design |
| 9 | 上游改变后 active cleaned/typeset pointer 是保留 stale last-selected 还是原子清空？ | 无论选择哪种，stale pointer 均不可 export-effective，不得新增 active flag | Persistence/UI integration design |
| 10 | cleaned-only preview 是否允许展示？ | 可以作为历史/诊断候选，但不满足 MVP-1 high-quality readiness/export | UI/Export design |
| 11 | 用户主动多次编辑如何与自动 one-correction budget 区分？ | 用户编辑必须创建新 upstream revision/dependency snapshot和新chain；不能重置同一自动chain | Workflow/UI design |
| 12 | 低对比度使用何种局部颜色统计？ | Renderer须保存实际前景/描边与cleaned background refs；不可读低对比blocking | Typesetting bounded Spike |

## 已关闭的原 blocker

- Spike manifest 与正式 DB relations 的事实源冲突：已按阶段分离；
- TextSegment content owner 与 slot 基数：已冻结唯一 owner、一 segment/一 block/一 slot；
- supported exclusion 与 unsupported skip：已拆分；
- Cleaning residue 可执行证据：已冻结最低 schema 与缺证据 blocking；
- correction budget 跨崩溃重复消费：已冻结原子 reservation 与幂等恢复。

当前没有需要维护者立即裁决的 blocking question。
