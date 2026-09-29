from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from application.context_plan import ContextError, Evidence, Layer, WorkerProfile
from application.gameplay_context import (
    GameplayCall,
    GameplayContextCoordinator,
    GameplayMode,
)
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.gameplay_context_repository import SQLiteGameplayContextRepository
from infrastructure.sqlite_runtime import sqlite3

WORLD_ID = "world.alpha"
WORLDLINE_ID = "line.main"
SESSION_ID = "session.main"
OWNER_ID = "owner.one"


@pytest_asyncio.fixture
async def world_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", WORLD_ID)
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT")
        canon.execute("INSERT INTO canon_fixture VALUES ('canon', 'immutable')")

    database = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version)
    _seed_session(paths)
    try:
        yield database, paths
    finally:
        await database.close()


def _world_connection(paths: DatabasePaths):
    connection = sqlite3.connect(paths.world, isolation_level=None, timeout=5)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _insert_domain_commit(connection, revision: int) -> None:
    connection.execute(
        "INSERT INTO domain_commits("
        "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
        "world_time,commit_time,operation_json,result_json"
        ") VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            revision,
            WORLDLINE_ID,
            f"commit.key.{revision}",
            f"request.digest.{revision}",
            f"request.{revision}",
            f"trace.{revision}",
            f"fixture-world-time-{revision}",
            f"fixture-commit-time-{revision}",
            "{}",
            "{}",
        ),
    )
    connection.execute(
        "INSERT INTO projection_outbox(revision,processed) VALUES (?,0)",
        (revision,),
    )
    connection.execute(
        "UPDATE world_meta SET revision=? WHERE singleton=1",
        (revision,),
    )


