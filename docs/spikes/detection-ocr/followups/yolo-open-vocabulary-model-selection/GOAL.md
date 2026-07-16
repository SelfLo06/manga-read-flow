# YOLO 开放词汇漫画检测实验准备 — GOAL

## 目标

本 Spike 只建立可重复、可审计且与正式业务代码隔离的实验条件，供以下模型比较：

- YOLOE-26 N / S / M：开放词汇检测与实例分割，作为 OCR 区域和清字 mask 候选；
- YOLOE-11 S / M：开放词汇检测与实例分割，作为稳定对比基线；
- YOLO-World V2.1 S / M：开放词汇检测，作为召回基线，不参与直接 mask 质量评分。

本 Spike 回答四个问题：

1. 三个模型家族的本地权重、输入样本、环境和结果是否可追溯地固定下来？
2. 在 RTX 4060 Laptop GPU（8GB）上，最小模型能否以 `device=0`、`half=true`、`imgsz=640` 被安全启动或明确记录阻塞原因？
3. 三种输出能否以同一 bbox 结果格式比较，同时只为真正的 segmentation 输出保存 mask？
4. 是否已具备进入提示词校准、模型/分辨率矩阵以及 OCR/清字下游评估的可信起点？

## 本轮范围

In scope：本地 manifest、七个权重的 hash、环境快照、可提交配置和 schema、统一结果格式、不可覆盖 run layout、条件式最小 smoke test。

Out of scope：完整提示词校准、40–60 页矩阵、OCR crop 指标、清字 mask 指标、正式 Provider Adapter、SQLite、ArtifactService、项目实体、正式 artifact、依赖安装或升级。

数据、权重和全部运行结果只位于 `data/local/**`，原图和权重只读；可提交示例不得包含真实路径或 hash。

## 后续阶段门禁

当前准确状态：

```text
Preparation：完成
结构化失败 smoke：完成
YOLOE GPU smoke inference：完成（YOLOE-26N 与 YOLOE-11S 均为 empty_result）
YOLO-World GPU smoke inference：BLOCKED（官方 checkpoint 的 exact config/runtime source 未公开匹配）
Prompt calibration：尚未解锁
```

`dependency_missing` 只能证明失败路径与结果保存机制有效，不能证明模型通过 smoke test。

1. **Preparation**：manifest、环境快照、权重核验、配置、schema 与结构化失败结果可以在 `dependency_missing` 下通过。
2. **提示词校准**：只有 YOLOE-26N、YOLOE-11S、YOLO-World V2.1-S 均完成真实 GPU 推理，且各自状态为 `success` 或 `empty_result` 时开始。若任何模型仍为 `dependency_missing`、`model_load_failed`、`runtime_error` 或 `oom`，必须显式缩减候选范围或继续修复，不得默认进入校准。
3. **模型尺寸与分辨率矩阵**：只有确定提示词组、权重 hash 与设备参数已锁定时开始；不得自动降低分辨率或 CPU 回退。
4. **OCR crop 与清字-mask 评估**：只有前一轮选出有限候选模型后开始；YOLO-World 仅进入 bbox/OCR 召回比较，不能进入 mask 评分。
5. **报告与架构决策**：只有下游结果、资源证据、失败样本和许可证审查齐备时开始。

## 决策与理由

- 将实验留在 `tools/spikes/**` 和 `data/local/**`：符合 Provider Adapter、ArtifactService 与 SQLite 的架构边界，也避免研究输出污染正式生命周期。
- 用内容 SHA-256 加相对路径生成 `sample_id`：同一文件的身份可复现，并避免可提交文件泄漏绝对路径。
- smoke 样本固定为 `sample_1308c0383ed99a66`（`original`，SHA-256 `b3dbd5a863d2ff8b4d54d26f1bdf7cc7be8a83bf0551e208dc4a08500b2e93b7`）：该页经人工核验，包含多个普通气泡、清晰竖排日文，背景不过度复杂；不会误选翻译版或无字版。
- 统一存储原图坐标 bbox 与归一化 bbox：overlay 可以无歧义回映射到原图；YOLO-World 不会获得伪造 mask。
- 所有 run 强制显式 `run_id` 且拒绝已有目录：失败结果可保留，重跑不能覆盖证据。
- `configs/models.yaml` 是七个模型与共享资产的唯一 registry 来源：环境报告与 smoke 共用同一加载、路径安全、存在性、大小和 SHA-256 校验 snapshot，不再维护代码内模型清单。
- YOLOE-26 与 YOLOE-11 分别固定并校验 `mobileclip2_b.ts` 与 `mobileclip_blt.ts`：调用 `set_classes` 时只允许解析已登记的本地资产，禁止 Ultralytics 自动下载或自动安装依赖。
- YOLOE runtime 固定在独立 `manga-yoloe` 环境：Python 3.11、Torch 2.9.1+cu126、Torchvision 0.24.1+cu126、Ultralytics 8.4.0；不修改项目依赖文件。

## 被拒绝的方案

- 将真实图片、环境快照或结果提交到 Git：会泄漏本地内容且破坏实验隔离。
- 将 YOLO-World bbox 栅格化为 mask：会把检测能力伪装成分割能力。
- 为完成 smoke test 自动安装依赖、回退 CPU 或 OOM 后缩小尺寸：会掩盖 8GB GPU 的真实可行性。
- 直接接入正式 DetectorProvider：会跨越本轮研究边界并提前固化不成熟选择。

## 风险与开放问题

- YOLO-World V2.1 checkpoint 还需要匹配的 MMYOLO 配置；本仓库未捆绑该配置。
- V2.1-S stage1 checkpoint 的 `meta.cfg` 依赖官方公开仓库及其历史中不存在的 `projects.YoloW.yolow` runtime；顶层相近 S config 的 detector、backbone、neck、head 和 fixed-padding path 均不同，不能作为精确配置强行加载。详见 `RUNTIME-ENABLEMENT.md`。
- 当前环境的可选推理包可能缺失或二进制不兼容；这应作为结构化证据，而非由脚本修复。
- 两个 YOLOE 最小模型在固定原版页面上均得到 `empty_result`；这证明 GPU 加载、推理、解析和空结果保存链路可用，但不证明当前 `text` 提示词具有漫画文字召回能力。计时仅作诊断证据，不作性能结论。
- 三个版本目录位于每部作品下且存在名称差异；manifest 只据父目录中的无字/中文标记归为 `original`、`translated`、`cleaned`，不推断任何复杂语义 `tags`。
- `original ↔ cleaned` 可在后续产生清字差异证据，但三类数量不一致，不能按排序配对。进入 cleaning-mask evaluation 前应另建仅本地的 `pairing.local.json`，依据作品、相对页路径、尺寸和人工抽查匹配；本轮不实现。
- 许可证、NSFW/内容策略和开放词汇提示词的实际效果均留待后续轮次确认。

## 验证场景

准备完成后应能验证：原图 hash 未变；模型 hash 可复算；缺依赖与 OOM 分别标准化；segmentation 可保存真实 mask；detection-only 不产生 mask；第二次同 run_id 被拒绝；不同 run 可并存；本地输出仍被 Git 忽略。
