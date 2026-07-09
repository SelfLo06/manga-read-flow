# Code Health Gate

版本：v0.1
状态：工程基线
范围：Implementation slices、code review、AI-assisted coding 与可维护性控制

---

## 1. 目的

Code Health Gate 用于控制实现过程中引入的非 bug 类缺陷。

非 bug 类缺陷是指：代码今天可能通过测试，但会让系统之后更难修改、更难测试、更难恢复，或更容易被改坏。

本 gate 关注：

- 架构边界漂移；
- 职责漂移；
- 过度耦合；
- 低内聚；
- 信息泄漏；
- 脆弱状态处理；
- 可测试性薄弱；
- 大文件膨胀；
- AI 生成代码膨胀。

本文档是高优先级工程规则。每个 implementation slice 的功能性验证通过后，都适用本规则。

---

## 2. 权威性与优先级

本 gate 必须保持当前项目基线：

- SRS；
- HLD；
- 最终详细设计；
- implementation slice documents；
- 既有 plans 中记录的 architecture invariants。

本文档不覆盖已接受的设计基线。当本文档与最终设计冲突时，停止并报告冲突。

Code Health Gate pass 可以重构局部实现细节。它不得扩大产品范围，也不得改变已接受的架构决策。

---

## 3. 范围

在某个功能性 implementation slice 通过其聚焦测试后运行本 gate。

除非用户明确授权更广泛 review，否则只 review 当前 slice diff。

本 gate 可以：

- 识别 smells；
- 修复局部安全 smells；
- 为边界失败添加聚焦测试；
- 按已接受的架构边界拆分文件；
- 报告延后风险。

本 gate 不可以：

- 引入新的产品功能；
- 实现真实 providers，除非 slice 明确允许；
- 添加 UI、API、frontend、export、ZIP 或 manifest 行为，除非 slice 明确允许；
- 重写最终设计基线；
- 执行大范围跨 slice refactors；
- 对无关文件执行纯格式化重写。

---

## 4. 严重级别分类

### A. 架构边界 Smells：阻塞

这些必须在 merge 前修复，或明确升级处理。

#### Provider Adapter

阻塞 smells：

- 访问 Repository、DAO、SQLite、ORM session、cursor、`app.db` 或 `project.db`；
- 登记 official artifacts；
- 写入 active OCR、translation、cleaned 或 typeset pointers；
- 创建 `QualityIssue`；
- 创建 `WorkflowDecision`；
- 决定 retry、fallback、skip、warning、block、pause、cancel 或 readiness；
- 将 secrets 存入 logs、snapshots、artifacts 或 database rows；
- 包含 provider-policy bypass 或 evasion behavior。

推荐方向：

- Provider 只返回结构化 provider results、标准化 errors、temporary outputs 和 sanitized metadata。

#### StageExecutor

阻塞 smells：

- 拥有 retry、fallback、skip、warning、block、pause、cancel 或 readiness 逻辑；
- 更新 active pointers；
- 创建 `WorkflowDecision`；
- 创建或 lifecycle-manage `QualityIssue`；
- 接收宽泛 repository access；
- 在 provider calls 期间持有 SQLite write transactions；
- 按 timestamp 选择 latest artifact 或 result。

推荐方向：

- StageExecutor 执行一个 stage，调用 Provider Adapter 或 local tool，通过 `StageEvidenceWriter` 记录窄 tool evidence，并把 evidence 返回给 WorkflowLoopEngine。

#### ArtifactService

阻塞 smells：

- 决定 workflow retry、fallback、skip、warning、block、pause、cancel 或 readiness；
- 选择 active page outputs；
- 直接修改 workflow state；
- 允许路径穿越到 Project workspace 外；
- 覆盖 original images；
- 将 filesystem paths 当作 workflow source of truth。

推荐方向：

- ArtifactService 拥有 official artifact lifecycle：path generation、atomic write 或 promotion、hash、metadata registration、storage state、missing / corrupt detection 和 cleanup boundaries。

