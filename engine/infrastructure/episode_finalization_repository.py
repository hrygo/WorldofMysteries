"""Atomic world.db persistence for finalized Episodes and their domain artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from contracts import Episode, StoryState

from .database_manager import (
    CommitRequest,
    DatabaseManager,
    DomainTransaction,
    IdempotencyConflict,
    RevisionConflict,
    StorageError,
    StoredEvent,
    _json,
)


@dataclass(frozen=True, slots=True)
class EpisodeFinalizationArtifacts:
    """Typed artifact groups referenced by one Episode's immutable identity lists."""

    character_events: tuple[dict[str, object], ...] = ()
    relationship_events: tuple[dict[str, object], ...] = ()
    knowledge_changes: tuple[dict[str, object], ...] = ()
    memories: tuple[dict[str, object], ...] = ()
    world_events: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodeFinalizationRequest:
    session_id: str
    expected_story_revision: int
    world_time: str
    expected_store_revision: int
    idempotency_key: str
    request_id: str
    trace_id: str
    episode: Episode
    artifacts: EpisodeFinalizationArtifacts


@dataclass(frozen=True, slots=True)
class EpisodeFinalizationResult:
    episode: Episode
    artifacts: EpisodeFinalizationArtifacts
    store_revision: int
    replayed: bool


_ARTIFACT_GROUPS = (
    ("character_events", "character_event_ids", "episode_character_events", False),
    ("relationship_events", "relationship_event_ids", "episode_relationship_events", False),
    ("knowledge_changes", "knowledge_change_ids", "episode_knowledge_changes", False),
    ("memories", "memory_ids", "character_episode_memories", True),
    ("world_events", "world_event_ids", "episode_world_events", False),
)

_ARTIFACT_SCHEMAS = {
    "knowledge_changes": "character_knowledge.schema.json",
    "memories": "character_memory.schema.json",
    "world_events": "world_event.schema.json",
}

_SOURCE_TABLES = (
    ("character_events", "turn_character_changes"),
    ("relationship_events", "turn_relationship_changes"),
    ("knowledge_changes", "turn_knowledge_changes"),
    ("world_events", "turn_world_events"),
)

_LOAD_EPISODE_BUNDLE_SQL = """
WITH episode_artifacts(kind,artifact_id,ordinal,character_id,payload_json) AS (
    SELECT 'character_events',artifact_id,ordinal,NULL,payload_json
    FROM episode_character_events WHERE episode_id=?
    UNION ALL
    SELECT 'relationship_events',artifact_id,ordinal,NULL,payload_json
    FROM episode_relationship_events WHERE episode_id=?
    UNION ALL
    SELECT 'knowledge_changes',artifact_id,ordinal,NULL,payload_json
    FROM episode_knowledge_changes WHERE episode_id=?
    UNION ALL
    SELECT 'memories',artifact_id,ordinal,character_id,payload_json
    FROM character_episode_memories WHERE episode_id=?
    UNION ALL
    SELECT 'world_events',artifact_id,ordinal,NULL,payload_json
    FROM episode_world_events WHERE episode_id=?
)
SELECT episodes.payload_json AS episode_payload,
       episode_finalizations.committed_world_revision AS store_revision,
       episode_artifacts.kind AS artifact_kind,
       episode_artifacts.artifact_id,
       episode_artifacts.character_id AS artifact_character_id,
       episode_artifacts.payload_json AS artifact_payload
FROM episodes
JOIN episode_finalizations ON episode_finalizations.episode_id=episodes.id
LEFT JOIN episode_artifacts ON 1=1
WHERE episodes.id=?
ORDER BY episode_artifacts.kind,episode_artifacts.ordinal
"""


@lru_cache(maxsize=None)
def _artifact_validator(group_name: str) -> Draft202012Validator | None:
    schema_name = _ARTIFACT_SCHEMAS.get(group_name)
    if schema_name is None:
        return None
    schema_path = (
        Path(__file__).resolve().parents[2] / "contracts" / "schemas" / schema_name
    )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, TypeError, ValueError, SchemaError):
        raise StorageError("Episode artifact contract is unavailable") from None
    return Draft202012Validator(schema)


