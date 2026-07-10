# Full Text Context Stability Follow-up — REPORT

## 1. Executive Summary

- Run ID：
- Git HEAD：
- Provider：
- Model：
- Stability trials：
- Paired fixtures：
- Empty Response Attribution：
- MVP Previous Context Policy：
- Overall Verdict：

核心结论：

---

## 2. Frozen Configuration

| Item | Value |
|---|---|
| Provider | |
| Model | |
| Temperature | |
| Max output tokens | |
| Timeout | |
| System prompt SHA-256 | |
| Repair prompt SHA-256 | |
| Schema SHA-256 | |
| Fixture set SHA-256 | |
| Random seed | |

运行期间输入是否变化：

```text
NO / YES
````

---

## 3. Same-request Stability

| Fixture                    | Trials | Success | Empty content | No choices | Timeout | Mixed outcome |
| -------------------------- | -----: | ------: | ------------: | ---------: | ------: | ------------- |
| context-dependent          |        |         |               |            |         |               |
| long-page                  |        |         |               |            |         |               |
| previous-page-with-context |        |         |               |            |         |               |

证据：

* 相同 request hash 是否同时出现成功和空响应：
* 空响应是否可重复：
* 空响应是否集中于特定输入：
* Provider response metadata 是否显示异常：

结论：

```text
PROVIDER_RANDOM
CONTEXT_ASSOCIATED
NOT_REPRODUCED
INCONCLUSIVE
```

---

## 4. Paired Fixture Validation

| Fixture | N/P pair valid | Current page hash equal | Glossary hash equal | Previous context differs |
| ------- | -------------- | ----------------------- | ------------------- | ------------------------ |
|         |                |                         |                     |                          |

有效 paired fixture 数：

无效 pair 及原因：

---

## 5. Runtime Results

| Group | Calls | Success | Empty response | Timeout | HTTP error | End-to-end valid rate |
| ----- | ----: | ------: | -------------: | ------: | ---------: | --------------------: |
| N     |       |         |                |         |            |                       |
| P     |       |         |                |         |            |                       |

| Metric                |  N |  P |
| --------------------- | -: | -: |
| Response success rate |    |    |
| Empty response rate   |    |    |
| Median latency        |    |    |
| Max latency           |    |    |
| Input tokens          |    |    |
| Output tokens         |    |    |

Previous context 是否降低响应稳定性：

```text
YES / NO / INCONCLUSIVE
```

---

## 6. Structural Results

分母仅包含 `SUCCESS_RESPONSE`。

| Metric                  |  N |  P |
| ----------------------- | -: | -: |
| First-pass JSON valid   |    |    |
| First-pass schema valid |    |    |
| Final schema valid      |    |    |
| Block mapping coverage  |    |    |
| Missing blocks          |    |    |
| Duplicate blocks        |    |    |
| Unknown blocks          |    |    |
| Repair attempted        |    |    |
| Repair recovered        |    |    |
| Repair failed           |    |    |

是否满足：

```text
final schema-valid = 100%
block mapping coverage = 100%
unknown block = 0
duplicate block = 0
```

---

## 7. Previous Context Quality Effect

| Fixture | Focus | N result | P result | Context effect |
| ------- | ----- | -------- | -------- | -------------- |
|         |       |          |          |                |

允许的 context effect：

```text
CONTEXT_IMPROVEMENT
NO_MEANINGFUL_EFFECT
CONTEXT_REGRESSION
CONTEXT_POLLUTION
```

汇总：

| Effect               | Count |
| -------------------- | ----: |
| Context improvement  |       |
| No meaningful effect |       |
| Context regression   |       |
| Context pollution    |       |

主要改善：

* 称谓一致：
* 专有名词一致：
* 连续对白：
* 主宾语或指代：

主要副作用：

* 历史内容复制：
* 历史语境覆盖当前页：
* 无依据消歧：
* 错误指代：

---

## 8. Translation Quality

只统计形成完整译文的 block。

| Group | ACCEPTABLE | REVIEW | UNUSABLE | NO_OUTPUT | NOT_EVALUABLE |
| ----- | ---------: | -----: | -------: | --------: | ------------: |
| N     |            |        |          |           |               |
| P     |            |        |          |           |               |

注意：

* `NO_OUTPUT` 不计入 `UNUSABLE`；
* runtime failure 不计入 schema-valid 分母；
* 无输出不得被描述为翻译质量失败。

---

## 9. Uncertainty and Disambiguation

| Metric                     |  N |  P |
| -------------------------- | -: | -: |
| Appropriate uncertainty    |    |    |
| Unsupported disambiguation |    |    |
| Missed material ambiguity  |    |    |
| Over-flagging              |    |    |

代表性问题：

| Fixture / Block | N/P | Source | Translation | Issue |
| --------------- | --- | ------ | ----------- | ----- |
|                 |     |        |             |       |

---

## 10. Conditional Token Diagnostic

是否执行：

```text
NO / YES
```

触发原因：

| Payload | 1200 tokens result | 2400 tokens result | Conclusion |
| ------- | ------------------ | ------------------ | ---------- |
|         |                    |                    |            |

本节结果不进入主 N/P 统计。

---

## 11. Independent Reviewer

* Reviewer：
* Review mode：只读
* 是否修改代码或实验输出：NO

Reviewer 检查：

* N/P 是否只差 previous context；
* runtime、structure、quality 是否分离；
* context improvement 是否有具体证据；
* context pollution 是否漏计；
* unsupported disambiguation 是否漏计；
* verdict 是否符合 HARNESS。

需要用户确认的边界样本：

---

## 12. Decision Against Harness

| Gate                         | Requirement                  | Actual | Result |
| ---------------------------- | ---------------------------- | ------ | ------ |
| Valid paired fixtures        | >= 4                         |        |        |
| P stability not below N      | required                     |        |        |
| Final schema-valid           | 100% of successful responses |        |        |
| Block mapping coverage       | 100%                         |        |        |
| Repeated context benefit     | required for GO              |        |        |
| Systematic context pollution | none                         |        |        |

---

## 13. Final Decisions

### Empty Response Attribution

```text
PROVIDER_RANDOM
CONTEXT_ASSOCIATED
NOT_REPRODUCED
INCONCLUSIVE
```

理由：

### MVP Previous Context Policy

```text
ENABLE_COMPACT_CONTEXT
ENABLE_AS_OPTIONAL
DISABLE_FOR_MVP
UNDECIDED
```

建议窗口：

```text
previous pages:
maximum blocks:
accepted / locked only:
```

### Overall Verdict

```text
GO
CONDITIONAL_GO
FURTHER_SPIKE
NO_GO
```

理由：

---

## 14. Parent Report Correction

对父报告进行以下定向修正：

* 区分 `NO_OUTPUT` 与 `UNUSABLE`；
* 区分 response rate 与 schema-valid rate；
* 修正 previous context 与 empty response 的归因；
* 修正 unsupported disambiguation 统计；
* 引用本 follow-up；
* 根据新证据更新父 Spike verdict。

不得删除父 run 原始失败证据。

---

## 15. Recommended Next Step

只选择一项：

```text
进入 TranslationProvider / ContextBuilder 最小设计
保留 Page-level + glossary，previous context 按需启用
继续 Provider stability Spike
继续 uncertainty 专项 Spike
停止 previous context 方案
```

---

## 16. Limitations

* Fixture 规模：
* Synthetic / real 样本比例：
* Provider 非确定性：
* Reviewer 局限：
* 未验证内容：