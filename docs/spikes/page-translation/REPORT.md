# Page Translation JSON Spike — REPORT

## 1. Executive Summary

* Run ID：`20260710T164512Z-9024bb`
* Git HEAD：`b15001e`
* Provider：OpenAI-compatible chat completions endpoint
* Model：`deepseek-v4-pro`
* Prompt version：`system-v1`
* Original run verdict：`NO_GO`
* Page Translation Core Verdict：`CONDITIONAL_GO`
* P0 Previous Context Policy：`DISABLE_FOR_MVP`
* 主要限制：父 run 的 D 组 Full Text Context 出现 2 次 `empty_response`，导致 end-to-end valid response rate 和 block coverage 不达标。后续 Full Text Context Stability Follow-up 未复现这两个 payload 的空响应；其唯一新空响应有明确的 token-limit 证据。因此父 run 不能证明 previous context 导致失败，也不能据此否定 Page Translation 核心能力。

本轮结论是：Page-level 和 glossary 在可返回响应的请求中表现可用。Full Text Context 的父 run 证据不足以支持默认启用；follow-up 的 `FURTHER_SPIKE` 仅表示 previous-context 证据不足，不表示 Page Translation 核心能力不可用。P0 采用 Page-level + glossary，保留 previous-context 的数据与追溯接口但默认不发送非空历史上下文。

---

## 2. API Smoke Test

| 检查项          | 结果 |
| ------------ | -- |
| 环境变量完整       | PASS |
| Endpoint 可连接 | PASS |
| API key 有效   | PASS |
| Model 可调用    | PASS |
| 返回非空响应       | PASS |
| 最小 JSON 请求成功 | PASS |
| 未发现密钥泄漏      | PASS |

Smoke Test 结论：

```text
PASS
```

偏差说明：首次零代码 smoke 使用过弱临时提示时收到 HTTP 200 但未取到有效结构化内容；随后用更明确 JSON 约束通过。正式 `api-smoke` 改为使用版本化 `system-v1` prompt 后通过。

---

## 3. Frozen Configuration

| 配置                      | 值 |
| ----------------------- | - |
| Provider                | openai-compatible |
| Model                   | deepseek-v4-pro |
| Temperature             | 0 |
| Max output tokens       | 1200 |
| Timeout                 | 60s |
| Retry limit             | 1 |
| Prompt template version | system-v1 |
| Repair prompt version   | repair-system-v1 |
| System prompt SHA-256   | `aac64d9616e3cdb32eb074723580ee604a5106b33b7cefe46e8dc4e97179f77c` |
| Repair prompt SHA-256   | `84b1bf1f044d63a94787d2001124cb04bc71ac1ed6fff3d2b04da22bd203b757` |
| Schema SHA-256          | `c11be9d1cee7fe935ce6b85bd31c45dc4772b2027970d3631b66d80e8d53a9ac` |
| Fixture set SHA-256     | `b0082286b3ac58d48c561bcaa35e9cf968e29fb37765e9f4e602ea0df467f581` |

运行期间是否发生输入变化：

```text
NO
```

---

## 4. Fixtures

| Fixture | 场景 | Block 数 | Glossary | Previous context |
| ------- | -- | ------: | -------- | ---------------- |
| basic-dialogue | basic-dialogue | 2 | 0 | 0 |
| multi-block | multi-block | 3 | 0 | 0 |
| context-dependent | context-dependent | 3 | 0 | 0 |
| terminology | terminology | 3 | 3 | 0 |
| previous-page | previous-page | 3 | 1 | 2 |
| ocr-noise | ocr-noise | 3 | 0 | 0 |
| sound-effects | sound-effects | 3 | 0 | 0 |
| long-page | long-page | 6 | 0 | 0 |

汇总：

* Page 数：8
* TextBlock 数：26
* Glossary term 数：4 fixture entries
* 包含前序上下文的 Page 数：1
* 包含实质性歧义的 Block 数：根据 reference 标注约 9 个
* 包含 OCR 噪声的 Block 数：3

