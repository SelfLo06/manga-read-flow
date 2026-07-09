# MVP-0 FakeProvider 单 Page 后端切片

本目录包含 Goal 4 已完成的实现规划包。

范围：

* 规划一个 Project、一个 Batch、一个 Page 和 deterministic FakeProvider workflow 的最小后端实现切片。
* 使用真实临时 SQLite files 和 filesystem artifacts。
* 在真实 provider integration 之前证明 persistence、workflow、artifact、issue、decision、recovery 和 idempotency 边界。
* 止步于 `ready_for_export`。

范围外：

* 本规划步骤中的生产实现。
* 完整 Web UI。
* FastAPI route design。
* 真实 OCR、translation、cleaning 或 typesetting provider integration。
* 真实 translation prompt templates。
* 实际 export output、ZIP、manifest 和 ExportRecord 实现。
* Batch-scale workflow。
* P1 / P2 features。

本包已经产出 implementation-ready slices、validation commands、file boundaries、commit strategy、review、open questions 和 Codex task prompts。下一步实现是 Slice 01：Foundation and Project Store。
