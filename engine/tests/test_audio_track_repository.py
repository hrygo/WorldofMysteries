"""W-V08 immutable StoryBook audio track revision tests."""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_turn_commit import StoryTurnCommitService
from contracts import NarrativeBlock, StateDelta, StorySession, StoryState, TurnTransaction
from infrastructure.audio_take_store import (
    DryRenderRecipe,
    RenderOutcome,
    SQLiteAudioTakeStore,
)
from infrastructure.audio_track_repository import (
    AudioTrackKind,
    AudioTrackRevision,
    AudioTrackUnit,
    SQLiteAudioTrackRepository,
)
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.database_schema import StorageError
from infrastructure.narrative_block_repository import SQLiteNarrativeBlockRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-storybook")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    return database, paths


def initial_session() -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session-book",
            "revision": 0,
            "turn": 0,
            "phase": "discovery",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["npc-1"],
            },
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "listen",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-book",
            "world_id": "world-storybook",
            "worldline_id": "line-main",
            "protagonist_id": "player",
            "story_seed_id": "seed-book",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def delta() -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-book-1",
            "turn_id": "turn-book-1",
            "outcome": "clean_success",
            "story_delta": {},
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


def validated_turn(value: StateDelta) -> TurnTransaction:
    return TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn-book-1",
            "session_id": "session-book",
            "idempotency_key": "book.turn.1",
            "status": "validated",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "state_delta_id": value.id,
            "committed_story_revision": None,
            "narrative_block_id": None,
        }
    )


def narrative() -> NarrativeBlock:
    return NarrativeBlock.model_validate(
        {
            "schema_version": "1.0",
            "id": "narrative-book-1",
            "story_session_id": "session-book",
            "source_story_revision": 1,
            "scene_id": "scene-1",
            "segments": [
                {
                    "type": "character",
                    "speaker_id": "npc-1",
                    "text": "不要打开那扇门。",
                    "speech_intent": "warning",
                }
            ],
            "source_state_delta_id": "delta-book-1",
        }
    )


async def prepare_story(database: DatabaseManager) -> None:
    value = delta()
    committed = await StoryTurnCommitService(
        SQLiteStorySessionCommitPort(database)
    ).commit_validated(
        initial_session(),
        value,
        validated_turn(value),
        store_expected_revision=0,
        request_id="request.book.1",
        trace_id="trace.book.1",
    )
    await SQLiteNarrativeBlockRepository(database).publish(
        turn_id=committed.turn.id,
        narrative=narrative(),
    )


def recipe(*, speed: float = 1.0) -> DryRenderRecipe:
    return DryRenderRecipe.build(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision="b" * 40,
        voice_id="npc-approved",
        voice_revision="voice-" + "c" * 40,
        spoken_text="不要打开那扇门。",
        pronunciation_revision="pron-v1",
        backend_fields={"speed": speed},
    )


def outcome() -> RenderOutcome:
    return RenderOutcome(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision="b" * 40,
        voice_id="npc-approved",
        voice_revision="voice-" + "c" * 40,
        receipt_id="receipt-book",
    )


async def publish_take(database, paths, *, speed: float, pcm: bytes):
    store = SQLiteAudioTakeStore(
        database,
        paths.world.parent / "assets",
        manifest_hmac_key=b"k" * 32,
    )
    return await store.publish_pcm(recipe(speed=speed), outcome(), pcm)


def track(take_id: str, *, revision: int = 1, unit_id: str = "speech-original",
          supersedes: str | None = None) -> AudioTrackRevision:
    return AudioTrackRevision(
        track_id=f"track-book-r{revision}",
        track_family_id="track-family-book",
        story_session_id="session-book",
        revision=revision,
        kind=AudioTrackKind.ORIGINAL if revision == 1 else AudioTrackKind.REDUB,
        supersedes_track_id=supersedes,
        units=(
            AudioTrackUnit(
                ordinal=0,
                unit_id=unit_id,
                turn_id="turn-book-1",
                narrative_block_id="narrative-book-1",
                segment_index=0,
                story_revision=1,
                take_id=take_id,
            ),
        ),
    )


async def world_revision(database: DatabaseManager) -> int:
    return (
        await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        )
    )[0]["revision"]


