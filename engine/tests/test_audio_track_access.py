"""W-V08 StoryBook authorization snapshot tests."""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_turn_commit import StoryTurnCommitService
from contracts import NarrativeBlock, StateDelta, StorySession, StoryState, TurnTransaction
from infrastructure.audio_take_store import DryRenderRecipe, RenderOutcome, SQLiteAudioTakeStore
from infrastructure.audio_track_access import StoryBookAudioAccessService, VoiceAuthorizationSnapshot
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
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-access")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version)
    return database, paths


def session() -> StorySession:
    state = StoryState.model_validate({
        "schema_version":"1.0","story_session_id":"session-access","revision":0,"turn":0,
        "phase":"discovery","scene":{"id":"scene-1","location_id":"room-1","active_character_ids":["npc-1"]},
        "world_time":"1349-06-12T21:45:00","protagonist_goal":"listen",
        "active_conflicts":[],"discovered_clue_ids":[],"secret_states":{},
        "commitments":{"hard_ids":[],"soft_ids":[]},"local_state":{},"pressure":{},
        "last_state_delta_id":None,
    })
    return StorySession.model_validate({
        "schema_version":"1.0","id":"session-access","world_id":"world-access",
        "worldline_id":"line-main","protagonist_id":"player","story_seed_id":"seed",
        "base_revisions":{"world":0,"character":0,"story":0},
        "story_state":state.model_dump(mode="json",exclude_none=True),"status":"active",
    })


async def prepare(database):
    value=StateDelta.model_validate({
        "schema_version":"1.0","id":"delta-1","turn_id":"turn-1","outcome":"clean_success",
        "story_delta":{},"character_deltas":[],"world_event_candidates":[],"evidence_ids":[],
    })
    turn=TurnTransaction.model_validate({
        "schema_version":"1.0","id":"turn-1","session_id":"session-access",
        "idempotency_key":"access.1","status":"validated",
        "base_revisions":{"world":0,"character":0,"story":0},
        "state_delta_id":"delta-1","committed_story_revision":None,"narrative_block_id":None,
    })
    committed=await StoryTurnCommitService(SQLiteStorySessionCommitPort(database)).commit_validated(
        session(),value,turn,store_expected_revision=0,request_id="req",trace_id="trace"
    )
    narrative=NarrativeBlock.model_validate({
        "schema_version":"1.0","id":"narrative-1","story_session_id":"session-access",
        "source_story_revision":1,"scene_id":"scene-1",
        "segments":[{"type":"character","speaker_id":"npc-1","text":"不要开门。","speech_intent":"warning"}],
        "source_state_delta_id":"delta-1",
    })
    await SQLiteNarrativeBlockRepository(database).publish(turn_id=committed.turn.id,narrative=narrative)


def recipe(speed=1.0):
    return DryRenderRecipe.build(
        provider_instance="speechrail-local",model_id="qwen3-tts-base",
        model_revision="b"*40,voice_id="npc-approved",voice_revision="voice-"+"c"*40,
        spoken_text="不要开门。",pronunciation_revision="pron-v1",backend_fields={"speed":speed},
    )


def outcome():
    return RenderOutcome(
        provider_instance="speechrail-local",model_id="qwen3-tts-base",
        model_revision="b"*40,voice_id="npc-approved",voice_revision="voice-"+"c"*40,
        receipt_id="receipt-access",
    )


def track(take_id, *, revision=1, supersedes=None):
    return AudioTrackRevision(
        track_id=f"track-r{revision}",track_family_id="family",story_session_id="session-access",
        revision=revision,kind=AudioTrackKind.ORIGINAL if revision==1 else AudioTrackKind.REDUB,
        supersedes_track_id=supersedes,
        units=(AudioTrackUnit(
            ordinal=0,unit_id=f"speech-r{revision}",turn_id="turn-1",
            narrative_block_id="narrative-1",segment_index=0,story_revision=1,take_id=take_id,
        ),),
    )


def allowed():
    return VoiceAuthorizationSnapshot(
        policy_revision="policy-2",
        authorized_voice_revisions=frozenset({
            ("speechrail-local","npc-approved","voice-"+"c"*40)
        }),
    )


def revoked():
    return VoiceAuthorizationSnapshot(
        policy_revision="policy-3",
        authorized_voice_revisions=frozenset({
            ("speechrail-local","another-voice","voice-"+"d"*40)
        }),
    )


async def test_historical_replay_requires_fresh_authorization_but_keeps_history(tmp_path):
    database,paths=await open_database(tmp_path)
    try:
        await prepare(database)
        store=SQLiteAudioTakeStore(database,paths.world.parent/"assets",manifest_hmac_key=b"k"*32)
        take=await store.publish_pcm(recipe(),outcome(),b"\x01\x00\x02\x00")
        repo=SQLiteAudioTrackRepository(database)
        original=track(take.take_id)
        await repo.publish(original)
        service=StoryBookAudioAccessService(repo,store)

        replay=await service.resolve_for_replay(original.track_id,allowed())
        assert replay.policy_revision=="policy-2"
        assert replay.replay.units[0].take.take_id==take.take_id

        with pytest.raises(StorageError,match="not currently authorized"):
            await service.resolve_for_replay(original.track_id,revoked())

        assert await repo.load(original.track_id)==original
        assert await store.load_take(take.take_id) is not None
    finally:
        await database.close()


async def test_revoked_voice_cannot_be_published_into_new_redub(tmp_path):
    database,paths=await open_database(tmp_path)
    try:
        await prepare(database)
        store=SQLiteAudioTakeStore(database,paths.world.parent/"assets",manifest_hmac_key=b"k"*32)
        take1=await store.publish_pcm(recipe(),outcome(),b"\x01\x00\x02\x00")
        take2=await store.publish_pcm(recipe(1.1),outcome(),b"\x03\x00\x04\x00")
        repo=SQLiteAudioTrackRepository(database)
        original=track(take1.take_id)
        await repo.publish(original)
        redub=track(take2.take_id,revision=2,supersedes=original.track_id)
        service=StoryBookAudioAccessService(repo,store)

        with pytest.raises(StorageError,match="not currently authorized"):
            await service.publish_authorized(redub,revoked())

        assert await repo.latest("family")==original
        published=await service.publish_authorized(redub,allowed())
        assert published.policy_revision=="policy-2"
        assert published.result.track==redub
        assert await repo.latest("family")==redub
    finally:
        await database.close()


async def test_authorization_is_exact_provider_voice_revision_not_friendly_voice_id(tmp_path):
    database,paths=await open_database(tmp_path)
    try:
        await prepare(database)
        store=SQLiteAudioTakeStore(database,paths.world.parent/"assets",manifest_hmac_key=b"k"*32)
        take=await store.publish_pcm(recipe(),outcome(),b"\x01\x00\x02\x00")
        repo=SQLiteAudioTrackRepository(database)
        original=track(take.take_id)
        await repo.publish(original)
        wrong_revision=VoiceAuthorizationSnapshot(
            policy_revision="policy-4",
            authorized_voice_revisions=frozenset({
                ("speechrail-local","npc-approved","voice-"+"e"*40)
            }),
        )

        with pytest.raises(StorageError,match="not currently authorized"):
            await StoryBookAudioAccessService(repo,store).resolve_for_replay(
                original.track_id,wrong_revision
            )
    finally:
        await database.close()
