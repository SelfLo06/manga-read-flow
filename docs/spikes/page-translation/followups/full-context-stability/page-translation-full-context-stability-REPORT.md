# Full Text Context Stability Follow-up — REPORT

## 1. Executive Summary

- Run ID：`20260710T173016Z-454fed`
- Git HEAD：`325a03b`
- Provider：OpenAI-compatible chat completions endpoint
- Model：`deepseek-v4-pro`
- Stability trials：15
- Paired fixtures：6
- Empty Response Attribution：`INCONCLUSIVE`
- MVP Previous Context Policy：`DISABLE_FOR_MVP`
- Overall Verdict：`FURTHER_SPIKE`

核心结论：

父 Spike 中 `context-dependent` 与 `long-page` 的空响应未在 Same-request Stability 复现。Stability 的 `runtime_success_count` 为 15/15（即 HTTP 成功、`choices >= 1` 且 content 非空），但端到端有效结果为 14/15：`S-long-page-01` 的非空响应因截断而未形成最终有效 JSON。N/P 配对实验中 P 组 18/18 成功，N 组 17/18 成功，唯一空响应发生在 N 组 `omitted-object`，并带有 `finish_reason=length`、`output_tokens=1200` 证据；2400-token 条件性诊断对同一 payload 成功返回完整合法结果。因此本轮不能证明 previous context 导致空响应。

但 previous context 的翻译收益也不够稳定：6 个 paired fixture 中多数为 `NO_MEANINGFUL_EFFECT`，没有达到 HARNESS 对“至少 2 个 fixture 出现可重复改善”的 GO 门槛。

---

## 2. Frozen Configuration

| Item | Value |
|---|---|
| Provider | openai-compatible |
| Model | deepseek-v4-pro |
| Temperature | 0 |
| Max output tokens | 1200 |
| Timeout | 60s |
| System prompt SHA-256 | `aac64d9616e3cdb32eb074723580ee604a5106b33b7cefe46e8dc4e97179f77c` |
| Repair prompt SHA-256 | `84b1bf1f044d63a94787d2001124cb04bc71ac1ed6fff3d2b04da22bd203b757` |
| Schema SHA-256 | `c11be9d1cee7fe935ce6b85bd31c45dc4772b2027970d3631b66d80e8d53a9ac` |
| Fixture set SHA-256 | `aebfdaf0488fc737183960a2128b66037f4c57b516580ec557eedea45536bee0` |
| Random seed | 20260710 |

运行期间输入是否变化：

```text
NO
```

---

## 3. Same-request Stability

`summary.json` 中 stability 的 `success_count` 语义为 `runtime_success_count`，不等于端到端最终有效结果数。

| Fixture                    | Trials | Runtime response success | End-to-end valid result | Empty content | No choices | Timeout | Mixed outcome |
| -------------------------- | -----: | -----------------------: | ----------------------: | ------------: | ---------: | ------: | ------------- |
| context-dependent          | 5 | 5/5 | 5/5 | 0 | 0 | 0 | false |
| long-page                  | 5 | 5/5 | 4/5 | 0 | 0 | 0 | false |
| previous-page-with-context | 5 | 5/5 | 5/5 | 0 | 0 | 0 | false |

汇总：

```text
Runtime response success: 15/15
End-to-end valid result: 14/15
```

`S-long-page-01` 的证据链：

```text
runtime_status = SUCCESS_RESPONSE
finish_reason = length
content non-empty
JSON / schema invalid
repair attempted once
repair failed
final validation invalid
```

证据：

* 相同 request hash 是否同时出现成功和空响应：NO
* 空响应是否可重复：NO
* 空响应是否集中于特定输入：NO
* Provider response metadata 是否显示异常：除 `S-long-page-01` 的 `finish_reason=length` 截断外，Same-request stability 未见 runtime 空响应异常。

结论：

```text
NOT_REPRODUCED_FOR_PARENT_EMPTY_PAYLOADS
```

最终 Empty Response Attribution 仍为 `INCONCLUSIVE`，因为 paired 实验中出现了一次新的 N 组 `EMPTY_CONTENT`。

---

## 4. Paired Fixture Validation

| Fixture | N/P pair valid | Current page hash equal | Glossary hash equal | Previous context differs |
| ------- | -------------- | ----------------------- | ------------------- | ------------------------ |
| honorific-continuity | YES | YES | YES | YES |
| proper-name-continuity | YES | YES | YES | YES |
| dialogue-continuity | YES | YES | YES | YES |
| omitted-object | YES | YES | YES | YES |
| pronoun-continuity | YES | YES | YES | YES |
| misleading-context | YES | YES | YES | YES |

有效 paired fixture 数：6

无效 pair 及原因：无。

---

## 5. Runtime Results

| Group | Calls | Success | Empty response | Timeout | HTTP error | End-to-end valid rate |
| ----- | ----: | ------: | -------------: | ------: | ---------: | --------------------: |
| N     | 18 | 17 | 1 | 0 | 0 | 94.44% |
| P     | 18 | 18 | 0 | 0 | 0 | 100.00% |

