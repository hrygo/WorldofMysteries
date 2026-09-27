"""Durable turn-domain evidence and atomic Episode finalization tests."""
from __future__ import annotations

import json
import sqlite3 as stdlib_sqlite3
from pathlib import Path
from dataclasses import replace
import asyncio
import threading

import pytest
import pytest_asyncio

from application.story_session_open import OpenStorySessionCommand
from contracts import Episode, StateDelta, StorySession, StoryState, TurnTransaction
from contracts.models import (
    CharacterDelta,
    CharacterPatch,
    KnowledgeCandidate,
    RelationshipDelta,
    RelationshipDimensions,
    WorldEventCandidate,
    WorldEventVisibility,
)
from infrastructure.database_manager import (
    DatabaseManager,
    DatabasePaths,
    IdempotencyConflict,
    StorageError,
)
from infrastructure.episode_finalization_repository import (
    EpisodeFinalizationArtifacts,
    EpisodeFinalizationRequest,
    SQLiteEpisodeFinalizationRepository,
)
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.outbox import OutboxProjector


def _session() -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session-1",
            "revision": 0,
            "turn": 0,
            "phase": "opening",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["player-1"],
            },
            "world_time": "1349-06-12T21:40:00",
            "protagonist_goal": "investigate",
            "active_conflicts": ["unknown_origin"],
            "discovered_clue_ids": [],
            "secret_states": {"secret-1": "hidden"},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-1",
            "world_id": "world-1",
            "worldline_id": "line-1",
            "protagonist_id": "player-1",
            "story_seed_id": "seed-1",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def _episode() -> Episode:
    return Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode-1",
            "world_id": "world-1",
            "worldline_id": "line-1",
            "story_seed_id": "seed-1",
            "protagonist_ids": ["player-1"],
            "title": "A partial truth",
            "start_world_time": "1349-06-12T21:40:00",
            "end_world_time": "1349-06-12T23:20:00",
            "ending": {"type": "partial_truth", "main_problem": "partially_resolved"},
            "secret_states": {"secret-1": "hidden"},
            "discovered_clue_ids": [],
            "unresolved_threads": ["unknown_origin"],
            "character_event_ids": [],
            "relationship_event_ids": ["relationship-event-1"],
            "knowledge_change_ids": ["knowledge-change-1"],
            "memory_ids": ["memory-1"],
            "world_event_ids": ["world-event-1"],
        }
    )


def _empty_episode() -> Episode:
    return Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode-1",
            "world_id": "world-1",
            "worldline_id": "line-1",
            "story_seed_id": "seed-1",
            "protagonist_ids": ["player-1"],
            "title": "A partial truth",
            "start_world_time": "1349-06-12T21:40:00",
            "end_world_time": "1349-06-12T23:20:00",
            "ending": {"type": "partial_truth", "main_problem": "partially_resolved"},
            "secret_states": {"secret-1": "hidden"},
            "unresolved_threads": ["unknown_origin"],
            "character_event_ids": [],
            "relationship_event_ids": [],
            "knowledge_change_ids": [],
            "memory_ids": [],
            "world_event_ids": [],
        }
    )


def _schema_valid_artifacts() -> EpisodeFinalizationArtifacts:
    return EpisodeFinalizationArtifacts(
        relationship_events=(
            {
                "id": "relationship-event-1",
                "change": {
                    "from_character_id": "player-1",
                    "to_character_id": "npc-1",
                    "dimension_deltas": {"trust": 0.1},
                    "evidence_ids": ["clue-1"],
                },
            },
        ),
        knowledge_changes=(
            {
                "schema_version": "1.0",
                "id": "knowledge-change-1",
                "character_id": "player-1",
                "worldline_id": "line-1",
                "proposition_id": "fact-1",
                "certainty": 0.8,
                "source": {"type": "observation", "ref": "clue-1"},
                "status": "probable",
                "revision": 0,
            },
        ),
        memories=(
            {
                "schema_version": "1.0",
                "id": "memory-1",
                "character_id": "player-1",
                "worldline_id": "line-1",
                "memory_type": "episode",
                "summary": "A remembered partial truth.",
                "importance": {
                    "overall": 0.5,
                    "emotional": 0.2,
                    "relationship": 0.3,
                    "identity": 0.1,
                },
                "source_ids": ["turn-1"],
                "retention": "long",
            },
        ),
        world_events=(
            {
                "schema_version": "1.0",
                "id": "world-event-1",
                "world_id": "world-1",
                "worldline_id": "line-1",
                "event_type": "evidence_recovered",
                "actors": ["player-1"],
                "targets": ["npc-1"],
                "cause": {"episode_id": "episode-1", "story_turn_id": "turn-1"},
                "payload": {"clue_id": "clue-1"},
                "visibility": {"public": False, "known_by": ["player-1"]},
                "persistence": "episode",
                "importance": "personal",
                "revision": 0,
            },
        ),
    )