Reference translation 是否与模型输入隔离：

```text
YES
```

---

## 5. Experiment Groups

| Group | 输入                                       |
| ----- | ---------------------------------------- |
| A     | Block-level baseline                     |
| B     | Page-level                               |
| C     | Page-level + glossary                    |
| D     | Page-level + glossary + previous context |

所有实验组是否使用相同模型与 generation 参数：

```text
YES
```

偏差：无。D 组失败没有重跑，按原始证据保留。

---

## 6. Runtime and Structural Results

以下四个指标使用不同分母，不能合并为单一 `schema-valid` 指标：

| 指标 | 定义 |
| --- | --- |
| API response rate | 非空 API / Provider 响应数 ÷ 请求数 |
| Schema-valid rate among non-empty responses | 最终 schema-valid 响应数 ÷ 非空响应数 |
| End-to-end valid response rate | 最终 schema-valid 响应数 ÷ 请求数 |
| Block coverage among all expected blocks | 已匹配 TextBlock 数 ÷ 全部预期 TextBlock 数 |

| 指标 | A | B | C | D |
| --- | -: | -: | -: | -: |
| Request count | 26 | 8 | 8 | 8 |
| API response rate | 26/26 (100%) | 8/8 (100%) | 8/8 (100%) | 6/8 (75%) |
| First-pass schema-valid among non-empty responses | 25/26 (96.15%) | 7/8 (87.50%) | 8/8 (100%) | 6/6 (100%) |
| Final schema-valid among non-empty responses | 26/26 (100%) | 8/8 (100%) | 8/8 (100%) | 6/6 (100%) |
| End-to-end valid response rate | 26/26 (100%) | 8/8 (100%) | 8/8 (100%) | 6/8 (75%) |
| Block coverage among all expected blocks | 26/26 (100%) | 26/26 (100%) | 26/26 (100%) | 17/26 (65.38%) |
| Missing / duplicate / unknown blocks in non-empty responses | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Wrong page ID / invalid uncertainty flags / empty translations | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

主要结构失败：

* `D-context-dependent-01`：`empty_response`，`NO_OUTPUT / NOT_EVALUABLE`，未进入 repair。
* `D-long-page-01`：`empty_response`，`NO_OUTPUT / NOT_EVALUABLE`，未进入 repair。
* `A-long-page-05`：first pass Markdown-wrapped JSON，一次 repair 成功。
* `B-terminology-01`：first pass Markdown-wrapped JSON，一次 repair 成功。

---

## 7. Repair Retry

| 指标                   | 结果 |
| -------------------- | -: |
| Retry attempted      | 2 |
| Retry recovered      | 2 |
| Retry failed         | 0 |
| Illegal second retry | 0 |

成功修复的问题：

* `markdown_wrapped_json` in `A-long-page-05`
* `markdown_wrapped_json` in `B-terminology-01`

未修复的问题：

* D 组两个 `empty_response` 属 API/runtime 失败，不执行 repair。

Repair 是否误改了原本合法译文：

```text
未发现；本轮只记录结构修复证据，未以 repair 做质量润色。
```

---

## 8. Translation Quality

以下评级为本地启发式预评级加独立 Codex reviewer 抽样判断，不是真人人工评审。

| Group | ACCEPTABLE | REVIEW | UNUSABLE | NO_OUTPUT / NOT_EVALUABLE |
| ----- | ---------: | -----: | -------: | ------------------------: |
| A     | 26 | 0 | 0 | 0 |
| B     | 26 | 0 | 0 | 0 |
| C     | 26 | 0 | 0 | 0 |
| D     | 17 | 0 | 0 | 9 blocks / 2 requests |

补充：D 组 9 个 block 属于 `NO_OUTPUT / NOT_EVALUABLE`，不是 `UNUSABLE` 翻译质量失败。父 run 初版统计把 runtime failure 混入质量失败，follow-up 已对此作出修正。

主要质量问题：

