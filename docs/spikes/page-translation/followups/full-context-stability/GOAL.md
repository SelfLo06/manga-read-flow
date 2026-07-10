# Full Text Context Stability Follow-up — GOAL

## 1. 背景

Page Translation 主 Spike 已证明：

* 文本 API 可以调用；
* Page-level JSON 翻译基本可行；
* TextBlock 映射可以完整校验；
* glossary 对术语一致性有收益；
* malformed JSON 可通过一次 repair 恢复。

但主 Spike 无法可靠判断 previous context 的效果。

原因：

1. 8 个 Page fixture 中只有 1 个包含非空 `previous_context`；
2. 两个 `empty_response` 出现在实际没有 previous context 的请求上；
3. 对应 C/D 请求内容和 request hash 相同；
4. 单次请求无法区分随机 Provider 故障与输入因素；
5. `NO_OUTPUT` 被混入翻译质量 `UNUSABLE`，导致运行稳定性与译文质量没有完全分离。

因此，本 follow-up 只验证：

```text
Provider 空响应是否随机发生
+
previous context 是否带来稳定、可重复的质量收益或副作用
```

---

## 2. 核心目标

回答以下问题：

1. 相同请求重复调用时，HTTP 200 空响应是否会随机发生；
2. 空响应是否与 previous context 的存在或长度相关；
3. previous context 是否改善：

   * 人名称谓；
   * 专有名词；
   * 连续对白；
   * 省略主语、宾语或指代；
4. previous context 是否造成：

   * 历史内容污染；
   * 错误指代；
   * 无依据消歧；
   * 当前页信息被历史内容覆盖；
5. 是否可以为 MVP 确定一个最小 previous context 策略；
6. Provider 的空响应风险是否需要 Workflow 层 retry 或 fallback。

---

## 3. 固定基线

继续使用主 Spike 的冻结配置：

```text
Provider：原 OpenAI-compatible endpoint
Model：deepseek-v4-pro
Temperature：0
Max output tokens：1200
Timeout：60s
System Prompt：system-v1
Repair Prompt：repair-system-v1
Output Schema：原 Page Translation Schema
```

必须记录并校验原有 Prompt 和 Schema SHA-256。

主实验期间不得修改：

* System Prompt；
* Repair Prompt；
* JSON Schema；
* 模型；
* temperature；
* timeout；
* token 上限。

若必须修改其中任一项，应停止本轮并建立新的实验配置，不能混入当前结果。

---

## 4. 实验一：相同请求稳定性复现

从主 Spike 冻结输入中选择：

```text
context-dependent
long-page
previous-page
```

其中：

* `context-dependent` 和 `long-page` 曾出现 HTTP 200 `empty_response`；
* `previous-page` 是原实验中真正包含 previous context 且成功的样本。

对每个冻结请求执行至少 5 次独立调用。

要求：

* 请求 payload 完全相同；
* 每次调用有独立 trial ID；
* 不进行 transport retry；
* `empty_response` 不执行 repair；
* 调用顺序采用固定随机种子交错排列；
* 不连续执行同一 fixture 的所有 trial。

本实验用于判断：

```text
相同输入是否出现成功 / 空响应混合结果
```

若同一 request hash 在不同 trial 中既成功又空响应，应将其归类为 Provider/runtime 非确定性，不能归因于 previous context。

---

## 5. 实验二：Previous Context 配对实验

准备 4–6 个 Page fixture。

每个 fixture 必须：

* 有真实非空前序上下文；
* 当前页内容确实可能受前页影响；
* 包含 2–8 个当前页 TextBlock；
* previous context 为前 1 页；
* previous context 不超过 20 个 TextBlock；
* 只包含 accepted / locked 翻译；
* reference translation 不进入请求。

至少覆盖：

```text
人物称谓延续
专有名词延续
跨页连续对白
省略主语或宾语
指代对象延续
历史上下文可能误导当前页
```

每个 fixture 建立严格配对：

### Group N：No Previous Context

```text
System Prompt
+ 当前页全部 TextBlocks
+ reading_order / grouping
+ 相关 glossary
+ previous_context = []
```

### Group P：With Previous Context

```text
与 Group N 完全相同
+ 非空 previous_context
```

N/P 之间唯一允许变化的输入是：

```text
previous_context
```

每个条件至少执行 3 次独立调用。

调用顺序必须交错，避免把 Provider 某个时间段的故障错误归因到某一组。

---

## 6. 请求身份与可比性

每次请求记录：

```text
fixture_id
group
trial_index
request_hash
current_page_hash
glossary_hash
previous_context_hash
prompt_hash
schema_hash
generation_config_hash
```

配对实验必须验证：

```text
N.current_page_hash == P.current_page_hash
N.glossary_hash == P.glossary_hash
N.prompt_hash == P.prompt_hash
N.schema_hash == P.schema_hash
N.generation_config_hash == P.generation_config_hash
N.previous_context_hash != P.previous_context_hash
```

若不满足，当前 fixture 不得进入配对统计。

---

## 7. Provider 响应证据

每次调用至少记录：

```text
HTTP status
latency_ms
response body presence
choices_count
message.content 是否存在
message.content 字符数
finish_reason
usage 是否存在
input_tokens
output_tokens
脱敏 Provider request ID
```

原始响应应脱敏保存。

不得保存：

* API key；
* Authorization header；
* `.env` 内容；
* 其他认证信息。