def _request(
    *,
    key: str = "finalize-episode-1",
    expected_revision: int = 1,
    expected_story_revision: int = 0,
    artifacts: EpisodeFinalizationArtifacts | None = None,
    episode: Episode | None = None,
) -> EpisodeFinalizationRequest:
    return EpisodeFinalizationRequest(
        session_id="session-1",
        expected_story_revision=expected_story_revision,
        world_time="1349-06-12T23:20:00",
        expected_store_revision=expected_revision,
        idempotency_key=key,
        request_id=f"request-{key}",
        trace_id=f"trace-{key}",
        episode=episode or _episode(),
        artifacts=artifacts or _schema_valid_artifacts(),
    )


@pytest.fixture
def paths(tmp_path: Path) -> DatabasePaths:
    layout = DatabasePaths.for_world(tmp_path / "worlds", "test-world")
    layout.canon.parent.mkdir(parents=True)
    with stdlib_sqlite3.connect(layout.canon) as connection:
        connection.execute(
            "CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT) STRICT"
        )
        connection.execute("INSERT INTO canon_fixture VALUES ('canon-1', 'immutable')")
    return layout


@pytest_asyncio.fixture
async def database(paths: DatabasePaths):
    opened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    await SQLiteStorySessionOpenPort(opened).open_session(
        OpenStorySessionCommand(
            initial_session=_session(),
            open_request_id="open-1",
            store_expected_revision=0,
            request_id="request-open",
            trace_id="trace-open",
        )
    )
    try:
        yield opened
    finally:
        await opened.close()


def _turn_settlement():
    delta = StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-1",
            "turn_id": "turn-1",
            "outcome": "partial_success",
            "story_delta": {"scene_id": "scene-2"},
            "character_deltas": [
                CharacterDelta(
                    character_id="player-1",
                    patches=[
                        CharacterPatch(
                            path="/state/location_id",
                            operation="set",
                            value="room-2",
                        )
                    ],
                    evidence_ids=["clue-1"],
                )
            ],
            "relationship_deltas": [
                RelationshipDelta(
                    from_character_id="player-1",
                    to_character_id="npc-1",
                    dimension_deltas=RelationshipDimensions(trust=0.1),
                    evidence_ids=["clue-1"],
                )
            ],
            "knowledge_candidates": [
                KnowledgeCandidate(
                    character_id="player-1",
                    proposition_id="fact-1",
                    certainty=0.8,
                    source_ref="clue-1",
                    status="probable",
                )
            ],
            "world_event_candidates": [
                WorldEventCandidate(
                    event_type="evidence_recovered",
                    actors=["player-1"],
                    targets=["npc-1"],
                    payload={"clue_id": "clue-1"},
                    visibility=WorldEventVisibility(
                        public=False, known_by=["player-1"]
                    ),
                )
            ],
            "evidence_ids": ["clue-1"],
        }
    )
    initial = _session()
    next_state = initial.story_state.model_copy(
        update={
            "revision": 1,
            "turn": 1,
            "world_time": "1349-06-12T23:20:00",
            "scene": initial.story_state.scene.model_copy(update={"id": "scene-2"}),
            "last_state_delta_id": delta.id,
        }
    )
    committed_session = initial.model_copy(update={"story_state": next_state})
    turn = TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn-1",
            "session_id": initial.id,
            "idempotency_key": "turn-idempotency-1",
            "status": "committed",
            "base_revisions": initial.base_revisions.model_dump(
                mode="json", exclude_none=True
            ),
            "state_delta_id": delta.id,
            "committed_story_revision": 1,
        }
    )
    return committed_session, delta, turn


