# 140 Translation

Translation 以版本化 OCR、页面顺序和 glossary version 为输入，生成 segment 对齐的简体中文结果与 Provider provenance。用户修改创建新 TranslationResult version，并使 Cleaning/Typesetting/Export 的相关结果 stale。

历史 page/full-context Spike 证明了受限调用与输入合同，不证明术语、称谓、代词、口吻或多页一致性达标。M1 可使用可信译文隔离视觉闭环；系统性语义质量属于 M2。

Provider refusal 必须记录并交由 WorkflowLoopEngine 决策，禁止绕过服务政策。风险包括 segment 串块、上下文泄露、术语漂移和 secrets 进入日志。验证覆盖单页、多 segment、术语版本、人工编辑、拒绝、局部重翻与 stale propagation；必要多页上下文边界待 M2 冻结。
