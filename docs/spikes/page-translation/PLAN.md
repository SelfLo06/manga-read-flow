# Page Translation JSON Spike — PLAN

## 1. 执行目标

按照 `GOAL.md` 与 `HARNESS.md`，完成一次真实文本 LLM API 的 Page 级翻译实验，验证：

```text
API smoke
→ 冻结 Prompt / Schema / fixtures
→ Block-level baseline
→ Page-level
→ Page-level + glossary
→ Full text context
→ 必要时一次 repair retry
→ 人工评级
→ REPORT
```

本计划只验证方案，不接入正式 Workflow。

---

## 2. 允许文件范围

允许创建或修改：

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

local_samples/page_translation/**
local_samples/spike_outputs/page-translation/**
```

禁止修改：

```text
src/manga_read_flow/**
docs/spikes/detection-ocr/**
数据库与正式 artifact
依赖文件与锁文件
本地 API 配置文件
```

---

## 3. CLI 设计

实验脚本建议提供：

```text
api-smoke
validate
run
verify
summarize
```

### `api-smoke`

执行最小文本请求，验证：

* 环境变量存在；
* endpoint、API key、模型可用；
* 返回非空结果；
* 最小 JSON 请求可完成；
* 不打印密钥或认证头。

Smoke 失败时停止，不进入正式实验。

### `validate`

验证：

* Prompt 文件存在且可读取；
* Schema 合法；
* manifest 与 fixtures 一致；
* `page_id`、`text_block_id`、`reading_order` 唯一；
* glossary 与 previous context 格式正确；
* reference translation 不在模型输入中；
* API 配置存在但不输出密钥。

### `run`

执行指定实验组，保存：

* 实际请求；
* 原始响应；
* JSON 解析结果；
* Schema 与 block mapping 校验；
* uncertainty flag 校验；
* latency、token usage；
* API 错误；
* retry 历史。

### `verify`

验证：

* Prompt、Schema、fixture hash 前后一致；
* 每个请求有响应或明确错误；
* retry 不超过一次；
* 汇总与明细一致；
* 输出不包含密钥。

### `summarize`

汇总结构、质量、上下文、术语和性能指标，生成 REPORT 所需数据。

---

## 4. Fixture 设计

准备 6–8 个冻结 Page fixture，至少覆盖：

```text
basic-dialogue
multi-block
context-dependent
terminology
previous-page
ocr-noise
sound-effects
long-page
```

建议目录：

```text
local_samples/page_translation/
├── manifest.json
├── schema.json
├── fixtures/
├── references/
└── ratings/
```

约束：

* `references/` 只用于人工评级；
* reference translation 不进入请求；
* previous context 只能包含前页 accepted / locked 翻译；
* 最大上下文为前 1 页、20 个 TextBlock；
* fixtures 冻结后不得在同一 run 中修改。

---

## 5. 请求组装

正常翻译请求由两部分组成：

### System message

读取：

```text
prompts/page-translation/system-v1.md
```

### User payload

根据实验组动态构造：

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
      "source_text": "..."
    }
  ],
  "glossary": [],
  "previous_context": []
}
```

API 支持原生 structured output 时，优先通过 API 参数传递 `schema.json`；本地仍必须执行二次校验。

---

## 6. 实验顺序

### Step 1：Preflight

记录：

```text
branch
HEAD
git status
baseline pytest
provider
model
generation config
Prompt hashes
Schema hash
fixture hashes
```

tracked 工作树存在无关修改时停止。

### Step 2：API Smoke

执行：

```text
api-smoke
```

只验证 API 可用性，不计入正式指标。

### Step 3：冻结输入

确认 Prompt、Schema、manifest 和 fixtures 完成。

从此刻起，同一正式 run 内不得修改。

### Step 4：实验组 A

Block-level Baseline：

```text
System Prompt + 单个 TextBlock
```

每个 block 独立请求。

### Step 5：实验组 B

Page-level：

```text
System Prompt
+ 当前页全部 blocks
+ reading_order / grouping
```

### Step 6：实验组 C

Page-level + Glossary：

```text
实验组 B
+ 相关 glossary
```

### Step 7：实验组 D

Full Text Context：

```text
实验组 C
+ 有界 previous accepted translations
```

所有实验组使用同一模型和参数。

### Step 8：Repair Retry

仅对以下错误执行一次：

```text
invalid_json
schema_invalid
wrong_page_id
missing_block
duplicate_block
unknown_block
invalid_uncertainty_flag
```

Repair 使用：

```text
prompts/page-translation/repair-system-v1.md
```

不得对拒绝、普通质量问题或合理歧义执行 repair。

### Step 9：人工评级

对有效输出逐 block 记录：

```text
ACCEPTABLE
REVIEW
UNUSABLE
```

同时记录：

```text
appropriate_uncertainty
unsupported_disambiguation
missed_material_ambiguity
over_flagging
context_pollution
```

评级不得反向修改模型输出。

### Step 10：汇总

比较：

* Block-level 与 Page-level；
* 无 glossary 与有 glossary；
* 无 previous context 与有 previous context；
* first-pass 与 repair 后结构；
* latency 与 token 增量。

---

## 7. 单元测试

单元测试不得调用真实 API。

至少覆盖：

1. Prompt 加载与 hash；
2. fixture / manifest 校验；
3. 重复 page 或 block ID；
4. reading order 冲突；
5. 合法 JSON；
6. Markdown 包裹；
7. invalid JSON；
8. wrong page ID；
9. missing / duplicate / unknown block；
10. 非法 uncertainty flag；
11. empty translation；
12. previous context 上限；
13. reference leakage 检测；
14. retry 只允许一次；
15. API key 日志脱敏；
16. summary 统计一致。

使用 fake client 或预置响应测试解析和评估逻辑。

---

## 8. 输出结构

每次正式运行写入：

```text
local_samples/spike_outputs/page-translation/<run_id>/
├── results.json
├── summary.json
├── requests.csv
├── translations.csv
├── ratings.csv
├── raw_responses/
└── logs/
```

`results.json` 至少包含：

```text
run metadata
provider / model
generation config
Prompt hashes
Schema hash
fixture hashes
experiment group
request result
retry history
block mapping
uncertainty flags
latency
token usage
failure tags
```

---

## 9. 验证命令

至少执行：

```bash
pytest tests/unit/test_page_translation_spike.py -q
pytest -q

python tools/spikes/page_translation/spike.py api-smoke
python tools/spikes/page_translation/spike.py validate
python tools/spikes/page_translation/spike.py run
python tools/spikes/page_translation/spike.py verify \
  --run-dir local_samples/spike_outputs/page-translation/<run_id>
python tools/spikes/page_translation/spike.py summarize \
  --run-dir local_samples/spike_outputs/page-translation/<run_id>

python -m json.tool \
  local_samples/spike_outputs/page-translation/<run_id>/results.json \
  > /dev/null

git diff --check
git status --short --untracked-files=all
```

CLI 参数允许根据实际实现小幅调整。

---

## 10. 停止条件

立即停止：

* API key 泄漏；
* API smoke 失败；
* baseline 测试失败；
* Prompt、Schema 或 fixture 在 run 中变化；
* 需要修改 `src/**`；
* 需要第二次 retry；
* 中途更换模型或参数；
* reference translation 进入请求；
* 针对单个 fixture 硬编码；
* 无法区分结构错误与翻译质量错误。

---

## 11. 完成条件

本 Spike 完成时必须具备：

* API smoke 结果；
* 冻结 Prompt、Schema 和 fixtures；
* 四组可比较实验；
* 完整原始响应；
* Schema 和 block mapping 指标；
* glossary 与 previous context 效果；
* uncertainty 评估；
* 一次 repair retry 数据；
* 人工质量评级；
* latency 与 token 数据；
* 明确的最终 verdict。
