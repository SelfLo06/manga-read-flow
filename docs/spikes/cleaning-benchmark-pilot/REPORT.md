# Cleaning Benchmark Pilot v0.1 — 人工复核准备包

本轮只生成复核材料与自动候选；未生成 `benchmark-manifest.jsonl`。所有差异 mask 均为待审候选，不是 ground truth，也未自动通过人工 review。

## 结果

- unresolved review bundle：17/17
- 确定性页面选择：24（work-003=12，work-004=12）
- 清理区域候选：48
- 初始 eligibility：{'pending': 48}
- 选择 seed：20260714
- 输入树 SHA-256：运行前 `63d3fc6e68b62d93a786518fbf0e5a7005449f779d4619de5d6331d9c119239e`；运行后 `63d3fc6e68b62d93a786518fbf0e5a7005449f779d4619de5d6331d9c119239e`

## 决策与理由

- 仅 work-003 与 work-004；只使用三版本完整、两侧配对分数至少 0.78、两侧配准均为 high 的 Gold candidate 自动资格页，并排除 17 个 unresolved 路径。Gold candidate 仅是页面技术资格，不代表人工 Gold 标注。
- 用固定 seed 的双作品轮替选择，保持作品覆盖并使同一输入和配置产生相同页面顺序。
- 候选来自已配准 JP 与 textless 的像素差异，做闭运算、连通域与极小区域过滤；每页至多两个，以减少简单区域淹没复核集。
- `region-review.csv` 的 eligibility、mask_status、protected_structure_status 均保留 pending，复杂度与结论留空，等待人工复核。

## 已拒绝的替代方案

- 不将自动 difference mask 升格为 Oracle mask / ground truth。
- 不从 Dev 或 Frozen Test 取样，也不运行 detector、OCR、VLM、LaMa、翻译或外部 API。
- 不按视觉难度预筛掉候选；预览包保留每页的主候选与非主候选（若存在）。

## 风险、验证与待决问题

- 配准或编码差异仍可能产生非文字候选；protected overlay 只是结构风险提示，必须由人工判断。
- 若某页面经连通域过滤后没有候选，工具不会伪造候选；应在后续人工决策后调整配置或页面集。
- 待人工填写 `manual-review-resolution.csv` 与 `region-review.csv` 后，才可生成最终 benchmark manifest。
- 已验证输入 hash 在运行前后相同；候选与复核图只写入 Git 忽略的本地目录。
