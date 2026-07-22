# 100 Import

Import 接收用户本地图片，验证文件类型与路径，把不可变原图复制到 Project workspace，并通过 ArtifactService 登记大小、SHA-256、媒体类型和来源。SQLite 不存图片 BLOB；任何后续阶段都不得覆盖原图。

当前 `ImportPageService`、ArtifactService 与 Project store 已形成后端正式路径，M0 已验证隔离、artifact 登记和恢复机制。仓库没有正式用户 API、CLI 或 Web 上传入口，也没有单页预览；因此 Import backend 为 `FORMAL_PATH_INTEGRATED`，但用户产品入口为 `NOT_IMPLEMENTED`，不能把后端 service 存在写成用户 Import 已完成。批量导入、ZIP 与资源预算仍属于 M3 后续。

拒绝直接处理任意外部路径或以文件名作为身份。风险包括 path traversal、伪造扩展名、重复导入和部分复制；验证覆盖允许/拒绝类型、同内容幂等、跨 Project 隔离、复制中断和原图 hash 不变。支持格式与上传限额尚待 API 设计冻结。
