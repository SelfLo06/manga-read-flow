# Goal 3 — R0 Container Association Validation Report v0.1

状态：`COMPLETE`

结论：`FURTHER_SPIKE`

## 1. Executive Summary

冻结的六例 R0 已完成一次 `B0/B1/P1` 轻量矩阵。结果证明了两件事：

1. 安全弃权有效：18/18 输出均为 `REVIEW_REQUIRED`，三种方法的 `false_low_risk_candidate_count` 都是 0；
2. 当前 P1 尚未证明优于简单 B1：P1 与 B0/B1 的 topology 都是 2/3，通过同样的 case-05 与 case-06、失败同样的 case-03；相对 Annotator A coarse reference，B1 在 case-05/06 更接近真实气泡，P1 则出现大面积背景传播。

因此本轮不进入 Pixel Text Mask Spike，也不进行 Cleaning preview。核心 `text seed → container/support association` 仍值得继续，因为 B1 已在 explicit/contact bubble 上显示有效局部关联，且 P1 能在接触容器上保持 different-container topology；但 P1 的 same-container calibration、有限 support 和传播停止条件需要独立修正，并使用新的 calibration 资产重新冻结，不能用本轮 R0 回调。

## 2. Frozen Inputs and Isolation

```text
R0 S1 run:             20260715T075811Z-3e9711
R0 results hash:       33f1061aac43e5b4ca4b86d66c8aec262d19eb33151a965aaf81e656d406da0a
R0 spec hash:          95d7d627eefb2b8d7c119364c6e362528848399e5b06a6de7f3c28a1bd7995e7
Goal 2 lock hash:      5ad91445bdf8bc29ba1ba3d4c48ac9f6f4838dd06601a3bc5a80310744e1f1cc
Harness hash:          bea1d1ee39200b44729936e05aee4f4ebfd0fa71eeec05212d2ec42d66364f11
R0 runner hash:        573d6333f765f2b87a65df98b808c368895fc887a1382f5c454ff287dc0d6e5d
Evaluator contract:    984ca71f1f1abe0a28fc09e222baad3e4d50c48329237c506b20d86f92dfb385
T_different / T_same:  0.40 / 0.75
```

算法 runner 的接口不接受 evaluator contract、Annotator A overlay、expected topology 或语义标签。`matrix.json` 明确记录：

```text
ground_truth_accessed        = false
parameter_updates_after_r0   = false
source_hashes_unchanged      = true
cleaning_performed           = false
```

Evaluator contract 在 R0 run 前冻结；A coarse reference 只在 run 完成后的 evaluator 阶段读取。Annotator B 没有 overlay，其选择题仍保留为语义/拓扑证据，不参与像素边界比较。

## 3. Run Artifacts

```text
matrix hash:           8884ab063fb5acdc7925a267f105fa6e6457f36bfe3553489e553473ad088bcb
evaluation hash:       5713132f03ffb34b8e9d7a9b668d4536200cb9939ec9bd9ee03b10234d096077
manual review hash:    6e89f81e451377db8c56d7e93a0c6cc7af53ab31b0cb6452d74108f54912f1da
evaluator runner hash: 80f8b53cdcd2a894c9335d6616e8cea169294c09c1398941c5361a2c2d4a49bf
```

本地输出：

```text
data/local/text-seeded-container-association/r0-final-blind-v0.3/goal3-runs/
  goal3-r0-v0.1/
    matrix.json
    results/*.json
    overlays/*.png
  goal3-evaluation-v0.1/
    evaluation.json
    MANUAL-COARSE-REVIEW.local.json
    contact-sheets/*.png
```

第一次执行被外层 10 分钟 timeout 终止，只完成 case-01 至 case-03，已保留为 `goal3-r0-v0.1.failed-timeout-attempt-1`，不计为有效 evaluation。第二次未改代码或参数，只延长外层 timeout；冻结计算约 19.6 分钟后完成全部结果，但 Windows/WSL 对非空目录的 `os.replace` 返回 WinError 145。正式目录实际已包含完整 18 个结果和 18 张 overlay；逐文件 hash 验证全部通过，残留复制目录另行保留。该问题是输出提交兼容性和性能限制，不改变算法结果。

## 4. Automated Metrics

| Method | Safety decision | Topology | Container type | False low-risk |
| --- | ---: | ---: | ---: | ---: |
| B0 | 6/6 | 2/3 | 0/6 | 0 |
| B1 | 6/6 | 2/3 | 0/6 | 0 |
| P1 | 6/6 | 2/3 | 2/6 | 0 |

解释：

