from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from ai.prompt_renderer import PromptRenderer
from application.context_compiler import CacheAwareContextCompiler
from application.context_plan import ContextError, Layer, WorkerProfile
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


def _bootstrap_payload(presentation: object = ...) -> dict[str, object]:
    """The bootstrap fixture, with its public-name allowlist overridable.

    ``...`` keeps the original payload, which declares no ``presentation`` at
    all — so the canary in the scene has no public name and the roster is empty.
    """
    payload: dict[str, object] = {
        "character": {
            "identity": {"id": PROTAGONIST_ID, "display_name": "Protagonist"},
            "private_dossier": "bootstrap.hidden-canary",
        }
    }
    if presentation is not ...:
        payload["presentation"] = presentation
    return payload


def _scene(*active_character_ids: str) -> dict[str, object]:
    return {
        "id": "scene.current",
        "location_id": "location.harbor",
        "active_character_ids": list(active_character_ids),
    }


@pytest_asyncio.fixture
async def committed_story_database(tmp_path: Path):
    database = await _open_story_database(tmp_path)
    try:
        yield database
    finally:
        await database.close()


async def _open_story_database(
    tmp_path: Path,
    *,
    scene: dict[str, object] | None = None,
    presentation: object = ...,
) -> DatabaseManager:
    """Build the committed-session fixture, with the roster inputs overridable.

    ``scene`` replaces the whole scene mapping and ``presentation`` replaces the
    bootstrap's ``presentation`` object; ``...`` means "leave as declared". Both
    are parameters because the roster projection reads exactly these two inputs
    and nothing else, and a fixture that cannot vary them can only ever test the
    one case where nobody is castable.
    """
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
                json.dumps(
                    _story_state() if scene is None else {**_story_state(), "scene": scene},
                    sort_keys=True,
                ),
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
                json.dumps(_bootstrap_payload(presentation), sort_keys=True),
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

    return database


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


async def _state_evidence(
    repository: SQLiteGameplayContextRepository,
    *,
    mode: GameplayMode,
    tag: str,
) -> list:
    coordinator = _coordinator(repository)
    prepared = await coordinator.prepare(_call(mode=mode, request_id=f"request.{tag}"))
    authorization = await repository.authorize(prepared.request, prepared.recipe)
    plan = CacheAwareContextCompiler().compile(
        prepared.request, authorization, prepared.profile
    )
    return [item for item in plan.ordered_evidence if item.layer == Layer.STATE]


