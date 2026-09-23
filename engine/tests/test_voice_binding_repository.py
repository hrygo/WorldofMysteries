"""W-V04 VoiceBinding world.db persistence and CAS semantics."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

import pytest
import pytest_asyncio

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
from engine.infrastructure.voice_binding_repository import SQLiteVoiceBindingRepository


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "voice-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


async def open_database(paths):
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


@pytest_asyncio.fixture
async def database(paths):
    db = await open_database(paths)
    try:
        yield db
    finally:
        await db.close()


def scope():
    return VoiceBindingScope(
        owner_id="player",
        world_id="voice-world",
        worldline_id="line-1",
        presentation_identity="klein-visible",
        phase="default",
        locale="zh-CN",
    )


def provider(revision="voice-" + "a" * 40):
    return ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
        voice_revision=revision,
        model_catalog_revision="b" * 40,
    )


def candidate(binding_id="binding-1", revision="voice-" + "a" * 40):
    return VoiceBinding.reserve(
        binding_id=binding_id,
        scope=scope(),
        persona=VoicePersonaRevision("voice-klein", "persona-r1"),
        provider=provider(revision),
        world_revision=7,
    )


async def world_revision(database):
    return (await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    ))[0]["revision"]


async def test_reserve_activate_and_restart_do_not_advance_world_revision(database, paths):
    repo = SQLiteVoiceBindingRepository(database)
    reserved = await repo.reserve(candidate())
    assert reserved.status is VoiceBindingStatus.RESERVED
    assert await world_revision(database) == 0

    active = await repo.activate("binding-1", expected_binding_revision=1)
    assert active.status is VoiceBindingStatus.ACTIVE
    assert active.binding_revision == 2
    assert active.reserved_at_world_revision == 7
    assert await world_revision(database) == 0

    await database.close()
    reopened = await open_database(paths)
    try:
        restored = await SQLiteVoiceBindingRepository(reopened).load("binding-1")
        assert restored == active
        assert await world_revision(reopened) == 0
    finally:
        await reopened.close()


async def test_concurrent_first_reservation_has_one_stable_winner(database):
    repo = SQLiteVoiceBindingRepository(database)
    candidates = [
        candidate(f"binding-{index}", "voice-" + chr(97 + index) * 40)
        for index in range(8)
    ]
    results = await asyncio.gather(*(repo.reserve(item) for item in candidates))
    assert len({item.binding_id for item in results}) == 1
    rows = await database.read_world("SELECT count(*) AS n FROM voice_bindings")
    assert rows == [{"n": 1}]
    assert await world_revision(database) == 0


async def test_stale_cas_cannot_change_persisted_binding(database):
    repo = SQLiteVoiceBindingRepository(database)
    await repo.reserve(candidate())
    active = await repo.activate("binding-1", expected_binding_revision=1)

    with pytest.raises(VoiceBindingConflict):
        await repo.rebind(
            "binding-1",
            expected_binding_revision=1,
            persona=VoicePersonaRevision("voice-klein", "persona-r2"),
            provider=provider("voice-" + "d" * 40),
        )

    assert await repo.load("binding-1") == active
    assert await world_revision(database) == 0


async def test_rebind_then_revoke_preserves_history_fields_and_blocks_new_render(database):
    repo = SQLiteVoiceBindingRepository(database)
    await repo.reserve(candidate())
    await repo.activate("binding-1", expected_binding_revision=1)
    rebound = await repo.rebind(
        "binding-1",
        expected_binding_revision=2,
        persona=VoicePersonaRevision("voice-klein", "persona-r2"),
        provider=provider("voice-" + "d" * 40),
    )
    assert rebound.status is VoiceBindingStatus.RESERVED
    assert rebound.binding_revision == 3

    revoked = await repo.revoke("binding-1", expected_binding_revision=3)
    assert revoked.status is VoiceBindingStatus.REVOKED
    assert revoked.binding_revision == 4
    assert revoked.provider.voice_revision == "voice-" + "d" * 40
    assert not revoked.permits_new_render
    assert await world_revision(database) == 0


async def test_worldline_fork_freezes_exact_binding_revision_and_isolates_parent(database):
    repo = SQLiteVoiceBindingRepository(database)
    await repo.reserve(candidate())
    parent_at_fork = await repo.activate("binding-1", expected_binding_revision=1)

    child = await repo.fork_scope_snapshot(
        scope(),
        expected_source_binding_revision=2,
        target_worldline_id="line-2",
        target_binding_id="binding-line-2",
    )

    assert child.scope.worldline_id == "line-2"
    assert child.binding_revision == parent_at_fork.binding_revision == 2
    assert child.persona == parent_at_fork.persona
    assert child.provider == parent_at_fork.provider
    assert child.status is VoiceBindingStatus.ACTIVE

    rebound = await repo.rebind(
        "binding-1",
        expected_binding_revision=2,
        persona=VoicePersonaRevision("voice-klein", "persona-r2"),
        provider=provider("voice-" + "d" * 40),
    )
    parent_after_fork = await repo.activate(
        "binding-1", expected_binding_revision=rebound.binding_revision
    )

    assert parent_after_fork.binding_revision == 4
    assert parent_after_fork.provider.voice_revision == "voice-" + "d" * 40
    assert await repo.load("binding-line-2") == child
    assert child.provider.voice_revision == "voice-" + "a" * 40
    assert await world_revision(database) == 0


async def test_worldline_fork_snapshot_is_idempotent_and_rejects_conflict(database):
    repo = SQLiteVoiceBindingRepository(database)
    await repo.reserve(candidate())
    await repo.activate("binding-1", expected_binding_revision=1)

    first = await repo.fork_scope_snapshot(
        scope(),
        expected_source_binding_revision=2,
        target_worldline_id="line-2",
        target_binding_id="binding-line-2",
    )
    repeated = await repo.fork_scope_snapshot(
        scope(),
        expected_source_binding_revision=2,
        target_worldline_id="line-2",
        target_binding_id="binding-line-2",
    )
    assert repeated == first

    with pytest.raises(VoiceBindingConflict, match="different voice binding snapshot"):
        await repo.fork_scope_snapshot(
            scope(),
            target_worldline_id="line-2",
            target_binding_id="another-binding-line-2",
        )


async def test_worldline_fork_rejects_parent_revision_drift_before_snapshot(database):
    repo = SQLiteVoiceBindingRepository(database)
    await repo.reserve(candidate())
    fork_point = await repo.activate("binding-1", expected_binding_revision=1)
    assert fork_point.binding_revision == 2

    rebound = await repo.rebind(
        "binding-1",
        expected_binding_revision=fork_point.binding_revision,
        persona=VoicePersonaRevision("voice-klein", "persona-r2"),
        provider=provider("voice-" + "d" * 40),
    )
    await repo.activate(
        "binding-1", expected_binding_revision=rebound.binding_revision
    )

    with pytest.raises(
        VoiceBindingConflict, match="moved after fork snapshot authorization"
    ):
        await repo.fork_scope_snapshot(
            scope(),
            expected_source_binding_revision=fork_point.binding_revision,
            target_worldline_id="line-2",
            target_binding_id="binding-line-2",
        )

    child_scope = VoiceBindingScope(
        owner_id="player",
        world_id="voice-world",
        worldline_id="line-2",
        presentation_identity="klein-visible",
        phase="default",
        locale="zh-CN",
    )
    assert await repo.load_scope(child_scope) is None
    assert await world_revision(database) == 0
