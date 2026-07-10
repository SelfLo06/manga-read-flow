# Page Translation JSON Spike — GOAL

## 1. 目标

验证真实文本 LLM API 能否基于完整 Page 文本上下文，稳定完成日文漫画到简体中文的结构化翻译。

本 Spike 验证的实际调用形态为：

```text
版本化 System Prompt
+ 当前页 OCR TextBlocks
+ reading_order / grouping
+ Project glossary
+ 有界前序已接受译文
→ 文本 LLM
→ Page 级结构化翻译 JSON
```

本 Spike 需要回答：

1. 当前 API、模型和 endpoint 是否可以稳定调用；
2. Page 级翻译是否优于逐 TextBlock 独立翻译；
3. 输出是否稳定符合固定 JSON Schema；
4. `page_id` 和 `text_block_id` 是否完整、准确保留；
5. 是否会出现漏块、重复块、未知块或错配；
6. glossary 是否改善术语一致性；
7. 前序已接受译文是否改善指代、称谓和连续对白；
8. 历史上下文是否会造成内容污染或错误复制；
9. 上下文不足时，不确定性标记是否合理、稳定；
10. malformed 或 partial output 是否能通过一次 repair retry 修复；
11. latency、token、拒绝和错误是否适合单 Page MVP；
12. 当前方案是否值得进入正式 TranslationProvider 和 TranslationContextBuilder 设计。

---

## 2. 前置门禁：API Smoke Test

正式实验前必须先执行最小文本 API smoke test。

Smoke Test 只验证：

* API 环境变量已配置；
* endpoint 可以连接；
* API key 有效；
  -指定模型存在且可调用；
  -能够返回非空文本响应；
  -最小结构化翻译请求可以完成；
  -日志和输出中不包含密钥或认证头。

Smoke Test 不进入正式实验指标。

若出现以下情况，立即停止：

* authentication failure；
* model not found；
* endpoint 配置错误；
  -持续 timeout；
  -密钥泄漏；
  -最小请求无法形成有效响应。

---

## 3. Prompt 基线

正常翻译和结构修复分别使用版本化 Prompt：

```text
prompts/page-translation/system-v1.md
prompts/page-translation/repair-system-v1.md
```

每次运行必须记录：

```text
prompt_template_version
repair_prompt_template_version
system_prompt_sha256
repair_prompt_sha256
```

正式实验开始后，Prompt 内容冻结。

Prompt 发生变化时必须创建新版本，不能覆盖现有版本，也不能将不同版本的结果直接合并统计。

---

## 4. 核心实验范围

本 Spike 覆盖：

* 日文到简体中文；
* Page 级批量翻译；
* 逐块独立翻译基线；
* 固定 OCR TextBlock 输入；
* reading order 和 grouping；
* glossary 动态输入；
* 有界前序已接受译文；
* 固定结构化 JSON 输出；
* schema 校验；
* TextBlock 映射完整性；
* 不确定性枚举校验；
* malformed / partial output 检测；
* 最多一次结构修复 retry；
* 基础人工翻译质量评估；
* latency、token usage、API 错误和拒绝记录。

---

## 5. 输入契约

每个 Page fixture 至少包含：

```json
{
  "page_id": "page_001",
  "source_language": "ja",
  "target_language": "zh-Hans",
  "blocks": [
    {
      "text_block_id": "tb_001",
      "reading_order": 1,
      "group_id": "group_01",
      "source_text": "こんにちは"
    }
  ],
  "glossary": [],
  "previous_context": []
}
```

### 当前页 TextBlocks

必须包含：

* `text_block_id`
* `reading_order`
* `source_text`

`group_id` 可为空，但其处理策略必须固定。

### Glossary

Spike 使用冻结的本地 glossary fixture。

每个术语至少包含：

```json
{
  "source": "先輩",
  "target": "前辈",
  "note": "称谓"
}
```

只传递与当前实验 Page 相关的术语。

### Previous Context

前序上下文限定为：

```text
最多前 1 页
最多 20 个历史 TextBlock
只使用 accepted 或 locked translation
```

不得使用：

* stale translation；
* failed result；
  -未接受 Provider candidate；
  -人工参考答案；
  -当前页面 expected translation。

---

## 6. 输出契约

模型输出固定为：

```json
{
  "page_id": "page_001",
  "translations": [
    {
      "text_block_id": "tb_001",
      "translation_text": "你好",
      "uncertainty_flags": []
    }
  ]
}
```

允许的不确定性标记：

```text
context_ambiguous
pronoun_resolution_uncertain
speaker_context_uncertain
addressee_context_uncertain
ocr_uncertain
```

输出要求：

* `page_id` 必须与输入一致；
* 每个输入 `text_block_id` 必须恰好出现一次；
* 不允许未知或重复 `text_block_id`；
* 不允许静默漏块；
* `translation_text` 必须为字符串；
* `uncertainty_flags` 必须为合法字符串数组；
* 不允许输出 Schema 之外的字段；
* 不允许 Provider 输出 workflow decision。

Provider 不得输出：

```text
retry
block
pause
warning
accepted
```

这些决定仍属于 QualityCheckService 和 WorkflowLoopEngine。

---

## 7. 核心实验组

至少执行以下四组：

### A. Block-level Baseline

```text
System Prompt
+ 单个 TextBlock
```

用于建立逐块独立翻译基线。

### B. Page-level

```text
System Prompt
+ 当前页全部 TextBlocks
+ reading_order / grouping
```

