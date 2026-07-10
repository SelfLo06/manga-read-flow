# Full Text Context Stability Follow-up — PLAN

## 1. 执行目标

完成两个隔离实验：

```text
S：相同请求重复调用稳定性
N/P：无上文与有上文的严格配对实验
```

最终回答：

1. HTTP 200 空响应是否属于 Provider 随机波动；
2. previous context 是否降低响应稳定性；
3. previous context 是否带来可重复的翻译质量收益；
4. MVP 应默认启用、按需启用或暂不启用 previous context。

本 follow-up 不接入正式产品代码。

---

## 2. 允许文件范围

允许创建或修改：

```text
docs/spikes/page-translation/followups/full-context-stability/
├── GOAL.md
├── HARNESS.md
├── PLAN.md
└── REPORT.md

tools/spikes/page_translation/full_context_followup.py
tests/unit/test_page_translation_full_context_followup.py

local_samples/page_translation/full_context_followup/**
local_samples/spike_outputs/page-translation-full-context/**
```

允许对父报告做定向修正：

```text
docs/spikes/page-translation/REPORT.md
```

只允许修正：

* `NO_OUTPUT` 与 `UNUSABLE` 的分类；
* response rate 与 schema-valid rate 的分母；
* previous context 与空响应的归因；
* unsupported disambiguation 统计冲突；
* follow-up 引用和最终 verdict。

禁止修改：

```text
src/manga_read_flow/**
prompts/page-translation/**
父 Spike 原始 results
父 Spike fixture
依赖文件和锁文件
数据库与正式 artifact
```

---

## 3. 实现策略

新建独立脚本：

```text
tools/spikes/page_translation/full_context_followup.py
```

可以复用父 Spike 中的：

* API client；
* Prompt 加载；
* Schema 校验；
* JSON 解析；
* repair 调用；
* hash；
  -日志脱敏；
  -结果汇总。

优先通过导入已有纯函数复用。

若父脚本不是可导入结构，允许复制少量 Spike 辅助逻辑，但不得为此重构正式产品代码，也不得建立通用框架。

---

## 4. CLI

建议提供：

```text
validate
run-stability
run-paired
verify
summarize
```

### `validate`

验证：

* Prompt 和 Schema hash 与父 Spike 一致；
* stability 请求存在；
* paired fixtures 合法；
* N/P 只差 `previous_context`；
* trial 数量满足 HARNESS；
* reference 未进入请求；
* API 环境存在但不打印密钥。

### `run-stability`

执行 Same-request Stability 实验。

### `run-paired`

执行 N/P 配对实验。

### `verify`

验证：

* 请求 hash 和配对 hash；
* trial 完整性；
  -调用顺序；
  -runtime 分类；
  -修复次数；
  -输出与统计一致；
  -不存在密钥泄漏。

### `summarize`

生成：

* runtime 稳定性汇总；
* N/P 响应率对比；
  -结构指标；
  -质量对比输入表；
  -REPORT 所需结论证据。

---

## 5. Fixture 目录

建议：

```text
local_samples/page_translation/full_context_followup/
├── manifest.json
├── stability/
├── paired/
├── references/
└── ratings/
```

### `stability/`

保存三个冻结请求：

```text
context-dependent.json
long-page.json
previous-page-with-context.json
```

优先从父 Spike 实际请求中导出，确保 payload 和 request hash 可核对。

### `paired/`

准备 4–6 个 fixture：

```text
paired/<fixture_id>.json
```

每个文件至少包含：

```json
{
  "fixture_id": "continuity-01",
  "current_page": {
    "page_id": "page-002",
    "source_language": "ja",
    "target_language": "zh-Hans",
    "blocks": []
  },
  "glossary": [],
  "previous_context": [],
  "evaluation_focus": [
    "dialogue_continuity",
    "pronoun_resolution"
  ]
}
```

N/P 请求由脚本生成，不保存两份可漂移的 fixture。

---

## 6. Fixture 选择

至少准备：