| Metric                | N | P |
| --------------------- | -: | -: |
| Response success rate | 94.44% | 100.00% |
| Empty response rate   | 5.56% | 0.00% |
| Median latency        | 7149ms | 5363ms |
| Max latency           | 21483ms | 15035ms |
| Input tokens          | 33126 | 34767 |
| Output tokens         | 9004 | 7737 |

Previous context 是否降低响应稳定性：

```text
NO
```

本轮唯一空响应发生在 N 组。

---

## 6. Structural Results

结构指标的分母仅包含 `SUCCESS_RESPONSE`。Stability 的 15 个 runtime-success 响应中，14 个最终结构有效；唯一例外为 `S-long-page-01`，其一次 repair 仍因长度截断失败。下表只列 N/P 配对实验。

| Metric                  | N | P |
| ----------------------- | -: | -: |
| First-pass JSON valid   | 100% | 100% |
| First-pass schema valid | 100% | 100% |
| Final schema valid      | 100% | 100% |
| Block mapping coverage  | 100% | 100% |
| Missing blocks          | 0 | 0 |
| Duplicate blocks        | 0 | 0 |
| Unknown blocks          | 0 | 0 |
| Repair attempted        | 0 | 0 |
| Repair recovered        | 0 | 0 |
| Repair failed           | 0 | 0 |

是否满足：

```text
final schema-valid = 100%
block mapping coverage = 100%
unknown block = 0
duplicate block = 0
```

YES for successful responses.

---

## 7. Previous Context Quality Effect

| Fixture | Focus | N result | P result | Context effect |
| ------- | ----- | -------- | -------- | -------------- |
| honorific-continuity | honorific | 已用“前辈” | 已用“前辈” | NO_MEANINGFUL_EFFECT |
| proper-name-continuity | proper name / term | 术语已正确 | 术语已正确 | NO_MEANINGFUL_EFFECT |
| dialogue-continuity | dialogue | 语义可用 | 语义可用，个别 trial 更接近 reference | NO_MEANINGFUL_EFFECT |
| omitted-object | omitted object | 1 次 NO_OUTPUT；成功 trial 有“给你”无依据消歧 | P 组稳定“交出去/交上去” | CONTEXT_IMPROVEMENT |
| pronoun-continuity | pronoun | 未明确补“流星石” | P 组也未明确补“流星石” | NO_MEANINGFUL_EFFECT |
| misleading-context | misleading context | 当前页正确 | P 组未复制旧天文台集合信息 | NO_MEANINGFUL_EFFECT |

汇总：

| Effect               | Count |
| -------------------- | ----: |
| Context improvement  | 1 |
| No meaningful effect | 5 |
| Context regression   | 0 |
| Context pollution    | 0 |

主要改善：

* 主宾语或指代：`omitted-object` 中 P 组更稳定地把 `渡す` 翻为“交出去/交上去”，符合 previous context 中“申请书交给老师”的语境。

主要副作用：

* 历史内容复制：未发现。
* 历史语境覆盖当前页：未发现；`misleading-context` 保持“体育馆集合”，没有被前页“旧天文台集合”覆盖。
* 无依据消歧：N 组 `omitted-object` token diagnostic 中出现“给你”，属于无 previous context 下的无依据对象补充；P 组未见系统性增加。
* 错误指代：未见系统性证据。

---

## 8. Translation Quality

只统计形成完整译文的 block。

| Group | ACCEPTABLE | REVIEW | UNUSABLE | NO_OUTPUT | NOT_EVALUABLE |
| ----- | ---------: | -----: | -------: | --------: | ------------: |
| N     | 0 | 0 | 0 | 2 | 34 |
| P     | 0 | 0 | 0 | 0 | 36 |

注意：

* `NO_OUTPUT` 不计入 `UNUSABLE`；
* runtime failure 不计入 schema-valid 分母；
* 无输出不得被描述为翻译质量失败。

本表仍待独立 reviewer 或用户将 `NOT_EVALUABLE` 样本细分为 `ACCEPTABLE / REVIEW / UNUSABLE`。本轮自动脚本只负责生成 review 输入，不自动宣称质量评级。

---

## 9. Uncertainty and Disambiguation

| Metric                     | N | P |
| -------------------------- | -: | -: |
| Appropriate uncertainty    | 未自动判定 | 未自动判定 |
| Unsupported disambiguation | 1 个代表样本 | 未见系统性增加 |
| Missed material ambiguity  | 未自动判定 | 未自动判定 |
| Over-flagging              | 未自动判定 | 未自动判定 |

代表性问题：

| Fixture / Block | N/P | Source | Translation | Issue |
| --------------- | --- | ------ | ----------- | ----- |
| omitted-object / oo-b001 | N diagnostic | 今日こそ渡す。 | 今天一定要给你。 | 无 previous context 下补出“你”，证据不足 |
| pronoun-continuity / pc-b001 | N/P | あれ、まだ光ってる。 | 仍译为“还在发光” | 未利用 previous context 显式消解为流星石 |

