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

1. **提示词校准**：只有 manifest、环境快照、三族最小 smoke 结果均存在（允许 `dependency_missing`）且结果 schema 有效时开始。
2. **模型尺寸与分辨率矩阵**：只有确定提示词组、权重 hash 与设备参数已锁定时开始；不得自动降低分辨率或 CPU 回退。
3. **OCR crop 与清字-mask 评估**：只有前一轮选出有限候选模型后开始；YOLO-World 仅进入 bbox/OCR 召回比较，不能进入 mask 评分。
4. **报告与架构决策**：只有下游结果、资源证据、失败样本和许可证审查齐备时开始。

## 决策与理由

- 将实验留在 `tools/spikes/**` 和 `data/local/**`：符合 Provider Adapter、ArtifactService 与 SQLite 的架构边界，也避免研究输出污染正式生命周期。
- 用内容 SHA-256 加相对路径生成 `sample_id`：同一文件的身份可复现，并避免可提交文件泄漏绝对路径。
- 统一存储原图坐标 bbox 与归一化 bbox：overlay 可以无歧义回映射到原图；YOLO-World 不会获得伪造 mask。
- 所有 run 强制显式 `run_id` 且拒绝已有目录：失败结果可保留，重跑不能覆盖证据。

## 被拒绝的方案

- 将真实图片、环境快照或结果提交到 Git：会泄漏本地内容且破坏实验隔离。
- 将 YOLO-World bbox 栅格化为 mask：会把检测能力伪装成分割能力。
- 为完成 smoke test 自动安装依赖、回退 CPU 或 OOM 后缩小尺寸：会掩盖 8GB GPU 的真实可行性。
- 直接接入正式 DetectorProvider：会跨越本轮研究边界并提前固化不成熟选择。

## 风险与开放问题

- YOLO-World V2.1 checkpoint 还需要匹配的 MMYOLO 配置；本仓库未捆绑该配置。
- 当前环境的可选推理包可能缺失或二进制不兼容；这应作为结构化证据，而非由脚本修复。
- 三个版本目录位于每部作品下且存在名称差异；manifest 只据父目录中的无字/中文标记归为 `original`、`translated`、`cleaned`，不推断任何复杂语义 `tags`。
- 许可证、NSFW/内容策略和开放词汇提示词的实际效果均留待后续轮次确认。

## 验证场景

准备完成后应能验证：原图 hash 未变；模型 hash 可复算；缺依赖与 OOM 分别标准化；segmentation 可保存真实 mask；detection-only 不产生 mask；第二次同 run_id 被拒绝；不同 run 可并存；本地输出仍被 Git 忽略。