async def _commit_first_turn(database: DatabaseManager):
    session, delta, turn = _turn_settlement()
    return await SQLiteStorySessionCommitPort(database).commit_turn(
        session,
        delta,
        turn,
        store_expected_revision=1,
        request_id="request-turn-1",
        trace_id="trace-turn-1",
    )


async def _request_from_committed_turn(
    database: DatabaseManager,
    *,
    key: str = "finalize-episode-1",
    expected_revision: int = 2,
) -> EpisodeFinalizationRequest:
    relationship_row = (
        await database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_relationship_changes "
            "WHERE session_id='session-1'"
        )
    )[0]
    character_row = (
        await database.read_world(
            "SELECT id,payload_json FROM turn_character_changes "
            "WHERE session_id='session-1'"
        )
    )[0]
    knowledge_row = (
        await database.read_world(
            "SELECT id,payload_json FROM turn_knowledge_changes "
            "WHERE session_id='session-1'"
        )
    )[0]
    world_event_row = (
        await database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_world_events "
            "WHERE session_id='session-1'"
        )
    )[0]
    relationship_candidate = json.loads(relationship_row["payload_json"])
    character_candidate = json.loads(character_row["payload_json"])
    knowledge_candidate = json.loads(knowledge_row["payload_json"])
    world_event_candidate = json.loads(world_event_row["payload_json"])
    episode = _episode().model_copy(
        update={
            "character_event_ids": [character_row["id"]],
            "relationship_event_ids": [relationship_row["id"]],
            "knowledge_change_ids": [knowledge_row["id"]],
            "world_event_ids": [world_event_row["id"]],
        }
    )
    artifacts = EpisodeFinalizationArtifacts(
        character_events=(
            {"id": character_row["id"], "change": character_candidate},
        ),
        relationship_events=(
            {"id": relationship_row["id"], "change": relationship_candidate},
        ),
        knowledge_changes=(
            {
                "schema_version": "1.0",
                "id": knowledge_row["id"],
                "character_id": knowledge_candidate["character_id"],
                "worldline_id": "line-1",
                "proposition_id": knowledge_candidate["proposition_id"],
                "certainty": knowledge_candidate["certainty"],
                "source": {
                    "type": "observation",
                    "ref": knowledge_candidate["source_ref"],
                },
                "status": knowledge_candidate["status"],
                "revision": 0,
            },
        ),
        memories=(
            {
                "schema_version": "1.0",
                "id": "memory-1",
                "character_id": "player-1",
                "worldline_id": "line-1",
                "memory_type": "episode",
                "summary": "A remembered partial truth.",
                "importance": {
                    "overall": 0.5,
                    "emotional": 0.2,
                    "relationship": 0.3,
                    "identity": 0.1,
                },
                "source_ids": [world_event_row["id"]],
                "retention": "long",
            },
        ),
        world_events=(
            {
                "schema_version": "1.0",
                "id": world_event_row["id"],
                "world_id": "world-1",
                "worldline_id": "line-1",
                "event_type": world_event_candidate["event_type"],
                "actors": world_event_candidate["actors"],
                "targets": world_event_candidate["targets"],
                "cause": {
                    "episode_id": "episode-1",
                    "story_turn_id": world_event_row["turn_id"],
                },
                "payload": world_event_candidate["payload"],
                "visibility": world_event_candidate["visibility"],
                "persistence": "episode",
                "importance": "personal",
                "revision": 0,
            },
        ),
    )
    return _request(
        key=key,
        expected_revision=expected_revision,
        expected_story_revision=1,
        episode=episode,
        artifacts=artifacts,
    )


