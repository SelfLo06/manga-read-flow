# 150 Cleaning 实验工具

- `cleaning_benchmark_pilot/`、`dataset_audit/`：数据集与人工复核工具。
- `mvp1/`：当前全页/单页 Cleaning runner seam。
- `visual_contract/`：可复用的受限视觉合同 evaluator。
- `physical_boundary/`：当前 Stage A 诊断与只读 mark-generation trace。

运行结果进入 `data/local/runs/150-cleaning/`，人工复核进入 `data/local/reviews/150-cleaning/`。当前 physical-boundary arms 为 NO_GO，不能由这些脚本推导 Stage B 或 Cleaner 授权。
