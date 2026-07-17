# MVP-1 Visual Contract Bounded Spike C — GOAL

状态：`IN_PROGRESS`

## 唯一目标

验证最小、run-local 的证据合同能否判断：清理候选 output 中是否仍存在人眼可辨识的
原文字形结构，而不只是深色像素是否被改动。

它承接 Spike B 的 instance/revision binding 与 safe completeness，替换其只依赖
`luminance <= 180` text core 的 residue 语义。

## 语义边界

| 对象 | 本轮语义 | 不能替代 |
|---|---|---|
| `text_core` | 高置信深色字形种子 | 完整 visible support |
| `visible_support_candidate` | 由 core、局部颜色差与有限连通扩张得到的应消失候选 | safe-edit 或精确 GT |
| `safe_edit` | 可实际写回的支持子集 | required support |
| `protected` | 不得修改的已知结构 | 背景或不确定带 |
| `uncertainty` | 边界/归属不确定像素 | protected 或可写像素 |
| `residue_component` | output 中相对局部背景仍有对比、且与 source support 结构连通的候选 | 单独亮度异常/噪点 |

## 允许与禁止

允许：新 Spike C 文档、run-local harness/test、独立 `data/local` run、少量确定性
control、PNG/JSON evidence 与人工 FORM。

禁止：真实 Cleaner/inpainting、Provider、正式 Workflow/QualityCheckService 接入、API、UI、
migration、数据库、ArtifactService、Repository、Typesetting、OCR/翻译、Batch/性能优化。

## 裁决

只有全部 deliberate residue positive 被拒绝、背景 negative 未误报、support 无明显视觉漏失、
unsafe required 正确 review、Spike B Validator 不退化且人工审查通过，才可 `PASS`。

固定支持样本成立、一般化尚未证明时允许 `PASS_WITH_LIMITS / GO_FOR_BOUNDED_REAL_CLEANER_SPIKE`。
若一次聚焦修订后仍无法区分浅色 residue 与普通背景变化，则 `CHANGES_REQUIRED /
NOT_GO_FOR_REAL_CLEANING`。