async def _roster_database(tmp_path: Path, *, scene, presentation) -> DatabaseManager:
    return await _open_story_database(
        tmp_path, scene=scene, presentation=presentation
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
        # checkpoint + scene_roster. The roster is its own evidence on purpose;
        # see `test_the_scene_roster_rides_its_own_evidence_and_not_the_checkpoint`.
        assert [item.kind for item in player_state] == ["checkpoint", "scene_roster"], tag

        player_authorization = await repository.authorize(player.request, player.recipe)
        player_plan = CacheAwareContextCompiler().compile(
            player.request, player_authorization, player.profile
        )
        # The compiler imposes its own order, so compare as a multiset: the claim
        # is that it kept exactly the state evidence it was handed, not that it
        # kept it in the order it arrived.
        planned_state = [
            item for item in player_plan.ordered_evidence if item.layer == Layer.STATE
        ]
        assert sorted(
            json.dumps(item.model_value(), sort_keys=True) for item in planned_state
        ) == sorted(
            json.dumps(item.model_value(), sort_keys=True) for item in player_state
        ), tag

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


# --- scene_roster (ADR-006 D2 / D5) ------------------------------------------

NAMES = {
    "char.state-test": "Player",
    "npc_doctor_morris": "莫里斯医生",
    "npc_jonathan_vale": "Jonathan",
}


@pytest.mark.asyncio
async def test_the_castable_roster_reaches_the_narrative_compiler_as_public_labels(
    tmp_path: Path,
) -> None:
    """The roster is what D3 will bind speech lines to, so it must arrive.

    And it must arrive as labels. The publication layer binds a voice by
    canonical id, but handing that id to the model would make every canonical
    identifier a prompt away from the narrator — the same leak
    ``disclosed_turn_facts`` exists to prevent for clues.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("char.state-test", "npc_doctor_morris", "npc_jonathan_vale"),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-labels",
        )
    finally:
        await database.close()

    roster = [item for item in state if item.kind == "scene_roster"]
    assert len(roster) == 1
    content = json.loads(roster[0].content_json)
    assert content["castable"] == ["莫里斯医生", "Jonathan"]
    assert content["scene_id"] == "scene.current"
    for character_id in NAMES:
        assert character_id not in roster[0].content_json


@pytest.mark.asyncio
async def test_the_trusted_side_keeps_the_ids_the_publication_layer_binds_by(
    tmp_path: Path,
) -> None:
    """Labels reach the model; ids stay where the voice is bound.

    Without the id on the authorized side there is nothing for the publication
    layer to attach a voice to, and the roster would be decoration.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("npc_doctor_morris"),
        presentation={"character_display_names": NAMES},
    )
    call = _call(mode=GameplayMode.NARRATIVE_COMPILATION, request_id="request.trusted")
    try:
        repository = SQLiteGameplayContextRepository(database)
        await _coordinator(repository).prepare(call)
        invocation = next(
            state
            for state in repository._invocations.values()
            if state.materialized.call == call
        )
        projected = next(
            item
            for item in invocation.materialized.facts
            if item.evidence.kind == "scene_roster"
        )
    finally:
        await database.close()

    assert json.loads(projected.fact.content_json)["castable"] == [
        {"character_id": "npc_doctor_morris", "label": "莫里斯医生"}
    ]
    assert projected.fact.known_by_subject_ids == (PROTAGONIST_ID,)
    assert projected.fact.public is False
    assert projected.fact.disclosed_to_owner is True


@pytest.mark.asyncio
async def test_no_consumer_but_the_narrative_compiler_is_offered_the_roster(
    tmp_path: Path,
) -> None:
    """Invariant 6, enforced by construction rather than by convention.

    Every other consumer of ``checkpoint`` would learn who else is in the room.
    A character may not know that, so the roster is admitted by one consumer
    only — and this is the test that would catch a second one appearing.

    The sweep is exhaustive over ``GameplayMode`` and the expected mapping is
    spelled out whole. Modes this fixture cannot serve are skipped by their
    ``ContextError``; had the assertion been "nobody else has it", a mode that
    silently stopped producing state at all would have passed unnoticed. Naming
    all three state-bearing modes means a fourth one appearing fails here.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("char.state-test", "npc_doctor_morris"),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        coordinator = _coordinator(repository)
        offered: dict[GameplayMode, list[str]] = {}
        for mode in GameplayMode:
            try:
                prepared = await coordinator.prepare(
                    _call(mode=mode, request_id=f"roster-sweep-{mode.value}")
                )
            except ContextError:
                continue
            kinds = [
                item.kind
                for item in prepared.request.evidence
                if item.layer == Layer.STATE
            ]
            if kinds:
                offered[mode] = kinds
    finally:
        await database.close()

    # The other two keep their scene: the roster is withheld, not the state.
    assert offered == {
        GameplayMode.ADVICE_INTERPRETATION: ["observation"],
        GameplayMode.CHARACTER_REASONING: ["checkpoint"],
        GameplayMode.NARRATIVE_COMPILATION: ["checkpoint", "scene_roster"],
    }


@pytest.mark.asyncio
async def test_the_roster_never_rides_the_shared_checkpoint(tmp_path: Path) -> None:
    """The reason the roster is its own evidence, stated as a test.

    Were it folded into ``checkpoint``, the assertions in
    ``test_no_consumer_but_the_narrative_compiler_is_offered_the_roster`` would
    still pass — the other consumers would simply be handed the roster along
    with the scene. This is the assertion that fails first.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("npc_doctor_morris"),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-separate",
        )
    finally:
        await database.close()

    checkpoint = next(item for item in state if item.kind == "checkpoint")
    assert "active_character_ids" not in checkpoint.content_json
    assert "castable" not in checkpoint.content_json
    assert "莫里斯医生" not in checkpoint.content_json


