# Page Translation JSON Spike — REPORT

## 1. Executive Summary

* Run ID：
* Git HEAD：
* Provider：
* Model：
* Prompt version：
* Final verdict：
* 是否允许进入正式 TranslationProvider 设计：
* 主要限制：

---

## 2. API Smoke Test

| 检查项          | 结果 |
| ------------ | -- |
| 环境变量完整       |    |
| Endpoint 可连接 |    |
| API key 有效   |    |
| Model 可调用    |    |
| 返回非空响应       |    |
| 最小 JSON 请求成功 |    |
| 未发现密钥泄漏      |    |

Smoke Test 结论：

```text
PASS / FAIL
```

失败或偏差说明：

---

## 3. Frozen Configuration

| 配置                      | 值 |
| ----------------------- | - |
| Provider                |   |
| Model                   |   |
| Temperature             |   |
| Max output tokens       |   |
| Timeout                 |   |
| Retry limit             | 1 |
| Prompt template version |   |
| Repair prompt version   |   |
| System prompt SHA-256   |   |
| Repair prompt SHA-256   |   |
| Schema SHA-256          |   |
| Fixture set SHA-256     |   |

运行期间是否发生输入变化：

```text
NO / YES
```

---

## 4. Fixtures

| Fixture | 场景 | Block 数 | Glossary | Previous context |
| ------- | -- | ------: | -------- | ---------------- |
|         |    |         |          |                  |

汇总：

* Page 数：
* TextBlock 数：
* Glossary term 数：
* 包含前序上下文的 Page 数：
* 包含实质性歧义的 Block 数：
* 包含 OCR 噪声的 Block 数：

Reference translation 是否与模型输入隔离：

```text
YES / NO
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
YES / NO
```

偏差：

---

## 6. Structural Results

| 指标                           |  A |  B |  C |  D |
| ---------------------------- | -: | -: | -: | -: |
| Request count                |    |    |    |    |
| API success                  |    |    |    |    |
| First-pass JSON parse rate   |    |    |    |    |
| First-pass schema-valid rate |    |    |    |    |
| Final schema-valid rate      |    |    |    |    |
| Block coverage               |    |    |    |    |
| Missing blocks               |    |    |    |    |
| Duplicate blocks             |    |    |    |    |
| Unknown blocks               |    |    |    |    |
| Wrong page ID                |    |    |    |    |
| Invalid uncertainty flags    |    |    |    |    |
| Empty translations           |    |    |    |    |

主要结构失败：

---

## 7. Repair Retry

| 指标                   | 结果 |
| -------------------- | -: |
| Retry attempted      |    |
| Retry recovered      |    |
| Retry failed         |    |
| Illegal second retry |  0 |

成功修复的问题：

未修复的问题：

Repair 是否误改了原本合法译文：

```text
NO / YES
```

---

## 8. Translation Quality

| Group | ACCEPTABLE | REVIEW | UNUSABLE |
| ----- | ---------: | -----: | -------: |
| A     |            |        |          |
| B     |            |        |          |
| C     |            |        |          |
| D     |            |        |          |

主要质量问题：

* meaning error：
* translation omission：
* hallucination：
* terminology inconsistency：
* tone / honorific error：
* OCR noise impact：

代表性样本：

| Fixture / Block | Group | Source | Translation | Rating | Issue |
| --------------- | ----- | ------ | ----------- | ------ | ----- |
|                 |       |        |             |        |       |

---

## 9. Page-Level Context Effect

比较 Group A 与 Group B。

| 指标                         | Block-level | Page-level | Delta |
| -------------------------- | ----------: | ---------: | ----: |
| ACCEPTABLE                 |             |            |       |
| REVIEW                     |             |            |       |
| UNUSABLE                   |             |            |       |
| Meaning errors             |             |            |       |
| Unsupported disambiguation |             |            |       |
| Median latency             |             |            |       |
| Input tokens               |             |            |       |

Page-level 明确改善的样本：

Page-level 明显退化的样本：

结论：

```text
BENEFICIAL / NEUTRAL / HARMFUL / INCONCLUSIVE
```

---

## 10. Glossary Effect

比较 Group B 与 Group C。

| 指标                      | Without glossary | With glossary |
| ----------------------- | ---------------: | ------------: |
| Expected terms          |                  |               |
| Correct terms           |                  |               |
| Term hit rate           |                  |               |
| Wrong term applications |                  |               |
| Translation regressions |                  |               |
| Token increase          |                  |               |

结论：

```text
USE_AS_HINT / REQUIRED / OPTIONAL / NOT_WORTH_MVP
```

---

## 11. Previous Context Effect

比较 Group C 与 Group D。

