# 工程规则

## 默认工作方式

普通任务只读 `AGENTS.md`、`000-30-current.md` 和一份直接相关的阶段 `NNN-00` 文档。架构、范围或跨阶段任务才按需读取产品、架构、Roadmap 与 Workflow 文档。保持最小变更，不做无关重构或依赖升级。

开始前检查 branch、HEAD 和工作区；结束前检查 diff。默认不 commit、push、pull、rebase、stash 或覆盖用户修改。临时 AI、IDE、日志、缓存和构建输出不进入 Git。

## 测试与验证

代码任务先识别测试，适合时先写测试。至少考虑正常、失败、边界、重启恢复、部分失败、幂等、Provider refusal、文件清理、软删除和导出阻断。无法运行的验证必须说明原因，不能虚构结果。路径重构还需检查 Markdown 链接、fixture/CLI 路径、`git diff --check` 与本地数据 ignore 状态。

## 文档与实验

当前事实只写入编号化文档。普通任务不创建独立任务目标、测试脚手架说明、执行计划、门禁表单、proposal、cross-review、code-health report 或长期 handoff。重要架构决策可在对应当前文档中保留“决策/理由/替代/风险/验证/开放问题”，需要长期独立追踪时再建立 ADR。

实验代码进入 `tools/experiments/<stage>/`，只保留可复用 runner/evaluator/config/helper；本地输入与结果进入 `data/local/`。单次运行报告只解释该 run，不充当算法规范、项目基线、Roadmap 或下一任务授权。

## 安全边界

不硬编码或记录 secrets；验证外部输入、限制上传类型并防止路径穿越。debug artifact 可能包含原图、OCR、译文和 Provider 响应，必须显式标记并按本地数据处理。受保护数据移动必须先复制、逐文件 hash 验证、更新引用、再验证后删除源副本。

## 拒绝的做法与验证场景

拒绝用删除测试掩盖产品失败、让 Provider 管理持久化、让 UI 直调工具、把历史运行报告继续当权威源，或为高风险任务自动扩张文档资产。工程规则通过小范围 diff、可解释测试结果、可追踪 artifact/attempt/decision 和可恢复的 Git 历史验证；具体阈值与部署方式仍由阶段设计决定。