* meaning error：未系统性发现，但 B 组 `先輩` 出现“学姐/学长”式无依据性别化。
* translation omission：D 组两个 empty response 导致 9 个 block 无模型输出；这是 runtime/provider 层 `NO_OUTPUT`，不应计为译文质量 `UNUSABLE`。
* hallucination：未见前页内容直接复制到当前页。
* terminology inconsistency：B 组未用 glossary，`蒼星祭`、`星見部`、`先輩` 不一致；C/D 改善明显。
* tone / honorific error：`先輩` 建议统一为“前辈”，避免无视觉依据性别化。
* OCR noise impact：B 组对 OCR 噪声有合理 `ocr_uncertain`，C/D 漏标较多。

代表性样本：

| Fixture / Block | Group | Source | Translation | Rating | Issue |
| --------------- | ----- | ------ | ----------- | ------ | ----- |
| terminology / tm-b001 | B | 蒼星祭の準備、進んでる？ | 蒼星祭的准备工作，进展如何？ | ACCEPTABLE | 未按 glossary 使用“苍星祭” |
| terminology / tm-b003 | B | 星見部の出し物も決めなきゃ。 | 星见部的展示内容也得定下来。 | ACCEPTABLE | 未按 glossary 使用“观星部” |
| previous-page / pp-b002 | B | わかった。先輩には内緒だからね。 | 知道了。要对学长保密哦。 | ACCEPTABLE | 无依据性别化 |
| context-dependent / cd-b002 | B | うん、でも今日こそ渡す。 | 嗯，不过我今天一定要给他。 | ACCEPTABLE | 指代对象未标不确定 |
| D / context-dependent | D | page | no model output | NO_OUTPUT / NOT_EVALUABLE | empty_response |
| D / long-page | D | page | no model output | NO_OUTPUT / NOT_EVALUABLE | empty_response |

---

## 9. Page-Level Context Effect

比较 Group A 与 Group B。

| 指标                         | Block-level | Page-level | Delta |
| -------------------------- | ----------: | ---------: | ----: |
| ACCEPTABLE                 | 26 | 26 | 0 |
| REVIEW                     | 0 | 0 | 0 |
| UNUSABLE                   | 0 | 0 | 0 |
| Meaning errors             | 未系统量化 | 未系统量化 | - |
| Unsupported disambiguation | 0 | 3 个明确样本 | +3 |
| Median latency             | 3949ms | 7101ms | +3152ms |
| Input tokens               | 46618 | 16263 | -30355 |

Page-level 明确改善的样本：

* 从请求数量和 token 总量看，Page-level 比逐块请求更经济。
* 翻译质量未明显劣化。

Page-level 明显退化的样本：

* B 组 first-pass schema-valid rate = 87.5%，低于 A 组 96.15%，需要依赖一次 repair 达到 100%。
* B 组中位 latency 高于单个 block 请求，但总请求数更少。

结论：

```text
BENEFICIAL_WITH_STRUCTURAL_REPAIR_RISK
```

---

## 10. Glossary Effect

比较 Group B 与 Group C。

| 指标                      | Without glossary | With glossary |
| ----------------------- | ---------------: | ------------: |
| Expected terms          | 3 | 3 |
| Correct terms           | 0-1 抽样判断 | 3 |
| Term hit rate           | 未严格量化 | 100% |
| Wrong term applications | 0 | 0 |
| Translation regressions | 未发现 | 未发现 |
| Token increase          | C total input tokens lower than B in this run due repair/token variance | - |

结论：

```text
USE_AS_HINT
```

独立 Codex reviewer 判断：C/D 明显改善 `苍星祭 / 观星部 / 前辈`，未见明显错误套用。

---

## 11. Previous Context Effect

比较 Group C 与 Group D。只有 `previous-page` fixture 真正包含非空 previous context；`context-dependent` 和 `long-page` 的 C/D request hash 相同，因此这两个页面的 D 组失败不能归因于 previous context。

