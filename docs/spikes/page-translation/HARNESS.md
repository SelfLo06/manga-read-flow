# Page Translation JSON Spike — HARNESS

## 1. 目的

本 HARNESS 用于保证 Page Translation Spike：

* 输入冻结；
* Prompt 可追踪；
* 实验组可比较；
* 结构错误、上下文错误和翻译质量问题可以分别归因；
* 结果可复现。

评估必须区分：

```text
API / runtime failure
JSON / TextBlock mapping failure
translation quality failure
context misuse or unsupported disambiguation
```

---

## 2. 固定实验配置

本轮只使用：

* 一个 Provider；
* 一个模型；
* 一套 generation 参数；
* 一个正常翻译 Prompt 版本；
* 一个 repair Prompt 版本；
* 一套冻结 fixtures；
* 一份固定 JSON Schema。

首次正式运行后不得中途修改模型、Prompt、Schema、fixture 或参数。

每次运行必须记录：

```text
provider
model
temperature
max_output_tokens
timeout
prompt_template_version
repair_prompt_template_version
system_prompt_sha256
repair_prompt_sha256
schema_sha256
fixture_sha256
```

---

## 3. API Smoke Test

正式实验前先执行最小文本 API smoke test。

验证：

1. 必要环境变量存在；
2. endpoint 可连接；
3. API key 有效；
4. 模型可调用；
5. 能返回非空结果；
6. 最小 JSON 翻译请求可以完成；
7. 日志和输出不包含密钥。

Smoke Test 不计入正式指标。

以下情况立即停止：

* authentication failure；
* model not found；
* endpoint 错误；
* 持续 timeout；
* API key 或认证头泄漏。

---

## 4. Fixture 集合

准备 6–8 个冻结 Page fixture，至少覆盖：

| 场景                | 重点             |
| ----------------- | -------------- |
| basic-dialogue    | 普通短对白          |
| multi-block       | 同页连续文本         |
| context-dependent | 省略主语、宾语或指代     |
| terminology       | 重复人名、称谓或专有名词   |
| previous-page     | 连续对白和历史称谓      |
| ocr-noise         | 错字、断行、异常符号     |
| sound-effects     | 拟声词和对白混合       |
| long-page         | block 较多、上下文较长 |

每个 fixture 至少包含：

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

约束：

* `page_id` 在 fixture 集合中唯一；
* 同页 `text_block_id` 唯一；
* `reading_order` 可排序且不重复；
* reference translation 不得进入模型输入；
* previous context 不能包含当前页答案。

---

## 5. Previous Context 边界

前序上下文固定为：

```text
最多前 1 页
最多 20 个 TextBlock
只使用 accepted 或 locked translation
```

不得使用：

* stale translation；
* failed result；
* 未接受 Provider 输出；
* 人工参考答案；
* 当前页 expected translation。

历史上下文只用于称谓、术语、指代和连续对白，不得成为当前页翻译内容。

---

## 6. 输出 Schema

输出固定为：

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

结构规则：

* `page_id` 必须完全一致；
* 每个输入 `text_block_id` 恰好出现一次；
* 不允许 missing、duplicate 或 unknown block；
* `translation_text` 必须为字符串；
* `uncertainty_flags` 必须为合法字符串数组；
* 不允许额外字段；
* 不允许输出 workflow decision。

---

## 7. 实验组

### A. Block-level Baseline

每个 TextBlock 独立调用。

输入：

```text
System Prompt
+ 单个 TextBlock
```

目的：建立缺少 Page 上下文时的基线。

### B. Page-level

输入：

```text
System Prompt
+ 当前页全部 TextBlocks
+ reading_order / grouping
```

目的：验证整页上下文收益。

### C. Page-level + Glossary

输入：

```text
Page-level
+ 相关 glossary
```

目的：验证术语一致性和错误套用风险。

### D. Full Text Context

输入：

```text
Page-level
+ glossary
+ previous accepted translations
```

目的：验证跨页称谓、指代和连续对白，同时检查历史内容污染。

所有组使用同一模型和 generation 参数。

---

## 8. 结构指标

记录：

```text
request_count
api_success_count
raw_json_parse_rate
first_pass_schema_valid_rate
final_schema_valid_rate
expected_block_count
matched_block_count
missing_block_count
duplicate_block_count
unknown_block_count
wrong_page_id_count
invalid_uncertainty_flag_count
block_coverage
```

定义：

```text
block_coverage =
matched input blocks / expected input blocks
```

---

## 9. 翻译质量评估

每个翻译 block 标记：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

检查：

* 基本语义；
* 漏译和增译；
* 否定、数字、敬语和语气；
* 人名和术语；
* Page 内连贯性；
* 历史内容污染；
* OCR 噪声导致的幻觉。

禁止使用逐字一致作为唯一标准。

