# Text-Seeded Container Association — R0 Selection v0.3

状态：Identity / ROI / Semantic / Topology Frozen；Pixel Boundary GT Not Frozen
选择日期：2026-07-15

## 1. 选择依据

维护者完成本地 `r0-candidate-review-v0.2/FORM.md`：

- 六类均有唯一主候选；
- 六类语义判断均为高信心；
- 没有“全部不合格”；
- 明确选择“当前 18 个候选足够，进入最终双人盲标包”；
- 选择表 SHA-256：`5b42977f3cca004a56b248c5676e17dd3376950a41df2141b6f1e3d16316a501`。

该选择先冻结 source、ROI 和 crop identity。A/B 选择题及 coordinator 裁决现已进一步冻结语义与容器拓扑；Annotator A overlay 冻结为 coarse target-region reference，但不构成 pixel-accurate boundary GT。完整裁决见 `R0-ADJUDICATION-v0.3.md`。

## 2. R0 Identity Freeze

| R0 ID | Source SHA-256 / size | ROI `[x,y,w,h]` | Crop SHA-256 | 维护者选择语义 |
| --- | --- | --- | --- | --- |
| `R0-contact-different-containers` | `_017.jpg`；`c3a3c6e8d011188efdcfe0f2542ade758fdda97ad6a20a9ad8a04cb5f6abc001`；`1406×2000` | `[0,40,430,540]` | `32b8c519e1c9f4ec068a9d9cb583bb95c9871229f861c3504dfd7aba157b308c` | 两个或更多不同容器，轮廓接触/重叠。 |
| `R0-same-container-multicol` | `black2.webp`；`95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb`；`1280×1698` | `[800,300,440,620]` | `949b849cfb16c3cdce579df707bb0c579357f818b39d862854c34793b1d6de2e` | 一个完整容器内至少两个文字列/组。 |
| `R0-broken-or-occluded-boundary` | `104.jpg`；`1ed974cc21b03333d2c730f0d0868cae2a4f63f8b130f0feeaba5aeecbe2a286`；`1055×1500` | `[600,100,300,390]` | `5e2f805cbd9646b7c1ff6cce9de99713f51f9ee19386a2c6cb3d55798376c997` | 原图边界确有缺失、遮挡或越出页面。 |
| `R0-free-text` | `015.jpg`；`93602139ba2ea722eebd2d2749ccd7fdebd3eb401a90263e748f7b8a066b5d97`；`1055×1500` | `[820,0,225,420]` | `e198a9299364f1fa510e7870c87fba0c4544a31568a55b7af8e5e5de7f92d428` | 无容器文字，适合验证有限 support region。 |
| `R0-not-text` | `_033.jpg`；`3bb99e47c6094489609c4f55370094d43ed83a1c4ec4e50812d9b26237e32e2e`；`1406×2000` | `[620,0,560,430]` | `6c7586c79f5fae7ebca856df7c1a3fe441036900b91cd92fd02388fa25b6d3a4` | 确认不是文字或 SFX。 |
| `R0-textured-decorative-risk` | `01.png`；`dbe860385fb32bec685c2a00bdceee4742ee07ad200f41766bf6c172398eec5a`；`2263×1600` | `[0,0,2263,1200]` | `2a60917a5f62474e30df32ba08c20eb90dca11a0289c480c2e92b60db1bd7c19` | 标题/装饰文字；作为复杂背景高风险负例，而非普通对话气泡。 |

完整 source 路径只保存在 Git ignored 的 coordinator key 中，不写入可提交的选择记录。

## 3. 分散性与盲标

- 六个 R0 使用六张不同源图；
- 分布于四个作品/来源桶，达到候选门禁的最低 `>= 4`；
- 五张源图来自 `data/local`，一张来自既有 `local_samples/real`；
- final blind pack 使用固定 seed `20260715` 随机化 case 编号；
- 维护者已知候选类别，因此若担任 Annotator A，A 是半盲；Annotator B 必须独立且未查看候选表与 coordinator mapping。

本地盲标包：

```text
data/local/text-seeded-container-association/r0-final-blind-v0.3/
```

## 4. 当前门禁状态

| 门禁 | 状态 |
| --- | --- |
| R0 source / ROI / crop identity | `FROZEN` |
| Maintainer semantic selection | `RECORDED, NOT GT` |
| A/B independent semantic annotation | `COMPLETE` |
| Semantic labels / container topology | `FROZEN` |
| Coarse target-region references | `FROZEN_FROM_ANNOTATOR_A` |
| Pixel-accurate visible / virtual boundary GT | `NOT_FROZEN` |
| Inter-annotator boundary agreement | `UNAVAILABLE` |
| Free-text exact min/max support envelope | `NOT_FROZEN`; 仅允许 coarse / 宽容差 reference |
| GT uncertainty-band numerical value | `NOT_FROZEN` |
| S1 coverage audit | `FROZEN`; final blind run `20260715T075811Z-3e9711` 覆盖 `6/6`，见 `S1-INPUT-FREEZE-v0.1.md` |
| Boundary margin numerical freeze | `REOPENED` |
| Calibration/evaluation split | `REOPENED` |
| `P_same_container` numerical thresholds | `PENDING`; scorer 不存在 |

## 5. 风险与停止条件

- A/B 选择题分歧必须在裁决记录中保留理由，不得静默覆盖；
- Q3 的中央目标已按 A coarse target scope 裁为 broken/occluded；crop 中邻接的非目标局部内容仍是 ROI 风险，不得静默消失；
- Q6 只能验证装饰文字/复杂背景风险与 abstention，不得用于宣称对话气泡能力；
- 任一 crop hash 不一致即停止；
- R0 已允许进入 container association Spike；但 pixel-accurate boundary GT、严格 boundary F1 与 uncertainty-band 数值仍不得使用或宣称冻结。

## 6. 验证

- 选择表唯一勾选、语义和信心已人工读取；
- 六个选中 crop hash 与 candidate coordinator key 一致；
- case 编号已随机化，annotator 表单不含类别映射；
- A/B 选择题已独立完成；B 为 semantic/topology reviewer，没有 overlay；
- A overlay 只冻结为 coarse target-region reference；
- 未运行 Cleaning、association、Detection/Grouping extension 或 benchmark manifest；
- 未 commit / push。
