from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from ai.prompt_renderer import PromptRenderer
from application.context_compiler import CacheAwareContextCompiler
from application.context_plan import Layer, WorkerProfile
from application.gameplay_context import (
    GameplayCall,
    GameplayContextCoordinator,
    GameplayMode,
)
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.gameplay_context_repository import SQLiteGameplayContextRepository
from infrastructure.sqlite_runtime import sqlite3

OWNER_ID = "owner.state-test"
WORLD_ID = "world.state-test"
WORLDLINE_ID = "line.state-test"
SESSION_ID = "session.state-test"
PROTAGONIST_ID = "char.state-test"

# Values planted in the committed state that must never reach any model prompt.
CANARIES = (
    "actor.hidden-canary",
    "bootstrap.hidden-canary",
    "commitment.hidden-canary",
    "conflict.hidden-canary",
    "goal.hidden-canary",
    "local.hidden-canary",
    "secret.hidden-canary",
    "secret.revealed-canary",
)


def _story_state() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "story_session_id": SESSION_ID,
        "revision": 2,
        "turn": 3,
        "phase": "investigation",
        "scene": {
            "id": "scene.current",
            "location_id": "location.harbor",
            "active_character_ids": [PROTAGONIST_ID, "actor.hidden-canary"],
        },
        "world_time": "1349-03-01T08:00:00Z",
        "protagonist_goal": "goal.hidden-canary",
        "active_conflicts": ["conflict.hidden-canary"],
        "discovered_clue_ids": ["clue.discovered"],
        "secret_states": {
            "secret.hidden-canary": "hidden",
            "secret.revealed-canary": "revealed",
        },
        "commitments": {
            "hard_ids": ["commitment.hidden-canary"],
            "soft_ids": [],
        },
        "local_state": {"private": "local.hidden-canary"},
        "pressure": {"private": 0.9},
        "last_state_delta_id": "delta.current",
    }


@pytest_asyncio.fixture
async def committed_story_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", WORLD_ID)
    paths.canon.parent.mkdir(parents=True)
    with sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT")
        canon.execute("INSERT INTO canon_fixture VALUES ('canon', 'immutable')")

    database = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version)
    connection = sqlite3.connect(paths.world, isolation_level=None, timeout=5)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
            "world_time,commit_time,operation_json,result_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                7,
                WORLDLINE_ID,
                "commit.state-test",
                "request.digest.state-test",
                "request.state-test",
                "trace.state-test",
                "fixture-world-time",
                "fixture-commit-time",
                "{}",
                "{}",
            ),
        )
        connection.execute("INSERT INTO projection_outbox(revision,processed) VALUES (7,0)")
        connection.execute("UPDATE world_meta SET revision=7 WHERE singleton=1")
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
                PROTAGONIST_ID,
                "seed.state-test",
                0,
                0,
                0,
                2,
                "active",
                json.dumps(_story_state(), sort_keys=True),
                7,
            ),
        )
        connection.execute(
            "INSERT INTO story_session_bootstraps("
            "session_id,scenario_id,content_version,content_digest,bootstrap_json,"
            "opened_store_revision"
            ") VALUES (?,?,?,?,?,?)",
            (
                SESSION_ID,
                "scenario.state-test",
                "v1",
                "a" * 64,
                json.dumps(
                    {
                        "character": {
                            "identity": {
                                "id": PROTAGONIST_ID,
                                "display_name": "Protagonist",
                            },
                            "private_dossier": "bootstrap.hidden-canary",
                        }
                    },
                    sort_keys=True,
                ),
                7,
            ),
        )
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        await database.close()
        raise
    finally:
        connection.close()

    try:
        yield database
    finally:
        await database.close()


class _Profiles:
    def profile(self, mode: GameplayMode, consumer: str) -> WorkerProfile:
        return WorkerProfile(
            consumer,
            "state-layer-test.v1",
            "Return a typed proposal.",
            '{"type":"object"}',
        )


def _call(
    *,
    subject_id: str = PROTAGONIST_ID,
    mode: GameplayMode = GameplayMode.CHARACTER_REASONING,
    request_id: str = "request.state-test",
    task_json: str = '{"advice":"observe"}',
) -> GameplayCall:
    return GameplayCall(
        mode,
        OWNER_ID,
        WORLD_ID,
        WORLDLINE_ID,
        subject_id,
        SESSION_ID,
        task_json,
        request_id,
    )