---

## 10. 上下文和不确定性评估

每个适用 block 记录：

```text
appropriate_uncertainty
unsupported_disambiguation
missed_material_ambiguity
over_flagging
context_pollution
```

定义：

* `appropriate_uncertainty`：确有影响译义的歧义，模型正确标记；
* `unsupported_disambiguation`：模型无依据补充姓名、性别、说话人、对象或主宾关系；
* `missed_material_ambiguity`：歧义可能改变译义，但模型未标记；
* `over_flagging`：普通省略不影响译义，却过度标记；
* `context_pollution`：错误复制或迁移历史上下文内容。

不确定性标记数量本身不代表质量。

---

## 11. 实验组对比指标

### Page-level 相对 Block-level

比较：

* `ACCEPTABLE` 比例；
* `REVIEW / UNUSABLE` 比例；
* 术语一致性；
* 指代和连续对白；
* unsupported disambiguation；
* latency 和 token 增量。

### Glossary 效果

记录：

```text
term_expected_count
term_correct_count
term_hit_rate
wrong_term_application_count
```

### Previous Context 效果

记录：

```text
context_improvement_count
context_no_effect_count
context_regression_count
context_pollution_count
```

---

## 12. Repair Retry

只对结构和映射错误执行一次 retry：

* invalid JSON；
* Markdown 包裹；
* schema invalid；
* wrong page ID；
* missing / duplicate / unknown block；
* 字段类型错误；
* 非法 uncertainty flag。

记录：

```text
retry_attempted
retry_recovered
retry_failed
```

禁止：

* 第二次 retry；
* repair 全页重译；
* 人工补造译文；
* 用 reference translation 修复输出；
* 对 refusal 执行绕过式 retry。

---

## 13. API 和性能指标

记录：

```text
latency_ms
input_tokens
output_tokens
estimated_cost
timeout_count
provider_error_count
refusal_count
empty_response_count
```

分别统计 Block-level 与 Page-level，避免只看总量。

---

## 14. 错误分类

统一使用：

```text
api_timeout
api_error
provider_refusal
empty_response
invalid_json
markdown_wrapped_json
schema_invalid
wrong_page_id
missing_block
duplicate_block
unknown_block
invalid_uncertainty_flag
empty_translation
translation_omission
translation_hallucination
terminology_inconsistent
meaning_error
unsupported_disambiguation
missed_material_ambiguity
context_pollution
```

一次请求可以包含多个标签。

---

## 15. 决策门槛

### GO

同时满足：

```text
API smoke test = pass
first-pass schema-valid rate >= 90%
final schema-valid rate = 100%
block coverage >= 98%
unknown block count = 0
duplicate block count = 0
ACCEPTABLE + REVIEW >= 90%
无系统性 context pollution
Page-level 相比 Block-level 有收益或无明显退化
latency 和 token 成本适合单 Page MVP
```

### CONDITIONAL_GO

核心能力可用，但存在：

* 偶发一次 repair retry；
* 少量人工复核；
* glossary 需要弱提示策略；
* previous context 需要更小窗口；
* uncertainty flags 需要 Quality Gate 解释；
* 个别 OCR 噪声或歧义样本质量不稳定。

### FURTHER_SPIKE

出现：

* fixture 覆盖不足；
* Prompt 或 Schema 尚未冻结；
* Page-level 与 Block-level 差异不明确；
* glossary 或 previous context 证据不足；
* uncertainty 评估无法可靠执行；
* API 环境不稳定。

### NO_GO

出现：

* final schema-valid 无法稳定达到 100%；
* block 映射错误不可控；
* Page-level 明显劣于 Block-level；
* previous context 经常污染当前译文；
* 大量 `UNUSABLE`；
* 延迟、成本或拒绝率无法接受。

---

## 16. 可复现性和输入完整性

每次运行记录：

```text
run_id
timestamp
git_head
branch
prompt hashes
schema hash
fixture hashes
provider
model
generation config
```

运行前后重新计算 fixture、Prompt 和 Schema SHA-256。

任一输入发生变化，当前 run 判定无效。

不得记录：

* API key；
* authorization header；
* `.env` 内容；
* 完整敏感响应头。

---

## 17. 最小输出

每次运行至少生成：

```text
results.json
summary.json
requests.csv
translations.csv
raw_responses/
logs/
```

人工评级应单独保存，不得修改原始模型响应。

---

## 18. 停止条件

出现以下情况立即停止：

* API key 泄漏；
* baseline 测试失败；
* Prompt、Schema 或 fixture 在 run 中变化；
* 需要修改 `src/**`；
* 需要第二次 retry；
* 需要中途更换模型或参数；
* 需要逐 fixture 硬编码；
* 参考译文进入模型输入；
* 无法区分结构错误和翻译质量错误。
