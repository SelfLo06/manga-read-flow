# Development Session Log — YYYY-MM-DD

> 本日志记录一次连续 Development Session 的实际变化、验证证据和交接状态。
> 正式需求、架构和设计以对应权威文档为准。

## Session Metadata

* Started:
* Ended:
* Log finalized:
* Time zone:
* Phase:
* Primary goal:
* Branch at start:
* Starting commit:
* Working tree at start:

## Completed

### 1. <Task / Slice / Review / Spike Name>

Status:

* Implementation:
* Validation:
* Review:
* Commit:

Result:

* <本 Session 实际形成的可观察结果>
* <只描述变化，不复制完整设计内容>

Scope:

* In scope:

  * <实际完成的范围>
* Explicitly not implemented:

  * <明确未进入的范围>

Evidence:

* Commit:

  * `<sha> <message>`
* Files or documents:

  * `<path>`
* Review or report:

  * `<path>`

Validation:

```text
<command>
```

Result:

```text
<actual result>
```

Notes:

* <失败原因、跳过原因或必要的范围说明>

### 2. <Optional Additional Work Item>

Status:

* Implementation:
* Validation:
* Review:
* Commit:

Result:

* <result>

Evidence:

* `<path or commit>`

Validation:

```text
<command>
```

Result:

```text
<actual result>
```

## Durable Decisions

### <Decision Title>

Decision:

* <本 Session 新形成并被接受的持久决定>

Rationale:

* <一到两句，不重复完整设计论证>

Source of truth:

* `<ADR / final design / GOAL / review path>`

Rejected or deferred alternative:

* <如适用>

如果没有形成新的持久决定：

```text
No new durable decisions.
```

## Problems and Learnings

### <Problem Title>

Observed:

* <实际现象>

Cause:

* <已确认根因；未确认时明确写 unknown>

Resolution:

* <已执行处理>

Remaining risk:

* <仍存在的风险>

Reusable lesson:

* <是否需要更新 Prompt Pattern、AGENTS、测试或门禁>

如果没有值得长期保留的问题，可删除本节。

## Local and Repository State

Repository-tracked changes:

* `<tracked files>`

Untracked files:

* `<untracked files or none>`

Ignored local files:

* `<ignored local-only files or none>`

Local environment changes:

* `<Conda / venv / tool installation / config changes>`

Notes:

* <说明哪些内容不属于仓库正式资产>

## Validation Status

| Validation         | Command     | Result     | Status                    |
| ------------------ | ----------- | ---------- | ------------------------- |
| Focused validation | `<command>` | `<result>` | passed / failed / skipped |
| Full suite         | `<command>` | `<result>` | passed / failed / skipped |
| Static checks      | `<command>` | `<result>` | passed / failed / skipped |
| Review gate        | `<review>`  | `<result>` | passed / failed / not run |

Skipped validation reasons:

* <无则写 None>

Do not claim success when required validation was not run without an accepted reason.

## Open Items

* [ ] <尚未完成且需要交接的具体事项>
* [ ] <已知 blocker>
* [ ] <deferred risk>
* [ ] <后续验证需求>

不要把长期路线图全部复制到这里，只保留下一 Session 可能需要处理的事项。

## Handoff

* Current phase:
* Branch at end:
* HEAD at end:
* Working tree at end:
* Implementation status:
* Focused validation status:
* Full validation status:
* Review status:
* Known blockers:
* Deferred risks:
* Next concrete task:
* Required inputs:

  * `<document / branch / local asset>`
* Allowed scope:

  * `<allowed files or activity>`
* Forbidden scope:

  * `<explicit non-goals>`
* Stop condition:

  * <出现什么情况时必须停止并报告>

## Final Session Summary

```text
<一到三行总结>

Example:
MVP-0 Slice 07 implementation and validation completed.
Backend closure review passed with deferred risks.
Next task is an isolated Detection + OCR Real Tool Spike.
```
