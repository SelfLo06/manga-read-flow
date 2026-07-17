# Real Bubble Fill Validation Follow-up — REPORT

## 1. Verdict

```text
FURTHER_SPIKE
```

4 张真实页上的受限 `AUTO_FILL` 未恢复。三层 mask 与像素级 safety gate 能阻止输出越过“标注的” allowed/protected 区域，但不能证明标注本身只覆盖真实气泡内部；且 200% 审查发现可辨认文字残留。独立 reviewer 进一步发现一个 allowed mask 延伸到手部/背景，因此本轮没有可自动接受的 A 类结果。

P0 决策：`restricted AUTO_FILL remains disabled`；A/B 一律 `REVIEW_REQUIRED`，D 保持 `SKIP`。

## 2. Scope / Environment

* 只使用 `black1.webp`、`black2.webp`、`gura.webp`、`gura_color.webp`；未使用 synthetic、inpaint、LaMa、VLM、网络、SQLite 或正式 artifact。
* Python 3.13.12，OpenCV 5.0.0，Pillow 12.2.0，NumPy 2.4.6；CPU-only。
* 验证：`pytest -q tests/unit/test_real_bubble_fill_followup.py` 为 11 passed；完整 `pytest -q` 为 147 passed。
* 初始分支/HEAD：`main` / `f39c0c24ca8198a99281aad424c87f87958ca599`；最终 freeze HEAD：`3088a9367cec5b80b073e46d711577b160e015fa`。

## 3. Fixture 与 Mask

| Fixture | Page | Class | Final policy | Final rating |
| --- | --- | --- | --- | --- |
| black2-top-right | black2 | A | REVIEW_REQUIRED | REVIEW |
| black2-middle-right | black2 | A | REVIEW_REQUIRED | UNUSABLE |
| black2-lower-left | black2 | A | REVIEW_REQUIRED | UNUSABLE |
| black1-bottom-right | black1 | A | REVIEW_REQUIRED | UNUSABLE |
| gura-top-dialogue | gura | A | REVIEW_REQUIRED | REVIEW |
| gura-color-small-center | gura_color | A | REVIEW_REQUIRED | UNUSABLE |
| gura-color-small-right | gura_color | A | REVIEW_REQUIRED | UNUSABLE |
| gura-color-lower-left | gura_color | A | REVIEW_REQUIRED | UNUSABLE |
| black1-top-right-sensitive | black1 | B | REVIEW_REQUIRED | REVIEW |
| gura-middle-right-sensitive | gura | B | REVIEW_REQUIRED | REVIEW |
| black1-music-note | black1 | D | SKIP | SKIP |
| gura-rec-overlay | gura | D | SKIP | SKIP |

分布为 8 A / 2 B / 2 D，四页均使用，单页不超过 4 个 fixture。每个 A/B 均有 glyph-level `text_mask`、`allowed_edit_mask`、`protected_mask`；D 仅有 `protected_mask` 与 skip reason。

最终 freeze：`FROZEN`，时间 `2026-07-13T08:12:40.312877+00:00`。

* fixture SHA-256：`531091919917c4b4a65ef92d4690c1da7fe92f1a0b2c206e8fa188cbcc080980`
* source set：`fb10688ca498ee88e56e4548cd8edc7fd922f90542f15dd5359b8c6d1641f4cc`
* text / allowed / protected：`381f91c139249b9b2123161a16a46dd612ed6944d7d4023a86406c8e2b5df0f2` / `faf6a92a3b29134d6f0ed32d9ceeb99f505761b891835c087042a00c2140ff97` / `8921ca73b4d4270024352ef2fb4b3768aec137dbb1129e66116409e33f2b297a`

页面选区图：

* `local_samples/cleaning/real_bubble_fill/previews/selection-{black1,black2,gura,gura_color}.png`

12 张 mask-review（均在 run 前生成；reviewer 事后否定了 `gura-color-small-right` 的语义有效性）：

* `.../mask-review/{black2-top-right,black2-middle-right,black2-lower-left,black1-bottom-right,black1-top-right-sensitive,black1-music-note,gura-top-dialogue,gura-middle-right-sensitive,gura-rec-overlay,gura-color-small-center,gura-color-small-right,gura-color-lower-left}.png`