#### QualityCheckService

阻塞 smells：

- 推进 workflow state；
- 更新 active pointers；
- 在 MVP-0 中直接持久化 issues，除非设计明确授权；
- 创建 `WorkflowDecision`；
- 执行 provider calls；
- 重写 artifacts 或 result versions。

推荐方向：

- QualityCheckService 返回 quality reports、issue drafts、severity、blocking flag、attribution 和 suggested action keys。

#### WorkflowLoopEngine

阻塞 smells：

- 直接使用 SQL、ORM sessions、cursors 或 table-shaped row dictionaries；
- 当 stage 设计要求 StageExecutor 时，绕过 StageExecutor 调用 Provider Adapter；
- 将 filesystem paths 作为 active artifacts 的 source of truth；
- 按 latest timestamp 选择 active result 或 artifact；
- 将 `Page.status` 当作 recovery source of truth；
- 直接执行 official artifact lifecycle operations；
- 绕过 QualityCheckService 执行 quality classification。

推荐方向：

- WorkflowLoopEngine 通过 repository contracts 和 ArtifactService reports 拥有 decisions、acceptance、retry budgets、fallback、skip、warning、block、readiness 和 recovery decisions。

#### Repository / DAO

阻塞 smells：

- 向 workflow / application / provider layers 暴露 raw connections、cursors、sessions 或 SQL；
- 成为以 table-shaped CRUD 为主要抽象的 generic `Repository<T>`；
- 嵌入 provider calls、artifact filesystem writes 或 workflow policy decisions；
- 在 `app.db` 和 `project.db` 之间使用跨数据库 foreign keys；
- 将 image bytes 或 large payloads 存入 SQLite。

推荐方向：

- Repository / DAO 是唯一 SQLite 访问入口，并暴露命名的、面向任务的 operations。

#### Data and Recovery

阻塞 smells：

- original images 被覆盖；
- image bytes 或 large payloads 存入 SQLite；
- recovery 只依赖 `Page.status`；
- normal export 或 readiness 忽略 unresolved blocking `QualityIssue`；
- warning readiness 静默变成 pure readiness；
- active output selection 使用 timestamps；
- stale OCR、translation、cleaned 或 typeset outputs 未经 validation、rerun 或显式 reuse decision 就变为 export-effective。

推荐方向：

- 使用 active pointers、dependency hashes、artifacts、attempts、decisions、tool logs、issues 和 stage statuses 作为 durable evidence。

---

### B. 模块化与职责 Smells：通常应在 Merge 前修复

这些通常表示设计侵蚀。安全时做局部修复。

Smells：

- God class 或 God service；
- 一个文件混合 orchestration、persistence、provider calls、quality checking、artifact lifecycle 和 readiness；
- helper module 变成垃圾桶；
- 重复 state transition logic；
- 重复 active pointer update logic；
- 重复 acceptance transaction logic；
- 具体实现类型泄漏到 public interfaces；
- public mutable state；
- 类似 `a.getB().getC().doSomething()` 的 message chains；
- 过宽 interfaces 迫使 clients 依赖未使用 methods；
- 违反 HLD dependency direction 的 cross-layer imports；
- domain DTOs 包含 persistence、provider 或 filesystem behavior；
- workflow policy 分散在多个 services。

推荐方向：

- 按职责拆分；
- 引入窄 contracts；
- 委托给拥有该信息的模块；
- 将 state transitions 移到 workflow-owned 的单一位置；
- 保持 public APIs 小而表达意图；
- 隐藏 data layout、SQL shape、artifact paths 和 provider temp outputs。

---

### C. 可测试性 Smells：局部可修则修，否则记录风险

Smells：