- B0/B1 不实现 container type classifier，因此 type 为 `uncertain`，计为 unsupported 而非正确；
- P1 正确输出 case-03/06 的 `implicit_container`，但 case-03 topology 仍错误；
- P1 把 case-01 NOT_TEXT、case-02/04 free text 和 case-05 explicit container 都判为 `implicit_container`；
- 所有风险 case 均 abstain，没有错误进入 low-risk。

## 5. Case-by-Case Results

| Case | Frozen expectation | B0 | B1 | P1 | Assessment |
| --- | --- | --- | --- | --- | --- |
| case-01 | NOT_TEXT；0 container | 生成 false-seed bbox；review | 生成 false-seed basin；review | 生成更大的 implicit region；review | 安全但分类失败；P1 放大误 seed。 |
| case-02 | free text；有限 support | 有界但偏大 | 背景泄漏 | 几乎扩到全 ROI，且判为 implicit | P1 free-text support 失败。 |
| case-03 | 1 implicit container；两组 same | 两个 target region | 气泡内仍分两个 source basin | 将 ellipsis 与正文判 different，并生成内部 virtual boundary | 三种方法 topology 均失败；P1 错误更明确。 |
| case-04 | 2 个高风险 free-text support | 有界但偏大 | 大面积背景泄漏 | 大面积背景泄漏并保留 false seed region | abstain 正确，support 语义失败。 |
| case-05 | 1 explicit container；same | 一个 target bbox | basin 与 A coarse bubble 接近 | topology 正确，但 region 泄漏到右侧/下方背景，且判 implicit | B1 明显优于 P1。 |
| case-06 | 2 implicit/contact containers；different | 两个 bbox | 两个 basin 与 A coarse bubbles 接近 | topology 正确并有 virtual boundary，但把背景分成两大片 | B1 coarse region 优于 P1。 |

## 6. Decisions and Rationale

### 6.1 Gate decision

`FURTHER_SPIKE`，不是 `GO_TO_PIXEL_TEXT_MASK_SPIKE`：P1 未显示相对 B1 的安全或区域质量收益，且错误的同容器分割与大面积背景传播会使后续文字 Mask 的局部上下文不可信。

`FURTHER_SPIKE`，而不是 `NO_GO`：没有 false-low-risk；关键 contact-different 与 same-container-multicol topology 均保留；B1 在两例真实气泡上给出良好 coarse association，说明维护者提出的 text-seeded container association 方向仍有技术信号。当前失败集中在 P1 scorer calibration 与传播 envelope，而不是方向本身已被证伪。

### 6.2 Rejected interpretations

- 不因 18/18 abstain 而宣称成功：安全弃权只是必要条件，不代表 association region 可用；
- 不用 case-03/05/06 回调 `0.40/0.75`：R0 是 evaluation-only；
- 不把 B1 的视觉贴合宣称为像素级 accuracy：A overlay 仅是 coarse reference；
- 不因 P1 在 case-06 形成 virtual boundary 就忽略其大面积背景泄漏；
- 不进入 Pixel Text Mask 或 Cleaning 来“用后续结果证明”当前 region。

## 7. Required Follow-up Before Pixel Text Mask

下一轮若获授权，应是一个聚焦的 association correction Spike，而不是扩大完整 benchmark：

1. 新增与 R0 隔离的 cross-upstream-group same-container calibration 资产，覆盖 case-03 类“ellipsis/短列 + 正文”；
2. 对 free text 冻结有限 support envelope 机制，不能让 geodesic basin 充满 ROI；
3. 对 false/isolated seed 冻结 suppression 或明确 `SKIP/REVIEW_REQUIRED without region` contract；
4. 将 B1 作为强基线：P1 必须在同容器判断或接触边界上至少修正一例，同时不能恶化 B1 已贴合的 bubble scope；
5. 新版本只能用新的 calibration 资产冻结；本 R0 结果只改变 verdict，不参与调参。

满足上述 focused gate 后，才重新判断是否进入 Pixel Text Mask Spike。

## 8. Limitations and Open Questions

- R0 只有六例，结论是技术方向判断，不是泛化性能；
- A coarse reference 允许定性/宽容差判断，不支持严格边界指标；
- B 不提供 overlay，因此没有双人边界一致性；
- 自包含 SLIC 在 case-04 上耗时过高，只适合作为离线 Spike；
- 尚未验证 P2、S2/S3 或 R1；这些不是当前最小 Goal 3 的前置门禁；
- 仍未生成 pixel text mask、safe edit region 或 cleaned image。

## 9. Validation

验证覆盖 frozen input/hash、GT isolation、B0/B1/P1 output contract、RLE、topology evaluator、禁止严格像素指标、18 个 artifact hash、source immutability 和 contact-sheet review。测试命令与最终结果见 Gate 文档。

```text
32 passed in 7.25s
```
