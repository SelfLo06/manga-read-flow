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
4. 以一个启用样本运行 YOLOE-26N、YOLOE-11S、YOLO-World V2.1 S；
5. 保存每族结构化结果、原始结果、归一化 bbox、真实 segmentation mask（若有）和 overlay；
6. 检查结果状态与输入未变，再决定是否进入下一阶段。

不在本轮执行提示词选择、完整矩阵、OCR 评分或清字 mask 评分。