- provider calls 发生在 SQLite write transactions 内；
- FakeProvider mode 隐藏在 global state 中；
- tests 不能控制 time、UUID、hash、workspace path、provider mode 或 retry budget；
- 关键边界只被宽泛 full-suite tests 覆盖；
- failure paths 没有聚焦测试；
- tests 只断言 `Page.status`，而不是 durable evidence；
- tests 依赖本地 absolute paths；
- FakeProvider slices 的 tests 依赖 network、real OCR、real LLM 或 GPU；
- tests 需要按 latest timestamp 排序才能通过。

推荐方向：

- 注入 clocks、UUID factories、workspace roots 和 FakeProvider modes；
- persistence slices 使用临时真实 SQLite files；
- 使用聚焦 integration tests 覆盖边界行为；
- 断言 attempts、decisions、issues、artifacts、active pointers 和 dependency hashes；
- 将真实 provider integration 保留到显式 Spike 或后续 slice scope。

---

### D. 局部可读性 Smells：机会性修复

安全且小的时候修复。

Smells：

- 命名不清晰；
- magic strings；
- 小段重复代码；
- 过长 `if/elif` chains；
- 异常信息不清晰；
- 过多注释用来弥补糟糕结构；
- enum 或 status 命名不一致；
- local functions 有隐藏 side effects；
- 宽泛 `except Exception` 且没有 normalization。

推荐方向：

- 重命名 private helpers；
- 抽取小型 private functions；
- 用既有 enums 或 constants 替换 magic strings；
- 改进 error normalization；
- 注释应解释 rationale，而不是解释缠绕的 control flow。

---

## 5. 将设计原则应用为 Review 规则

把这些原则作为实际 review 问题使用。

### Responsibility Assignment

询问：

- 这个模块负责什么？
- 它维护什么数据？
- 它执行什么操作？
- 它是否有超过一个变更原因？

Smells：

- 一个 service 既 orchestration workflow 又写 SQL；
- 一个 provider 既调用工具又创建 domain rows；
- 一个 repository 既持久化数据又决定 workflow policy。

推荐方向：

- 适当时保持 data responsibility 和 behavior responsibility 接近；
- 将 orchestration、persistence、quality classification、provider calls 和 artifact lifecycle 分离。

---

### Collaboration

询问：

- 哪些对象协作完成这个 behavior？
- 协作是否显式且可测试？
- 某个对象是否过度了解另一个对象的内部？

Smells：

- 深层 message chains；
- service 穿透多个对象去修改 nested state；
- workflow code 依赖 provider-specific response internals。

推荐方向：

- 使用窄 DTOs 和显式 stage results；
- 让每个模块暴露 behavior，而不是内部结构。

---

### Information Expert

询问：

- 哪个模块拥有做出这个 decision 所需的信息？
- decision 是否位于那里？

项目专属映射：

- workflow decision → WorkflowLoopEngine；
- quality classification → QualityCheckService；
- official artifact state → ArtifactService 加 artifact metadata repository；
- SQLite query and persistence → Repository / DAO；
- provider invocation details → Provider Adapter；
- acceptance transaction → WorkflowLoopEngine through Unit of Work。

Smell：

- 一个模块依赖另一个模块的隐藏内部信息来做 decision。

推荐方向：

- 将 behavior 移到拥有所需信息的模块，或暴露窄 query / report。

---

### Creator

询问：

- 谁拥有安全创建这个对象所需的数据？
- 谁应该创建 official domain rows？

项目专属映射：

- Provider Adapter 只能创建 provider output DTOs；
- StageExecutor 只能创建 stage evidence；
- WorkflowLoopEngine acceptance 创建 accepted OCR / Translation result versions 和 active pointer changes；
- ArtifactService 创建 official artifact metadata；
- Repository 通过命名 operations 持久化 rows。

Smell：

- Provider 创建 `OCRResult`、`TranslationResult`、`QualityIssue` 或 official artifact rows。

推荐方向：

- provider outputs 在 workflow 接受前保持为 candidates。

---

### Controller