| 指标 | 父 run 可支持的结论 |
| ---- | ------------------ |
| 真正带非空 previous context 的 fixture | `previous-page` 1 个，共 3 个 block |
| Context improvements | 未证实明确、可归因的改善 |
| No meaningful effect | `previous-page` 的 3 个已评估 block |
| Runtime no output | 2 个请求、9 个 block；不归因于 previous context |
| Context pollution | 0 个已观察样本 |
| Token / latency 对比 | 父 run 受两次无输出和仅一个有效上下文 fixture 限制，不用于推断 context 效应 |

父 run 的唯一有效 C/D 上下文比较是 `previous-page`。其 3 个 block 在 C/D 中均可用，只有“按约定 / 照约定”的同义措辞差异；没有足够证据将其认定为 previous context 带来的改善。称谓“前辈”在 C/D 中都可用，不能作为历史上下文的独立收益。

指代处理仍证据不足：`context-dependent` 的 C/D request hash 相同，且 D 请求未返回，不能据此判断 previous context 的收益或回归。

发现的污染：

* 未发现把“旧天文台”等 previous context 文本复制到当前页。

建议上下文窗口：

```text
FURTHER_SPIKE_REQUIRED
```

当前不能推荐正式窗口。Follow-up 显示父 run 两个空响应 payload 在 5 次重复中均未复现，且唯一新空响应发生在 N 组并有明确 `TOKEN_LIMIT_ASSOCIATED` 证据；P 组 18/18 成功，未发现 previous context 降低稳定性。父 run 因而不能归因于 previous context；但 previous context 的可重复质量收益仍不足。

---

## 12. Uncertainty Evaluation

| 指标                         | 数量 |
| -------------------------- | -: |
| Flagged blocks             | 约 5 |
| Appropriate uncertainty    | 5 |
| Unsupported disambiguation | 3 个明确样本 |
| Missed material ambiguity  | 23 |
| Over-flagging              | 0 |
| Invalid flags              | 0 |

各标记使用次数：详见 `translations.csv`；抽样可见主要为 `ocr_uncertain`，歧义指代漏标更突出。

结论：

* 是否能避免无依据补充姓名、性别或人物关系：不稳定。明确样本包括 `先輩 → 学姐`、`先輩 → 学长`，以及 `渡す → 给他`；在缺少足够原文或可信上下文依据时，均归入 `unsupported_disambiguation`。
* 是否漏掉实质性歧义：是，`context-dependent` 与 `ocr-noise` 漏标明显。
* 是否存在系统性过度标记：未发现。
* 是否适合作为 QualityCheckService 输入：暂不适合直接使用，需要后续 quality gate 解释层和更可靠 prompt/评估。

---

## 13. API and Performance

| Group | Median latency | Max latency | Input tokens | Output tokens | Estimated cost |
| ----- | -------------: | ----------: | -----------: | ------------: | -------------: |
| A     | 3949ms | 8819ms | 46618 | 5715 | 未计算 |
| B     | 7101ms | 14271ms | 16263 | 3401 | 未计算 |
| C     | 7343ms | 16658ms | 14969 | 4688 | 未计算 |
| D     | 11492ms | 23502ms | 11242 | 3357 | 未计算 |

错误统计：

| Failure          | Count |
| ---------------- | ----: |
| api_timeout      | 0 |
| api_error        | 0 |
| provider_refusal | 0 |
| empty_response   | 2 |

单 Page MVP 性能结论：

* A/B/C 性能可进一步评估；D 组 max latency 23.5s 且有 empty response，当前不适合 MVP 默认路径。

---

## 14. Failure Taxonomy