| 指标                   | Without previous context | With previous context |
| -------------------- | -----------------------: | --------------------: |
| Context improvements |                          |                       |
| No effect            |                          |                       |
| Regressions          |                          |                       |
| Context pollution    |                          |                       |
| Token increase       |                          |                       |
| Latency increase     |                          |                       |

改善的内容：

* 称谓一致：
* 专有名词一致：
* 连续对白：
* 指代处理：

发现的污染：

建议上下文窗口：

```text
NO_CONTEXT
PREVIOUS_1_PAGE
PREVIOUS_N_BLOCKS
OTHER
```

---

## 12. Uncertainty Evaluation

| 指标                         | 数量 |
| -------------------------- | -: |
| Flagged blocks             |    |
| Appropriate uncertainty    |    |
| Unsupported disambiguation |    |
| Missed material ambiguity  |    |
| Over-flagging              |    |
| Invalid flags              |    |

各标记使用次数：

| Flag                         | Count |
| ---------------------------- | ----: |
| context_ambiguous            |       |
| pronoun_resolution_uncertain |       |
| speaker_context_uncertain    |       |
| addressee_context_uncertain  |       |
| ocr_uncertain                |       |

结论：

* 是否能避免无依据补充姓名、性别或人物关系：
* 是否漏掉实质性歧义：
* 是否存在系统性过度标记：
* 是否适合作为 QualityCheckService 输入：

---

## 13. API and Performance

| Group | Median latency | Max latency | Input tokens | Output tokens | Estimated cost |
| ----- | -------------: | ----------: | -----------: | ------------: | -------------: |
| A     |                |             |              |               |                |
| B     |                |             |              |               |                |
| C     |                |             |              |               |                |
| D     |                |             |              |               |                |

错误统计：

| Failure          | Count |
| ---------------- | ----: |
| api_timeout      |       |
| api_error        |       |
| provider_refusal |       |
| empty_response   |       |

单 Page MVP 性能结论：

---

## 14. Failure Taxonomy

| Failure type               | Count | Retryable | Recommended handling |
| -------------------------- | ----: | --------- | -------------------- |
| invalid_json               |       |           |                      |
| schema_invalid             |       |           |                      |
| missing_block              |       |           |                      |
| duplicate_block            |       |           |                      |
| unknown_block              |       |           |                      |
| invalid_uncertainty_flag   |       |           |                      |
| translation_omission       |       |           |                      |
| translation_hallucination  |       |           |                      |
| terminology_inconsistent   |       |           |                      |
| unsupported_disambiguation |       |           |                      |
| missed_material_ambiguity  |       |           |                      |
| context_pollution          |       |           |                      |

---

## 15. MVP Handling Recommendations

建议主链路：

```text
构造 PageTranslationContext
→ 调用 TranslationProvider
→ 本地 Schema 与映射校验
→ 结构失败时一次 repair retry
→ QualityCheckService 检查译文和 uncertainty flags
→ WorkflowLoopEngine 决定 continue / warning / block / manual
```

建议约束：

* Prompt 使用版本化仓库文件；
* Page 级调用为默认方案；
* glossary：
* previous context：
* uncertainty flags：
* repair retry：
* refusal / timeout：
* raw request / response retention：

不得采用：

* 无限 retry；
* 静默接受 partial output；
* 人工补造缺失 block；
* Provider 自行决定 workflow 状态；
* 把参考译文传给模型；
* 自动消除无法确认的说话人或指代歧义。

---

## 16. Decision Against Harness

| 门槛                      |           要求 | 实际 | 结果 |
| ----------------------- | -----------: | -: | -- |
| API smoke               |         PASS |    |    |
| First-pass schema-valid |        ≥ 90% |    |    |
| Final schema-valid      |         100% |    |    |
| Block coverage          |        ≥ 98% |    |    |
| Unknown blocks          |            0 |    |    |
| Duplicate blocks        |            0 |    |    |
| ACCEPTABLE + REVIEW     |        ≥ 90% |    |    |
| Context pollution       |       无系统性问题 |    |    |
| Page-level effect       |    有收益或无明显退化 |    |    |
| Performance             | 适合单 Page MVP |    |    |

---

## 17. Final Verdict

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

### 判定理由

### 允许进入正式设计的条件

* TranslationProvider：
* PageTranslationContextBuilder：
* Prompt versioning：
* Glossary：
* Previous context：
* Schema validation：
* Repair retry：
* Uncertainty handling：
* Quality Gate：
* Provenance / hash：

### 是否启动 Translation Context Necessity Spike

```text
NOT_NOW
RECOMMENDED_AFTER_REAL_PAGE_INTEGRATION
REQUIRED_BEFORE_PRODUCT_MVP
```

依据：

---

## 18. Recommended Next Step

只选择一项：

```text
进入正式 TranslationProvider 与 ContextBuilder 最小设计
执行针对性 Page Translation follow-up Spike
更换模型或调用配置后重做
停止当前方案
```