询问：

- 哪个模块接收并协调 system event？

项目专属映射：

- API handler 校验并委托；
- ApplicationService 拥有 use-case entry；
- WorkflowLoopEngine 控制 workflow decisions；
- StageExecutor 只控制一个 stage execution；
- TaskRunner 运行 background tasks。

Smell：

- API handler 执行长 workflow execution；
- StageExecutor 变成隐藏的 WorkflowLoopEngine；
- Repository 开始控制 task progress。

推荐方向：

- 将控制保持在正确抽象层级。

---

### Low Coupling

询问：

- 这个模块能否在不迫使无关模块变化的情况下改变？
- 它是否依赖具体实现细节？

Smells：

- workflow import 具体 SQLite repository implementation；
- provider import repository modules；
- tests 需要 internal table names；
- public APIs 暴露 implementation-specific DTOs。

推荐方向：

- 依赖窄 contracts；
- 将具体实现隐藏在 adapters 或 repositories 后。

---

### High Cohesion

询问：

- 这个文件中的所有 functions 是否服务于一个清晰职责？
- 新开发者是否知道相关 behavior 应加在哪里？

Smells：

- `workflow_loop.py` 同时包含 decision policy、recovery、acceptance、readiness、provider calls 和 persistence mapping；
- `repositories.py` 包含系统所有 query；
- `utils.py` 包含无关 helpers。

推荐方向：

- 按已接受架构边界或内聚职责拆分。

---

### Law of Demeter

询问：

- caller 是否只和自己的直接 collaborators 对话？
- 它是否在导航另一个对象的内部结构？

Smells：

- `a.getB().getC().doSomething()`；
- workflow code 读取 nested provider internals；
- service 穿透 repository return objects 去修改 nested data。

推荐方向：

- 添加 domain method、service method、query method 或 DTO，直接表达所需 operation。

---

### Program to Interfaces

询问：

- caller 依赖 contract 还是 concrete implementation？
- implementation 能否在测试中替换？

Smells：

- application 或 workflow code 直接依赖 `Sqlite...` classes；
- provider contract 应被使用的位置硬编码 provider implementation；
- FakeProvider 之后无法替换成真实 provider adapter。

推荐方向：

- 在预期需要替换的地方使用窄 protocol / interface / contract-like boundaries。

---

### Interface Segregation

询问：

- caller 是否获得了比自己需要更多的 methods？
- interface 是否允许 forbidden writes？

Smells：

- StageExecutor 接收 broad repositories；
- QualityCheckService 接收 persistence writers；
- Provider 接收带 database 或 artifact registration capability 的 context；
- 一个 repository interface 暴露无关 operations。

推荐方向：

- 拆成窄 interfaces，例如 `StageEvidenceWriter`、readiness query、artifact metadata query、result version writer 和 workflow acceptance operation。

---

### Liskov Substitution and Inheritance Coupling

询问：

- subclass 能否在不改变行为预期的情况下替换 parent？
- inheritance 是否被用于 implementation reuse？

Smells：

- subclass override parent method 但语义不同；
- test FakeProvider 继承 real provider 并禁用主要行为；
- base class 包含 workflow policy，subclasses 只 override 部分逻辑。

推荐方向：

- 优先 composition 和显式 strategy objects；
- 需要 polymorphism 时使用纯抽象 contracts。

---

### Composition Over Inheritance

询问：

- behavior 是由 collaborators 组装出来，还是埋在 parent class 中？

Smells：

- providers、repositories 或 stage executors 存在深 inheritance hierarchy；
- subclass 需要了解 parent internals；
- tests 中通过 override methods 禁用 behavior。

推荐方向：

- 通过窄 collaborators 组合 provider clients、mappers、validators 和 policies。

---

### Information Hiding

询问：

- 这个模块隐藏了什么 design decision？
- 该隐藏细节是否泄漏？

项目专属隐藏细节：

