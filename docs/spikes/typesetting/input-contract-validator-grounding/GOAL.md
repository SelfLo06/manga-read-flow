# Typesetting Input Contract & Validator Grounding — GOAL

## 目标

在 `case-71`、`case-72` 上建立可追踪的临时端到端输入合同，并验证 Typesetting validator 的 region 语义与真实气泡内部一致。

本 Goal 回答：

1. 每个 Detection fragment 经 Grouping、OCR、Translation、Container/Cleaning 后去了哪里；
2. 一个 container 内多个文字段能否保持独立身份、顺序和译文；
3. Typesetting 是否使用独立、可审查的 region，而非 Cleaning safe mask 或展示 overlay；
4. 越界、触边和错误容器负例是否必然被拒绝；
5. 临时 workflow 每阶段与总耗时是多少。

## 冻结范围

- 两页：`case-71`、`case-72`；不扩样本。
- 复用冻结 S1 Detection/Grouping、Goal 6 Cleaning 风险与写回结果。
- 对每个 group/segment 真实调用 MangaOCR。
- 使用已验证的 Page-level Translation API；无 previous context；不使用硬编码译文。
- E1 才生成 typesetting block；E2/E3 保留完整 exclusion reason。
- 不接正式 Provider、Workflow、数据库或 ArtifactService。

## 门禁

- 100% source fragment 恰好映射到一个 group 和一个 segment；
- 100% segment 有 OCR 结果或明确失败原因；
- Translation 输入输出 block ID 完整、无 unknown/duplicate/missing；
- case-71 大容器的多个段落保持独立 segment ID；
- 每个 E1 block 使用独立持久化的 `typesetting_region`；
- safe 正例通过，overflow、boundary-touch、wrong-container 负例全部拒绝；
- region overlay 经人工确认与真实气泡边界一致；
- `timings.json` 同时包含复用阶段、执行阶段和 total wall time。

任一门禁失败则保持 `NO_GO`，不进入字号、换行或样式优化。

## 非目标

- 不重新训练或调 Detection/Grouping/Association/Cleaning；
- 不做整书实验；
- 不冻结字体、字号或换行策略；
- 不将开发期 region 人工确认变成产品运行期步骤；
- 不 commit、不 push，除非另行授权。
