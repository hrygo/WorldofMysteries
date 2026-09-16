# SQLite WAL 并发与锁故障排查决策树

在多任务并发读写时，如果出现 `sqlite3.OperationalError: database is locked`，按以下决策树排查：

```text
出现 database is locked
   │
   ├── 是否有长事务未关闭？
   │      └── 排查: 检查代码中是否有长时间运行的 `SELECT` 处于未 `fetchall()` 状态阻碍 checkpoint
   │
   ├── 是否有多处直接 open 开启写连接？
   │      └── 排查: 确认是否严格遵守 Invariant #11，必须且仅能通过 `execute_world_write()` 单写队列写入
   │
   ├── busy_timeout 是否生效？
   │      └── 检查: 执行 `PRAGMA busy_timeout;` 确认是否大于等于 5000ms
   │
   └── 是否跨越了不同文件系统挂载点？
          └── 检查: SQLite WAL 在部分 NFS/SMB 网络挂载上不可靠，macOS 本地 APFS 必须开启共享内存 (`-shm`)
```