@pytest.mark.asyncio
async def test_story_commit_persists_each_typed_domain_change_with_its_commit_revision(
    database: DatabaseManager,
):
    session, delta, turn = _turn_settlement()
    result = await SQLiteStorySessionCommitPort(database).commit_turn(
        session,
        delta,
        turn,
        store_expected_revision=1,
        request_id="request-turn-1",
        trace_id="trace-turn-1",
    )

    assert result.store_revision == 2
    assert result.delta == delta
    expected_tables = {
        "turn_character_changes": (
            "character_id",
            "player-1",
            delta.character_deltas[0].model_dump(mode="json", exclude_none=True),
        ),
        "turn_relationship_changes": (
            "from_character_id",
            "player-1",
            delta.relationship_deltas[0].model_dump(mode="json", exclude_none=True),
        ),
        "turn_knowledge_changes": (
            "proposition_id",
            "fact-1",
            delta.knowledge_candidates[0].model_dump(mode="json", exclude_none=True),
        ),
        "turn_world_events": (
            "event_type",
            "evidence_recovered",
            delta.world_event_candidates[0].model_dump(
                mode="json", exclude_none=True
            ),
        ),
    }
    for table, (subject_column, subject_id, expected_payload) in expected_tables.items():
        rows = await database.read_world(
            f"SELECT {subject_column},payload_json,committed_world_revision "
            f"FROM {table} WHERE state_delta_id=?",
            (delta.id,),
        )
        assert rows == [
            {
                subject_column: subject_id,
                "payload_json": json.dumps(
                    expected_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "committed_world_revision": 2,
            }
        ]
    assert await database.read_world(
        "SELECT revision,processed FROM projection_outbox"
    ) == [{"revision": 1, "processed": 0}, {"revision": 2, "processed": 0}]


@pytest.mark.parametrize(
    "stage", ["before_apply", "after_apply", "after_events", "before_commit"]
)
@pytest.mark.asyncio
async def test_story_commit_failure_rolls_back_domain_changes_with_story_state(
    database: DatabaseManager, stage: str
):
    def fail_at(point: str) -> None:
        if point == stage:
            raise RuntimeError("injected turn settlement failure")

    database._fault_hook = fail_at
    session, delta, turn = _turn_settlement()
    with pytest.raises(RuntimeError, match="injected turn settlement failure"):
        await SQLiteStorySessionCommitPort(database).commit_turn(
            session,
            delta,
            turn,
            store_expected_revision=1,
            request_id="request-turn-1",
            trace_id="trace-turn-1",
        )

    assert await database.read_world("SELECT story_revision FROM story_sessions") == [
        {"story_revision": 0}
    ]
    assert await database.read_world("SELECT count(*) AS n FROM story_state_deltas") == [
        {"n": 0}
    ]
    for table in (
        "turn_character_changes",
        "turn_relationship_changes",
        "turn_knowledge_changes",
        "turn_world_events",
    ):
        assert await database.read_world(
            f"SELECT count(*) AS n FROM {table}"
        ) == [{"n": 0}]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 1}
    ]
    assert await database.read_world("SELECT count(*) AS n FROM projection_outbox") == [
        {"n": 1}
    ]


@pytest.mark.asyncio
async def test_story_commit_freezes_nested_inputs_before_writer_queue_admission(
    database: DatabaseManager,
):
    entered, release = threading.Event(), threading.Event()

    def block_writer() -> None:
        entered.set()
        assert release.wait(5)

    blocker = asyncio.create_task(database._submit(block_writer))
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)

        session, delta, turn = _turn_settlement()
        pending = asyncio.create_task(
            SQLiteStorySessionCommitPort(database).commit_turn(
                session,
                delta,
                turn,
                store_expected_revision=1,
                request_id="request-turn-1",
                trace_id="trace-turn-1",
            )
        )
        await asyncio.sleep(0)
        session.story_state.scene.id = "mutated-after-admission"
        delta.story_delta.scene_id = "mutated-after-admission"
        delta.character_deltas[0].patches[0].value = "mutated-after-admission"
    finally:
        release.set()

    await blocker
    await pending
    persisted_state = (
        await database.read_world(
            "SELECT story_state_json FROM story_sessions WHERE id='session-1'"
        )
    )[0]["story_state_json"]
    persisted_delta = (
        await database.read_world(
            "SELECT payload_json FROM story_state_deltas WHERE id='delta-1'"
        )
    )[0]["payload_json"]
    persisted_change = (
        await database.read_world(
            "SELECT payload_json FROM turn_character_changes WHERE state_delta_id='delta-1'"
        )
    )[0]["payload_json"]

    assert json.loads(persisted_state)["scene"]["id"] == "scene-2"
    assert json.loads(persisted_delta)["story_delta"]["scene_id"] == "scene-2"
    assert (
        json.loads(persisted_delta)["character_deltas"][0]["patches"][0]["value"]
        == "room-2"
    )
    assert json.loads(persisted_change)["patches"][0]["value"] == "room-2"


