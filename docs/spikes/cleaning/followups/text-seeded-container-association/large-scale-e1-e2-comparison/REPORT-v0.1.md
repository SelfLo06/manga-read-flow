# 40 页 E1 与 E1+E2 激进清字对比实验报告 v0.1

状态：`COMPLETE_WITH_DIAGNOSTIC_FAILURES`

## 1. 正式裁决

```text
E2_AUTO_CLEANING:
NO_GO
原因：唯一 E2 候选残字明显；没有普通对白 E2 正例。

E1_LARGE_SCALE_EVIDENCE:
INCONCLUSIVE
原因：0 个 E1 context，0 像素实际写回。

ASSOCIATION_COVERAGE:
FAIL
原因：36/40 页 regionless；40 页只产生 2 个 context。

B1_BATCH_READINESS:
FAIL
原因：全页无界 priority-flood 可消耗约 14GB 并触发 OOM；缺少局部 ROI 与资源上限。
```

`DO_NOT_PROMOTE_E2` 仍是正确的总裁决，但证据边界必须写成：

```text
有效覆盖极低
+ 唯一 E2 候选失败
+ 没有普通对白 E2 正例
```

本实验不支持“所有普通对白 E2 必然无法自动处理”，也不支持“E1 清字无效”。

## 2. 实际样本量与可见质量

| 项目 | 结果 |
| --- | ---: |
| 输入页数 | 40 |
| `REGIONLESS_ABSTENTION` | 36（90%） |
| `COARSE_CONTAINER_SEARCH` | 3 |
| `BOUNDED_SUPPORT` | 1 |
| 最终 context | 2 |
| E1 context | 0 |
| E2 context | 1 |
| E3 context | 1 |

实际进入 mask 的只有：

| 页 | 路由 | 风险 | 结果 |
| --- | --- | --- | --- |
| `case-01` 封面 | bounded support | E3 | 两臂均跳过 |
| `case-40` 封底 | coarse container | E2 | E1 跳过；E1+E2 修改 2,188 像素 |

`case-40` 是封底版权文字，不是普通对白气泡。Telea radius=2 只清掉部分笔画，仍有
明显可读残字，人工质量失败。因此它只能否决当前候选的自动采纳，不能代表普通对白
E2 的总体质量。

E1 写回为 0，不是 fill 执行后失败，而是上游没有交付任何 E1 context。E1 在本次整书
实验中实际未被测试。

## 3. Association 覆盖率失败

### 3.1 原因分布

| 原因 | 页数 | 占 40 页 |
| --- | ---: | ---: |
| `extreme_seed_geometry` | 33 | 82.5% |
| `no_seed` | 2 | 5% |
| `oversized_fragment_seed` | 1 | 2.5% |
| `topology_uncertain` | 2 | 5% |

`topology_uncertain` 属于 3 个 coarse-search 页中的两个，不属于 36 个 regionless 页面。

### 3.2 已确认根因：crop 阈值被用于整页全局几何

`routed_association._input_geometry()` 对 `page.fragments` 中**全部 fragment**取一个联合
bbox，再用它除以整页宽高：

```text
x1/y1 = 全部 fragment 的最小坐标
x2/y2 = 全部 fragment 的最大坐标
seed_span_ratio = 联合 bbox 的最大边跨度 / 页面对应边
seed_bbox_area_ratio = 联合 bbox 面积 / 页面面积
```

随后 `run_routed_association()` 在任何局部分组、B1 或 container evidence 计算之前检查：

```text
span >= 0.85 OR area >= 0.65
→ 整页 REGIONLESS_ABSTENTION(extreme_seed_geometry)
```

这两个阈值只在 Goal 5 的 4 个 calibration crop 上冻结；当时每个输入只有 0–4 个
fragment、0–2 个 group，正式 evaluation 也只有 0–6 个 fragment、0–3 个 group。本书
内页通常有 6–112 个 fragment、4–19 个 group，多个普通对白组自然散布于全页各处。

对 33 个失败页复算：

| 触发方式 | 页数 |
| --- | ---: |
| span 与 area 同时超限 | 24 |
| 仅 span 超限 | 6 |
| 仅 area 超限 | 3 |

因此这不是偶发画风误差，而是已确认的计算粒度错配：用于单 crop/局部候选的极端几何
规则，被应用到了整页多 group 的联合几何上。

### 3.3 已确认根因：路由与 topology 是 page-global

当前 `RoutedResult` 对整页只允许一个 `route`。一旦全局 extreme gate 触发，页面中所有
正常 group 都与异常 group 一起丢失，没有 per-group 或 local-cluster 结果。

即使通过 extreme gate，coarse-search 的 `_topology()` 仍遍历整页所有 group pair；只要
任意一对为 uncertain，就将整页 `topology=uncertain`，并令
`goal6_trial_eligible=false`：

| 页 | group 数 | group-pair 数 | same | different | uncertain | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `case-26` | 9 | 36 | 1 | 34 | 1 | 整页不可进入 Goal 6 |
| `case-38` | 11 | 55 | 2 | 45 | 8 | 整页不可进入 Goal 6 |

