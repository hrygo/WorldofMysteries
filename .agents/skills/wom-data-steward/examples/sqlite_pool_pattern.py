"""
sqlite_pool_pattern.py - SQLite 四库物理隔离与单写多读生产级参考实现样例

展示：
  1. 四库物理隔离连接工厂
  2. canon.db 强制只读 query_only = ON
  3. world.db WAL 模式与 busy_timeout
  4. 专用单写异步队列 (Single-Writer Queue)，彻底消除 SQLITE_BUSY
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, Callable, Coroutine


class DatabaseManager:
    """四库物理隔离数据库管理器"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.canon_path = self.data_dir / "canon.db"
        self.world_path = self.data_dir / "world.db"
        self.retrieval_path = self.data_dir / "retrieval.db"
        self.runtime_path = self.data_dir / "runtime.db"

        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._writer_task: asyncio.Task | None = None
        self._running = False

    def get_canon_connection(self) -> sqlite3.Connection:
        """只读获取 Canon 历史锚点连接"""
        conn = sqlite3.connect(f"file:{self.canon_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def get_world_read_connection(self) -> sqlite3.Connection:
        """并发只读获取 World 现实状态连接"""
        conn = sqlite3.connect(self.world_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA query_only = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    async def execute_world_write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        """通过单写队列串行提交 World 写事务，杜绝锁竞争"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        await self._write_queue.put((fn, fut))
        return await fut

    async def start(self):
        """启动后台单写消费 Worker"""
        self._running = True
        self._writer_task = asyncio.create_task(self._write_worker())

    async def stop(self):
        """优雅关闭"""
        self._running = False
        if self._writer_task:
            await self._write_queue.put(None)
            await self._writer_task

    async def _write_worker(self):
        """独占 world.db 写连接的单一事件循环"""
        conn = sqlite3.connect(self.world_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")

        while self._running:
            item = await self._write_queue.get()
            if item is None:
                break
            fn, fut = item
            try:
                with conn:
                    result = fn(conn)
                fut.set_result(result)
            except Exception as e:
                fut.set_exception(e)
            finally:
                self._write_queue.task_done()
        conn.close()
