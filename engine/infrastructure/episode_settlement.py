"""Production post-COMMIT settlement for scenario-selected terminal turns.

Once a Story turn is durably committed, the runtime publishes its frozen
expression (BeatPlan + NarrativeBlock) and finalizes an Episode only when the
trusted scenario policy reports a terminal decision with a finalization recipe.
The authored Episode narrative is loaded from the packaged content; every
identity list, the world time, the secret states and the discovered clues are
bound from the committed turns, so production never reuses the acceptance
oracle. Settlement runs strictly after COMMIT: a failure here never rewrites a
committed fact and is replayed idempotently on the next attempt.
"""
from __future__ import annotations

import json
from pathlib import Path

from application.post_commit_expression import (
    CommittedExpressionInput,
    PostCommitExpressionService,
)
from application.scenario_policy import ScenarioPolicyPort
from application.story_turn_commit import StoryTurnCommitResult
from contracts import BeatPlan, Episode, TurnStatus

from .database_manager import DatabaseManager, RevisionConflict, StorageError
from .episode_finalization_repository import (
    EpisodeFinalizationArtifacts,
    EpisodeFinalizationRequest,
    SQLiteEpisodeFinalizationRepository,
)
from .story_bootstrap_repository import SQLiteStoryBootstrapRepository
from .story_session_repository import SQLiteStorySessionCommitPort


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ScenarioSettlementFailure(RuntimeError):
    """Structured post-COMMIT failure that leaves the committed turn intact."""

    def __init__(self, *, stage: str, code: str) -> None:
        super().__init__(code)
        self.stage = stage
        self.code = code


def _failure_code(error: Exception, fallback: str) -> str:
    if isinstance(error, RevisionConflict):
        return "revision_conflict"
    code = getattr(error, "code", None)
    if (
        isinstance(code, str)
        and code
        and len(code) <= 128
        and code.isascii()
        and all(char.islower() or char.isdigit() or char == "_" for char in code)
    ):
        return code
    return fallback


