# Full Text Context Stability Follow-up — HARNESS

## 1. 目的

本 HARNESS 用于区分三类问题：

```text
Provider / runtime 非确定性
previous context 引起的稳定性变化
previous context 引起的翻译质量变化
```

不得把以下概念混合统计：

```text
无响应
结构无效
映射错误
译文质量不可用
```

---

## 2. 固定配置

主实验沿用父 Spike 配置：

```text
Provider：原 OpenAI-compatible endpoint
Model：deepseek-v4-pro
Temperature：0
Max output tokens：1200
Timeout：60s
System Prompt：system-v1
Repair Prompt：repair-system-v1
Schema：父 Spike schema
```

运行前记录：

```text
git_head
provider
model
generation_config
system_prompt_sha256
repair_prompt_sha256
schema_sha256
fixture_set_sha256
```

正式运行开始后不得修改上述配置。

---

## 3. 实验组成

本 follow-up 包含两个独立实验。

### S：Same-request Stability

固定请求：

```text
context-dependent
long-page
previous-page-with-context
```

每个请求至少执行：

```text
5 次独立 trial
```

要求：

* payload 完全一致；
* request hash 完全一致；
* 不执行 transport retry；
* empty response 不执行 repair；
* trial 顺序交错；
* 使用固定随机种子；
* 不连续跑完同一 fixture。

目标是判断相同请求是否出现：

```text
成功 / 空响应混合
```

---

### N/P：Previous Context Paired Test

准备：

```text
4–6 个有效配对 fixture
```

每个 fixture 包含：

```text
N：无 previous context
P：有 previous context
```

每个条件至少执行：

```text
3 次独立 trial
```

因此每个 fixture 最少：

```text
3 × N + 3 × P = 6 次调用
```

N/P 唯一允许变化的字段是：

```text
previous_context
```

---

## 4. Fixture 合格条件

进入配对统计的 fixture 必须满足：

* 当前页包含 2–8 个 TextBlock；
* 有真实非空前页上下文；
* previous context 不超过前 1 页、20 个 block；
* current page、glossary、Prompt、Schema、参数完全相同；
* reference translation 未进入请求；
* 当前页确实存在可能受前页影响的语义点。

至少覆盖：

```text
称谓延续
专有名词延续
连续对白
省略主语或宾语
指代延续
可能被历史上下文误导的页面
```

---

## 5. 配对完整性校验

每个 N/P pair 必须满足：

```text
N.current_page_hash == P.current_page_hash
N.glossary_hash == P.glossary_hash
N.prompt_hash == P.prompt_hash
N.schema_hash == P.schema_hash
N.generation_config_hash == P.generation_config_hash
N.previous_context_hash != P.previous_context_hash
```

任一条件不满足：

```text
PAIR_INVALID
```

该 fixture 不得进入 N/P 对比统计。

---

## 6. 调用顺序

所有 trial 使用固定随机种子生成交错顺序。

约束：

* 不连续执行同一 fixture 的全部 trial；
* N/P 交错；
* S 实验与 N/P 实验分开统计；
* 记录实际调用顺序和时间；
* 不因某次失败立即重跑。

避免把特定时间段的 Provider 波动错误归因到某一实验组。

---

## 7. Runtime 分类

每次调用只能归入一个主要 runtime 状态：

```text
SUCCESS_RESPONSE
HTTP_ERROR
TIMEOUT
EMPTY_BODY
NO_CHOICES
EMPTY_CONTENT
PROVIDER_REFUSAL
CLIENT_ERROR
```

定义：

### SUCCESS_RESPONSE

必须同时满足：

```text
HTTP 请求成功
choices_count >= 1
message.content 存在
message.content.strip() 非空
```

### EMPTY_CONTENT

HTTP 和 choice 存在，但：

```text
message.content 为空或仅含空白
```

### NO_CHOICES

响应存在，但：

```text
choices 为空或缺失
```

HTTP 200 不自动等于成功。

---

## 8. Provider 证据

每次调用记录：

```text
trial_id
fixture_id
group
trial_index
request_hash
HTTP status
latency_ms
response_body_present
choices_count
content_present
content_length
finish_reason
usage_present
input_tokens
output_tokens
provider_request_id
runtime_status
```

`provider_request_id` 必须脱敏。

不得记录：

```text
API key
Authorization header
.env 内容
完整认证响应头
```

---

## 9. Structure 分类

仅对 `SUCCESS_RESPONSE` 执行结构校验。

记录：

```text
json_parse_valid
schema_valid
page_id_valid
block_mapping_valid
missing_block_count
duplicate_block_count
unknown_block_count
invalid_uncertainty_flag_count
empty_translation_count
```

结构失败时最多允许一次 repair：

```text
repair_attempted
repair_recovered
repair_failed
```

以下情况不得 repair：

