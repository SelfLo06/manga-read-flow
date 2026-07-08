# Phase 2C Execution Contract：真实设计结果

本文给项目维护者看，解释执行契约阶段最终决定了 Provider、ArtifactService、QualityCheckService、StageExecutor 怎么协作。

## 源文件

- [../design/execution-contract/final/execution-contract-dd-v0.1.md](../design/execution-contract/final/execution-contract-dd-v0.1.md)
- [../design/execution-contract/final/provider-adapter-contract.md](../design/execution-contract/final/provider-adapter-contract.md)
- [../design/execution-contract/final/artifact-service-contract.md](../design/execution-contract/final/artifact-service-contract.md)
- [../design/execution-contract/final/quality-check-contract.md](../design/execution-contract/final/quality-check-contract.md)
- [../design/execution-contract/final/stage-executor-contract.md](../design/execution-contract/final/stage-executor-contract.md)
- [../design/execution-contract/final/fakeprovider-readiness.md](../design/execution-contract/final/fakeprovider-readiness.md)

## ProviderResult envelope 已经固定

Provider Adapter 返回统一结果，不直接返回数据库对象。

核心 outcome：

```text
success
partial_success
failure
refusal
invalid_output
```

底层意义：

- OCR/翻译/清字/嵌字工具都走同一类结果 envelope。
- `refusal` 是第一等 outcome。
- invalid JSON / schema mismatch 是 `invalid_output`。
- Page 翻译只返回部分 TextBlock 时是 `partial_success`，并要显式列出 missing target。

Provider Adapter 禁止：

- 访问 SQLite；
- 创建 OCRResult / TranslationResult；
- 注册 official artifact；
- 创建 QualityIssue；
- 决定 retry/fallback/skip/warning/block；
- 返回 provider-policy workaround。

## Provider 只能写临时文件

Provider 可以把输出写到 attempt temp root，但不能决定官方路径。

流程是：

```text
Provider temp output
-> StageExecutor 收集 evidence
-> ArtifactService promote/register official artifact
-> WorkflowLoopEngine acceptance 后才可能 active
```

底层意义：

- 一个文件被生成，不等于系统接受它。
- 一个 artifact 被注册，也不等于它是当前输出。
- active pointer 只能由 WorkflowLoopEngine acceptance 更新。

## ArtifactService 的职责已经固定

ArtifactService 负责：

- 官方路径；
- 原子写入 / promote；
- hash；
- metadata；
- retention；
- storage_state；
- cleanup；
- missing/hash-invalid 检测。

ArtifactService 不负责：

- retry；
- fallback；
- warning；
- block；
- readiness；
- QualityIssue；
- active pointer。

如果 active artifact 文件丢了：

```text
ArtifactService: storage_state = missing
WorkflowLoopEngine: 决定 rebuild / warning / pause / block
```

## QualityCheckService 返回 issue draft，不推进状态

QualityCheckService 输入：

- Provider outcome；
- artifact evidence；
- candidate output；
- dependency hashes；
- profile quality strictness；
- tool/attempt metadata。

输出：

- issue drafts；
- severity；
- blocking；
- discovered_stage；
- root_stage；
- message key；
- suggested action key；
- lifecycle suggestion。

它不写数据库，不更新 active pointer，不创建 WorkflowDecision。

底层意义：

- “发现问题”和“决定怎么办”分离。
- 质量检查可以说“这像 typesetting overflow”，但不能说“允许 warning export”。

## StageExecutor 是一段执行，不是 workflow engine

StageExecutor 做一件事：

```text
执行一个 stage attempt，并返回 StageResult evidence
```

它收到 `StageExecutionContext`，里面有：

- task/stage/target identity；
- profile snapshot；
- provider selection；
- active pointers；
- input/config/context hashes；
- artifact validation evidence；
- temp root；
- pause/cancel safe boundary。

它返回 `StageResult`，里面有：

- attempt evidence；
- provider evidence；
- artifact evidence；
- candidate outputs；
- quality evidence；
- dependency evidence；
- boundary flags。

它不能返回：

- WorkflowDecision；
- next stage；
- retry budget mutation；
- active pointer mutation；
- final readiness；
- fallback provider selection。

## 事务边界已经固定

关键硬规则：

```text
provider call 期间不能持有 SQLite write transaction
```

执行顺序：

1. 短事务创建 running WorkflowAttempt。
2. 释放数据库写事务。
3. 调用 Provider / 本地工具。
4. 短事务写 ToolRunLog / attempt evidence。
5. ArtifactService 注册 official artifact。
6. QualityCheckService 生成 report/draft。
7. WorkflowLoopEngine acceptance 事务写 decision / issue / result / active pointer / status。

底层意义：

- provider 很慢或卡住时不会锁住 SQLite。
- 崩溃时至少知道 attempt 已开始。
- 只有 acceptance 事务成功后，结果才是 current。

## FakeProvider 必须模拟真实边界

FakeProvider 不是直接插数据库的测试捷径。

它也必须：

- 返回真实 ProviderResult envelope；
- 写 temp files 而非 official paths；
- 不创建 QualityIssue；
- 不更新 active pointers；
- 使用 deterministic fake modes；
- fake mode 必须在 profile snapshot 或 task test config 中可追溯。

必须覆盖的 fake modes 包括：

- happy path；
- OCR fail once；
- OCR empty；
- translation invalid JSON；
- provider refusal；
- partial translation；
- cleaning skip；
- typesetting overflow；
- missing active artifact。

## 这个阶段没有决定什么

没有决定：

- 真实 OCR/LLM prompt；
- 真实 provider JSON schema；
- 具体 Python DTO 类名；
- SQL DDL；
- FastAPI route；
- UI 展示；
- ZIP/export manifest。

它只固定“执行边界”和“证据如何流动”。
