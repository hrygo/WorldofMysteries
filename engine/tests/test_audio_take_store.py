"""W-V07 RenderKey/RenderManifest/AudioTake durable cache foundation."""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from infrastructure.audio_take_store import (
    DryRenderRecipe,
    RenderOutcome,
    SQLiteAudioTakeStore,
)
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.database_schema import StorageError
from infrastructure.sqlite_runtime import sqlite3


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-cache")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    return database, paths


def recipe(
    *,
    model_revision: str = "b" * 40,
    voice_revision: str = "voice-" + "a" * 40,
    pronunciation_revision: str = "pron-v1",
    backend_fields: dict[str, object] | None = None,
) -> DryRenderRecipe:
    return DryRenderRecipe.build(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision=model_revision,
        voice_id="klein-approved",
        voice_revision=voice_revision,
        spoken_text="克莱恩没有打开那扇门。",
        pronunciation_revision=pronunciation_revision,
        backend_fields=backend_fields or {"speed": 1.0},
    )


def outcome(
    *,
    model_revision: str = "b" * 40,
    voice_revision: str = "voice-" + "a" * 40,
) -> RenderOutcome:
    return RenderOutcome(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision=model_revision,
        voice_id="klein-approved",
        voice_revision=voice_revision,
        receipt_id="render-receipt-1",
    )


def pcm(seed: int = 1) -> bytes:
    return bytes([seed, 0, seed + 1, 0, seed + 2, 0, seed + 3, 0])


async def world_revision(database: DatabaseManager) -> int:
    return (
        await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        )
    )[0]["revision"]


def test_render_key_changes_for_exact_model_voice_pronunciation_and_native_backend():
    base = recipe()
    assert recipe(model_revision="c" * 40).render_key != base.render_key
    assert recipe(voice_revision="voice-" + "d" * 40).render_key != base.render_key
    assert recipe(pronunciation_revision="pron-v2").render_key != base.render_key
    assert recipe(backend_fields={"speed": 0.9}).render_key != base.render_key

    # Local playback volume/pause/scene FX are intentionally absent from the dry recipe.
    assert base.payload().keys() == {
        "schema_version",
        "kind",
        "provider_instance",
        "model_id",
        "model_revision",
        "voice_id",
        "voice_revision",
        "spoken_text_sha256",
        "pronunciation_revision",
        "backend_fingerprint",
        "format",
    }


async def test_publish_take_is_atomic_durable_authenticated_and_does_not_advance_world_revision(tmp_path):
    database, paths = await open_database(tmp_path)
    assets = paths.world.parent / "assets"
    key = b"k" * 32
    try:
        store = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=key,
        )
        published = await store.publish_pcm(recipe(), outcome(), pcm())

        assert not published.replayed
        assert await world_revision(database) == 0
        rows = await database.read_world("SELECT * FROM audio_takes")
        assert len(rows) == 1
        assert rows[0]["render_key"] == recipe().render_key
        assert rows[0]["status"] == "complete"
        assert (assets / published.relative_path).is_file()

        loaded = await store.load(recipe().render_key)
        assert loaded is not None
        assert loaded.file_sha256 == published.file_sha256
        assert loaded.manifest["resolved"]["voice_revision"] == outcome().voice_revision
        assert loaded.manifest["audio"]["sample_count"] == 4
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        store = SQLiteAudioTakeStore(
            reopened,
            assets,
            manifest_hmac_key=key,
        )
        loaded = await store.load(recipe().render_key)
        assert loaded is not None
        replay = await store.publish_pcm(recipe(), outcome(), pcm())
        assert replay.replayed
        assert (
            await reopened.read_world("SELECT count(*) AS n FROM audio_takes")
        )[0]["n"] == 1
        assert await world_revision(reopened) == 0
    finally:
        await reopened.close()


async def test_crash_after_asset_publish_leaves_detectable_orphan_without_phantom_complete_row(tmp_path):
    database, paths = await open_database(tmp_path)
    assets = paths.world.parent / "assets"

    def fault(stage: str):
        if stage == "after_asset_publish":
            raise RuntimeError("injected crash")

    try:
        store = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"o" * 32,
            fault_hook=fault,
        )
        with pytest.raises(RuntimeError, match="injected crash"):
            await store.publish_pcm(recipe(), outcome(), pcm())

        assert await database.read_world("SELECT * FROM audio_takes") == []
        orphans = await SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"o" * 32,
        ).orphan_relative_paths()
        assert len(orphans) == 1
        assert orphans[0].startswith("Takes/")
        assert await world_revision(database) == 0
    finally:
        await database.close()


async def test_wrong_manifest_key_and_corrupt_file_fail_closed(tmp_path):
    database, paths = await open_database(tmp_path)
    assets = paths.world.parent / "assets"
    try:
        good = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"a" * 32,
        )
        published = await good.publish_pcm(recipe(), outcome(), pcm())

        wrong = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"b" * 32,
        )
        with pytest.raises(StorageError, match="authentication"):
            await wrong.load(recipe().render_key)

        (assets / published.relative_path).write_bytes(b"\x00\x00")
        with pytest.raises(StorageError, match="metadata|digest"):
            await good.load(recipe().render_key)
    finally:
        await database.close()


async def test_same_render_key_cannot_be_rebound_to_different_audio(tmp_path):
    database, paths = await open_database(tmp_path)
    assets = paths.world.parent / "assets"
    try:
        store = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"c" * 32,
        )
        await store.publish_pcm(recipe(), outcome(), pcm(1))
        with pytest.raises(StorageError, match="already bound"):
            await store.publish_pcm(recipe(), outcome(), pcm(5))

        assert (
            await database.read_world("SELECT count(*) AS n FROM audio_takes")
        )[0]["n"] == 1
        assert len(await store.orphan_relative_paths()) == 1
    finally:
        await database.close()


async def test_resolved_backend_identity_mismatch_is_rejected_before_file_publication(tmp_path):
    database, paths = await open_database(tmp_path)
    assets = paths.world.parent / "assets"
    try:
        store = SQLiteAudioTakeStore(
            database,
            assets,
            manifest_hmac_key=b"d" * 32,
        )
        with pytest.raises(StorageError, match="does not match RenderKey"):
            await store.publish_pcm(
                recipe(),
                outcome(model_revision="e" * 40),
                pcm(),
            )
        assert await database.read_world("SELECT * FROM audio_takes") == []
        assert not assets.exists()
    finally:
        await database.close()


def test_manifest_hmac_key_is_mandatory_and_never_has_a_weak_default(tmp_path):
    with pytest.raises(StorageError, match="at least 32"):
        SQLiteAudioTakeStore(
            object(),  # type: ignore[arg-type]
            tmp_path / "assets",
            manifest_hmac_key=b"short",
        )
