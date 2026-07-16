# Text-Seeded Container Association — R0 Candidate Expansion

版本：v0.3
状态：Maintainer Selection Complete / 已转入 R0 identity freeze
日期：2026-07-15

## 1. 决定

维护者明确撤回 v0.2 的实例冻结，理由是旧 R0 实际只使用 5 张源图，且 `data/local` 只贡献两张，覆盖不足。

维护者随后完成 18 候选选择表，六类均给出高信心主候选并批准进入 A/B 盲标。最终 identity/ROI 见 `R0-SELECTION-v0.3.md`；本文继续保留候选扩展过程与风险记录。

在维护者完成候选选择前：

- 旧六例全部降级为 historical anchor；
- 不存在 final R0 source、ROI 或语义 GT；
- boundary margin、S1 final run、calibration/evaluation split 与 `P_same_container` 网格均不得声称已冻结；
- 不开始 association、Cleaning、pixel mask、safe edit region 或 Workflow 实现。

## 2. 扩大筛选范围

只读盘点得到：

| 范围 | 数量 |
| --- | ---: |
| `data/local` 图片总数，包括派生图和运行产物 | 约 2,049 |
| 本地 manifest 中 enabled original | 10 部作品 / 555 页 |
| 第一轮等距视觉筛选 | 10 部作品 / 80 页 |
| 维护者选择问卷 | 6 类 × 3 项 = 18 ROI |
| 问卷涉及的不同源图 | 14 |
| 其中位于 `data/local` 的不同源图 | 11 |
| 问卷中的 `data/local` 作品 | 6 |

筛选只使用本地 manifest 的 `version == original && enabled == true`。cleaned、translated、无字版及 YOLO run output 不进入候选源图。

## 3. 当前候选问题

| Question | 目标类别 | 选择规则 |
| --- | --- | --- |
| Q1 | 相邻/接触但不同容器 | 必须确认不同容器；优先真实接触而非单纯距离近。 |
| Q2 | 同容器多文字列/组 | 必须包含完整容器和至少两个文字列/组。 |
| Q3 | broken/occluded/page-clipped boundary | 缺失必须来自原图，不得只是 ROI 人为裁断。 |
| Q4 | free text | 必须区分 free text、implicit container、SFX/标题。 |
| Q5 | not-text false seed | 确认不是文字/SFX，同时应具有合理误 seed 风险。 |
| Q6 | textured/transparent/complex risk | 风险必须来自真实背景或支持区域，而非普通白气泡。 |

本地填写包：

```text
data/local/text-seeded-container-association/r0-candidate-review-v0.2/
```

该目录包含真实图像 crop、路径与 hash，保持 Git ignored；不是 benchmark manifest。

## 4. 选择后的门禁

1. 每类必须有一个主候选；“全部不合格”触发该类继续筛选，而不是强制选择。
2. 主候选语义为低信心或 uncertain 时不得冻结。
3. 六个主候选若来自少于 4 部作品，必须检查备选或扩展候选。
4. 任一关键字符、容器或断裂点因 ROI 被人为裁断，候选失效。
5. source SHA-256 与 crop SHA-256 必须复算一致。
6. 通过后才生成最终 Annotator A/B 独立边界盲标包。

## 5. 理由与拒绝方案

选择“先候选问卷、后边界盲标”，因为在实例身份仍有争议时直接画精确 GT 会浪费标注并固化偏差。

拒绝：

- 继续沿用旧五张图；
- 从 2,049 张混合文件中直接随机抽样而不区分 original/cleaned/translated；
- 让维护者必须从三个候选中选一个；
- 先看 detector/scorer 输出再挑容易通过的样本；
- 将本地 crop 组织成正式 benchmark manifest。

## 6. 风险

- 80 页筛选仍不是完整阅读 555 页；稀有接触/破损边界可能遗漏；
- 当前 18 个 ROI 的 `data/local` 候选集中于 6 部作品，仍可能需要第二轮扩展；
- 某些 crop 在局部看似 broken boundary，但可能只是 ROI 截断；维护者选择题专门检查这一点；
- Q4/Q6 可能在 free text、implicit container 与 decorative overlay 之间产生语义分歧；低信心时必须继续找。

## 7. 验证与开放项

已验证：

- 本地 original manifest 的版本字段；
- 10 部作品、555 页计数；
- 18 个 ROI 均未越出 source 尺寸；
- 18 个 crop 和 14 个 source 的 SHA-256 已记录；
- crop 不包含算法叠加、旧 mask 或预期答案；
- 未生成 benchmark manifest，未运行 Cleaning 或 association。

开放项：

1. 维护者填写六题选择表；
2. 根据“全部不合格/低信心”决定是否继续扩大；
3. 对最终六例执行跨作品集中度检查；
4. 再生成 Annotator A/B 精确边界盲标包。
