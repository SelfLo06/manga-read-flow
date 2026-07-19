# 100 Import

Import 接收用户本地图片，验证文件类型与路径，把不可变原图复制到 Project workspace，并通过 ArtifactService 登记大小、SHA-256、媒体类型和来源。SQLite 不存图片 BLOB；任何后续阶段都不得覆盖原图。

当前已有 `import_page` 与 Project store 的后端基础，M0 已验证隔离、artifact 登记和恢复机制；正式上传 API/UI、批量导入、ZIP 与资源预算属于 M1/M3 后续。

拒绝直接处理任意外部路径或以文件名作为身份。风险包括 path traversal、伪造扩展名、重复导入和部分复制；验证覆盖允许/拒绝类型、同内容幂等、跨 Project 隔离、复制中断和原图 hash 不变。支持格式与上传限额尚待 API 设计冻结。