- SQLite schema 和 SQL 细节；
- artifact filesystem paths 和 temp paths；
- provider-specific response format；
- retry budget storage；
- active pointer update mechanics；
- readiness query mechanics；
- recovery reconciliation details。

Smells：

- workflow code 依赖 table names；
- UI / API 接收 artifact filesystem paths 作为 authoritative data；
- provider temp paths 未经 ArtifactService 泄漏进 official metadata；
- result selection 依赖 timestamp ordering。

推荐方向：

- 暴露稳定 operations 和 reports，而不是内部表示。

---

### Encapsulate Change

询问：

- 什么最可能变化？
- 变化点是否被隔离？

可能变化点：

- OCR provider；
- translation provider；
- cleaner；
- typesetter；
- quality policy；
- retry / fallback policy；
- artifact retention；
- repository implementation；
- API schema；
- UI review flow。

Smells：

- provider-specific logic 扩散到 workflow；
- quality thresholds 在多个地方 hardcode；
- artifact retention logic 出现在 ArtifactService 之外。

推荐方向：

- 将变化的 policy 或 provider behavior 隔离到拥有它的模块后面。

---

### Least Privilege

询问：

- 这个 caller 是否只拥有自己需要的 capability？

Smells：

- StageExecutor 接收 full Unit of Work；
- Provider 接收 Project repositories；
- QualityCheckService 接收 active pointer writer；
- tests 在 public evidence 可用时仍使用 private internals。

推荐方向：

- 传递窄 capabilities；
- 通过 API shape 拒绝访问，而不是靠约定。

---

## 6. 文件大小策略

行数本身不是设计规则，但大文件是职责漂移的强证据。

手写 Python 产品代码的项目阈值：

| File size | Policy |
| --- | --- |
| <= 400 lines | 正常。 |
| 400-700 lines | 当职责内聚时可接受。 |
| 700-1000 lines | review trigger。解释为什么文件仍然内聚。 |
| > 1000 lines | 除非有明确理由，否则按职责拆分。 |
| > 2000 lines | 严重 smell。merge 前必须拆分或升级处理。 |

允许例外：

- generated code；
- vendored third-party code；
- 带清晰标签的一次性 migration 或 bootstrap scripts；
- 少见的 test fixture generation scripts。

通常 2000+ 行不可接受的文件：

- workflow modules；
- repositories；
- provider adapters；
- artifact services；
- application services；
- domain models；
- quality services；
- stage executors。

推荐拆分示例：

```text
workflow/
  engine.py
  decision_policy.py
  acceptance.py
  readiness.py
  recovery.py
  retry_budget.py
  stage_plan.py
```

```text
persistence/
  project_identity_repository.py
  content_state_repository.py
  result_version_repository.py
  workflow_execution_repository.py
  quality_issue_repository.py
  artifact_metadata_repository.py
  readiness_query_repository.py
  unit_of_work.py
```

---

## 7. Slice 集成

标准实现流程：

```text
1. Implement the slice.
2. Run the focused slice test.
3. Run Code Health Gate on the current diff.
4. Apply local safe refactors only.
5. Rerun the focused slice test.
6. Run full pytest if feasible.
7. Commit only when validation passes and commit is authorized.
```

Code Health Gate 在功能正确性建立后运行，因此 refactoring 有工作中的安全网。

不要用本 gate 扩大 slice。

---

## 8. Review Checklist

### Provider Adapter

检查：

* 无 database imports；
* 无 repository 或 Unit of Work access；
* 无 official artifact registration；
* 无 QualityIssue creation；
* 无 WorkflowDecision creation；
* 无 retry / fallback / skip / warning / block / readiness logic；
* 无 policy bypass 或 evasion behavior；
* secrets 永不持久化；
* outputs 结构化且已 sanitized。

### StageExecutor

检查：