def _freeze_payload(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise StorageError("Episode artifact must be an object")
    try:
        encoded = _json(dict(value))
        frozen = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise StorageError("Episode artifact is invalid") from None
    if not isinstance(frozen, dict):
        raise StorageError("Episode artifact must be an object")
    return frozen


def _freeze_artifacts(
    episode: Episode, artifacts: EpisodeFinalizationArtifacts
) -> EpisodeFinalizationArtifacts:
    if not isinstance(artifacts, EpisodeFinalizationArtifacts):
        raise StorageError("Episode finalization artifacts are invalid")
    frozen_groups: dict[str, tuple[dict[str, object], ...]] = {}
    for group_name, episode_field, _table, is_memory in _ARTIFACT_GROUPS:
        records = getattr(artifacts, group_name)
        if not isinstance(records, tuple):
            raise StorageError("Episode artifact groups must be immutable tuples")
        frozen = tuple(_freeze_payload(item) for item in records)
        if group_name in {"character_events", "relationship_events"} and any(
            set(item) != {"id", "change"} or not isinstance(item.get("change"), dict)
            for item in frozen
        ):
            raise StorageError("Episode artifact does not satisfy its contract")
        validator = _artifact_validator(group_name)
        if validator is not None:
            try:
                for item in frozen:
                    validator.validate(item)
            except ValidationError:
                raise StorageError(
                    "Episode artifact does not satisfy its contract"
                ) from None
        ids = [item.get("id") for item in frozen]
        expected_ids = list(getattr(episode, episode_field) or [])
        if ids != expected_ids or any(
            not isinstance(item, str) or not item.strip() for item in ids
        ):
            raise ValueError("episode artifact identities must match the Episode")
        if is_memory and any(
            not isinstance(item.get("character_id"), str)
            or not item["character_id"].strip()
            for item in frozen
        ):
            raise ValueError("character memory requires a character identity")
        frozen_groups[group_name] = frozen
    return EpisodeFinalizationArtifacts(**frozen_groups)


def _load_committed_story_evidence(
    tx: DomainTransaction, session_id: str
) -> dict[str, object]:
    turns = tx.execute(
        "SELECT id,state_delta_id FROM turn_transactions WHERE session_id=?",
        (session_id,),
    )
    if not turns:
        raise StorageError("Episode finalization requires committed Story evidence")
    changes: dict[str, dict[str, tuple[str, dict[str, object]]]] = {}
    character_ids: set[str] = set()
    for group_name, table in _SOURCE_TABLES:
        group: dict[str, tuple[str, dict[str, object]]] = {}
        rows = tx.execute(
            f"SELECT id,turn_id,payload_json FROM {table} WHERE session_id=?",
            (session_id,),
        )
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                raise StorageError("Committed Story evidence is invalid") from None
            if not isinstance(payload, dict):
                raise StorageError("Committed Story evidence is invalid")
            group[row["id"]] = (row["turn_id"], payload)
            for field in ("character_id", "from_character_id", "to_character_id"):
                value = payload.get(field)
                if isinstance(value, str) and value:
                    character_ids.add(value)
            for field in ("actors", "targets"):
                values = payload.get(field)
                if isinstance(values, list):
                    character_ids.update(
                        value for value in values if isinstance(value, str) and value
                    )
        changes[group_name] = group
    source_permissions: dict[str, set[str]] = {}
    for group_name, group in changes.items():
        for change_id, (_turn_id, payload) in group.items():
            if group_name == "character_events":
                allowed = {payload.get("character_id")}
            elif group_name == "relationship_events":
                allowed = {
                    payload.get("from_character_id"),
                    payload.get("to_character_id"),
                }
            elif group_name == "knowledge_changes":
                allowed = {payload.get("character_id")}
            else:
                visibility = payload.get("visibility")
                if not isinstance(visibility, dict):
                    allowed = set()
                elif visibility.get("public") is True:
                    allowed = set(character_ids)
                else:
                    known_by = visibility.get("known_by", [])
                    allowed = (
                        set(known_by)
                        if isinstance(known_by, list)
                        else set()
                    )
            source_permissions[change_id] = {
                value for value in allowed if isinstance(value, str) and value
            }
    return {
        "changes": changes,
        "character_ids": character_ids,
        "source_permissions": source_permissions,
    }


def _validate_committed_story_evidence(
    *,
    episode: Episode,
    artifacts: EpisodeFinalizationArtifacts,
    session: Mapping[str, object],
    evidence: Mapping[str, object],
    story_state: StoryState,
) -> None:
    changes = evidence["changes"]
    source_permissions = evidence["source_permissions"]
    character_ids = evidence["character_ids"] | {session["protagonist_id"]}
    if (
        episode.secret_states != story_state.secret_states
        or (episode.discovered_clue_ids or [])
        != (story_state.discovered_clue_ids or [])
        or episode.unresolved_threads != (story_state.active_conflicts or [])
        or episode.end_world_time != story_state.world_time
    ):
        raise StorageError("Episode facts do not match committed StoryState")

    def source_for(group_name: str, artifact: Mapping[str, object]):
        artifact_id = artifact.get("id")
        group = changes[group_name]
        if not isinstance(artifact_id, str) or artifact_id not in group:
            raise StorageError("Episode artifact lacks committed Story evidence")
        return group[artifact_id]

    for artifact in artifacts.character_events:
        _turn_id, candidate = source_for("character_events", artifact)
        if (
            set(artifact) != {"id", "change"}
            or artifact.get("change") != candidate
        ):
            raise StorageError("Episode artifact lacks committed Story evidence")

    for artifact in artifacts.relationship_events:
        _turn_id, candidate = source_for("relationship_events", artifact)
        if set(artifact) != {"id", "change"} or artifact.get("change") != candidate:
            raise StorageError("Episode artifact lacks committed Story evidence")

    for artifact in artifacts.knowledge_changes:
        _turn_id, candidate = source_for("knowledge_changes", artifact)
        source = artifact.get("source")
        if (
            artifact.get("worldline_id") != session["worldline_id"]
            or artifact.get("character_id") != candidate.get("character_id")
            or artifact.get("proposition_id") != candidate.get("proposition_id")
            or artifact.get("certainty") != candidate.get("certainty")
            or artifact.get("status") != candidate.get("status")
            or not isinstance(source, dict)
            or source.get("ref") != candidate.get("source_ref")
        ):
            raise StorageError("Episode artifact lacks committed Story evidence")

    for artifact in artifacts.memories:
        sources = artifact.get("source_ids")
        if (
            artifact.get("worldline_id") != session["worldline_id"]
            or artifact.get("character_id") not in character_ids
            or not isinstance(sources, list)
            or not sources
            or any(
                source not in source_permissions
                or artifact.get("character_id")
                not in source_permissions.get(source, set())
                for source in sources
            )
        ):
            raise StorageError("Episode artifact lacks committed Story evidence")

    for artifact in artifacts.world_events:
        turn_id, candidate = source_for("world_events", artifact)
        cause = artifact.get("cause")
        if (
            artifact.get("world_id") != session["world_id"]
            or artifact.get("worldline_id") != session["worldline_id"]
            or artifact.get("event_type") != candidate.get("event_type")
            or artifact.get("actors") != candidate.get("actors")
            or artifact.get("targets") != candidate.get("targets")
            or artifact.get("payload") != candidate.get("payload")
            or artifact.get("visibility") != candidate.get("visibility")
            or not isinstance(cause, dict)
            or cause.get("episode_id") != episode.id
            or cause.get("story_turn_id") != turn_id
        ):
            raise StorageError("Episode artifact lacks committed Story evidence")


def _artifact_payloads(artifacts: EpisodeFinalizationArtifacts) -> dict[str, object]:
    return {
        group_name: list(getattr(artifacts, group_name))
        for group_name, _episode_field, _table, _is_memory in _ARTIFACT_GROUPS
    }


class SQLiteEpisodeFinalizationRepository:
    """Commits one Episode and its referenced domain artifacts in world.db."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def finalize(
        self, request: EpisodeFinalizationRequest
    ) -> EpisodeFinalizationResult:
        if not isinstance(request, EpisodeFinalizationRequest):
            raise StorageError("Episode finalization request is invalid")
        if not isinstance(request.episode, Episode):
            raise StorageError("Episode finalization requires a validated Episode")
        if (
            not isinstance(request.session_id, str)
            or not request.session_id.strip()
            or len(request.session_id) > 256
            or "\x00" in request.session_id
        ):
            raise StorageError("Episode finalization session identity is invalid")
        if (
            isinstance(request.expected_story_revision, bool)
            or not isinstance(request.expected_story_revision, int)
            or request.expected_story_revision < 0
        ):
            raise StorageError("Episode story revision is invalid")

        try:
            episode = Episode.model_validate(
                request.episode.model_dump(mode="json", exclude_none=True)
            )
        except (TypeError, ValueError):
            raise StorageError("Episode finalization requires a valid Episode") from None
        artifacts = _freeze_artifacts(episode, request.artifacts)
        episode_payload = episode.model_dump(mode="json", exclude_none=True)
        artifact_payload = _artifact_payloads(artifacts)
        finalization_digest = hashlib.sha256(
            _json({"episode": episode_payload, "artifacts": artifact_payload}).encode(
                "utf-8"
            )
        ).hexdigest()
        artifact_events = tuple(
            StoredEvent(
                event_id=_artifact_event_id(episode.id, group_name, record["id"]),
                aggregate_id=episode.id,
                event_type=f"story.episode.{group_name}",
                payload={"artifact_id": record["id"], "artifact": record},
                episode_id=episode.id,
            )
            for group_name, _episode_field, _table, _is_memory in _ARTIFACT_GROUPS
            for record in getattr(artifacts, group_name)
        )

        request_record = CommitRequest(
            worldline_id=episode.worldline_id,
            world_time=request.world_time,
            expected_revision=request.expected_store_revision,
            idempotency_key=request.idempotency_key,
            request_id=request.request_id,
            trace_id=request.trace_id,
            operation={
                "kind": "story.episode.finalize",
                "session_id": request.session_id,
                "episode_id": episode.id,
                "expected_story_revision": request.expected_story_revision,
                "finalization_digest": finalization_digest,
            },
            events=(
                StoredEvent(
                    event_id=_finalization_event_id(episode.id),
                    aggregate_id=episode.id,
                    event_type="story.episode.finalized",
                    payload={"episode_id": episode.id},
                    episode_id=episode.id,
                ),
                *artifact_events,
            ),
        )

        def apply(tx: DomainTransaction) -> dict[str, object]:
            sessions = tx.execute(
                "SELECT world_id,worldline_id,protagonist_id,story_seed_id,"
                "story_state_json,"
                "story_revision,status "
                "FROM story_sessions WHERE id=?",
                (request.session_id,),
            )
            if len(sessions) != 1:
                raise StorageError("StorySession is unavailable for finalization")
            session = sessions[0]
            if (
                session["world_id"] != episode.world_id
                or session["worldline_id"] != episode.worldline_id
                or episode.protagonist_ids != [session["protagonist_id"]]
                or (
                    episode.story_seed_id is not None
                    and session["story_seed_id"] != episode.story_seed_id
                )
            ):
                raise StorageError("Episode identity does not match its StorySession")
            if session["story_revision"] != request.expected_story_revision:
                raise RevisionConflict("Story revision changed before finalization")
            if session["status"] not in {"active", "closing"}:
                raise StorageError("StorySession is not finalizable")

            try:
                story_state = StoryState.model_validate(
                    json.loads(session["story_state_json"])
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                raise StorageError("Committed StoryState is invalid") from None
            if request.world_time != story_state.world_time:
                raise StorageError(
                    "Finalization world time does not match committed StoryState"
                )
            evidence = _load_committed_story_evidence(tx, request.session_id)
            _validate_committed_story_evidence(
                episode=episode,
                artifacts=artifacts,
                session=session,
                evidence=evidence,
                story_state=story_state,
            )

            tx.execute(
                "UPDATE story_sessions SET status='finalized',committed_world_revision=? "
                "WHERE id=?",
                (tx.revision, request.session_id),
            )
            tx.execute(
                "INSERT INTO episodes("
                "id,world_id,worldline_id,session_id,story_seed_id,payload_json,"
                "committed_world_revision) VALUES (?,?,?,?,?,?,?)",
                (
                    episode.id,
                    episode.world_id,
                    episode.worldline_id,
                    request.session_id,
                    episode.story_seed_id,
                    _json(episode_payload),
                    tx.revision,
                ),
            )
            for group_name, _episode_field, table, is_memory in _ARTIFACT_GROUPS:
                for ordinal, record in enumerate(getattr(artifacts, group_name)):
                    if is_memory:
                        tx.execute(
                            "INSERT INTO character_episode_memories("
                            "episode_id,artifact_id,ordinal,character_id,payload_json,"
                            "committed_world_revision) VALUES (?,?,?,?,?,?)",
                            (
                                episode.id,
                                record["id"],
                                ordinal,
                                record["character_id"],
                                _json(record),
                                tx.revision,
                            ),
                        )
                    else:
                        tx.execute(
                            f"INSERT INTO {table}("
                            "episode_id,artifact_id,ordinal,payload_json,"
                            "committed_world_revision) VALUES (?,?,?,?,?)",
                            (
                                episode.id,
                                record["id"],
                                ordinal,
                                _json(record),
                                tx.revision,
                            ),
                        )
            tx.execute(
                "INSERT INTO episode_finalizations("
                "episode_id,idempotency_key,request_digest,committed_world_revision"
                ") VALUES (?,?,?,?)",
                (
                    episode.id,
                    request.idempotency_key,
                    finalization_digest,
                    tx.revision,
                ),
            )
            return {
                "episode_id": episode.id,
                "store_revision": tx.revision,
                "finalization_digest": finalization_digest,
            }

        try:
            committed = await self._database.commit_resolved(request_record, apply)
        except RevisionConflict:
            raise
        except IdempotencyConflict:
            raise

        expected_result = {
            "episode_id": episode.id,
            "store_revision": committed.revision,
            "finalization_digest": finalization_digest,
        }
        if committed.value != expected_result:
            raise StorageError("Episode finalization replay does not match its request")
        persisted = await self.load(episode.id)
        if persisted.episode != episode or persisted.artifacts != artifacts:
            raise StorageError("Persisted Episode finalization does not match its request")
        return EpisodeFinalizationResult(
            episode=persisted.episode,
            artifacts=persisted.artifacts,
            store_revision=committed.revision,
            replayed=committed.replayed,
        )

    async def load(self, episode_id: str) -> EpisodeFinalizationResult:
        if (
            not isinstance(episode_id, str)
            or not episode_id.strip()
            or len(episode_id) > 256
            or "\x00" in episode_id
        ):
            raise StorageError("Episode identity is invalid")
        rows = await self._database.read_world(
            _LOAD_EPISODE_BUNDLE_SQL,
            (episode_id, episode_id, episode_id, episode_id, episode_id, episode_id),
        )
        if not rows:
            raise StorageError("Episode finalization was not found")
        try:
            episode = Episode.model_validate(json.loads(rows[0]["episode_payload"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise StorageError("Persisted Episode is invalid") from None

        loaded_group_lists: dict[str, list[dict[str, object]]] = {
            group_name: [] for group_name, _episode_field, _table, _is_memory in _ARTIFACT_GROUPS
        }
        for row in rows:
            group_name = row["artifact_kind"]
            if group_name is None:
                continue
            if group_name not in loaded_group_lists:
                raise StorageError("Persisted Episode artifact type is invalid")
            try:
                artifact = json.loads(row["artifact_payload"])
            except (TypeError, ValueError, json.JSONDecodeError):
                raise StorageError("Persisted Episode artifact is invalid") from None
            if (
                not isinstance(artifact, dict)
                or artifact.get("id") != row["artifact_id"]
                or (
                    group_name == "memories"
                    and artifact.get("character_id")
                    != row["artifact_character_id"]
                )
            ):
                raise StorageError("Persisted Episode artifact identity is invalid")
            loaded_group_lists[group_name].append(artifact)
        artifacts = EpisodeFinalizationArtifacts(
            **{
                group_name: tuple(values)
                for group_name, values in loaded_group_lists.items()
            }
        )
        artifacts = _freeze_artifacts(episode, artifacts)
        return EpisodeFinalizationResult(
            episode=episode,
            artifacts=artifacts,
            store_revision=rows[0]["store_revision"],
            replayed=False,
        )


def _finalization_event_id(episode_id: str) -> str:
    digest = hashlib.sha256(episode_id.encode("utf-8")).hexdigest()
    return f"episode-finalized:{digest}"


def _artifact_event_id(episode_id: str, kind: str, artifact_id: str) -> str:
    digest = hashlib.sha256(
        "\0".join((episode_id, kind, artifact_id)).encode("utf-8")
    ).hexdigest()
    return f"episode-artifact:{digest}"