@pytest.mark.asyncio
async def test_an_undeclared_roster_projects_no_roster_evidence(tmp_path: Path) -> None:
    """Absent is not empty.

    A session that never declared a roster has not said "nobody is here", and
    projecting an empty one would tell the model exactly that.
    """
    database = await _roster_database(
        tmp_path,
        scene={"id": "scene.current", "location_id": "location.harbor"},
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-undeclared",
        )
    finally:
        await database.close()

    assert [item.kind for item in state] == ["checkpoint"]


@pytest.mark.asyncio
async def test_an_empty_scene_still_projects_an_empty_roster(tmp_path: Path) -> None:
    """The other half of absent-is-not-empty: this one *is* a claim."""
    database = await _roster_database(
        tmp_path,
        scene=_scene(),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-empty",
        )
    finally:
        await database.close()

    roster = next(item for item in state if item.kind == "scene_roster")
    assert json.loads(roster.content_json)["castable"] == []


@pytest.mark.asyncio
async def test_a_character_with_no_public_name_is_omitted_rather_than_named_by_id(
    tmp_path: Path,
) -> None:
    """Fail-closed, exactly as the clue projection is.

    The scene here names someone the content pack gives no public name for.
    Emitting their canonical id would put ``actor.hidden-canary`` in front of
    the narrator — turning a missing label into a disclosure.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("npc_doctor_morris", "actor.hidden-canary"),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-unnamed",
        )
        rendered = None
        coordinator = _coordinator(repository)
        prepared = await coordinator.prepare(
            _call(
                mode=GameplayMode.NARRATIVE_COMPILATION, request_id="request.roster-render"
            )
        )
        authorization = await repository.authorize(prepared.request, prepared.recipe)
        plan = CacheAwareContextCompiler().compile(
            prepared.request, authorization, prepared.profile
        )
        rendered = PromptRenderer(b"r" * 32).render(plan).messages_json
    finally:
        await database.close()

    roster = next(item for item in state if item.kind == "scene_roster")
    assert json.loads(roster.content_json)["castable"] == ["莫里斯医生"]
    assert "actor.hidden-canary" not in rendered


@pytest.mark.asyncio
async def test_the_player_avatar_is_excluded_from_the_projected_roster(
    tmp_path: Path,
) -> None:
    """ADR-006 D5, at the boundary the model actually sees.

    The protagonist is given a public name in ``NAMES`` on purpose. Without one
    the label filter would drop them first, the exclusion would never run, and
    this test would pass for the wrong reason — removing the exclusion entirely
    would leave it green.
    """
    assert PROTAGONIST_ID in NAMES

    database = await _roster_database(
        tmp_path,
        scene=_scene("char.state-test", "npc_doctor_morris"),
        presentation={"character_display_names": NAMES},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-d5",
        )
    finally:
        await database.close()

    roster = next(item for item in state if item.kind == "scene_roster")
    assert json.loads(roster.content_json)["castable"] == ["莫里斯医生"]


@pytest.mark.asyncio
async def test_a_malformed_name_table_casts_nobody_rather_than_failing_the_read(
    tmp_path: Path,
) -> None:
    """Fail-closed at the reader, not fail-open at the model.

    Anything that is not a string-to-string table yields an empty one, so the
    worst outcome is a silent narrator. Trusting a malformed table instead would
    put ``None`` or an int in front of the model as somebody's name.
    """
    database = await _roster_database(
        tmp_path,
        scene=_scene("npc_doctor_morris"),
        presentation={"character_display_names": {"npc_doctor_morris": 7}},
    )
    try:
        repository = SQLiteGameplayContextRepository(database)
        state = await _state_evidence(
            repository,
            mode=GameplayMode.NARRATIVE_COMPILATION,
            tag="roster-malformed",
        )
    finally:
        await database.close()

    roster = next(item for item in state if item.kind == "scene_roster")
    assert json.loads(roster.content_json)["castable"] == []