| Fixture                | 主要风险         |
| ---------------------- | ------------ |
| honorific-continuity   | `先輩`、称谓延续    |
| proper-name-continuity | 人名或专有名词统一    |
| dialogue-continuity    | 跨页连续对白       |
| omitted-object         | `渡す` 等宾语省略   |
| pronoun-continuity     | 指代对象依赖前页     |
| misleading-context     | 前页上下文可能误导当前页 |

至少 4 个必须通过配对校验。

优先使用真实漫画式文本或真实 OCR 结果；允许少量 synthetic fixture 补足单一风险。

---

## 7. 调用矩阵

### S 实验

```text
3 个请求 × 5 trials = 15 次调用
```

使用固定随机种子打乱调用顺序。

同一 fixture 的 5 次请求必须具有：

```text
相同 payload
相同 request_hash
不同 trial_id
```

不执行 transport retry。

---

### N/P 实验

假设使用 6 个 fixture：

```text
6 fixtures × 2 groups × 3 trials = 36 次调用
```

每个 fixture：

```text
N1 P1 N2 P2 N3 P3
```

实际顺序统一随机交错，不保证局部严格交替，但必须避免同组集中执行。

固定随机种子和实际执行顺序写入 run metadata。

---

## 8. 请求构造

### N 组

```json
{
  "page_id": "...",
  "source_language": "ja",
  "target_language": "zh-Hans",
  "blocks": [],
  "glossary": [],
  "previous_context": []
}
```

### P 组

除 `previous_context` 外，与 N 完全相同：

```json
{
  "page_id": "...",
  "source_language": "ja",
  "target_language": "zh-Hans",
  "blocks": [],
  "glossary": [],
  "previous_context": [
    {
      "page_id": "page-001",
      "blocks": [
        {
          "source_text": "...",
          "translation_text": "..."
        }
      ]
    }
  ]
}
```

不得加入：

* 当前页参考译文；
* stale 或 failed translation；
* 未接受候选；
  -额外人物说明；
  -人工推断的 speaker ID。

---

## 9. Trial 结果记录

每次调用保存：

```text
trial_id
experiment
fixture_id
group
trial_index
request_hash
current_page_hash
glossary_hash
previous_context_hash
HTTP status
latency_ms
response body presence
choices_count
content presence
content length
finish_reason
usage presence
input tokens
output tokens
runtime status
first validation
repair result
final validation
```

Provider request ID 只保存脱敏值。

---

## 10. Runtime 处理

运行时不自动重发失败请求。

以下状态直接记录：

```text
HTTP_ERROR
TIMEOUT
EMPTY_BODY
NO_CHOICES
EMPTY_CONTENT
PROVIDER_REFUSAL
CLIENT_ERROR
```

这些状态：

* 不执行 repair；
* 不计入 schema-valid 分母；
  -质量评级为 `NO_OUTPUT / NOT_EVALUABLE`。

同一 payload 的下一 scheduled trial 不视为 retry。

---

## 11. Structure 与 Repair

仅对非空 content 执行：

```text
JSON parse
Schema validation
page_id validation
TextBlock mapping validation
uncertainty enum validation
```

仅结构问题允许一次 repair。

记录首轮和最终结果，禁止第二次 repair。

---

## 12. 质量评价准备

脚本生成待评审表：

```text
ratings/pairs.csv
```

至少包含：

```text
fixture_id
text_block_id
trial_index
N translation
P translation
reference
evaluation_focus
runtime status
```

评审时隐藏不必要的 Provider metadata。

由独立 reviewer 记录：

```text
N rating
P rating
context effect
reason
unsupported disambiguation
context pollution
uncertainty assessment
```

自动脚本不得根据字符串差异自动认定 context improvement。

---

## 13. 单元测试

测试不得调用真实 API。

至少覆盖：

1. 父 Prompt / Schema hash 校验；
2. stability payload hash 一致；
3. N/P 只差 previous context；
4. current page hash 不一致时 pair invalid；
5. glossary hash 不一致时 pair invalid；
6. trial 数不足；
7. 固定随机顺序可复现；
8. HTTP 200 + empty content 分类；
9. no choices 分类；
10. missing usage 不误判为空响应；
11. runtime failure 不执行 repair；
    12.结构错误最多一次 repair；
