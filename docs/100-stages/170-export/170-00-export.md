# 170 Export

Export 只读取当前 active、非 stale 且 artifact hash 一致的 typeset/允许回退结果，生成单图或后续 ZIP/manifest；不得覆盖项目原始素材。ExportCheck 汇总 blocker、warning、skip 和来源版本，决定 readiness 证据，最终流程决定仍由 WorkflowLoopEngine 承担。

M0 已验证 readiness 与阻断机制；M1 的单图导出和 Web 操作入口尚未完成，ZIP/整章 manifest 属于 M3。

拒绝直接导出最新文件、忽略 stale 依赖或把 blocked 页面静默排除。warning 是否可导出必须读取该次运行的版本化 ProcessingProfileSnapshot；M1 的具体策略值仍待冻结。风险是 active pointer 与文件不一致、部分失败遗漏、输出路径 traversal 和用户导出被清理。验证覆盖 ready、warning、blocked、stale、缺失 artifact、重复导出、软删除和用户 export 保留。