class ScenarioSettlement:
    """Publish frozen expression and finalize terminal scenario sessions."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        expression: PostCommitExpressionService,
        content_path: Path,
        scenario: ScenarioPolicyPort,
        frozen_expression: bool = True,
    ) -> None:
        self._database = database
        self._expression = expression
        self._content_path = Path(content_path)
        self._scenario = scenario
        self._bootstraps = SQLiteStoryBootstrapRepository(database)
        self._story = SQLiteStorySessionCommitPort(database)
        # A live turn narrates through the delivery pipeline, which publishes a
        # character segment the speech contract can authorize. The frozen
        # templates emit speakerless narration, so publishing both for one turn
        # would be a genuine double-write, not an idempotent replay.
        self._frozen_expression = frozen_expression
        self._episodes = SQLiteEpisodeFinalizationRepository(database)

    @property
    def episodes(self) -> SQLiteEpisodeFinalizationRepository:
        return self._episodes

    async def settle(self, result: StoryTurnCommitResult) -> None:
        """Idempotently settle one committed turn and report post-COMMIT failures."""
        await self._settle(result, publish_expression=True)

    async def finalize_only(self, result: StoryTurnCommitResult) -> None:
        """Finalize a terminal scenario without re-publishing its expression."""
        await self._settle(result, publish_expression=False)

    async def _settle(
        self,
        result: StoryTurnCommitResult,
        *,
        publish_expression: bool,
    ) -> None:
        try:
            finalization = await self._finalization_context(result)
            if finalization is not None and await self._episode_is_finalized(
                result.session.id
            ):
                return
        except ScenarioSettlementFailure:
            raise
        except Exception as exc:  # noqa: BLE001 - classify post-COMMIT lookup failures
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code=_failure_code(exc, "episode_preflight_failed"),
            ) from exc

        try:
            if publish_expression and self._frozen_expression:
                await self._publish_expression(result)
        except Exception as exc:  # noqa: BLE001 - the turn is already durable
            raise ScenarioSettlementFailure(
                stage="expression_publish",
                code=_failure_code(exc, "expression_publish_failed"),
            ) from exc

        try:
            await self._finalize_terminal_scenario(result, finalization)
        except ScenarioSettlementFailure:
            raise
        except Exception as exc:  # noqa: BLE001 - report, never disguise, failure
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code=_failure_code(exc, "episode_finalize_failed"),
            ) from exc

    async def _publish_expression(self, result: StoryTurnCommitResult) -> None:
        turn = result.turn
        if turn.committed_story_revision is None:
            return
        await self._expression.publish(
            turn_number=turn.committed_story_revision,
            commit=CommittedExpressionInput(
                session_id=turn.session_id,
                turn_id=turn.id,
                story_revision=turn.committed_story_revision,
                state_delta_id=result.delta.id,
                turn_status=TurnStatus.COMMITTED,
            ),
        )

    async def _finalize_terminal_scenario(
        self,
        result: StoryTurnCommitResult,
        finalization: tuple[object, object] | None,
    ) -> None:
        if finalization is None:
            return
        session = result.session
        bootstrap, recipe = finalization
        if await self._episode_is_finalized(session.id):
            return

        target_revision = result.turn.committed_story_revision
        target_state = session.story_state
        current_session = await self._story.load_session(session.id)
        if (
            target_revision is None
            or target_state.revision != target_revision
            or current_session.story_state.revision != target_revision
            or current_session.story_state != target_state
        ):
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="session_advanced",
            )
        if current_session.status.value not in {"active", "closing"}:
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="session_not_finalizable",
            )

        committed_evidence = frozenset(
            current_session.story_state.discovered_clue_ids or ()
        )
        decision = self._scenario.decision(current_session, committed_evidence)
        current_recipe = self._scenario.finalization_recipe(
            bootstrap, current_session
        )
        if not decision.terminal or current_recipe != recipe:
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="session_advanced",
            )

        authored = _read_json(self._content_path.parent / recipe.episode_filename)
        memory_template = _read_json(
            self._content_path.parent / recipe.memory_filename
        )
        artifacts = await self._build_artifacts(current_session, memory_template)
        episode = self._build_episode(current_session, authored, artifacts)
        revision_rows = await self._database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        )
        if (
            len(revision_rows) != 1
            or type(revision_rows[0]["revision"]) is not int
            or revision_rows[0]["revision"] < 0
        ):
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="world_revision_unavailable",
            )
        await self._episodes.finalize(
            EpisodeFinalizationRequest(
                session_id=current_session.id,
                expected_story_revision=current_session.story_state.revision,
                world_time=current_session.story_state.world_time or "",
                expected_store_revision=revision_rows[0]["revision"],
                idempotency_key=f"finalize-episode-{session.id}",
                request_id=f"request_finalize_{session.id}",
                trace_id=f"trace_finalize_{session.id}",
                episode=episode,
                artifacts=artifacts,
            )
        )

    async def _finalization_context(
        self, result: StoryTurnCommitResult
    ) -> tuple[object, object] | None:
        session = result.session
        if session.id != result.turn.session_id or result.delta.turn_id != result.turn.id:
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="episode_source_identity_mismatch",
            )
        committed_evidence = frozenset(
            session.story_state.discovered_clue_ids or ()
        )
        decision = self._scenario.decision(session, committed_evidence)
        if not decision.terminal:
            return None
        if (
            result.turn.committed_story_revision is None
            or session.story_state.revision != result.turn.committed_story_revision
        ):
            raise ScenarioSettlementFailure(
                stage="episode_finalize",
                code="session_advanced",
            )
        bootstrap = await self._bootstraps.require(session.id)
        recipe = self._scenario.finalization_recipe(bootstrap, session)
        if recipe is None:
            return None
        return bootstrap, recipe

    async def _episode_is_finalized(self, session_id: str) -> bool:
        try:
            await self._episodes.load_by_session(session_id)
        except StorageError as exc:
            rows = await self._database.read_world(
                "SELECT id FROM episodes WHERE session_id=?", (session_id,)
            )
            if not rows:
                return False
            raise ScenarioSettlementFailure(
                stage="episode_lookup",
                code="episode_bundle_unavailable",
            ) from exc
        return True

    async def _build_artifacts(
        self, session, memory_template: dict
    ) -> EpisodeFinalizationArtifacts:
        session_id = session.id
        worldline_id = session.worldline_id
        world_id = session.world_id
        character_rows = await self._database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_character_changes "
            "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
            (session_id,),
        )
        relationship_rows = await self._database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_relationship_changes "
            "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
            (session_id,),
        )
        knowledge_rows = await self._database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_knowledge_changes "
            "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
            (session_id,),
        )
        world_event_rows = await self._database.read_world(
            "SELECT id,turn_id,payload_json FROM turn_world_events "
            "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
            (session_id,),
        )
        character_events = tuple(
            {"id": row["id"], "change": json.loads(row["payload_json"])}
            for row in character_rows
        )
        relationship_events = tuple(
            {"id": row["id"], "change": json.loads(row["payload_json"])}
            for row in relationship_rows
        )
        knowledge_changes = tuple(
            _knowledge_artifact(row, worldline_id=worldline_id)
            for row in knowledge_rows
        )
        episode_id = f"episode_{session_id}"
        world_events = tuple(
            _world_event_artifact(
                row,
                episode_id=episode_id,
                world_id=world_id,
                worldline_id=worldline_id,
            )
            for row in world_event_rows
        )
        source_ids = [row["id"] for row in character_rows]
        return EpisodeFinalizationArtifacts(
            character_events=character_events,
            relationship_events=relationship_events,
            knowledge_changes=knowledge_changes,
            memories=(_memory_artifact(memory_template, source_ids),),
            world_events=world_events,
        )

    def _build_episode(
        self, session, authored: dict, artifacts: EpisodeFinalizationArtifacts
    ) -> Episode:
        state = session.story_state
        return Episode.model_validate(
            {
                **authored,
                "id": f"episode_{session.id}",
                "end_world_time": state.world_time,
                "secret_states": state.secret_states,
                "discovered_clue_ids": state.discovered_clue_ids or [],
                # The authored narrative (title/ending/unresolved_threads) is the
                # scenario truth; every identity list is bound from the real
                # committed settlement rows, never from the acceptance oracle.
                "character_event_ids": [i["id"] for i in artifacts.character_events],
                "relationship_event_ids": [
                    i["id"] for i in artifacts.relationship_events
                ],
                "knowledge_change_ids": [i["id"] for i in artifacts.knowledge_changes],
                "memory_ids": [i["id"] for i in artifacts.memories],
                "world_event_ids": [i["id"] for i in artifacts.world_events],
            }
        )


def _knowledge_artifact(row: dict, *, worldline_id: str) -> dict:
    candidate = json.loads(row["payload_json"])
    return {
        "schema_version": "1.0",
        "id": row["id"],
        "character_id": candidate["character_id"],
        "worldline_id": worldline_id,
        "proposition_id": candidate["proposition_id"],
        "certainty": candidate["certainty"],
        "source": {
            "type": "investigation",
            "ref": candidate["source_ref"],
            "reliability": candidate["certainty"],
        },
        "status": candidate["status"],
        "revision": 0,
    }


def _world_event_artifact(
    row: dict, *, episode_id: str, world_id: str, worldline_id: str
) -> dict:
    candidate = json.loads(row["payload_json"])
    return {
        "schema_version": "1.0",
        "id": row["id"],
        "world_id": world_id,
        "worldline_id": worldline_id,
        "event_type": candidate["event_type"],
        "actors": candidate["actors"],
        "targets": candidate["targets"],
        "cause": {"episode_id": episode_id, "story_turn_id": row["turn_id"]},
        "payload": candidate["payload"],
        "visibility": candidate["visibility"],
        "persistence": "episode",
        "importance": "world",
        "revision": 0,
    }


def _memory_artifact(template: dict, source_ids: list[str]) -> dict:
    return {**template, "source_ids": list(source_ids)}


class _SettlementBeatPlanPort:
    """Adapt the durable BeatPlan repository to the expression BeatPlanPort.

    `PostCommitExpressionService` publishes a BeatPlan that carries the session
    and source revision but not the turn id, while the durable repository binds
    each BeatPlan to its committed `turn_transactions` row. The turn is resolved
    deterministically from `(session_id, source_story_revision)`, the same
    binding the BeatPlan row itself stores.
    """

    def __init__(self, repository, database: DatabaseManager) -> None:
        self._repository = repository
        self._database = database

    async def publish(self, beat_plan: BeatPlan) -> None:
        if not isinstance(beat_plan, BeatPlan):
            raise TypeError("BeatPlan publication requires a typed BeatPlan")
        rows = await self._database.read_world(
            "SELECT id FROM turn_transactions "
            "WHERE session_id=? AND committed_story_revision=?",
            (beat_plan.story_session_id, beat_plan.source_story_revision),
        )
        if len(rows) != 1:
            raise LookupError("committed turn for BeatPlan is unavailable")
        await self._repository.publish(
            turn_id=rows[0]["id"], beat_plan=beat_plan
        )


class SettlingCommitPort:
    """Commit port decorator that settles expression and Episode after COMMIT.

    The durable turn commit is delegated untouched; settlement runs strictly
    after it, so a post-COMMIT failure can never undo an authoritative fact.
    """

    def __init__(self, port, settlement: ScenarioSettlement) -> None:
        self._port = port
        self._settlement = settlement

    async def load_session(self, session_id: str):
        return await self._port.load_session(session_id)

    async def load_delta(self, delta_id: str):
        return await self._port.load_delta(delta_id)

    async def load_turn(self, turn_id: str):
        return await self._port.load_turn(turn_id)

    async def commit_turn(
        self,
        session,
        delta,
        turn,
        *,
        store_expected_revision: int,
        request_id: str,
        trace_id: str,
    ):
        result = await self._port.commit_turn(
            session,
            delta,
            turn,
            store_expected_revision=store_expected_revision,
            request_id=request_id,
            trace_id=trace_id,
        )
        # The "immediately after commit" acceptance checkpoint is announced by
        # the commit port itself, which both wirings share. It used to be
        # announced here, where the durable path never reaches: a boundary only
        # the synchronous methods cross is not a boundary the run is judged on.
        await self._settlement.settle(result)
        return result
