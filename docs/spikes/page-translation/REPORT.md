# Page Translation JSON Spike — REPORT

## 1. Executive Summary

* Run ID：`20260710T164512Z-9024bb`
* Git HEAD：`b15001e`
* Provider：OpenAI-compatible chat completions endpoint
* Model：`deepseek-v4-pro`
* Prompt version：`system-v1`
* Final verdict：`NO_GO`
* 是否允许进入正式 TranslationProvider 设计：`NO`
* 主要限制：D 组 Full Text Context 出现 2 次 `empty_response`，导致 final schema-valid rate = 75%、block coverage = 65.38%，未达到 HARNESS 的 100% final schema-valid 和 >=98% coverage 门槛。

本轮结论是：Page-level 和 glossary 在可返回响应的请求中表现可用，但 Full Text Context 当前不稳定，不能进入正式 Provider / ContextBuilder 设计。

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

## 6. Structural Results

| 指标                           | A | B | C | D |
| ---------------------------- | -: | -: | -: | -: |
| Request count                | 26 | 8 | 8 | 8 |
| API success                  | 26 | 8 | 8 | 6 |
| First-pass JSON parse rate   | 100% | 100% | 100% | 100% |
| First-pass schema-valid rate | 96.15% | 87.50% | 100% | 75.00% |
| Final schema-valid rate      | 100% | 100% | 100% | 75.00% |
| Block coverage               | 100% | 100% | 100% | 65.38% |
| Missing blocks               | 0 | 0 | 0 | 0 |
| Duplicate blocks             | 0 | 0 | 0 | 0 |
| Unknown blocks               | 0 | 0 | 0 | 0 |
| Wrong page ID                | 0 | 0 | 0 | 0 |
| Invalid uncertainty flags    | 0 | 0 | 0 | 0 |
| Empty translations           | 0 | 0 | 0 | 0 |

主要结构失败：

* `D-context-dependent-01`：`empty_response`，未进入 repair。
* `D-long-page-01`：`empty_response`，未进入 repair。
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

| Group | ACCEPTABLE | REVIEW | UNUSABLE |
| ----- | ---------: | -----: | -------: |
| A     | 26 | 0 | 0 |
| B     | 26 | 0 | 0 |
| C     | 26 | 0 | 0 |
| D     | 17 | 0 | 9 |

主要质量问题：

* meaning error：未系统性发现，但 B 组 `先輩` 出现“学姐/学长”式无依据性别化。
* translation omission：D 组两个 empty response 导致 9 个 block 无有效译文。
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
| D / context-dependent | D | page | no effective response | UNUSABLE | empty_response |
| D / long-page | D | page | no effective response | UNUSABLE | empty_response |

---

## 9. Page-Level Context Effect

比较 Group A 与 Group B。

| 指标                         | Block-level | Page-level | Delta |
| -------------------------- | ----------: | ---------: | ----: |
| ACCEPTABLE                 | 26 | 26 | 0 |
| REVIEW                     | 0 | 0 | 0 |
| UNUSABLE                   | 0 | 0 | 0 |
| Meaning errors             | 未系统量化 | 未系统量化 | - |
| Unsupported disambiguation | 0 | 0 | 0 |
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

比较 Group C 与 Group D。

| 指标                   | Without previous context | With previous context |
| -------------------- | -----------------------: | --------------------: |
| Context improvements | 0 | 3 |
| No effect            | - | 0 |
| Regressions          | 0 | 9 unusable due empty response |
| Context pollution    | 0 | 0 |
| Token increase       | 14969 | 11242 |
| Latency increase     | median 7343ms | median 11492ms |

改善的内容：

* 称谓一致：`先輩` 更稳定为“前辈”。
* 专有名词一致：未见明显新增收益。
* 连续对白：`previous-page` 可用样本中语义自然。
* 指代处理：证据不足，因为 D 组 `context-dependent` 未返回。

发现的污染：

* 未发现把“旧天文台”等 previous context 文本复制到当前页。

建议上下文窗口：

```text
FURTHER_SPIKE_REQUIRED
```

当前不能推荐正式窗口，因为 D 组稳定性失败。

---

## 12. Uncertainty Evaluation

| 指标                         | 数量 |
| -------------------------- | -: |
| Flagged blocks             | 约 5 |
| Appropriate uncertainty    | 5 |
| Unsupported disambiguation | 0 |
| Missed material ambiguity  | 23 |
| Over-flagging              | 0 |
| Invalid flags              | 0 |

各标记使用次数：详见 `translations.csv`；抽样可见主要为 `ocr_uncertain`，歧义指代漏标更突出。

结论：

* 是否能避免无依据补充姓名、性别或人物关系：不稳定，B 组有“学长/学姐”式无依据性别化。
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
| unsupported_disambiguation | 0 counted, but gendered “学长/学姐” needs review | no | QualityCheckService risk |
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

## 16. Final Verdict

```text
NO_GO
```

理由：

* HARNESS 的 GO 要求 final schema-valid rate = 100%、block coverage >= 98%。
* 本轮 D 组 final schema-valid rate = 75%、block coverage = 65.38%。
* D 组发生 2 次 empty response，造成 9 个 TextBlock 无有效译文。
* Previous context 的质量收益无法抵消稳定性失败。

是否进入正式 TranslationProvider / ContextBuilder 设计：

```text
NO
```

建议下一步：

* 先做 Further Spike，专门验证 Full Text Context 的请求大小、timeout、max token、provider empty response 行为和是否需要更小 previous-context 窗口。
* 同时加强 uncertainty prompt 与评价标准，尤其是指代、省略、OCR 噪声漏标。

---

## 17. Limitations and Deviations

* Fixture 为小规模 synthetic text-only 样本，不能代表全部漫画。
* 没有发送图片，也没有验证视觉语境。
* 评级包含启发式自动评级和 Codex reviewer 抽样，不是真人人工评审。
* 未计算真实成本。
* 没有重跑 D 组失败请求；本报告保留首次正式 run 的失败证据。
* 未接入正式 Workflow、Provider、Repository 或数据库。
