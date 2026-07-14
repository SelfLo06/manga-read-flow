# YOLO 开放词汇模型选择 Spike

这是研究性、只读输入的实验工具，不是正式 `DetectorProvider`。它不会访问 SQLite、创建项目/页面/TextBlock/WorkflowAttempt/QualityIssue，亦不会使用 ArtifactService 或修改 `src/manga_read_flow/**`。

当前门禁为 `PASS_WITH_FIXES`：Preparation 与结构化失败 smoke 已完成；真实 GPU smoke inference 尚未完成，prompt calibration 尚未解锁。

## 可提交与仅本地内容

提交脚本、测试、配置、schema 和匿名示例；只在 `data/local/yolo-model-selection/` 写 manifest、环境快照和 run 输出。所有真实图片、权重、hash、OCR 文本、overlay、mask、crop、日志和运行结果必须保持 Git ignored。

## 命令

```bash
pytest tests/unit/test_yolo_model_selection_spike.py -q

python tools/spikes/yolo_model_selection/environment_report.py

python tools/spikes/yolo_model_selection/build_manifest.py \
  --root data/local \
  --output data/local/yolo-model-selection/manifest.local.json

python tools/spikes/yolo_model_selection/smoke_test.py \
  --run-id 20260714T000000Z-smoke
```

`run_id` 必须显式给出且此前未使用。输出为：

```text
data/local/yolo-model-selection/runs/{run_id}/
├── run-config.json
├── environment.json
├── raw/
├── normalized/
├── overlays/
├── masks/
├── crops/
├── logs/
└── summary.json
```

YOLOE 仅在 `torch` 与 `ultralytics` 已可用时加载；YOLO-World V2.1 仅在其 MMYOLO 依赖已可用且提供匹配模型配置后才能加载。依赖缺失时不安装任何包，而是保存 `dependency_missing`。建议在独立的 GPU conda/venv 环境中按所选 YOLOE 和 MMYOLO/YOLO-World 版本的官方兼容矩阵安装 PyTorch、CUDA、Ultralytics、MMEngine、MMDetection、MMCV 与 MMYOLO；不要改动本项目依赖文件。

smoke 样本由 `configs/inference.yaml` 的 `smoke_sample` 固定为一张人工核验过的原版页面，并同时校验 `sample_id`、`required_version` 与 SHA-256。`configs/models.yaml` 的权重路径统一以仓库相对的 `weights_root: data/local` 为基准；YOLO-World 的 `config_path` 在匹配配置取得并核验前保持 `null`。

## 结果语义

`normalized/` 中 bbox 同时有原图 `bbox_xyxy` 和 `bbox_normalized_xyxy`。YOLOE 的真实预测 mask 才会被导出到 `masks/`；YOLO-World 只保存 bbox，绝不生成虚假 mask。可接受状态见 `schemas/normalized-result.schema.json`。