这确认了“一个异常或不确定关系毒死整页”的第二条 page-global 联锁。另一个尚未在本书
触发、但代码中存在的全局门禁是：弱 container evidence 时只要全页 group 数大于 2，
也会整页 `too_many_groups_without_container`。

合理的后续粒度应是：

```text
Page
└── text group / local group cluster
    ├── false / oversized seed → 只跳过该局部 seed/group
    ├── free text              → 该局部 bounded support
    └── container-bearing      → 该局部 coarse search
```

## 4. B1 批处理稳定性失败

`case-10` 包含约占页面 12.7% 的单个 SFX/装饰 fragment。原始全页 B1 在该输入上消耗
约 14GB 内存并被 OOM 杀死；连续长进程还使 WSL 重启。

实现根因不是 Telea：

1. B1 为完整 `1406×2000` 页面创建 markers、gradient、owners、levels；
2. `_seeded_watershed()` 将 marker 像素逐个作为 Python tuple 压入 `heapq`；
3. 每次更低路径 relaxation 都可再次压入像素；
4. 没有 ROI、降采样、队列长度、工作内存或耗时上限；
5. coarse route 还可能在 topology 后再次运行全页 B1。

本实验新增的 10% oversized-seed guard 是必要的运行熔断器，但它把 `case-10` 整页
regionless，只保证实验继续运行，不是正确的语义修复。最终通过每 3 页一批、断点续跑
完成，也不能把 B1 视作批处理可用实现。

后续 B1 至少需要：逐 group/local ROI、ROI 最大尺寸、L1/coarse 分辨率、队列与内存
预算、单页/单 ROI 可恢复隔离，以及超限只跳过对应局部 seed。

## 5. 写回合同与 Cleaning 质量必须分开

两臂的 `changed_outside_effective = 0` 只证明 compositing 没有修改 `M_effective` 外的
像素。它不证明 mask 完整、语义对象正确、气泡结构安全或视觉质量可接受。

`case-40` 是直接反例：mask 外改动为 0，但残字明显，人工效果仍不可接受。

## 6. 性能

| 阶段 | 耗时 | 占已记录总耗时 |
| --- | ---: | ---: |
| Detection/Grouping | 280.68 s | 约 82.4% |
| Association + Mask | 59.74 s | 约 17.5% |
| E2 Telea 写回 | 0.214 s | 小于 0.1% |

已记录总耗时约 340.64 秒，即约 8.52 秒/页；不含调试、OOM 重启、断点重跑和 artifact
渲染的人工作业时间。

association 耗时高度集中：

| 页 | association 耗时 |
| --- | ---: |
| `case-26` | 14.47 s |
| `case-38` | 15.64 s |
| `case-40` | 17.11 s |

三页合计占 association 总耗时约 85.4%。多数 `extreme_seed_geometry` 页面在 B1 前快速
返回，只需约十几毫秒。因此当前瓶颈不是 inpaint，而是：共享上游耗时高、有效 context
覆盖接近于零，以及少数真正进入全页 B1 的页面计算成本无界。

继续优化 Telea、替换 inpaint 或重建器不会改善本次端到端有效性。

## 7. 已排除的误因

- 不是 OCR `no_seed` 普遍失败：只有 2 页无 seed；33 页有大量 fragment，但被全局几何
  门禁整页拦截。
- 不是 E1 fill 失败：没有 E1 context 到达 fill。
- 不是 E2 执行速度问题：唯一 E2 写回仅需 0.214 秒。
- 不是 mask 越界写回：两臂 `changed_outside_effective=0`。
- 不是 Pixel Mask 本身导致覆盖率崩塌：大多数页面在 mask 构建前已被 association 拒绝。

## 8. 下一步

先做一个独立的 `Association Coverage / Local Routing Correction` 诊断与修正目标，停止
继续扩大 E2 或替换清字后端。最小验证应使用本书冻结 S1 资产，比较 page-global router
与 group/local-cluster router：

1. 33 个 extreme 页是否能保留普通对白局部组；
2. 异常/SFX seed 是否只局部 abstain；
3. uncertain pair 是否只影响相关组件，而非整页；
4. 每个 local ROI 是否满足明确的像素、队列、内存和超时预算；
5. 在不产生跨容器泄漏的前提下，是否能显著增加 E1/E2 context。

只有 association 覆盖率先通过，E1 与普通对白 E2 的整书质量对照才真正有意义。

## 9. 证据产物

- `data/local/text-seeded-container-association/large-scale-e1-e2-comparison-v0.1/s1-timing.json`
- `data/local/text-seeded-container-association/large-scale-e1-e2-comparison-v0.1/candidates/matrix.json`
- `data/local/text-seeded-container-association/large-scale-e1-e2-comparison-v0.1/candidates/book-contact-sheet-e1-vs-e1-plus-e2.jpg`
- `data/local/text-seeded-container-association/large-scale-e1-e2-comparison-v0.1/candidates/case-40/e2-delta-crop-e1-left-e1-plus-e2-right.jpg`

本实验未修改原图，未生成 `AUTO_ACCEPT`，未接入 CleanerProvider/Workflow，未 commit
或 push。
