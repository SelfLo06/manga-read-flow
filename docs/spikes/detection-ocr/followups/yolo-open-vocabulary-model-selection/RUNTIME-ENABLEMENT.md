# YOLO-World V2.1 Runtime Enablement

## 门禁结论

```text
Preparation Gate：PASS
YOLOE Runtime Enablement：PASS
YOLO-World Runtime Enablement：BLOCKED
Prompt Calibration Execution：LOCKED
Prompt Calibration Review：LOCKED
Model/Resolution Matrix：LOCKED
```

阻塞发生在 Phase A2“找到匹配配置”。因此未创建 `manga-yolo-world` 环境、未实现近似 runner、未执行 YOLO-World smoke，也未进入 Harness 硬化和提示词校准。

## 已固定的官方来源

- Repository：`https://github.com/AILab-CVC/YOLO-World.git`
- Repository commit：`4f70adbaacf5685bd9ec5bea85f1f91057f6fc0b`
- MMYOLO submodule commit：`4d97b3a06609dba94b8ec584be2f2029cfdb7519`
- 官方仓库没有 release tag；本地 vendor 以 detached HEAD 固定上述 commit，不以浮动 `master` 作为证据。
- 官方 README 将 YOLO-World V2.1-S、stage1、640 checkpoint 发布在 `wondervictor/YOLO-World-V2.1`；本地 checkpoint 与该 release asset 的大小和 SHA-256 一致。

本地 vendor source、checkpoint、checkpoint 内嵌配置和后续环境证据均位于 `data/local/**`，由 Git ignore 覆盖，不提交源码副本或本地运行产物。

## Checkpoint 证据

```text
checkpoint: models/yolo-world-v2.1/s_stage1-d1c1d7d8.pth
size: 305058846 bytes
sha256: d1c1d7d8611a3b97f74cf813faf911c2e047a6529622621943b4022c679ecce0

checkpoint-embedded config:
models/yolo-world-v2.1/configs/s_stage1-d1c1d7d8.checkpoint-embedded.py
size: 47675 bytes
sha256: e99e95a9ccd1f9a7555f1c77cf966dd79cba665e0550ad9c1aae232ae4ad9a6c
```

Checkpoint 的 `meta.cfg` 是当前最强的精确匹配证据，明确包含：

- `img_scale = (640, 640)`；
- YOLOv8-S 的 `deepen_factor = 0.33`、`widen_factor = 0.5`；
- stage1 的 100-epoch pre-training 配置和 CC-LiteV2/RAM++ 250k 数据定义；
- fixed-padding text path，包含 `padding_to_max=True`、80 个 runtime text slots 和 padding mask；
- `custom_imports = ['projects.YoloW.yolow']`；
- `YOLOWDetector`、`MMTransformer`、`HuggingCLIPLanguageBackboneV2`、`YOLOWv8PAFPN`、`YOLOWv8Head` 等精确 runtime 类型。

## 无法通过 A2 的原因

锁定的官方 repository commit、其两个公开分支以及完整 Git 历史中都不存在 `projects/YoloW/yolow` 或上述精确类型。当前仓库中最接近的可提交配置是：

```text
configs/pretrain/
yolo_world_v2_s_vlpan_bn_2e-3_100e_4x8gpus_obj365v1_goldg_train_lvis_minival.py
```

但它使用 `YOLOWorldDetector`、`MultiModalYOLOBackbone`、`HuggingCLIPLanguageBackbone`、`YOLOWorldPAFPN` 和 `YOLOWorldHead`，且没有 checkpoint 内嵌配置的 fixed-padding runtime 类型与 CC-LiteV2 pipeline。它只能视为相近配置，不能证明与 `s_stage1-d1c1d7d8.pth` 精确匹配。

官方 README 的 V2.1-S 640 model-card 行还错误链接到 `x_stage1-62b674ad.pth`，不能用该链接反向证明 S config。Checkpoint 自身的 SHA、尺寸和 `meta.cfg` 能确认权重身份，但不能补齐缺失的官方 runtime source。

## 决策与理由

- 不在 `models.yaml` 填入相近的顶层 S config：这会把未经证明的结构映射伪装成 source of truth。
- 不通过别名、宽松 `strict=False` 或忽略 missing/unexpected keys 强行加载：这违反“不得使用近似配置”和 checkpoint diagnostics 门禁。
- 不从非官方 fork 拼装缺失的 `projects.YoloW`：本轮来源预算只允许官方仓库。
- 不提前创建环境或继续 Phase B–E：即使依赖可安装，也不能解决 exact config/runtime source 缺失。

## 被拒绝的替代方案

- 直接使用顶层 `configs/pretrain/yolo_world_v2_s_*.py`；
- 从 checkpoint 类型名推测类名映射并修改 config；
- 以 `strict=False` 的低 missing-key 数量代替官方匹配证据；
- 下载替代 checkpoint；
- 切换到 Ultralytics YOLO-World 实现；
- CPU fallback 或降低 `imgsz`。

## 风险与开放问题

- 需要官方维护者提供 V2.1 stage1 checkpoint 对应的 `projects/YoloW` source/config commit，或明确给出到当前公开 config/runtime 的无损迁移映射。
- 在 exact source 未补齐前，无法可信验证 fixed padding label 是否被过滤，也无法生成 checkpoint load diagnostics。
- YOLO-World runtime gate 未通过，因此 180-job Prompt Calibration 不得执行。

## 已执行验证

- 当前分支与干净工作树检查；
- 基线单元测试：`23 passed`；
- 官方 repository 和 submodule commit 固定；
- checkpoint 与内嵌 config 的大小及 SHA-256 复算；
- 官方 source 两个分支和完整历史的类型/config 搜索；
- `data/local/vendor/**`、checkpoint config 和既有 run 继续被 Git ignore。

