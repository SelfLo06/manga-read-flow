# YOLO 开放词汇模型选择 Spike

这是研究性、只读输入的实验工具，不是正式 `DetectorProvider`。它不会访问 SQLite、创建项目/页面/TextBlock/WorkflowAttempt/QualityIssue，亦不会使用 ArtifactService 或修改 `src/manga_read_flow/**`。

当前门禁：`Preparation PASS`、`YOLOE Runtime Enablement PASS`；YOLO-World Runtime Enablement 待执行，prompt calibration 继续锁定。YOLOE-26N 与 YOLOE-11S 已在固定原版样本、`device=0`、`half=true`、`imgsz=640` 下完成真实 GPU 推理，结果均为合法 `empty_result`。

## 可提交与仅本地内容

提交脚本、测试、配置、schema 和匿名示例；只在 `data/local/yolo-model-selection/` 写 manifest、环境快照和 run 输出。所有真实图片、权重、hash、OCR 文本、overlay、mask、crop、日志和运行结果必须保持 Git ignored。

## 命令

```bash
pytest tests/unit/test_yolo_model_selection_spike.py -q

python tools/spikes/yolo_model_selection/environment_report.py \
  --models-config docs/spikes/detection-ocr/followups/yolo-open-vocabulary-model-selection/configs/models.yaml

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

YOLOE 仅在 `torch`、`ultralytics` 与 `clip` 已可用，且对应本地文本编码器通过大小与 SHA-256 校验时加载；`set_classes` 期间禁止自动安装依赖和下载资产。YOLO-World V2.1 仅在其 MMYOLO 依赖已可用且提供匹配模型配置后才能加载。依赖缺失时不安装任何包，而是保存 `dependency_missing`。两个模型体系使用独立 GPU 环境，不改动本项目依赖文件。

smoke 样本由 `configs/inference.yaml` 的 `smoke_sample` 固定为一张人工核验过的原版页面，并同时校验 `sample_id`、`required_version` 与 SHA-256。`configs/models.yaml` 是环境报告和 smoke 共用的唯一 registry 来源，权重与共享资产路径统一以仓库相对的 `weights_root: data/local` 为基准；YOLO-World 的 `config_path` 在匹配配置取得并核验前保持 `null`。

## 结果语义

`normalized/` 中 bbox 同时有原图 `bbox_xyxy` 和 `bbox_normalized_xyxy`。YOLOE 的真实预测 mask 才会被导出到 `masks/`；YOLO-World 只保存 bbox，绝不生成虚假 mask。可接受状态见 `schemas/normalized-result.schema.json`。
