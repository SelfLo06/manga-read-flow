# 验证清单——整页清字台账 v0.1

每项均要求：输入与 durable facts 可查询；命名 Repository operation；owner；事务边界；decision/issue；pointer；recovery；artifact 或数值证据。Provider 与图像计算均在写事务外。

| # | 场景／输入 | 持久事实与操作 | 预期 decision／issue／pointer／recovery evidence |
|---:|---|---|---|
| 1 | case-71，6 segment | freeze inventory=6；`freeze_cleaning_inventory` | 每项均有 inventory id；未完成不得 accept |
| 2 | 71 g002/s01 | validated result + member + `CLEANED_PASS` | 实例 PASS；尚不更新 page pointer |
| 3 | 71 g002/s02 | correction 后新 revision result + member | `CLEANED_PASS`；旧 issue 保留 relation |
| 4 | 71 其余 g001/g003/g004/g005 无 ledger | 四条 `MISSING_REQUIRED_EVIDENCE` | blocking issues；pointer null/不变 |
| 5 | 71 补齐四项 | 6 unique dispositions + members | 可生成 official-but-unselected combined candidate |
| 6 | 71 页验证全过 | pass validation + no blockers | `accept_page_cleaning_atomically` 更新 pointer |
| 7 | 72 g002 unsafe=710 | inventory + unsafe metric/ref | `BLOCKED_UNSAFE_REQUIRED`，blocking |
| 8 | 72 g004 unsafe=70 | 同上 | `BLOCKED_UNSAFE_REQUIRED`，blocking |
| 9 | 72 g003 E3/review | reason/evidence + policy snapshot | `INCOMPLETE_REVIEW` 或阻塞的 `UNSUPPORTED_E3` |
| 10 | 72 g005/g007 无 ledger | 每项 inventory/disposition | `MISSING_REQUIRED_EVIDENCE`，不得静默遗漏 |
| 11 | 72 全部失败 | every inventory item one current disposition | page `blocked`，pointer 不变 |
| 12 | 同一 instance member 重复 | member-to-result unique query | `CONTRACT_INVALID` / duplicate issue |
| 13 | 少一个 segment disposition | inventory reconciliation | missing disposition issue，拒绝 acceptance |
| 14 | A 的 changed pixel 落入 B ownership | per-pair cross-write count/artifact | `BLOCKED_WRONG_INSTANCE_WRITE` |
| 15 | A/B actual changed mask 相交 | pair overlap count/artifact | `BLOCKED_INSTANCE_OVERLAP` |
| 16 | BubbleInstance revision 改变 | stale relation propagation | result/member/candidate/validation stale；pointer 清空 |
| 17 | unresolved blocking issue | issue relation query | acceptance predicate false；pointer 不变 |
| 18 | combined artifact hash mismatch | ArtifactService integrity fact | artifact issue；candidate not accepted；pointer 清空/不变 |
| 19 | 相同 correction idempotency key | `reserve_or_replay_correction` | 返回同一 ordinal=1 reservation/attempt |
| 20 | 同 chain 新 key | unique correction-chain rule | `reject_second_automatic_correction`；无 ordinal=2 |
| 21 | provider 成功、promotion 前崩溃 | attempt/tool evidence；无 official artifact | orphan 不提升；reservation 可 replay，不再扣预算 |
| 22 | promotion 后、acceptance 前崩溃 | official unselected artifact + run facts | recovery 重验/accept 或 block；pointer 不变 |
| 23 | acceptance UoW 失败 | SQLite rollback | 无部分 issue/decision/member/pointer/run terminal state |
| 24 | v2 old Project 打开 | v3 migration ledger | 原子 up；失败为 migration_failed，repositories 不暴露 |
| 25 | migration 中断/失败 | checksum + transaction rollback | workflow 不运行；不得伪造 run |
| 26 | 明确不支持 SFX | role/reason/source-preserved + profile | `UNSUPPORTED_SFX` 可见、非阻塞；无自动清字 |
| 27 | 普通对白缺证据 | target_class=ordinary_dialogue | blocking，不得降为 unsupported warning |
| 28 | candidate 已存在未验收 | candidate/member/validation refs | official-but-unselected；active pointer 不更新 |
| 29 | expected active pointer 冲突 | expected-state guard | abort/reload，不改任何 acceptance state |
| 30 | 任意 run | original artifact hash before/after | 原图 hash 不变；任何不符为 blocking |

## 通用验收

- `CLEANED_PASS` 必须同时绑定 validated instance result、accepted member、required/safe/protected/uncertainty/instance/visible-support evidence 和 fresh fingerprint。
- page validator 从同一 original deterministic composition 重算；要求 member union 等于 combined delta，并保留每 pair 的 overlap/wrong-instance 计数与 artifact。
- `unsupported` 只在 profile 明示的范围外、source preserved 且理由证据完整时非阻塞；普通对白/旁白不是该豁免。
- 所有 acceptance / block / stale 均由短 UoW 收口；任何外部调用、artifact promotion、composition、validator 计算均在事务外。