* 在 SQLite write transactions 之外调用 provider；
* 只写入窄 tool evidence；
* 不更新 active pointers；
* 不决定最终 workflow outcome；
* 不创建 QualityIssues 或 WorkflowDecisions；
* 将 refusal / failure / invalid output 作为 evidence 处理；
* 只通过 ArtifactService promote temp files。

### ArtifactService

检查：

* 所有 official artifacts 都经由 ArtifactService；
* metadata 中的 paths 是 project-relative；
* path traversal 被阻止；
* original images 不可变；
* missing / hash-invalid detection 只报告 artifact state；
* 不做 workflow outcome decisions。

### QualityCheckService

检查：

* 除非明确授权，否则 repository-free；
* 分类 issues 但不推进 workflow state；
* 返回 issue drafts / reports；
* 不更新 active pointers；
* 不调用 providers；
* 不持久化 decisions。

### WorkflowLoopEngine

检查：

* 拥有 decisions 和 acceptance；
* 无直接 SQL / session / cursor usage；
* 不绕过 StageExecutor 调用 provider；
* 无 timestamp-based active selection；
* 无 `Page.status`-only recovery；
* 使用 profile snapshot policy；
* 在需要时记录 decisions 和 issue links；
* 使用 expected state 和 dependency hashes guard acceptance。

### Repository / Unit of Work

检查：

* 隐藏 SQLite details；
* 不泄漏 raw session / cursor / connection；
* 主要抽象不是 generic table-shaped repository；
* named operations 与 workflow needs 对齐；
* provider code 不能访问 persistence；
* write transactions 短；
* provider calls 位于 write transactions 之外；
* acceptance transaction 有 guard。

### Domain DTOs / Value Objects

检查：

* 无 database behavior；
* 无 filesystem side effects；
* 无 provider calls；
* 无 workflow decisions；
* 可行时 immutable；
* 名称反映 domain concepts；
* 不嵌入 large payloads。

### Tests

检查：

* 存在聚焦 integration test 覆盖 slice behavior；
* 相关时测试 architecture boundary failure；
* 断言 durable evidence；
* FakeProvider slices 的 tests 不依赖 real providers；
* tests 不要求 absolute local paths；
* scope 内覆盖 failure / refusal / invalid-output paths。

### File Size

检查：

* 任何超过 700 行的文件都有清晰理由；
* 任何超过 1000 行的文件有拆分计划或显式理由；
* 任何超过 2000 行的产品文件，除非升级处理，否则阻塞 merge。

---

## 9. Code Health Gate 期间允许的 Refactors

当变更局部且安全时允许：

* 抽取 private helpers；
* 按既有架构边界拆分文件；
* 重命名不清晰的 private functions、classes 或 variables；
* 用既有 contracts 替换直接 concrete dependencies；
* 为发现的 boundary smells 添加聚焦测试；
* 移除重复 local logic；
* 规范化 local error handling；
* 用既有 enums 或 constants 替换 magic strings；
* 通过 delegation 降低 message chains；
* 在不破坏已接受 public contract 时收窄 interface。

---

## 10. Code Health Gate 期间禁止的 Refactors

未经明确授权禁止：

* 新产品功能；
* 真实 provider integration；
* API / UI / frontend changes，除非 slice 允许；
* export output、ZIP、manifest 或 `ExportRecord`，除非 slice 允许 export；
* final design baseline changes；
* 大范围纯格式化重写；
* 大型 cross-slice refactors；
* 需要设计批准的 public contract changes；
* migration strategy changes；
* dependency upgrades；
* CI / toolchain expansion；
* slice scope 外的 cleanup scheduler 或 retention policy expansion。

---

## 11. 停止条件

遇到以下情况停止并报告：

* 存在 unrelated dirty working tree；
* 修复 smell 需要更广泛架构重设计；
* 当前 slice boundaries 不足；
* final design documents 看起来错误、缺失或互相矛盾；
* product behavior 会在 slice 外改变；
* validation 无法运行；
* 必需修复会触碰 forbidden files；
* code smell 暴露 unresolved design decision；
* 文件超过 2000 行且无法在当前 slice 内安全拆分。