```text
HTTP_ERROR
TIMEOUT
EMPTY_BODY
NO_CHOICES
EMPTY_CONTENT
PROVIDER_REFUSAL
```

---

## 10. 质量分类

只对最终形成完整、可校验译文的 block 评级：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

无模型输出或结构无法恢复时记录：

```text
NO_OUTPUT
NOT_EVALUABLE
```

禁止将 `NO_OUTPUT` 计入 `UNUSABLE`。

---

## 11. Previous Context 评价

对每个有效 N/P 配对 block 记录：

```text
CONTEXT_IMPROVEMENT
NO_MEANINGFUL_EFFECT
CONTEXT_REGRESSION
CONTEXT_POLLUTION
```

并记录具体原因：

```text
term_consistency
honorific_consistency
dialogue_continuity
pronoun_resolution
subject_object_resolution
unsupported_disambiguation
historical_content_copy
historical_context_override
```

每个判断必须关联：

```text
fixture_id
text_block_id
N translation
P translation
reference or reviewer note
```

---

## 12. Stability 指标

### Same-request Stability

按 request hash 统计：

```text
trial_count
success_count
empty_content_count
no_choices_count
timeout_count
HTTP_error_count
mixed_outcome
```

若同一 request hash 同时出现成功和空响应：

```text
mixed_outcome = true
```

这支持 `PROVIDER_RANDOM`，不能归因于 previous context。

---

### N/P Runtime 对比

分别计算：

```text
N response_success_rate
P response_success_rate
N empty_response_rate
P empty_response_rate
N median_latency
P median_latency
```

同时按 fixture 配对比较，不能只比较总数。

---

## 13. 结构门槛

对所有非空响应，要求：

```text
final schema-valid rate = 100%
block mapping coverage = 100%
unknown block count = 0
duplicate block count = 0
illegal second repair = 0
```

结构指标的分母只能是：

```text
SUCCESS_RESPONSE
```

同时单独计算：

```text
end_to_end_valid_response_rate
=
最终完整有效响应数 / 总调用数
```

---

## 14. Previous Context 收益门槛

previous context 可判为有价值，至少满足：

* 4 个有效 paired fixture；
* 至少 2 个 fixture 出现可重复改善；
* 改善不只出现于单个 trial；
* 没有系统性 context pollution；
* 没有明显提高空响应率；
* 没有系统性增加 unsupported disambiguation。

若大多数 fixture 为：

```text
NO_MEANINGFUL_EFFECT
```

则不应默认启用 previous context。

---

## 15. Empty Response 归因

最终只能选择：

```text
PROVIDER_RANDOM
CONTEXT_ASSOCIATED
NOT_REPRODUCED
INCONCLUSIVE
```

### PROVIDER_RANDOM

满足任一：

* 同一 request hash 在不同 trial 中既成功又空响应；
* 空响应分散出现在 N/P 两组，且无稳定相关性。

### CONTEXT_ASSOCIATED

必须满足：

* P 组空响应率稳定高于 N；
* 至少 2 个 fixture 重复出现；
* 相同 current page 的 N 成功、P 多次失败；
* 排除调用时段和配置变化。

### NOT_REPRODUCED

所有重复 trial 均成功，未再次出现空响应。

### INCONCLUSIVE

样本不足、结果冲突或无法排除 Provider 波动。

---

## 16. 条件性 Token 诊断

仅当空响应被复现，且证据显示可能与输出长度相关时，才允许执行：

```text
max_output_tokens = 2400
```

其他配置保持不变。

诊断组单独标记：

```text
TOKEN_DIAGNOSTIC
```

不得进入主 N/P 统计。

---

## 17. Reviewer

使用独立只读 reviewer 检查：

* N/P 是否真正只差 previous context；
* runtime 和 translation quality 是否分离；
* context improvement 是否有具体证据；
* context pollution 是否漏计；
* unsupported disambiguation 是否漏计；
* verdict 是否符合 HARNESS。

Reviewer 不修改代码、fixture、原始响应或指标。

需要用户判断的边界样本单独列出。

---

## 18. 决策门槛

### GO

同时满足：

```text
至少 4 个有效 paired fixture
P 组响应稳定性不低于 N
非空响应 final schema-valid = 100%
block mapping coverage = 100%
previous context 有可重复质量收益
无系统性 context pollution
```

### CONDITIONAL_GO

满足核心可行性，但需要：

```text
compact previous context
按需启用
Workflow 层一次运行重试
manual review
```

### FURTHER_SPIKE

出现：

```text
有效 pair 不足
空响应归因不明确
previous context 收益不稳定
Provider 波动过大
```

### NO_GO

出现：

```text
P 组可重复降低响应率
previous context 经常污染当前页
previous context 经常造成实质性误译
缩小上下文后仍不可接受
```

---

## 19. 最终输出

必须给出两个独立结论：

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

总 verdict：

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

不得用单次失败或单个 fixture 推导整体结论。
