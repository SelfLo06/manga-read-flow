# R0 Blind Pack — Coordinator Case Key

> 仅供 coordinator。A/B 独立提交前，两名标注者不得打开本文。

版本：v0.1
生成日期：2026-07-15

## 派生规则

- 所有 crop 均由冻结 source SHA-256 与 ROI 确定性生成；
- ROI 格式为原图坐标 `[x, y, width, height]`；
- crop 没有 resize、rotate、算法叠加或人工标记；
- 输出时移除文件元数据；
- crop hash 用于确认标注者使用了未修改的底图。

## Case 映射与完整性

| Blind case | R0 ID | Source SHA-256 | ROI | Crop 尺寸 | Crop SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `case-01` | `R0-same-container-multicol` | `95434f5436059b3427dd817e49e071adf795b001c9774553a9608960128965bb` | `[800, 300, 440, 620]` | `440×620` | `30087ffc5c5baf840511d46ad02c55040d5cf78e0dea623b0de0586d0c70ce10` |
| `case-02` | `R0-not-text` | `a31442650c6f84d5f3f15bf4daf25a109ec968e4728ee73e10a075a7a3502444` | `[980, 80, 160, 140]` | `160×140` | `7aba47c7d96d989e168ebece900d29e20e2397627d029ca02ac0b45ba8ebb7c5` |
| `case-03` | `R0-free-text` | `318bec1ff1147645f48bec491d6e0e6811f8ee5d2610252bb36ce5757e5f8647` | `[100, 310, 190, 110]` | `190×110` | `466e023d42333e1d840980b27d33060408394385b24c9fb7b17d5337d1d74727` |
| `case-04` | `R0-contact-hard09` | `aa34d4743036c040348c68066bd07b38df4de32d04539bc2193c26ceb9c0c77c` | `[0, 1020, 300, 430]` | `300×430` | `682226a8c1dd2ce63855ab408290803b60aca8373acb9da8c7e2201c0ce777fd` |
| `case-05` | `R0-textured-risk` | `33c9ae0922a559f2a187e312e55ac90597c367f7c377371a50dadddd68652d69` | `[540, 410, 400, 260]` | `400×260` | `3a6c7d3b1538a6434279c272a0cdc61565711c86f44e818e8b8425409875c3d4` |
| `case-06` | `R0-broken-boundary` | `318bec1ff1147645f48bec491d6e0e6811f8ee5d2610252bb36ce5757e5f8647` | `[0, 700, 300, 436]` | `300×436` | `341d4f9374badd785028ac9ed497d9b63c04f53a13aa4286a8ab4302dbbd0e4d` |

## Source 路径

| Blind case | Source |
| --- | --- |
| `case-01` | `local_samples/real/black2.webp` |
| `case-02` | `data/local/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)/(C80) [蒼空市場 (蒼)] 東奔西走ブレイカー (東方Project)/_023.jpg` |
| `case-03` | `local_samples/real/gura.webp` |
| `case-04` | `data/local/(C78) [真珠貝 (武田弘光)] YUITAま (ToLOVEる -とらぶる-) [カラー化]/(C78) [真珠貝 (武田弘光)] YUITAま (ToLOVEる -とらぶる-) [カラー化]/yuitama_09.png` |
| `case-05` | `local_samples/generated/synthetic_04_complex_background_skip.webp` |
| `case-06` | `local_samples/real/gura.webp` |

本文只固定映射与输入完整性，不提供标注答案。语义裁决必须来自 A/B 独立标注及后续 adjudication。
