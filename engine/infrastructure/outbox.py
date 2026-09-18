"""Recoverable event projection, isolated from authoritative Domain commits.

This first projection is an internal event index, not FTS/vector/graph search or
Context Compiler authorization. No model-facing query is exposed. A new/deleted
retrieval.db starts from the immutable journal, even when all outbox rows were
previously acknowledged.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import stat
from typing import Callable, Protocol

from .database_manager import DatabaseManager
from .database_schema import StorageError, connect, initialize


class TransactionalOutboxProtocol(Protocol):
    async def run_once(self, *, limit: int = 32) -> ProjectionResult: ...


@dataclass(frozen=True)
class ProjectionResult:
    indexed_revision: int
    observed_world_revision: int
    applied_events: int
    rebuilt: bool


class OutboxProjector:
    def __init__(self, database: DatabaseManager, *, fault_hook: Callable[[str], None] | None = None):
        self.database = database
        self._lock = asyncio.Lock()
        self._fault_hook = fault_hook

    async def run_once(self, *, limit: int = 32) -> ProjectionResult:
        if type(limit) is not int or not 1 <= limit <= 128:
            raise StorageError('Invalid projection batch limit')
        return await self._run(limit=limit, rebuild=False)

    async def rebuild(self) -> ProjectionResult:
        """Rebuild this event index from one authoritative snapshot; not all indexes."""
        return await self._run(limit=None, rebuild=True)

    async def _run(self, *, limit: int | None, rebuild: bool) -> ProjectionResult:
        async with self._lock:
            async def operation():
                result = await asyncio.to_thread(self._project, limit, rebuild)
                # Never acknowledge until the independent projection COMMIT is durable.
                if self._fault_hook:
                    self._fault_hook('before_acknowledge')
                await self.database.mark_projected(self.database.store_id, result.indexed_revision)
                return result
            task = asyncio.create_task(operation())
            cancelled = False
            while True:
                try:
                    result = await asyncio.shield(task)
                    break
                except asyncio.CancelledError:
                    cancelled = True
                    if task.done():
                        result = task.result()
                        break
            if cancelled:
                raise asyncio.CancelledError
            return result

    def _hit(self, stage: str):
        if self._fault_hook:
            self._fault_hook(stage)

    def _project(self, limit: int | None, rebuild: bool) -> ProjectionResult:
        path = self.database.paths.retrieval
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Different worker objects/processes must not race rebuild against draining.
        fd = os.open(Path(str(path)+'.projector.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise StorageError('Invalid projection lease')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StorageError('Another projection worker owns this index') from None
            return self._project_locked(path, limit, rebuild)
        finally:
            os.close(fd)  # Preserve inode for any waiting worker; never unlink lease.

    def _project_locked(self, path, limit, rebuild):
        with closing(connect(self.database.paths.world, readonly=True)) as source, closing(connect(path)) as target:
            initialize(target, 'retrieval')
            source.execute('BEGIN')
            world = source.execute('SELECT * FROM world_meta WHERE singleton=1').fetchone()
            if world['store_id'] != self.database.store_id:
                raise StorageError('Authoritative store identity changed')
            target.execute('BEGIN IMMEDIATE')
            try:
                metadata = target.execute('SELECT * FROM projection_meta WHERE singleton=1').fetchone()
                if metadata and metadata['store_id'] != world['store_id']:
                    raise StorageError('Projection belongs to another world')
                if metadata is None and target.execute('SELECT count(*) FROM projected_events').fetchone()[0]:
                    raise StorageError('Projection identity is missing from populated index')
                checkpoint = metadata['last_indexed_revision'] if metadata else 0
                if checkpoint > world['revision'] and not rebuild:
                    raise StorageError('Projection is ahead of authoritative history; rebuild required')
                if rebuild:
                    target.execute('DELETE FROM projected_events')
                    checkpoint = 0
                revisions = source.execute('SELECT revision FROM domain_commits WHERE revision>? ORDER BY revision LIMIT ?',
                                           (checkpoint, limit if limit is not None else -1))
                end = checkpoint
                # Verify ordered contiguous commit history instead of advancing to max().
                for row in revisions:
                    if row[0] != end + 1:
                        raise StorageError('Authoritative commit history has a gap')
                    end = row[0]
                if end > world['revision']:
                    raise StorageError('Journal exceeds authoritative world revision')
                if (limit is None or end - checkpoint < limit) and end != world['revision']:
                    raise StorageError('Authoritative commit history is incomplete')
                rows = source.execute('SELECT event_id,revision,worldline_id,world_time,aggregate_id,event_type,'
                                      'cause_id,episode_id,turn_id,payload_json FROM domain_events '
                                      'WHERE revision>? AND revision<=? ORDER BY revision,event_id', (checkpoint, end))
                count = 0
                for row in rows:
                    target.execute('INSERT INTO projected_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', tuple(row))
                    count += 1
                    self._hit('after_project_event')
                target.execute('INSERT INTO projection_meta VALUES (1, ?, ?) ON CONFLICT(singleton) '
                               'DO UPDATE SET last_indexed_revision=excluded.last_indexed_revision',
                               (world['store_id'], end))
                self._hit('before_projection_commit')
                target.execute('COMMIT')
            except BaseException:
                if target.in_transaction:
                    target.execute('ROLLBACK')
                raise
            self._hit('after_projection_commit')
            return ProjectionResult(end, world['revision'], count, rebuild)