12. NO_OUTPUT 不计入 UNUSABLE；
13. schema-valid 分母只含成功响应；
14. end-to-end valid response rate；
15. mixed outcome 检测；
16. secret redaction；
17. summary 与 trial 明细一致。

---

## 14. 正式执行顺序

```text
Preflight
→ baseline pytest
→ 实现脚本与单元测试
→ 聚焦测试
→ 全量 pytest
→ validate
→ 冻结 follow-up fixtures
→ run-stability
→ verify stability
→ run-paired
→ verify paired
→ summarize
→ 独立 reviewer
→ 填写 follow-up REPORT
→ 定向修正父 REPORT
→ 最终测试与 diff 检查
```

不得在正式运行期间修改 Prompt、Schema、fixture、模型或参数。

---

## 15. 输出目录

每次 run：

```text
local_samples/spike_outputs/page-translation-full-context/<run_id>/
├── metadata.json
├── stability-results.json
├── paired-results.json
├── summary.json
├── trials.csv
├── pair-comparisons.csv
├── ratings.csv
├── raw_responses/
└── logs/
```

原始响应和汇总结果分离。

不得覆盖父 Spike 输出。

---

## 16. 汇总要求

### Stability

按 request hash 汇总：

```text
trial count
success rate
empty response rate
mixed outcome
latency
token usage
```

### N/P

分别统计：

```text
N/P response success rate
N/P empty response rate
N/P end-to-end valid rate
N/P median latency
N/P token usage
```

### Structure

只对成功响应统计：

```text
first-pass schema-valid
final schema-valid
mapping coverage
repair recovery
```

### Quality

只对可评价结果统计：

```text
context improvement
no meaningful effect
context regression
context pollution
unsupported disambiguation
```

---

## 17. 条件性 Token 诊断

仅在满足 HARNESS 条件时执行。

对单个已复现空响应的 payload：

```text
max_output_tokens = 2400
其余配置保持不变
```

结果写入：

```text
token-diagnostic-results.json
```

不得混入主实验统计，也不得顺便修改 timeout 或 Prompt。

---

## 18. REPORT

填写：

```text
docs/spikes/page-translation/followups/full-context-stability/REPORT.md
```

必须分别给出：

```text
Empty Response Attribution
MVP Previous Context Policy
Overall Verdict
```

同时列明：

* 事实；
* reviewer 判断；
  -统计限制；
  -未完成项；
  -需要用户确认的语义边界。

---

## 19. 父报告修正

Follow-up 完成后，定向更新父 REPORT。

不得删除原始 `NO_GO` 运行证据，但应明确：

* 两个空响应发生在无 previous context 差异的请求；
* 原运行不能证明 context 导致失败；
* 9 个 block 属 `NO_OUTPUT`；
* 非空响应 schema-valid 应单独计算；
* follow-up 提供新的最终归因。

父报告 verdict 是否改为 `FURTHER_SPIKE` 或其他结论，由 follow-up 证据决定。

---

## 20. 停止条件

立即停止：

* API 密钥泄漏；
* baseline 测试失败；
* 需要修改 `src/**`；
* 需要新增依赖；
* N/P 除 previous context 外存在差异；
* fixture 在正式 run 中变化；
  -调用顺序或 trial 数无法追踪；
  -需要自动 transport retry；
  -需要第二次 repair；
* reference 进入模型请求；
  -无法区分 runtime、structure 和 quality。

---

## 21. 完成条件

Follow-up 完成时必须具备：

* 至少 15 次 same-request stability trial；
* 至少 4 个有效 N/P fixture；
* 每个 N/P 条件至少 3 次 trial；
  -完整 runtime 响应证据；
  -可复核的 pair hash；
  -独立结构指标；
  -独立质量评级；
  -empty response 归因；
  -MVP previous context 策略；
  -符合 HARNESS 的最终 verdict；
  -父 REPORT 的定向修正。