@pytest.mark.asyncio
async def test_turn_and_episode_artifacts_project_incrementally_and_rebuild_from_world(
    database: DatabaseManager,
):
    session, delta, turn = _turn_settlement()
    committed = await SQLiteStorySessionCommitPort(database).commit_turn(
        session,
        delta,
        turn,
        store_expected_revision=1,
        request_id="request-turn-1",
        trace_id="trace-turn-1",
    )
    assert committed.store_revision == 2
    request = await _request_from_committed_turn(database)
    finalized = await SQLiteEpisodeFinalizationRepository(database).finalize(request)
    assert finalized.store_revision == 3

    fail_projection = True

    def fail_after_projected_event(stage: str) -> None:
        if fail_projection and stage == "after_project_event":
            raise RuntimeError("injected domain projection failure")

    projector = OutboxProjector(database, fault_hook=fail_after_projected_event)
    with pytest.raises(RuntimeError, match="injected domain projection failure"):
        await projector.run_once()
    assert await database.read_world(
        "SELECT count(*) AS n FROM projection_outbox WHERE processed=0"
    ) == [{"n": 3}]
    with stdlib_sqlite3.connect(database.paths.retrieval) as connection:
        assert connection.execute("SELECT count(*) FROM projected_events").fetchone()[0] == 0
    assert await database.read_world(
        "SELECT count(*) AS n FROM turn_character_changes"
    ) == [{"n": 1}]
    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 1}]

    fail_projection = False
    projected = await projector.run_once()
    assert projected.indexed_revision == 3
    assert projected.applied_events == 12
    repeated = await projector.run_once()
    assert repeated.indexed_revision == 3
    assert repeated.observed_world_revision == 3
    assert repeated.applied_events == 0
    assert repeated.rebuilt is False

    def projected_rows():
        with stdlib_sqlite3.connect(database.paths.retrieval) as connection:
            connection.row_factory = stdlib_sqlite3.Row
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT event_type,payload_json FROM projected_events ORDER BY event_id"
                )
            ]

    before_rebuild = projected_rows()
    event_payloads = {
        row["event_type"]: json.loads(row["payload_json"])
        for row in before_rebuild
    }
    assert event_payloads["story.domain.character.candidate"]["change"] == (
        delta.character_deltas[0].model_dump(mode="json", exclude_none=True)
    )
    assert event_payloads["story.domain.relationship.candidate"]["change"] == (
        delta.relationship_deltas[0].model_dump(mode="json", exclude_none=True)
    )
    assert event_payloads["story.domain.knowledge.candidate"]["change"] == (
        delta.knowledge_candidates[0].model_dump(mode="json", exclude_none=True)
    )
    projected_world_event = event_payloads["story.domain.world_event.candidate"][
        "change"
    ]
    assert projected_world_event == delta.world_event_candidates[0].model_dump(
        mode="json", exclude_none=True
    )
    assert projected_world_event["visibility"] == {
        "public": False,
        "known_by": ["player-1"],
    }
    assert event_payloads["story.episode.memories"]["artifact"] == (
        request.artifacts.memories[0]
    )
    assert event_payloads["story.episode.world_events"]["artifact"] == (
        request.artifacts.world_events[0]
    )

    database.paths.retrieval.unlink()
    rebuilt = await projector.rebuild()
    assert rebuilt.rebuilt is True
    assert rebuilt.indexed_revision == 3
    assert rebuilt.applied_events == 12
    assert projected_rows() == before_rebuild