def _coordinator(repository: SQLiteGameplayContextRepository) -> GameplayContextCoordinator:
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
async def test_committed_state_flows_through_domain_policy_and_compiler_without_hidden_data(
    committed_story_database,
) -> None:
    repository = SQLiteGameplayContextRepository(committed_story_database)
    coordinator = _coordinator(repository)
    call = _call()

    prepared = await coordinator.prepare(call)
    state_evidence = [item for item in prepared.request.evidence if item.layer == Layer.STATE]

    assert len(state_evidence) == 1
    evidence = state_evidence[0]
    assert evidence.kind == "checkpoint"
    assert evidence.source_revision == 2
    assert evidence.committed_revision == 7
    assert json.loads(evidence.content_json) == {
        "character_id": PROTAGONIST_ID,
        "discovered_clue_ids": ["clue.discovered"],
        "scene": {"id": "scene.current", "location_id": "location.harbor"},
        "story_revision": 2,
        "world_time": "1349-03-01T08:00:00Z",
    }

    invocation = next(
        state for state in repository._invocations.values() if state.materialized.call == call
    )
    projected = next(
        item
        for item in invocation.materialized.facts
        if item.evidence.source_id == evidence.source_id
    )
    assert projected.fact.known_by_subject_ids == (PROTAGONIST_ID,)
    assert projected.fact.public is False
    # The current scene is a *committed result the owner is entitled to see*, so
    # it rides the player-disclosure axis. It stays non-public: unrelated
    # consumers must still go through eligibility, not read it for free.
    assert projected.fact.disclosed_to_owner is True
    assert projected.fact.hidden is False

    authorization = await repository.authorize(prepared.request, prepared.recipe)
    plan = CacheAwareContextCompiler().compile(prepared.request, authorization, prepared.profile)
    compiled_state = [item for item in plan.ordered_evidence if item.layer == Layer.STATE]
    assert compiled_state == [evidence]

    rendered = PromptRenderer(b"s" * 32).render(plan)
    state_messages = [
        json.loads(message["content"])
        for message in rendered.messages()
        if message["role"] == "user"
        and json.loads(message["content"]).get("section") == "current_state"
    ]
    assert len(state_messages) == 1
    assert state_messages[0]["evidence"] == evidence.model_value()
    assert all(canary not in rendered.messages_json for canary in CANARIES)

    other_character = await coordinator.prepare(
        _call(
            subject_id="char.other",
            request_id="request.other-character",
            task_json=(
                '{"advice":"observe","visibility":{"public":true,'
                '"known_by":["char.other"],"disclosed_to_owner":true}}'
            ),
        )
    )
    assert not any(item.layer == Layer.STATE for item in other_character.request.evidence)

    # The narrative compiler is a player-disclosure scope, and the compiler
    # rejects any non-state-optional consumer that arrives without current state.
    # It must therefore reach the model with the committed scene -- through the
    # disclosure axis, while the character-knowledge axis stays exclusive to the
    # character reasoner.
    for mode, tag in ((GameplayMode.NARRATIVE_COMPILATION, "narrative"),):
        player = await coordinator.prepare(_call(mode=mode, request_id=f"request.{tag}"))
        player_state = [item for item in player.request.evidence if item.layer == Layer.STATE]
        assert len(player_state) == 1, tag

        player_authorization = await repository.authorize(player.request, player.recipe)
        player_plan = CacheAwareContextCompiler().compile(
            player.request, player_authorization, player.profile
        )
        assert [
            item for item in player_plan.ordered_evidence if item.layer == Layer.STATE
        ] == player_state, tag

        player_rendered = PromptRenderer(b"p" * 32).render(player_plan)
        assert all(canary not in player_rendered.messages_json for canary in CANARIES), tag


@pytest.mark.asyncio
async def test_advice_interpreter_reaches_the_model_with_its_own_state_projection(
    committed_story_database,
) -> None:
    """The live advice path must reach the model with a current-state view.

    `_ALLOWED_KINDS["advice_interpreter"]` is
    {observation, available_target, current_goal, pressure}, so the interpreter
    gets its own purpose-built projection rather than the narrative
    `checkpoint`, whose vocabulary it is not allowed to consume.
    """
    repository = SQLiteGameplayContextRepository(committed_story_database)
    coordinator = _coordinator(repository)
    advice = await coordinator.prepare(
        _call(
            mode=GameplayMode.ADVICE_INTERPRETATION,
            request_id="request.advice",
        )
    )
    authorization = await repository.authorize(advice.request, advice.recipe)
    plan = CacheAwareContextCompiler().compile(advice.request, authorization, advice.profile)

    state = [item for item in plan.ordered_evidence if item.layer == Layer.STATE]
    assert len(state) == 1
    # The kind must be one the advice vocabulary actually admits; the narrative
    # checkpoint is not, and reusing it is exactly what this projection avoids.
    assert state[0].kind == "observation"
    assert json.loads(state[0].content_json)["scene"] == {
        "id": "scene.current",
        "location_id": "location.harbor",
    }
    rendered = PromptRenderer(b"a" * 32).render(plan)
    assert all(canary not in rendered.messages_json for canary in CANARIES)

    # The narrative checkpoint stays out of the interpreter's evidence entirely.
    assert all(item.kind != "checkpoint" for item in plan.ordered_evidence)
