"""W-V06 DeliveryCursor control handlers and authenticated IPC wiring."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile

import pytest
import pytest_asyncio

from contracts.envelope import EngineIPCEnvelope
from infrastructure.audio.delivery_control import DeliveryCursorControlRuntime
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.delivery_cursor_repository import SQLiteDeliveryCursorRepository
from infrastructure.ipc_framing import read_frame, write_frame
from infrastructure.ipc_server import LocalIPCServer


@pytest.fixture
def paths(tmp_path: Path):
    layout = DatabasePaths.for_world(tmp_path, "delivery-ipc-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def database(paths):
    db = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield db
    finally:
        await db.close()


def payload(**patch):
    value = {
        "schema_version": "1.0",
        "operation": "update",
        "track_id": "track-1",
        "consumer_id": "local-playback",
        "unit_id": "speech-1",
        "generation": 3,
        "source_offset_frames": 0,
        "total_source_frames": 100,
        "evidence": "queued",
        "stop_reason": None,
        "expected_cursor_revision": 0,
    }
    value.update(patch)
    return value


async def test_control_runtime_create_get_and_cas_conflict(database):
    runtime = DeliveryCursorControlRuntime(SQLiteDeliveryCursorRepository(database))
    created, error = await runtime.handle_update(payload())
    assert error is None
    assert created["cursor"]["cursor_revision"] == 1
    assert created["cursor"]["fully_output"] is False

    loaded, error = await runtime.handle_get(
        {
            "schema_version": "1.0",
            "operation": "get",
            "track_id": "track-1",
            "consumer_id": "local-playback",
        }
    )
    assert error is None
    assert loaded == created

    advanced, error = await runtime.handle_update(
        payload(
            source_offset_frames=100,
            evidence="rendered_estimate",
            stop_reason="completed",
            expected_cursor_revision=1,
        )
    )
    assert error is None
    assert advanced["cursor"]["cursor_revision"] == 2
    assert advanced["cursor"]["fully_output"] is False

    stale, error = await runtime.handle_update(
        payload(
            source_offset_frames=100,
            evidence="measured_loopback",
            expected_cursor_revision=1,
        )
    )
    assert stale is None
    assert error == "delivery_cursor_conflict"


async def test_control_runtime_create_is_fail_closed(database):
    runtime = DeliveryCursorControlRuntime(SQLiteDeliveryCursorRepository(database))

    value, error = await runtime.handle_update(
        payload(
            source_offset_frames=1,
            evidence="scheduled",
        )
    )
    assert value is None
    assert error == "delivery_cursor_create_requires_queued_start"

    value, error = await runtime.handle_update(
        {"schema_version": "1.0", "operation": "update", "__unknown": True}
    )
    assert value is None
    assert error == "schema_invalid"


def _request(method: str, body: dict, request_id: str) -> dict:
    return EngineIPCEnvelope(
        kind="request",
        protocol_version="1.0",
        request_id=request_id,
        trace_id="trace-delivery",
        method=method,
        payload=body,
    ).model_dump()


async def test_authenticated_ipc_advertises_and_executes_delivery_cursor_handlers(database):
    runtime = DeliveryCursorControlRuntime(SQLiteDeliveryCursorRepository(database))
    with tempfile.TemporaryDirectory(prefix="wom-delivery-ipc-") as directory:
        path = Path(directory).resolve() / "engine.sock"
        server = LocalIPCServer(
            path,
            "a" * 64,
            control_handlers=runtime.control_handlers(),
        )
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(path)
            await write_frame(
                writer,
                _request(
                    "system.handshake",
                    {
                        "app_version": "0.1.0",
                        "app_build": "test",
                        "supported_protocols": ["1.0"],
                        "session_token": "a" * 64,
                    },
                    "req-hello",
                ),
            )
            hello = await read_frame(reader)
            assert hello["status"] == "ok"
            assert {
                "voice.delivery.get",
                "voice.delivery.update",
            } <= set(hello["payload"]["capabilities"])

            await write_frame(
                writer,
                _request(
                    "voice.delivery.update",
                    payload(),
                    "req-create",
                ),
            )
            created = await read_frame(reader)
            assert created["status"] == "ok"
            assert created["payload"]["cursor"]["cursor_revision"] == 1

            await write_frame(
                writer,
                _request(
                    "voice.delivery.get",
                    {
                        "schema_version": "1.0",
                        "operation": "get",
                        "track_id": "track-1",
                        "consumer_id": "local-playback",
                    },
                    "req-get",
                ),
            )
            loaded = await read_frame(reader)
            assert loaded["status"] == "ok"
            assert loaded["payload"] == created["payload"]

            writer.close()
            await writer.wait_closed()
        finally:
            await server.close()


async def test_default_ipc_does_not_advertise_delivery_cursor(runtime_path=None):
    with tempfile.TemporaryDirectory(prefix="wom-delivery-default-") as directory:
        path = Path(directory).resolve() / "engine.sock"
        server = LocalIPCServer(path, "b" * 64)
        await server.start()
        try:
            assert "voice.delivery.get" not in server.capabilities
            assert "voice.delivery.update" not in server.capabilities
        finally:
            await server.close()