async def test_original_track_is_durable_insert_only_and_pins_complete_take(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        await prepare_story(database)
        take = await publish_take(
            database, paths, speed=1.0, pcm=b"\x01\x00\x02\x00"
        )
        before = await world_revision(database)
        repo = SQLiteAudioTrackRepository(database)
        value = track(take.take_id)

        published = await repo.publish(value)
        assert not published.replayed
        assert await repo.load(value.track_id) == value
        assert await repo.latest(value.track_family_id) == value
        assert await repo.is_take_pinned(take.take_id)
        assert await repo.pinned_take_ids() == frozenset({take.take_id})
        assert await world_revision(database) == before

        replay = await repo.publish(value)
        assert replay.replayed
        assert await world_revision(database) == before
    finally:
        await database.close()


async def test_redub_creates_new_revision_and_cannot_overwrite_original_narrative(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        await prepare_story(database)
        first_take = await publish_take(
            database, paths, speed=1.0, pcm=b"\x01\x00\x02\x00"
        )
        second_take = await publish_take(
            database, paths, speed=0.9, pcm=b"\x03\x00\x04\x00"
        )
        repo = SQLiteAudioTrackRepository(database)
        original = track(first_take.take_id)
        await repo.publish(original)

        redub = track(
            second_take.take_id,
            revision=2,
            unit_id="speech-redub",
            supersedes=original.track_id,
        )
        await repo.publish(redub)

        assert await repo.load(original.track_id) == original
        assert await repo.latest(original.track_family_id) == redub
        assert await repo.pinned_take_ids() == frozenset(
            {first_take.take_id, second_take.take_id}
        )

        changed_story = AudioTrackRevision(
            track_id="track-book-r3",
            track_family_id=original.track_family_id,
            story_session_id=original.story_session_id,
            revision=3,
            kind=AudioTrackKind.REDUB,
            supersedes_track_id=redub.track_id,
            units=(
                AudioTrackUnit(
                    ordinal=0,
                    unit_id="speech-illegal",
                    turn_id="turn-book-1",
                    narrative_block_id="narrative-book-1",
                    segment_index=0,
                    story_revision=2,
                    take_id=second_take.take_id,
                ),
            ),
        )
        with pytest.raises(StorageError, match="narrative identity|committed turn"):
            await repo.publish(changed_story)
    finally:
        await database.close()


async def test_redub_must_extend_latest_revision_and_take_must_exist(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        await prepare_story(database)
        take = await publish_take(
            database, paths, speed=1.0, pcm=b"\x01\x00\x02\x00"
        )
        repo = SQLiteAudioTrackRepository(database)
        original = track(take.take_id)
        await repo.publish(original)

        with pytest.raises(StorageError, match="complete AudioTake"):
            await repo.publish(
                track(
                    "take-missing",
                    revision=2,
                    unit_id="speech-missing",
                    supersedes=original.track_id,
                )
            )

        with pytest.raises(StorageError, match="revision chain|latest revision"):
            await repo.publish(
                AudioTrackRevision(
                    track_id="track-book-r3",
                    track_family_id=original.track_family_id,
                    story_session_id=original.story_session_id,
                    revision=3,
                    kind=AudioTrackKind.REDUB,
                    supersedes_track_id=original.track_id,
                    units=original.units,
                )
            )
    finally:
        await database.close()


async def test_audio_asset_transaction_cannot_update_or_delete_tracks(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        await prepare_story(database)
        take = await publish_take(
            database, paths, speed=1.0, pcm=b"\x01\x00\x02\x00"
        )
        repo = SQLiteAudioTrackRepository(database)
        value = track(take.take_id)
        await repo.publish(value)

        with pytest.raises(sqlite3.DatabaseError):
            await database.audio_asset_write(
                lambda tx: tx.execute(
                    "UPDATE audio_tracks SET revision=99 WHERE track_id=?",
                    (value.track_id,),
                )
            )
        with pytest.raises(sqlite3.DatabaseError):
            await database.audio_asset_write(
                lambda tx: tx.execute(
                    "DELETE FROM audio_track_units WHERE track_id=?",
                    (value.track_id,),
                )
            )
        assert await repo.load(value.track_id) == value
    finally:
        await database.close()
