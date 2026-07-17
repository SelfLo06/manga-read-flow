# Typesetting Input Contract & Validator Grounding — HARNESS

## 临时 workflow

```text
Frozen Detection/Grouping
→ group 内段落保真拆分
→ MangaOCR
→ Page-level Translation
→ provenance ledger
→ bubble/typesetting-region candidate
→ validator 正反例
→ overlay 与人工审查
```

## ID 合同

每条 ledger 必须保存：

```text
asset_id
fragment_id
text_group_id
segment_id
ocr_result_id
translation_segment_id
container_id
cleaning_risk / cleaning_decision
typesetting_block_id 或 exclusion_reason
typesetting_region_id
```

一个 container 可以对应多个 segment。禁止用 container ID 代替 text group/segment ID。

## OCR 与 Translation

- OCR crop 来自冻结 fragment 的 union bbox，保留 crop hash。
- OCR 字符串允许错误，但不得为空后静默进入 Translation。
- Translation 使用真实 API、固定 `system-v1` prompt、temperature 0。
- 每页一次 Page-level 请求；无 previous context。
- 允许一次仅结构 repair；禁止人工补造译文。
- 保存 request hash、prompt hash、model、latency 和 token usage；不保存密钥或认证头。

## Region 合同

本轮 `typesetting_region` 是独立二值 artifact candidate。不得使用：

- Cleaning `safe` / `effective` mask；
- 从可视化 overlay 反推的 coarse region；
- TextBlock bbox 冒充真实气泡边界。

候选将清字页深色线稿膨胀为边界屏障，再以对应 group seed 选择封闭的浅色内部连通域。不得直接使用亮像素全页连通域，因为白色页面背景可能经抗锯齿缺口与多个气泡串联。候选必须输出 mask 与 overlay，只有人工确认后才能冻结为本 Goal 的 region reference。

## Validator

统一计算：

```text
overflow_pixels
overflow_ratio
minimum_inner_margin
boundary_touch
region_id
region_sha256
```

通过条件：`overflow_pixels == 0`、`minimum_inner_margin >= 2px`、`boundary_touch == false`。

每个页面至少验证：

- safe-inside 正例；
- deliberate-overflow 负例；
- deliberate-boundary-touch 负例；
- wrong-container 负例。

## 计时合同

使用单调 wall clock，记录毫秒：

| Stage | 说明 |
|---|---|
| detection | 冻结复用，耗时 0，标记 `reused` |
| grouping | 冻结复用，耗时 0，标记 `reused` |
| association | 冻结复用，耗时 0，标记 `reused` |
| cleaning | 冻结复用，耗时 0，标记 `reused` |
| input_load | 读取与哈希校验 |
| ocr_model_init | MangaOCR 初始化 |
| ocr | 两页全部 segment OCR |
| translation | 两次主请求及可能的 repair |
| provenance | ledger 构建与完整性验证 |
| region_construction | region mask candidate |
| validator | 正反例 |
| visualization | overlay/表单 |
| total | 本次临时 workflow 总 wall time |

失败或跳过也必须记录 `status`、`duration_ms` 和 reason。

允许从输入 hash 完全一致、上游阶段均为 `completed` 的失败 run 断点恢复。恢复时必须同时记录：

- `current_attempt_wall_time_ms`；
- 跨断点的 `cumulative_pipeline_time_ms` / `total_wall_time_ms`；
- 每个复用阶段的原始 `duration_ms` 与 `source_run`。

Provider 瞬时失败的失败尝试单独保留，不计入正式算法累计耗时。

## 停止条件

- API 配置/认证失败或密钥泄漏；
- OCR 模型无法加载；
- Translation 出现不可修复结构映射错误；
- 任一 fragment 无去向；
- region candidate 为空、跨越页面大范围或无法人工解释；
- validator 接受任一故意负例；
- 需要修改 `src/**` 或正式 Workflow。