用于验证整页文本上下文的实际价值。

### C. Page-level + Glossary

```text
Page-level
+ 相关 glossary
```

用于验证术语一致性及其副作用。

### D. Full Text Context

```text
Page-level
+ glossary
+ 有界 previous accepted translations
```

用于验证连续对白、称谓和指代改善，以及历史内容污染风险。

所有组必须使用同一模型和冻结参数。

---

## 8. 不确定性验证

本 Spike 不验证正式 speaker identification，但必须验证模型能否在上下文不足时避免无依据消歧。

重点检查：

* 是否无依据补充姓名；
* 是否无依据确定性别；
* 是否无依据确定说话人；
* 是否无依据确定对话对象；
* 是否错误补全被省略的主语或宾语；
* 是否遗漏会实质影响译义的歧义；
* uncertainty flags 是否过度使用；
* uncertainty flags 是否稳定使用。

人工评估至少记录：

```text
unsupported_disambiguation
missed_material_ambiguity
appropriate_uncertainty
over_flagging
```

---

## 9. Repair Retry

仅对以下问题允许执行一次 repair retry：

* invalid JSON；
* Markdown 包裹；
* schema invalid；
* wrong page ID；
* missing block；
* duplicate block；
* unknown block；
  -字段类型错误；
  -非法 uncertainty flag。

Retry 只修复结构和映射。

不得：

* 执行第二次 retry；
  -借 repair 全页重译；
  -人工补造模型答案；
  -消除合理歧义；
  -绕过 Provider 拒绝。

---

## 10. 非目标

本 Spike 不执行：

* 正式 TranslationProvider 集成；
* WorkflowLoopEngine 接入；
* TranslationContextBuilder 正式实现；
* Repository 或 SQLite 访问；
* GlossaryRepository 扩展；
* ArtifactService 登记；
* QualityIssue 创建；
* 当前页图片输入；
* VLM 或多模态翻译；
* speaker ID；
  -气泡与人物权威关联；
  -角色检测或跨页跟踪；
  -视觉情绪识别；
* Cleaning、Typesetting、API 或 Web UI；
  -多 Provider 横向比较；
  -多模型排行榜；
* Provider 内容策略绕过。

视觉语境问题后续由独立的：

```text
Translation Context Necessity Spike
```

根据真实文本翻译结果决定是否启动。

---

## 11. 硬边界

* API 密钥仅从环境变量读取；
* 不得将密钥写入源码、fixture、Prompt、日志或输出；
* 不修改 `src/manga_read_flow/**`；
* 不修改 Detection/OCR Spike；
* 不访问正式数据库；
* 不提交本地 `.env`；
* 不允许无限 retry；
* 不允许逐 fixture 硬编码；
* 不允许用参考译文修正模型输入；
* 不允许中途更换模型或参数；
* 不 commit、不 push，除非结果审查后明确授权。

---

## 12. 成功条件

Spike 至少应证明：

* API smoke test 通过；
* Page-level 翻译相较 block-level 存在可观察收益，或至少没有明显退化；
* 大多数首轮请求返回 schema-valid JSON；
* 一次 retry 后核心 fixture 均形成完整结构；
* 输入和输出 TextBlock 一一对应；
* unknown、duplicate 和 missing block 可被可靠检测；
* glossary 对术语一致性有明确收益或可判定无价值；
* previous context 的收益和污染风险可量化；
* unsupported disambiguation 可被人工识别；
* uncertainty flags 具有基本可用性；
  -结构错误与翻译质量错误能够区分；
  -API 错误、timeout 和 refusal 可结构化记录；
  -延迟和 token 用量适合单 Page MVP。

---

## 13. 最终决策

最终结论只能是：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

### GO

结构稳定、映射完整、Page 级上下文有效、性能可接受，可以进入正式 TranslationProvider 和 TranslationContextBuilder 最小设计。

### CONDITIONAL_GO

核心方案可用，但需要以下一项或多项约束：

* 一次 repair retry；
  -人工翻译复核；
  -严格 schema 校验；
* glossary 仅作为弱提示；
* previous context 需要更小窗口；
* uncertainty flag 需要 Quality Gate 解释；
  -个别内容需要 manual fallback。

### FURTHER_SPIKE

证据不足，例如：

* fixture 缺乏上下文歧义样本；
* Page-level 与 block-level 差异无法判断；
* glossary 或 previous context 实验设计不充分；
* uncertainty 输出无法可靠评估；
  -API 环境不稳定；
  -Prompt 或 Schema 尚未真正冻结。

### NO_GO

出现以下情况之一：

-最终结构无法稳定校验；
-TextBlock 丢失或错配不可控；
-Page-level 翻译没有价值且增加明显风险；
-历史上下文频繁污染当前译文；
-大量译文不可用；
-延迟、成本、拒绝或错误明显不适合 MVP。

---

## 14. 预期产物

```text
prompts/page-translation/
├── system-v1.md
└── repair-system-v1.md

docs/spikes/page-translation/
├── GOAL.md
├── HARNESS.md
├── PLAN.md
└── REPORT.md

tools/spikes/page_translation/spike.py
tests/unit/test_page_translation_spike.py

local_samples/page_translation/
local_samples/spike_outputs/page-translation/<run_id>/
```

本 GOAL 冻结后，下一步是修订 `HARNESS.md`，固定实验组、指标、人工评级、不确定性评估和退出门槛。