def _seed_session(paths: DatabasePaths) -> None:
    connection = _world_connection(paths)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_domain_commit(connection, 1)
        connection.execute(
            "INSERT INTO story_sessions("
            "id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "base_world_revision,base_character_revision,base_story_revision,"
            "story_revision,status,story_state_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                SESSION_ID,
                WORLD_ID,
                WORLDLINE_ID,
                "char-a",
                "seed.alpha",
                0,
                0,
                0,
                0,
                "active",
                json.dumps(
                    {
                        "revision": 0,
                        "scene": {"id": "opening"},
                        "secret_states": {"secret.hidden": "hidden"},
                    }
                ),
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _commit_turn(
    paths: DatabasePaths,
    revision: int,
    story_revision: int,
    *,
    knowledge_changes: tuple[dict[str, Any], ...] = (),
    world_events: tuple[dict[str, Any], ...] = (),
) -> None:
    connection = _world_connection(paths)
    turn_id = f"turn.{revision}"
    delta_id = f"delta.{revision}"
    try:
        connection.execute("BEGIN IMMEDIATE")
        _insert_domain_commit(connection, revision)

        turn_candidates = {
            "knowledge_candidates": [change["payload"] for change in knowledge_changes],
            "world_event_candidates": [event["payload"] for event in world_events],
        }
        connection.execute(
            "INSERT INTO story_state_deltas("
            "id,session_id,turn_id,story_revision,payload_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?)",
            (
                delta_id,
                SESSION_ID,
                turn_id,
                story_revision,
                json.dumps(turn_candidates, sort_keys=True),
                revision,
            ),
        )
        connection.execute(
            "INSERT INTO turn_transactions("
            "id,session_id,idempotency_key,status,base_world_revision,"
            "base_character_revision,base_story_revision,player_advice_id,"
            "action_intent_id,state_delta_id,committed_story_revision,"
            "narrative_block_id,transaction_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                turn_id,
                SESSION_ID,
                f"turn.key.{revision}",
                "committed",
                revision - 1,
                0,
                story_revision - 1,
                None,
                None,
                delta_id,
                story_revision,
                None,
                json.dumps(turn_candidates, sort_keys=True),
                revision,
            ),
        )

        for ordinal, change in enumerate(knowledge_changes):
            payload = change["payload"]
            connection.execute(
                "INSERT INTO turn_knowledge_changes("
                "id,session_id,turn_id,state_delta_id,ordinal,character_id,"
                "proposition_id,payload_json,committed_world_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    change["id"],
                    SESSION_ID,
                    turn_id,
                    delta_id,
                    ordinal,
                    change["character_id"],
                    change["proposition_id"],
                    json.dumps(payload, sort_keys=True),
                    revision,
                ),
            )

        for ordinal, event in enumerate(world_events):
            payload = event["payload"]
            connection.execute(
                "INSERT INTO turn_world_events("
                "id,session_id,turn_id,state_delta_id,ordinal,event_type,"
                "payload_json,committed_world_revision"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    event["id"],
                    SESSION_ID,
                    turn_id,
                    delta_id,
                    ordinal,
                    payload["event_type"],
                    json.dumps(payload, sort_keys=True),
                    revision,
                ),
            )

        connection.execute(
            "UPDATE story_sessions SET story_revision=?,status='active',"
            "story_state_json=?,committed_world_revision=? WHERE id=?",
            (
                story_revision,
                json.dumps(
                    {
                        "revision": story_revision,
                        "scene": {"id": f"scene.{story_revision}"},
                        "secret_states": {"secret.hidden": "hidden"},
                    }
                ),
                revision,
                SESSION_ID,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _insert_uncommitted_candidate(paths: DatabasePaths) -> None:
    candidate = {
        "character_id": "char-a",
        "proposition_id": "prop.pending",
        "certainty": 1.0,
        "source_ref": "candidate.only",
        "status": "confirmed",
    }
    connection = _world_connection(paths)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO turn_transactions("
            "id,session_id,idempotency_key,status,base_world_revision,"
            "base_character_revision,base_story_revision,player_advice_id,"
            "action_intent_id,state_delta_id,committed_story_revision,"
            "narrative_block_id,transaction_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "turn.pending",
                SESSION_ID,
                "turn.key.pending",
                "received",
                2,
                0,
                0,
                "advice.pending",
                None,
                None,
                None,
                None,
                json.dumps({"knowledge_candidates": [candidate]}),
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _knowledge_change(
    character_id: str, proposition_id: str, *, status: str = "confirmed"
) -> dict[str, Any]:
    return {
        "id": f"{character_id}.{proposition_id}",
        "character_id": character_id,
        "proposition_id": proposition_id,
        "payload": {
            "character_id": character_id,
            "proposition_id": proposition_id,
            "certainty": 1.0,
            "source_ref": f"evidence.{proposition_id}",
            "status": status,
        },
    }


def _world_event(
    event_id: str,
    *,
    public: bool,
    known_by: tuple[str, ...] = (),
    hidden: bool = False,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "payload": {
            "event_type": "observation",
            "actors": [],
            "targets": [],
            "payload": {"event_id": event_id, "hidden": hidden},
            "visibility": {"public": public, "known_by": list(known_by)},
        },
    }


class _Profiles:
    def profile(self, mode: GameplayMode, consumer: str) -> WorkerProfile:
        return WorkerProfile(
            consumer,
            "test-profile.v1",
            "Return a typed proposal.",
            '{"type":"object"}',
        )


def _call(
    subject_id: str = "char-a",
    *,
    mode: GameplayMode = GameplayMode.CHARACTER_REASONING,
    request_id: str | None = None,
) -> GameplayCall:
    return GameplayCall(
        mode,
        OWNER_ID,
        WORLD_ID,
        WORLDLINE_ID,
        subject_id,
        SESSION_ID,
        '{"advice":"observe"}',
        request_id or f"request.{subject_id}.{mode.value}",
    )


def _coordinator(
    repository: SQLiteGameplayContextRepository,
) -> GameplayContextCoordinator:
    return GameplayContextCoordinator(
        snapshot=repository,
        authorization=repository,
        profiles=_Profiles(),
        lore=repository.lore_port,
        world=repository.world_port,
        character=repository.character_port,
        story=repository.story_port,
        memory=repository.memory_port,
    )


@pytest.mark.asyncio
async def test_repository_exposes_knowledge_only_after_its_sqlite_commit(
    world_database,
) -> None:
    database, paths = world_database
    repository = SQLiteGameplayContextRepository(database)
    coordinator = _coordinator(repository)

    before = await coordinator.prepare(_call(request_id="request.before"))
    assert "knowledge:char-a:prop.after-commit" not in {
        item.source_id for item in before.request.evidence
    }

    _commit_turn(
        paths,
        2,
        1,
        knowledge_changes=(_knowledge_change("char-a", "prop.after-commit"),),
    )

    after = await coordinator.prepare(_call(request_id="request.after"))
    by_source = {item.source_id: item for item in after.request.evidence}
    fact = by_source["knowledge:char-a:prop.after-commit"]
    assert after.request.world_revision == 2
    assert after.request.story_revision == 1
    assert fact.committed_revision == 2
    assert fact.source_revision == 2


@pytest.mark.asyncio
async def test_repository_isolates_subject_knowledge_and_excludes_hidden_or_pending_facts(
    world_database,
) -> None:
    database, paths = world_database
    _commit_turn(
        paths,
        2,
        1,
        knowledge_changes=(
            _knowledge_change("char-a", "prop.a-private"),
            _knowledge_change("char-b", "prop.b-private"),
        ),
        world_events=(
            _world_event("event.a-private", public=False, known_by=("char-a",)),
            _world_event("event.hidden", public=False, known_by=("char-a",), hidden=True),
            _world_event("event.public", public=True),
        ),
    )
    _insert_uncommitted_candidate(paths)

    coordinator = _coordinator(SQLiteGameplayContextRepository(database))
    char_a = await coordinator.prepare(_call("char-a", request_id="request.char-a"))
    char_b = await coordinator.prepare(_call("char-b", request_id="request.char-b"))

    sources_a = {item.source_id for item in char_a.request.evidence}
    sources_b = {item.source_id for item in char_b.request.evidence}
    assert "knowledge:char-a:prop.a-private" in sources_a
    assert "world-event:event.a-private" in sources_a
    assert "knowledge:char-b:prop.b-private" not in sources_a
    assert "world-event:event.hidden" not in sources_a
    assert "knowledge:prop.pending" not in sources_a

    assert "knowledge:char-b:prop.b-private" in sources_b
    assert "knowledge:char-a:prop.a-private" not in sources_b
    assert "world-event:event.a-private" not in sources_b
    assert "world-event:event.hidden" not in sources_b
    assert "knowledge:prop.pending" not in sources_b

    advice = await coordinator.prepare(
        _call(
            "char-a",
            mode=GameplayMode.ADVICE_INTERPRETATION,
            request_id="request.advice",
        )
    )
    sources_advice = {item.source_id for item in advice.request.evidence}
    assert "world-event:event.public" in sources_advice
    assert "world-event:event.a-private" not in sources_advice
    assert "knowledge:char-a:prop.a-private" not in sources_advice
    assert "world-event:event.hidden" not in sources_advice
    assert "knowledge:prop.pending" not in sources_advice


@pytest.mark.asyncio
async def test_repository_authorization_cannot_expand_or_mutate_snapshot_candidates(
    world_database,
) -> None:
    database, paths = world_database
    _commit_turn(
        paths,
        2,
        1,
        knowledge_changes=(_knowledge_change("char-a", "prop.authorized"),),
    )
    repository = SQLiteGameplayContextRepository(database)
    prepared = await _coordinator(repository).prepare(_call(request_id="request.authorization"))
    recipe = prepared.recipe
    existing = prepared.request.evidence[0]
    extra = Evidence(
        "retrieval:uncommitted",
        1,
        "retrieval_candidate",
        Layer.RECALL,
        '{"proposition_id":"prop.pending"}',
        world_id=WORLD_ID,
        worldline_id=WORLDLINE_ID,
        subject_id="char-a",
        available_at_tick=1,
        committed_revision=2,
    )

    expanded_request = replace(
        prepared.request,
        evidence=prepared.request.evidence + (extra,),
    )
    expanded_view = await repository.authorize(expanded_request, recipe)
    assert extra.fingerprint not in expanded_view.grants

    tampered = replace(existing, content_json='{"tampered":true}')
    tampered_request = replace(prepared.request, evidence=(tampered,))
    with pytest.raises(ContextError, match="context_source_changed"):
        await repository.authorize(tampered_request, recipe)


class _PausingRepository(SQLiteGameplayContextRepository):
    def __init__(self, database: DatabaseManager) -> None:
        super().__init__(database)
        self.read_started = threading.Event()
        self.resume_read = threading.Event()
        self.port_events: list[tuple[str, object]] = []

    def _read_committed_rows(self, connection, call, session, world_revision):
        self.read_started.set()
        if not self.resume_read.wait(timeout=5):
            raise TimeoutError("test did not release the snapshot reader")
        return super()._read_committed_rows(connection, call, session, world_revision)

    async def eligibility(self, scope, snapshot, recipe):
        self.port_events.append(("eligibility", snapshot))
        return await super().eligibility(scope, snapshot, recipe)

    async def _load_facet(self, facet, call, snapshot, recipe, eligibility):
        self.port_events.append((facet.value, snapshot))
        return await super()._load_facet(facet, call, snapshot, recipe, eligibility)


@pytest.mark.asyncio
async def test_repository_uses_one_read_snapshot_for_every_facet_during_concurrent_commit(
    world_database,
) -> None:
    database, paths = world_database
    _commit_turn(
        paths,
        2,
        1,
        knowledge_changes=(_knowledge_change("char-a", "prop.before-writer"),),
        world_events=(_world_event("event.before-writer", public=True, known_by=("char-a",)),),
    )
    repository = _PausingRepository(database)
    coordinator = _coordinator(repository)
    prepare_task = asyncio.create_task(coordinator.prepare(_call(request_id="request.concurrent")))

    assert await asyncio.to_thread(repository.read_started.wait, 5)
    await asyncio.to_thread(
        _commit_turn,
        paths,
        3,
        2,
        knowledge_changes=(_knowledge_change("char-a", "prop.during-writer"),),
        world_events=(_world_event("event.during-writer", public=True, known_by=("char-a",)),),
    )
    repository.resume_read.set()

    prepared = await prepare_task
    source_ids = {item.source_id for item in prepared.request.evidence}
    assert prepared.request.world_revision == 2
    assert prepared.request.story_revision == 1
    assert "knowledge:char-a:prop.before-writer" in source_ids
    assert "world-event:event.before-writer" in source_ids
    assert "knowledge:char-a:prop.during-writer" not in source_ids
    assert "world-event:event.during-writer" not in source_ids
    assert {item.committed_revision for item in prepared.request.evidence} == {2}

    first_events = tuple(repository.port_events)
    eligibility_index = next(
        index for index, (kind, _) in enumerate(first_events) if kind == "eligibility"
    )
    facet_indexes = [index for index, (kind, _) in enumerate(first_events) if kind != "eligibility"]
    assert facet_indexes
    assert eligibility_index < min(facet_indexes)
    assert len({id(snapshot) for _, snapshot in first_events}) == 1

    after_writer = await coordinator.prepare(_call(request_id="request.after-writer"))
    after_ids = {item.source_id for item in after_writer.request.evidence}
    assert after_writer.request.world_revision == 3
    assert after_writer.request.story_revision == 2
    assert "knowledge:char-a:prop.during-writer" in after_ids
    assert "world-event:event.during-writer" in after_ids
