---
name: wom-data-steward
description: >-
  《诡秘世界》四库物理隔离与数据内核管家技能。指导 SQLite 多模型架构（canon.db, world.db, retrieval.db, runtime.db）、
  Transactional Outbox 异步事件、单写多读并发队列与 100% 幂等重建实现。
---

# 《诡秘世界》四库物理隔离与数据内核技能 (wom-data-steward)

本技能用于指导 `AGT-DATA` (Data Steward) 及其他专精角色在 `engine/infrastructure/` 下构建高并发、安全隔离的多模型 SQLite 数据内核。

---

## 1. 四库物理隔离模型 (Invariant 10 & 11)

| 数据库文件 | 性质 | 读写权限 | 职责与存储内容 | 恢复与重建策略 |
|:---|:---|:---|:---|:---|
| **`canon.db`** | 原著历史锚点 | **只读 (PRAGMA query_only = ON)** | 既定原著历史、序列魔药配方、非凡能力锚定数据 | 随安装包静态分发，严格不可修改 |
| **`world.db`** | 用户现实权威 | **强事务可读写 (WAL 模式)** | 用户世界线演进、角色身份特质、关系网、历史快照 | 核心权威事实源，定期创建备份 |
| **`retrieval.db`** | 检索与向量投影 | **异步可写** | FTS 全文索引、向量 Embeddings、关系图拓扑缓存 | **删除后 100% 幂等无损重建** |
| **`runtime.db`** | 运行时瞬态缓存 | **内存 / 临时持久** | UDS IPC 会话状态、TTS 指纹缓存索引、未完成任务 | 进程重启可完全丢弃清空 |

---

## 2. 核心持久化与并发管理模式

### 2.1 单写多读事务锁治理 (WAL Mode & Single-Writer)
SQLite 在多进程/多线程并发写时容易触发 `SQLITE_BUSY`。
必须贯彻以下连接配置准则：
```python
# 针对 world.db
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```
- **写入隔离**：所有对 `world.db` 的写操作必须由单线程异步队列（Actor / Outbox Manager）串行提交，杜绝写写竞争。
- **并发读取**：读取连接支持多连接并发开启，不阻塞写事务。
- **生产级参考实现**：参考 [`examples/sqlite_pool_pattern.py`](./examples/sqlite_pool_pattern.py)。
- **常见锁冲突排查**：参考 [`references/wal_troubleshooting.md`](./references/wal_troubleshooting.md)。

### 2.2 Transactional Outbox 异步投影模式
当 `OutcomeResolver` 产生 `StateDelta` 并写入 `world.db` 时：
1. 状态提交与 Outbox 记录在同一个本地 SQLite 事务中原子提交；
2. 后台 Worker 消费 Outbox 事件，异步生成 Embeddings 并写入 `retrieval.db`；
3. 即使 `retrieval.db` 写入延迟或崩溃，`world.db` 事实已永久确立（提交即命运）。

---

## 3. 验证与数据质量门禁

```bash
# 验证四库连接管理器与 Outbox 测试
uv run --directory engine pytest tests/ -k "database or outbox or sqlite"

# 执行架构适应度检查 (确认 domain 层未被 SQLite 驱动反向污染)
python3 scripts/check_architecture_fitness.py
```