`HTTP 200` 不能自动视为成功。

成功必须满足：

```text
存在 choice
且 message.content 非空
```

---

## 8. 结果分类

必须分开统计以下层级。

### Runtime / Provider

```text
SUCCESS_RESPONSE
HTTP_ERROR
TIMEOUT
EMPTY_BODY
NO_CHOICES
EMPTY_CONTENT
MISSING_USAGE
PROVIDER_REFUSAL
```

### Structure

只对非空响应统计：

```text
JSON_PARSE_VALID
SCHEMA_VALID
BLOCK_MAPPING_VALID
REPAIR_RECOVERED
REPAIR_FAILED
```

### Translation Quality

只对形成完整译文的 block 统计：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

没有模型输出时记录：

```text
NO_OUTPUT
NOT_EVALUABLE
```

不得把 `NO_OUTPUT` 计入翻译质量 `UNUSABLE`。

---

## 9. Previous Context 质量评价

逐配对 fixture 判断：

```text
CONTEXT_IMPROVEMENT
NO_MEANINGFUL_EFFECT
CONTEXT_REGRESSION
CONTEXT_POLLUTION
```

检查：

* 称谓是否更一致；
* 专有名词是否更一致；
* 连续对白是否更自然；
* 指代是否更准确；
* 是否复制前页内容；
* 是否引入当前页不存在的人物或事件；
* 是否无依据补充性别、说话人或对象；
* uncertainty flag 是否更合理。

必须记录具体 block 证据，不能只统计总数。

---

## 10. Empty Response 条件诊断

主实验不改变 token 和 timeout 配置。

仅当空响应被复现，且响应证据显示以下情况之一时：

```text
finish_reason = length
存在 reasoning 内容但 final content 为空
输出 token 上限疑似耗尽
```

才允许对受影响 payload 做一个条件性诊断：

```text
max_output_tokens：1200 → 2400
其他输入和参数保持不变
```

该诊断结果单独报告，不进入主 N/P 配对统计。

不得同时修改多个参数。

---

## 11. 非目标

本 follow-up 不执行：

* 修改长期翻译 Prompt；
* 优化 uncertainty Prompt；
* 正式 TranslationProvider 集成；
* Workflow retry 实现；
* ContextBuilder 正式实现；
* Repository 或数据库修改；
* VLM 或图片输入；
* 角色识别；
* 多模型比较；
* 多 Provider 比较；
* 成本优化；
* Cleaning 或 Typesetting。

Uncertainty 的系统性改进应在本 follow-up 收口后独立处理。

---

## 12. 成功条件

### Provider Stability

至少能够判断：

```text
PROVIDER_RANDOM
CONTEXT_ASSOCIATED
NOT_REPRODUCED
INCONCLUSIVE
```

不得仅依据单次失败判断。

### Previous Context

至少 4 个有效配对 fixture 完成全部 trial，并能够判断：

* 是否存在可重复的质量收益；
* 是否存在系统性污染或退化；
* 是否导致更高的空响应率；
* 是否适合 MVP 默认启用。

### 结构要求

对非空响应：

```text
final schema-valid rate = 100%
block mapping coverage = 100%
unknown block = 0
duplicate block = 0
```

允许最多一次结构 repair。

---

## 13. 决策输出

最终 verdict 只能是：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

同时必须给出两个独立结论。

### Empty Response Attribution

```text
PROVIDER_RANDOM
CONTEXT_ASSOCIATED
NOT_REPRODUCED
INCONCLUSIVE
```

### MVP Previous Context Policy

```text
ENABLE_COMPACT_CONTEXT
ENABLE_AS_OPTIONAL
DISABLE_FOR_MVP
UNDECIDED
```

### GO

满足：

* previous context 未降低响应稳定性；
* 对非空响应结构完整；
* 存在可重复质量收益；
* 没有系统性 context pollution。

### CONDITIONAL_GO

核心方案可用，但需要：

* compact context；
* Workflow 层一次运行重试；
* manual review；
* 或 previous context 仅对特定页面启用。

### FURTHER_SPIKE

出现：

* 空响应无法归因；
* Provider 稳定性不足；
* 有效配对样本不足；
* 上下文收益和副作用不明确。

### NO_GO

出现：

* previous context 明确、可重复地降低响应率；
* 经常造成历史污染或实质性误译；
* 缩小到 MVP 窗口后仍不可接受。

---

## 14. 预期产物

```text
docs/spikes/page-translation/followups/full-context-stability/
├── GOAL.md
├── HARNESS.md
├── PLAN.md
└── REPORT.md

local_samples/page_translation/full_context_followup/
local_samples/spike_outputs/page-translation-full-context/<run_id>/
```

允许复用主 Spike 脚本中的通用加载、校验和脱敏逻辑，但不得为 follow-up 引入正式产品抽象。

---

## 15. 对父报告的处理

主 Spike 的原始 run 和原始证据必须保留。

Follow-up 完成后，根据新证据对：

```text
docs/spikes/page-translation/REPORT.md
```

增加定向更正或 follow-up 引用，至少修正：

* `NO_OUTPUT` 与 `UNUSABLE` 的区分；
* response rate 与 schema-valid rate 的区分；
* previous context 与空响应的归因；
* unsupported disambiguation 的统计冲突；
* 主 Spike 最终 verdict 是否应调整为 `FURTHER_SPIKE`。

不得删除或改写原始 run 数据。