---

## 10. Conditional Token Diagnostic

是否执行：

```text
YES
```

触发原因：`NP-omitted-object-N-01` 为 HTTP 200、choices=1、content empty、`finish_reason=length`、`output_tokens=1200`。

| Payload | 1200 tokens result | 2400 tokens result | Conclusion |
| ------- | ------------------ | ------------------ | ---------- |
| omitted-object / N / trial 1 | EMPTY_CONTENT, finish_reason=length | SUCCESS_RESPONSE, valid JSON, finish_reason=stop | `TOKEN_LIMIT_ASSOCIATED`；诊断不进入主统计 |

该具体失败归类为 `TOKEN_LIMIT_ASSOCIATED`，不得归因于 previous context，也不作为随机 Provider 失败计数。

---

## 11. Independent Reviewer

* Reviewer：独立 Codex reviewer `Boyle`
* Review mode：只读
* 是否修改代码或实验输出：NO

Reviewer 检查：

* N/P 只差 previous context：确认是。
* runtime、structure、quality 是否分离：基本分离，`NO_OUTPUT` 未计入 `UNUSABLE`；`S-long-page-01` 已明确为 runtime 成功但结构失败，不能仅以 runtime success 描述为最终有效。
* context improvement：`omitted-object` 明确改善；`proper-name-continuity` 有弱改善，但 glossary 混杂。
* context pollution：未发现；`misleading-context` 没有把“体育馆”覆盖成“天文台”。
* unsupported disambiguation：未发现系统性证据。
* verdict：reviewer 建议可视为“带护栏进入 MVP”的更乐观结论；本报告按 HARNESS 枚举和收益门槛保守判为 `FURTHER_SPIKE`。

需要用户确认的边界样本：

* `omitted-object / oo-b001`：`渡す` 是否应译为“交出去/交上去”，是否允许无上下文译成“给你”。
* `pronoun-continuity / pc-b001`：是否需要把 `あれ` 明确译为“流星石”，还是保持“那个/它”更安全。
* `dialogue-continuity / dc-b001`：`答え` 译为“答案/回答”均可，需确认风格偏好。
* `proper-name-continuity / pn-b001`：`唯也说会来` 是否算错误归因。
* `misleading-context / mc-b002`：`改天` 与 `下次` 是否等价可接受。

---

## 12. Decision Against Harness

| Gate                         | Requirement                  | Actual | Result |
| ---------------------------- | ---------------------------- | ------ | ------ |
| Valid paired fixtures        | >= 4                         | 6 | PASS |
| P stability not below N      | required                     | P 100% vs N 94.44% | PASS |
| Final schema-valid           | 100% of successful responses | N/P 100% | PASS |
| Block mapping coverage       | 100%                         | N/P 100% | PASS |
| Repeated context benefit     | required for GO              | 1 fixture improvement | FAIL |
| Systematic context pollution | none                         | none found | PASS |

---

## 13. Final Decisions

### Empty Response Attribution

```text
INCONCLUSIVE
```

理由：

* 父 run 两个空响应 payload 在 5 次重复中均未复现。
* paired 实验只有 1 次新空响应，且发生在 N 组。
* 该空响应具备明确 token-limit 证据并在 2400-token 诊断中成功，归类为 `TOKEN_LIMIT_ASSOCIATED`。
* 样本仍不足以把空响应整体归为 `PROVIDER_RANDOM` 或 `NOT_REPRODUCED`。

### MVP Previous Context Policy

```text
DISABLE_FOR_MVP
```

含义：P0 默认构造 Page-level + glossary 请求，`previous_context = []`。保留 `previous_context` 字段、hash 和 provenance seam，但不默认发送非空历史上下文；这不是永久删除该能力。

理由：

* 没有证据表明 P 组降低响应稳定性，也未发现系统性 context pollution。
* 但可重复的普遍收益不足，主要改善集中在 `omitted-object` 一个 fixture。
* 因此当前证据不支持在 P0 默认启用 previous context。

### Overall Verdict

```text
FURTHER_SPIKE
```

理由：

* 结构层满足门槛。
* 稳定性没有证明 previous context 有害。
* 质量收益未达到 GO 门槛，需要更强 fixture 或更明确 context construction 策略。
* 此 verdict 表示 previous-context 证据不足，不表示 Page Translation 核心能力不可用。

---

## 14. Limitations

* 样本仍是小规模 synthetic text-only fixtures。
* 没有视觉上下文，不能判断说话人、视线和画面指代。
* 自动脚本未完成最终 `ACCEPTABLE / REVIEW / UNUSABLE` 质量评级，只生成 review 输入。
* 条件性 token diagnostic 只对一个 payload 执行，不进入主统计。
* 本轮没有修改正式 Workflow、Provider、Repository 或数据库。
