# 140 Translation

Translation 以版本化 OCR、页面顺序和 glossary version 为输入，生成 segment 对齐的简体中文结果与 Provider provenance。用户修改创建新 TranslationResult version，并使 Cleaning/Typesetting/Export 的相关结果 stale。

## Implementation Status

```text
Historical page/full-context Spike: EXPERIMENT_ONLY
Real LLM Provider Adapter: NOT IMPLEMENTED
Production input assembler: NOT IMPLEMENTED
Authoritative translation input unit: NOT YET FROZEN
Structured group/segment alignment: NOT IMPLEMENTED
TranslationCheck with real Provider: NOT IMPLEMENTED
Formal real-provider acceptance: NOT IMPLEMENTED
Manual edit product entry: NOT IMPLEMENTED
M1: NOT COMPLETE
```

当前只确定 Translation 将调用大模型。通用 TranslationResult/pointer 和 FakeProvider lifecycle 不证明真实翻译已实现；历史 page/full-context Spike 只证明受限实验调用，不证明产品输入合同或术语、称谓、代词、口吻质量。OCR/Grouping 提供给 Translation 的 authoritative unit 和 alignment 仍需后续最小设计核实，本文不提前冻结 fragment 或 text-group 方案。

页面级最小上下文属于 M1 可考虑范围；跨页一致性、系统性 semantic review 和更完整语义质量仍属于 M2。

Provider refusal 必须记录并交由 WorkflowLoopEngine 决策，禁止绕过服务政策。风险包括 fragment/group 对齐错误、上下文泄露、术语漂移和 secrets 进入日志。验证需覆盖单页、正式输入 identity、结构化对齐、术语版本、人工编辑、拒绝、局部重翻与 stale propagation；必要多页上下文边界待 M2 冻结。