@pytest.mark.asyncio
async def test_episode_finalization_commits_episode_and_all_artifacts_atomically(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    result = await SQLiteEpisodeFinalizationRepository(database).finalize(request)

    assert result.store_revision == 3
    assert result.replayed is False
    assert result.episode == request.episode
    assert result.artifacts == request.artifacts
    assert await database.read_world(
        "SELECT status,committed_world_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "finalized", "committed_world_revision": 3}]
    assert await database.read_world(
        "SELECT id,committed_world_revision FROM episodes"
    ) == [{"id": "episode-1", "committed_world_revision": 3}]
    assert await database.read_world(
        "SELECT artifact_id FROM character_episode_memories WHERE episode_id='episode-1'"
    ) == [{"artifact_id": "memory-1"}]
    assert await database.read_world(
        "SELECT episode_id,idempotency_key,committed_world_revision FROM episode_finalizations"
    ) == [
        {
            "episode_id": "episode-1",
            "idempotency_key": "finalize-episode-1",
            "committed_world_revision": 3,
        }
    ]
    assert await database.read_world(
        "SELECT revision,processed FROM projection_outbox ORDER BY revision"
    ) == [
        {"revision": 1, "processed": 0},
        {"revision": 2, "processed": 0},
        {"revision": 3, "processed": 0},
    ]


@pytest.mark.asyncio
async def test_episode_finalization_rejects_commit_time_outside_committed_story_time(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)

    with pytest.raises(StorageError, match="Finalization world time"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            replace(request, world_time="1349-06-13T00:00:00")
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]
    assert await database.read_world(
        "SELECT status,committed_world_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "active", "committed_world_revision": 2}]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 2}
    ]


@pytest.mark.asyncio
async def test_episode_finalization_rejects_artifacts_without_committed_turn_evidence(
    database: DatabaseManager,
):
    world_time = _session().story_state.world_time
    request = _request(
        episode=_episode().model_copy(update={"end_world_time": world_time})
    )
    request = replace(request, world_time=world_time)

    with pytest.raises(StorageError, match="committed Story evidence"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(request)

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]
    assert await database.read_world(
        "SELECT status FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "active"}]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 1}
    ]


@pytest.mark.asyncio
async def test_episode_finalization_rejects_artifacts_with_unmatched_committed_ids(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    unsupported = _request(expected_revision=2, expected_story_revision=1)

    with pytest.raises(StorageError, match="committed Story evidence"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(unsupported)

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]
    assert await database.read_world(
        "SELECT status,story_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "active", "story_revision": 1}]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 2}
    ]


@pytest.mark.parametrize(
    ("group_name", "field_name", "replacement"),
    [
        (
            "character_events",
            "change",
            {
                "character_id": "player-1",
                "patches": [
                    {
                        "path": "/state/location_id",
                        "operation": "set",
                        "value": "unsupported-room",
                    }
                ],
                "evidence_ids": ["clue-1"],
            },
        ),
        (
            "relationship_events",
            "change",
            {
                "from_character_id": "player-1",
                "to_character_id": "other-character",
                "dimension_deltas": {"trust": 0.1},
                "evidence_ids": ["clue-1"],
            },
        ),
        ("knowledge_changes", "proposition_id", "unsupported-proposition"),
        ("memories", "source_ids", ["unknown-turn"]),
        ("world_events", "payload", {"fabricated": True}),
    ],
)
@pytest.mark.asyncio
async def test_episode_finalization_rejects_changed_artifact_content_for_committed_source(
    database: DatabaseManager,
    group_name: str,
    field_name: str,
    replacement: object,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    original = getattr(request.artifacts, group_name)[0]
    if field_name == "change":
        changed = {**original, "change": replacement}
    else:
        changed = {**original, field_name: replacement}
    changed_artifacts = replace(
        request.artifacts,
        **{group_name: (changed,)},
    )

    with pytest.raises(StorageError, match="committed Story evidence"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            replace(request, artifacts=changed_artifacts)
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]
    assert await database.read_world(
        "SELECT status,story_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "active", "story_revision": 1}]


@pytest.mark.asyncio
async def test_episode_finalization_rejects_private_event_memory_for_unaware_character(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    altered_memory = {
        **request.artifacts.memories[0],
        "character_id": "npc-1",
    }
    altered_artifacts = replace(request.artifacts, memories=(altered_memory,))

    with pytest.raises(StorageError, match="committed Story evidence"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            replace(request, artifacts=altered_artifacts)
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]


@pytest.mark.asyncio
async def test_episode_finalization_rejects_episode_secret_state_not_in_committed_story(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    changed_episode = Episode.model_validate(
        {
            **request.episode.model_dump(mode="json", exclude_none=True),
            "secret_states": {"secret-1": "revealed"},
        }
    )

    with pytest.raises(StorageError, match="Episode facts do not match committed StoryState"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            replace(request, episode=changed_episode)
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("discovered_clue_ids", ["unsupported-clue"]),
        ("unresolved_threads", []),
    ],
)
@pytest.mark.asyncio
async def test_episode_finalization_rejects_story_summary_outside_committed_state(
    database: DatabaseManager,
    field_name: str,
    replacement: list[str],
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    episode_data = request.episode.model_dump(mode="json", exclude_none=True)
    episode_data[field_name] = replacement
    changed_episode = Episode.model_validate(episode_data)

    with pytest.raises(StorageError, match="Episode facts do not match committed StoryState"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            replace(request, episode=changed_episode)
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]


@pytest.mark.parametrize(
    ("group_name", "episode_field", "artifact"),
    [
        (
            "memories",
            "memory_ids",
            {
                "schema_version": "1.0",
                "id": "memory-1",
                "character_id": "player-1",
                "worldline_id": "line-1",
                "memory_type": "episode",
                "summary": "A remembered partial truth.",
                "source_ids": ["turn-1"],
                "retention": "long",
            },
        ),
        (
            "memories",
            "memory_ids",
            {
                **_schema_valid_artifacts().memories[0],
                "future_contract_field": "must be rejected",
            },
        ),
        (
            "world_events",
            "world_event_ids",
            {
                "schema_version": "1.0",
                "id": "world-event-1",
                "world_id": "world-1",
                "worldline_id": "line-1",
                "event_type": "evidence_recovered",
                "actors": ["player-1"],
                "targets": ["npc-1"],
                "payload": {"clue_id": "clue-1"},
                "visibility": {"public": False, "known_by": ["player-1"]},
                "importance": "personal",
                "revision": 0,
            },
        ),
        (
            "world_events",
            "world_event_ids",
            {
                **_schema_valid_artifacts().world_events[0],
                "future_contract_field": "must be rejected",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_episode_finalization_rejects_artifacts_outside_strict_contracts(
    database: DatabaseManager,
    group_name: str,
    episode_field: str,
    artifact: dict[str, object],
):
    episode = _empty_episode().model_copy(
        update={episode_field: [artifact["id"]]}
    )
    artifacts = replace(
        EpisodeFinalizationArtifacts(),
        **{group_name: (artifact,)},
    )

    with pytest.raises(StorageError, match="artifact does not satisfy"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(
            _request(episode=episode, artifacts=artifacts)
        )

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]


@pytest.mark.asyncio
async def test_finalized_story_session_rejects_new_turn_from_old_active_snapshot(
    database: DatabaseManager,
):
    committed_turn = await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    finalized = await SQLiteEpisodeFinalizationRepository(database).finalize(request)
    next_delta = committed_turn.delta.model_copy(
        update={"id": "delta-2", "turn_id": "turn-2"}
    )
    next_state = committed_turn.session.story_state.model_copy(
        update={
            "revision": 2,
            "turn": 2,
            "scene": committed_turn.session.story_state.scene.model_copy(
                update={"id": "scene-3"}
            ),
            "last_state_delta_id": next_delta.id,
        }
    )
    next_session = committed_turn.session.model_copy(update={"story_state": next_state})
    next_turn = committed_turn.turn.model_copy(
        update={
            "id": "turn-2",
            "idempotency_key": "turn-idempotency-2",
            "base_revisions": committed_turn.turn.base_revisions.model_copy(
                update={"story": 1}
            ),
            "state_delta_id": next_delta.id,
            "committed_story_revision": 2,
        }
    )

    with pytest.raises(StorageError, match="Finalized StorySession"):
        await SQLiteStorySessionCommitPort(database).commit_turn(
            next_session,
            next_delta,
            next_turn,
            store_expected_revision=finalized.store_revision,
            request_id="request-after-finalization",
            trace_id="trace-after-finalization",
        )

    assert await database.read_world(
        "SELECT status,story_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "finalized", "story_revision": 1}]
    assert await database.read_world("SELECT count(*) AS n FROM turn_transactions") == [
        {"n": 1}
    ]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 3}
    ]


@pytest.mark.parametrize(
    "stage", ["before_apply", "after_apply", "after_events", "before_commit"]
)
@pytest.mark.asyncio
async def test_episode_finalization_failure_rolls_back_episode_artifacts_and_session(
    database: DatabaseManager, stage: str
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)

    def fail_at(point: str) -> None:
        if point == stage:
            raise RuntimeError("injected finalization failure")

    database._fault_hook = fail_at
    with pytest.raises(RuntimeError, match="injected finalization failure"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(request)

    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 0}]
    assert await database.read_world(
        "SELECT count(*) AS n FROM character_episode_memories"
    ) == [{"n": 0}]
    assert await database.read_world(
        "SELECT count(*) AS n FROM episode_finalizations"
    ) == [{"n": 0}]
    assert await database.read_world(
        "SELECT status,committed_world_revision FROM story_sessions WHERE id='session-1'"
    ) == [{"status": "active", "committed_world_revision": 2}]
    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 2}
    ]
    assert await database.read_world("SELECT count(*) AS n FROM projection_outbox") == [
        {"n": 2}
    ]


@pytest.mark.asyncio
async def test_episode_finalization_replay_is_idempotent_and_binds_artifact_content(
    database: DatabaseManager,
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    repository = SQLiteEpisodeFinalizationRepository(database)
    committed = await repository.finalize(request)
    replay = await repository.finalize(
        replace(request, request_id="retry-request", trace_id="retry-trace")
    )

    assert replay.replayed is True
    assert replay.store_revision == committed.store_revision == 3
    assert await database.read_world("SELECT count(*) AS n FROM episodes") == [{"n": 1}]
    assert await database.read_world(
        "SELECT count(*) AS n FROM character_episode_memories"
    ) == [{"n": 1}]
    altered_artifacts = replace(
        request.artifacts,
        memories=(
            {
                **request.artifacts.memories[0],
                "summary": "Changed after commit.",
            },
        ),
    )
    with pytest.raises(IdempotencyConflict):
        await repository.finalize(replace(request, artifacts=altered_artifacts))


@pytest.mark.asyncio
async def test_episode_finalization_requires_exact_episode_artifact_ids(
    database: DatabaseManager,
):
    incomplete = replace(
        _request(),
        artifacts=replace(_request().artifacts, memories=()),
    )
    with pytest.raises(ValueError, match="episode artifact identities"):
        await SQLiteEpisodeFinalizationRepository(database).finalize(incomplete)

    assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == [
        {"n": 1}
    ]


@pytest.mark.asyncio
async def test_episode_bundle_read_during_finalization_sees_one_complete_snapshot(
    database: DatabaseManager, monkeypatch
):
    await _commit_first_turn(database)
    request = await _request_from_committed_turn(database)
    entered, release = threading.Event(), threading.Event()

    def pause_before_commit(stage: str) -> None:
        if stage == "before_commit":
            entered.set()
            assert release.wait(5)

    database._fault_hook = pause_before_commit
    repository = SQLiteEpisodeFinalizationRepository(database)
    original_read_world = database.read_world
    queries: list[str] = []

    async def track_read_world(sql: str, parameters: tuple = ()):
        queries.append(sql)
        return await original_read_world(sql, parameters)

    monkeypatch.setattr(database, "read_world", track_read_world)
    pending = asyncio.create_task(repository.finalize(request))
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        with pytest.raises(StorageError, match="Episode finalization was not found"):
            await repository.load("episode-1")
    finally:
        release.set()

    result = await pending
    assert result.episode == request.episode
    loaded = await repository.load("episode-1")
    assert loaded.episode == request.episode
    assert loaded.artifacts == request.artifacts
    assert len(queries) == 3
    assert all("WITH episode_artifacts" in query for query in queries)
