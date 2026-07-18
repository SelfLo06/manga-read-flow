# 开放问题——整页清字台账 v0.1

以下不阻塞本设计或 schema implementation，但必须在相应实现 Slice 中以测试收口：

1. 同一 BubbleInstance 覆盖多个 segment 时，validator 的 per-segment residue attribution 采用独立 partition artifact 还是一个带 component-to-segment mapping 的 validator evidence artifact；无论选择何者，missing/duplicate 必须可查询。
2. `processing_artifact` 现有 artifact type vocabulary 是否需增加专用的 `actual_changed_mask`、`page_validation_evidence` 等稳定类型；这不改变 ArtifactService 单一入口。
3. 新 issue relation table 如何映射既有 UI/查询 DTO；本 Goal 不设计 API/UI。
4. completion migration 的 checksum 常量由 Slice 2 实现按当前 lightweight runner 固定；一经提交不得改写。

已关闭：stale 时清空 active cleaned pointer；历史由 immutable run/candidate/member/validation/issue/artifact relations 读取，不保留一个语义含混的 stale active pointer。

已关闭：v3 的物理迁移分期。根据 [迁移分期修订 v0.1.1](migration-staging-amendment-v0.1.1.md)，foundation 与 completion 两条不可变 marker 共同构成完整逻辑 v3，不升级 v4。