| Failure type               | Count | Retryable | Recommended handling |
| -------------------------- | ----: | --------- | -------------------- |
| invalid_json               | 0 | yes | one repair |
| markdown_wrapped_json      | 2 | yes | one repair, prompt tighten |
| schema_invalid             | 0 after repair | yes | one repair |
| missing_block              | 0 | yes | one repair |
| duplicate_block            | 0 | yes | one repair |
| unknown_block              | 0 | yes | one repair |
| invalid_uncertainty_flag   | 0 | yes | one repair |
| empty_response             | 2 | no | provider/runtime failure handling, no repair |
| translation_omission       | 9 effective missing blocks from D empty responses | no | retry policy belongs outside provider adapter |
| terminology_inconsistent   | B terminology sample | no | glossary hint helps |
| unsupported_disambiguation | 3 个明确样本：`先輩 → 学姐`、`先輩 → 学长`、`渡す → 给他` | no | QualityCheckService 风险；不把其他 reviewer 边界判断机械计为错误 |
| missed_material_ambiguity  | 23 heuristic count | no | prompt/quality gate improvement |
| context_pollution          | 0 | no | continue monitoring |

---

## 15. Independent Reviewer Notes

Evaluator：独立 Codex reviewer `Einstein`，只读抽样检查 `translations.csv`、fixture、reference、summary/requests；未修改文件，未读取 `.env`。

Reviewer 判断：

* B 组术语明显弱于 C/D：`蒼星祭`、`星見部` 未按术语表；`先輩` 被性别化为“学姐/学长”。
* C/D 术语改善明显，未见明显错误套用。
* C/D 未发现把 previous context 的“旧天文台”等历史内容复制进当前页。
* Uncertainty 漏标明显：`context-dependent`、`ocr-noise`、可能的 `previous-page/pp-b003`。
* D 组 `context-dependent` 和 `long-page` 无译文，无法做质量审查。

需要用户确认的边界样本：

* `context-dependent`：`渡す` 的对象/收件人是否允许译成“他”。
* `terminology`：`ユイ` 的统一译名，以及“帮我/帮我们”的口吻。
* `previous-page`：`先輩` 是否始终译“前辈”，不做“学长/学姐”。
* `ocr-noise`：`文宇`、`読めなぃ` 这类 OCR 噪声是否必须保留 `ocr_uncertain`。

---

## 16. Final Decisions

### Original Run Verdict

```text
NO_GO
```

这是父 run 的历史 verdict：D 组端到端有效率为 6/8、全量 block coverage 为 17/26，未达到当时 Full Text Context 的门槛。原始 run 数据和失败证据保持不变。

### Page Translation Core Verdict

```text
CONDITIONAL_GO
```

理由：

* Page-level structured translation 可用，TextBlock mapping 可严格校验。
* glossary 有实际收益。
* 一次 structural repair 可恢复 markdown-wrapped JSON。
* 成功响应可达到 100% final schema-valid 和 mapping coverage。
* follow-up 中 previous context 未显示稳定性伤害。
* uncertainty flags 仍不可靠，且 output token limit / incomplete output 必须显式处理。

### P0 Previous Context Policy

```text
DISABLE_FOR_MVP
```

P0 默认输入固定为：

```text
versioned System Prompt
+ current Page TextBlocks
+ reading_order / grouping
+ relevant Project glossary
+ previous_context = []
```

保留 `previous_context` 字段、hash 和 provenance seam，但不默认发送非空历史上下文；这不是永久删除该能力。

### Provider / Workflow Follow-up

* output token limit 必须可配置；`finish_reason = length` 归为 incomplete output。
* Provider Adapter 只返回结构化结果和错误证据，不决定 retry。
* WorkflowLoopEngine 根据 `ProcessingProfileSnapshot` 决定是否提高 token budget 后重试，且 retry 必须有界。
* uncertainty flags 只能作为弱质量证据，不能单独决定 block。

---

## 17. Limitations and Deviations

* Fixture 为小规模 synthetic text-only 样本，不能代表全部漫画。
* 没有发送图片，也没有验证视觉语境。
* 评级包含启发式自动评级和 Codex reviewer 抽样，不是真人人工评审。
* 未计算真实成本。
* 没有重跑 D 组失败请求；本报告保留首次正式 run 的失败证据。
* 未接入正式 Workflow、Provider、Repository 或数据库。