## 4. Run 与安全结果

正式分析 run：`20260713T081323Z-c7993e`，目录：`local_samples/spike_outputs/cleaning-real-bubble-fill/20260713T081323Z-c7993e/`。

此前 `20260713T080533Z-416d32`、`20260713T081010Z-b1f6ed` 发现 glyph-mask undercoverage 后均保留，metadata 标记 `valid_for_verdict=false`，旧 mask 也归档在 `masks-history/`。

| Method | Candidates | Median | Max |
| --- | ---: | ---: | ---: |
| fixed_white | 20 | 2.324 ms | 2.493 ms |
| border_sampled_fill | 20 | 5.151 ms | 5.624 ms |

40 个 A/B candidate 记录并通过 source hash、输出尺寸、路径、`changed_outside_allowed_edit=0`、`changed_inside_protected=0` 检查；2 个 D 没有 normal candidate。注意：该像素级 PASS 只对人工 mask 的边界有效，不能替代气泡语义边界检查。

## 5. Ratings、失败与审查

每个方法/膨胀组合：0 ACCEPTABLE、4 REVIEW、6 UNUSABLE。A 类最终为 `0/8 ACCEPTABLE`。

failure taxonomy：`text_residue=24`、`anti_aliasing_residue=8`、`near_boundary=8`、`review_required=8`、`bubble_border_damage=4`。

只读 reviewer 复查 source、三层 overlay、raw candidate、difference 与 200% zoom 后要求采用更严格评级：

* `black2-top-right`、`gura-top-dialogue` 从可接受降为 REVIEW；前者有浅色字形残留，后者有浅色残留及细小轮廓侵入。
* `gura-color-small-right` 从可接受降为 UNUSABLE；allowed/text mask 涵盖气泡左侧手部/背景，输出产生白块。该发现说明当前 formal run 不能作为任何 AUTO_FILL 证据。
* 其余五个 A 类 UNUSABLE 与 200% 图中的可辨认文本残留一致；B 无 AUTO_FILL，D 无候选。

## 6. 图像交付物

所有 A/B comparison（均包含 source、三层 overlay、四种 candidate、difference、200% zoom、rating）：

* `.../comparisons/black2-top-right.png`
* `.../comparisons/black2-middle-right.png`
* `.../comparisons/black2-lower-left.png`
* `.../comparisons/black1-bottom-right.png`
* `.../comparisons/black1-top-right-sensitive.png`
* `.../comparisons/gura-top-dialogue.png`
* `.../comparisons/gura-middle-right-sensitive.png`
* `.../comparisons/gura-color-small-center.png`
* `.../comparisons/gura-color-small-right.png`
* `.../comparisons/gura-color-lower-left.png`

图集：

* `.../accepted-gallery/index.png`（最终无 accepted entry）
* `.../review-gallery/index.png`
* `.../rejected-gallery/index.png`

代表性 200% 成功候选（仅作为 review 对照，不是 P0 acceptance）：`comparisons/black2-top-right.png`、`comparisons/gura-top-dialogue.png`。代表性失败：`comparisons/black2-middle-right.png`、`comparisons/gura-color-lower-left.png`。

## 7. Harness 与下一步

| Gate | Actual | Result |
| --- | --- | --- |
| A ACCEPTABLE >=7/8 | 0/8 | FAIL |
| B 自动接受 | 0/2 | PASS |
| D normal candidates | 0/2 | PASS |
| source mutation | 0 | PASS |
| changed outside annotated allowed | 0 | PASS（但不足以证明语义安全） |
| changed inside annotated protected | 0 | PASS（但不足以证明语义安全） |
| severe damage accepted | 0 | PASS |

风险/限制：样本很少、mask 人工制作、当前 allowed mask 仍可能错误地覆盖非气泡结构；未验证自动 mask、更多漫画风格、Typesetting 后效果。建议下一步只做 `Mask Generation Follow-up`，先证明 semantic bubble interior / protected region 的标注或检测可靠，再重开 fill 验证。
