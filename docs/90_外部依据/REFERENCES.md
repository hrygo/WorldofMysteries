# External Technical References

> **状态**：设计基线技术依据  
> **截至**：2026-09-16

## Python Runtime

- Python 3.14.7  
  https://www.python.org/downloads/release/python-3147/
- Active Python Releases  
  https://www.python.org/getit/
- Python on macOS  
  https://docs.python.org/3/using/mac.html

工程 Runtime Profile 固定 CPython `3.14.7` standard GIL build。Python 3.14 是当前稳定 feature series；Python 3.15 尚为 pre-release。AgentScope 的 `requires-python` 为 `>=3.11`，实际完整依赖锁必须在 Packaging/AI Gate 中验证。

---

## SQLite

- SQLite Release History / 3.53.4  
  https://sqlite.org/changes.html

工程 Runtime Profile 固定 SQLite `3.53.4`，不依赖系统自带 SQLite。

### WAL / Multi-database atomicity
- SQLite — Write-Ahead Logging  
  https://www.sqlite.org/wal.html
- SQLite — ATTACH DATABASE  
  https://sqlite.org/lang_attach.html

基线使用方式：`world.db` 单文件承载 Domain 强事务；`retrieval.db` 通过 Transactional Outbox 更新，不假设 WAL 下多个数据库文件 crash-atomic。

### Durability
- SQLite — PRAGMA synchronous  
  https://www.sqlite.org/pragma.html

基线：权威 `world.db` 使用 WAL + `synchronous=FULL`；检索投影可采用较弱 durability profile。

### FTS
- SQLite — FTS5 Extension  
  https://www.sqlite.org/fts5.html

基线：实体短词使用 alias exact/prefix；中文自由文本使用 trigram FTS；语义召回由 VectorIndexProvider 补充。

### Vector
- SQLite — Vec1 Vector Extension  
  https://sqlite.org/vec1/doc/trunk/doc/vec1.md
- SQLite Forum — Vec1 version 0.7  
  https://sqlite.org/forum/info/a09b103d9d41ed25a357a42aa22ca32a93d4a5fb9b10eb40ab3e14cde508e8f1

当前事实基线：
- Vec1 当前为 0.7，尚未达到 1.0；
- 官方 Roadmap 明确标注 testing insufficient；
- ARM 可使用 NEON；
- 因此 Vec1 是本地 vector candidate，不是 Domain dependency。

产品基线采用 exact-first；ANN 启用前必须通过 recall/latency/rebuild/failure 测试。

### Schema / Integrity / Backup
- SQLite — STRICT Tables  
  https://www.sqlite.org/stricttables.html
- SQLite — Foreign Key Support  
  https://www.sqlite.org/foreignkeys.html
- SQLite — Online Backup API  
  https://sqlite.org/backup.html
- SQLite — PRAGMA integrity_check / foreign_key_check  
  https://www.sqlite.org/pragma.html

---

## AgentScope

- AgentScope GitHub  
  https://github.com/agentscope-ai/agentscope
- AgentScope NEWS  
  https://github.com/agentscope-ai/agentscope/blob/main/docs/NEWS.md
- AgentScope Documentation  
  https://doc.agentscope.io/
- AgentScope `pyproject.toml`  
  https://github.com/agentscope-ai/agentscope/blob/main/pyproject.toml

基线：
- AgentScope 当前 Python requirement 为 `>=3.11`；
- 工程 Runtime Profile 固定 Python `3.14.7` + AgentScope `2.0.8`；
- AgentScope 作为 AI execution framework；
- structured outputs、tools、bounded agent、middleware 可用；
- Pipeline 可用于 AI-side fixed logic；
- Realtime voice agent 不进入 MVP 正确性关键路径；
- exact package version 由 lockfile 固定。

---

## Apple macOS Process / Sandbox

- Apple — Enabling App Sandbox  
  https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html
- Apple — Process / NSTask  
  https://developer.apple.com/documentation/foundation/process
- Apple — XPC  
  https://developer.apple.com/documentation/xpc

基线：SwiftUI App 与 Local Engine 使用独立进程。使用 `Process/NSTask` 启动的 child process 继承父 App sandbox；嵌入式 helper 必须按 Apple sandbox/signing 要求配置。需要不同 sandbox entitlements 或更强 privilege separation 时使用 XPC service，不改变 Domain IPC Contract。用户动态授权文件的访问不能假定随静态 sandbox 权限自动继承，必须通过数据传递、bookmark 或独立授权机制处理。

---

## Technology Selection Notes

### Kùzu
- https://github.com/kuzudb/kuzu

仓库已归档/read-only，不作为长期基础依赖。

### pgvector
- https://github.com/pgvector/pgvector

保留为未来 Remote Engine / PostgreSQL cloud profile 的向量实现候选。

### DuckDB
- https://duckdb.org/docs/stable/connect/concurrency

用于分析型工作负载的候选，不作为本地 Domain transaction kernel。
