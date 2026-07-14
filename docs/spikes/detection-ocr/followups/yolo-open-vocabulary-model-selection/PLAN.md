# YOLO 开放词汇漫画检测实验准备 — PLAN

```text
Preparation
→ smoke test
→ prompt calibration
→ model-size and resolution matrix
→ OCR crop evaluation
→ cleaning-mask evaluation
→ report and architecture decision
```

本轮只实现 **Preparation** 和条件式 **smoke test**：

1. 核验本地目录、七个权重和 Git ignore；
2. 扫描三类作品内图片版本，生成仅本地保存的 manifest；
3. 固定模型、提示词和推理配置，记录环境与权重 hash；
4. 以配置中固定且核验过的 `original` 样本运行 YOLOE-26N、YOLOE-11S、YOLO-World V2.1 S；
5. 保存每族结构化结果、原始结果、归一化 bbox、真实 segmentation mask（若有）和 overlay；
6. 检查结果状态与输入未变，再决定是否进入下一阶段。

不在本轮执行提示词选择、完整矩阵、OCR 评分或清字 mask 评分。

## Runtime Enablement 后续切片

不得在项目 base 环境安装全部推理依赖。后续使用两个隔离 GPU 环境：

```text
完成四项准备修正
→ 创建 YOLOE 环境（torch / torchvision / ultralytics）
→ YOLOE-26N@640 真实 smoke
→ YOLOE-11S@640 真实 smoke
→ 创建 YOLO-World V2.1 环境（torch / mmengine / mmcv / mmdet / mmyolo）
→ 补齐并核验匹配 checkpoint 的 MMYOLO config
→ YOLO-World V2.1-S@640 真实 smoke
→ 三族结果均可解析且状态为 success 或 empty_result
→ 才进入 prompt calibration
```

在进入 cleaning-mask evaluation 前，另行建立本地 `pairing.local.json`；本轮不实现配对逻辑。

当前执行状态：

```text
Preparation Gate：PASS
YOLOE Runtime Enablement：PASS
  YOLOE-26N@640：empty_result
  YOLOE-11S@640：empty_result
YOLO-World Runtime Enablement：待执行
Prompt Calibration：继续锁定
```

YOLOE smoke 的 GPU 显存与耗时只作为链路诊断证据；`warmup_runs`、`timed_runs`、CUDA 同步、按模型重置峰值显存和真正框架 raw output 仍是 Prompt Calibration 前债务。