停止的 Code Health Gate 应产出简短报告，说明 blocker 和 recommended next action。

---

## 12. 验证

局部 refactor 后的最小验证：

```bash
pytest <focused-slice-test>
```

可行时的推荐验证：

```bash
pytest <focused-slice-test>
pytest -q
```

只有在已经配置时才运行的可选检查：

```bash
ruff check .
mypy .
markdownlint docs/engineering/code-health-gate.md
```

除非另有独立任务授权，否则不要在 Code Health Gate pass 期间添加新工具。

---

## 13. Codex Review Prompt Pattern

在某个 slice implementation 通过其聚焦测试后使用。

```text
Goal:
Perform a Code Health Review Pass for the current implementation slice.

This is not a feature implementation task. Review the current slice diff for non-bug code smells and architecture boundary drift. Fix only local, safe issues within the current slice boundaries.

Source documents:
- AGENTS.md
- docs/SRS-v1.0.md
- docs/HLD.md
- docs/engineering/code-health-gate.md
- the exact slice document that was just implemented
- relevant final detailed designs for the touched modules

Scope:
Review only files changed in the current slice diff.

Check for:
- architecture boundary violations;
- responsibility drift;
- excessive coupling;
- low cohesion;
- information leakage;
- message chains;
- public mutable state;
- concrete implementation leakage;
- over-wide interfaces;
- provider/stage/artifact/quality/workflow/repository boundary drift;
- provider calls inside write transactions;
- timestamp-based active selection;
- Page.status-only recovery;
- large-file growth;
- tests that pass while hiding important boundary failures.

Allowed changes:
- local refactors inside files already changed by the slice;
- splitting a changed file along accepted architecture boundaries;
- focused test additions for discovered boundary smells;
- private helper extraction;
- private renaming;
- removing duplicated local logic.

Forbidden changes:
- new product features;
- real provider integration;
- API/UI/frontend changes unless the slice explicitly allowed them;
- export output, ZIP, manifest, or ExportRecord unless the slice explicitly allowed them;
- docs/design/**/final/**;
- broad formatting-only rewrites;
- cross-slice refactors;
- public contract changes without explicit authorization;
- dependency or toolchain changes.

Validation:
Run the focused slice test.
Then run pytest -q if feasible.

Stop conditions:
- unrelated dirty working tree exists;
- fixing the smell requires broader design work;
- required changes touch forbidden files;
- validation cannot run;
- current slice scope is insufficient;
- a product file exceeds 2000 lines and cannot be safely split in this pass.

Final report:
- files reviewed;
- smells found;
- smells fixed;
- smells deferred;
- validation commands and results;
- confirmation that no forbidden files changed;
- confirmation that no architecture boundary was violated;
- remaining risks.
```

---

## 14. 最终报告要求

每次 Code Health Gate pass 必须报告：

* files reviewed；
* smells found；
* smells fixed；
* smells deferred；
* tests or commands run；
* pass / fail result；
* validation skipped and reason，如有；
* forbidden files touched：yes / no；
* final design baselines changed：yes / no；
* architecture boundary violation remaining：yes / no；
* file size risks remaining。

validation 未运行时，不要声称成功。

---

## 15. Merge Rule

存在以下情况时，slice 不应 merge：

* 仍有任何 Category A smell；
* focused tests 失败；
* validation 未运行且没有清晰可接受原因；
* forbidden files 被修改；
* final design baselines 未经明确授权被修改；
* hand-written product code 超过 2000 行且未升级处理；
* implementation 超出 slice 范围。

slice 只有在满足以下条件时，才可带已记录的 Category C 或 D issues merge：

* issue 是 non-blocking；
* risk 已记录；
* next action 清晰；
* architecture boundaries 保持完整。
