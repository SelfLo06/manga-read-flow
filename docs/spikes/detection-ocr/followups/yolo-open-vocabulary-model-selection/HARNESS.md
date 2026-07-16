# YOLO 开放词汇漫画检测实验准备 — HARNESS

| # | 准备场景 | 通过证据 |
|---:|---|---|
| 1 | 检测真实图片版本目录 | manifest 只据作品内父目录的版本标记归为 `original`、`translated`、`cleaned`。 |
| 2 | 扫描支持格式 | 仅扫描 PNG、JPG、JPEG、WEBP。 |
| 3 | 稳定 sample ID | 相同相对路径和内容 hash 的 `sample_id` 恒定。 |
| 4 | 原图 hash | 每条记录具有 SHA-256。 |
| 5 | 原图只读 | 构建 manifest 不复制、不移动、不覆盖输入。 |
| 6 | 七个权重存在 | 环境快照包含七条 `weight_exists` 和大小。 |
| 7 | 权重 hash | 环境快照包含每个存在权重的 SHA-256。 |
| 8 | 环境快照 | 记录 OS、Python、PyTorch/CUDA、GPU、驱动、包版本和 Git 状态。 |
| 9 | 缺少依赖 | 生成 `dependency_missing` 规范化结果而不是崩溃。 |
| 10 | OOM | 生成 `oom`，不改 `imgsz`、不改 device、不重试降级。 |
| 11 | 原始与归一化结果 | 每个 smoke 模型在 `raw/` 和 `normalized/` 各有一份 JSON。 |
| 12 | overlay 坐标 | bbox 同时保存原图坐标与归一化坐标，并可反归一化。 |
| 13 | run 隔离 | 已存在 run_id 时抛出错误；新 run 不覆盖旧目录。 |
| 14 | 本地内容不进 Git | `git check-ignore` 覆盖模型、manifest、环境和 runs。 |

## 失败处理

`dependency_missing`、`model_load_failed`、`invalid_output`、`oom`、`runtime_error` 与 `empty_result` 都是可保存的结果状态。只有显式人工创建的新 run_id 才允许重跑；脚本不安装依赖、不使用 CPU fallback、不在 OOM 后降低输入尺寸。
