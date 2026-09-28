"""Read-only SQLite adapters for gameplay context snapshot and facet ports.

The repository establishes one world.db read transaction, materializes trusted
committed facts, and closes the transaction before any model-side work. Facet
ports consume only that immutable materialization; none opens a second "latest"
read or derives visibility from a prompt or a retrieval result.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from application.context_plan import (
    AuthorizationView,
    ContextError,
    ContextInput,
    ContextScope,
    Evidence,
    Layer,
    canonical_json,
    digest,
    parse_json,
)
from application.gameplay_context import (
    CharacterContextPort,
    ContextFacet,
    ContextSnapshot,
    ContextSnapshotPort,
    EligibilityTicket,
    GameplayAuthorizationPort,
    GameplayCall,
    GameplayRecipe,
    LoreContextPort,
    MemoryContextPort,
    StoryContextPort,
    WorldContextPort,
)
from domain.context_visibility import (
    ContextAuthorization,
    ContextConsumer,
    ContextEligibility,
    ContextFact,
    ContextIdentity,
    ContextVisibilityError,
    authorize_candidates,
    issue_eligibility,
)
from infrastructure.database_manager import DatabaseManager
from infrastructure.database_schema import connect

_POLICY_REVISION = "context-visibility.v1"
_CACHE_LIMIT = 128
_TICKET_LIMIT = 256


@dataclass(frozen=True, slots=True)
class _ProjectedFact:
    fact: ContextFact
    evidence: Evidence
    facets: frozenset[ContextFacet]


@dataclass(frozen=True, slots=True)
class _CommittedRows:
    turn_knowledge: tuple[Mapping[str, object], ...] = ()
    episode_knowledge: tuple[Mapping[str, object], ...] = ()
    turn_events: tuple[Mapping[str, object], ...] = ()
    episode_events: tuple[Mapping[str, object], ...] = ()
    episode_memories: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class _MaterializedSnapshot:
    call: GameplayCall
    recipe: GameplayRecipe
    snapshot: ContextSnapshot
    facts: tuple[_ProjectedFact, ...]


@dataclass(slots=True)
class _InvocationState:
    materialized: _MaterializedSnapshot
    eligibility: ContextEligibility | None = None


@dataclass(frozen=True, slots=True)
class _IssuedTicket:
    ticket: EligibilityTicket
    state: _InvocationState
    eligibility: ContextEligibility


class _FacetAdapter:
    """A small facet-specific view over a shared repository snapshot."""

    def __init__(self, repository: SQLiteGameplayContextRepository, facet: ContextFacet) -> None:
        self._repository = repository
        self._facet = facet

    async def load(
        self,
        call: GameplayCall,
        snapshot: ContextSnapshot,
        recipe: GameplayRecipe,
        eligibility: EligibilityTicket,
    ) -> tuple[Evidence, ...]:
        return await self._repository._load_facet(self._facet, call, snapshot, recipe, eligibility)


class SQLiteGameplayContextRepository(ContextSnapshotPort, GameplayAuthorizationPort):
    """Implements the existing snapshot, authorization, and facet read ports.

    The concrete repository deliberately has no writer API. It supports the
    currently modeled private/public sources: committed character knowledge,
    committed world-event visibility, and committed character Episode memories.
    Unknown or malformed visibility metadata is excluded rather than inferred.
    """

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database
        self._snapshots: OrderedDict[int, _InvocationState] = OrderedDict()
        self._invocations: OrderedDict[tuple[object, ...], _InvocationState] = OrderedDict()
        self._tickets: dict[str, _IssuedTicket] = {}
        self.lore_port: LoreContextPort = _FacetAdapter(self, ContextFacet.LORE)
        self.world_port: WorldContextPort = _FacetAdapter(self, ContextFacet.WORLD)
        self.character_port: CharacterContextPort = _FacetAdapter(self, ContextFacet.CHARACTER)
        self.story_port: StoryContextPort = _FacetAdapter(self, ContextFacet.STORY)
        self.memory_port: MemoryContextPort = _FacetAdapter(self, ContextFacet.MEMORY)

    async def resolve(self, call: GameplayCall, recipe: GameplayRecipe) -> ContextSnapshot:
        if not isinstance(call, GameplayCall) or not isinstance(recipe, GameplayRecipe):
            raise ContextError("invalid_gameplay_context_request")
        materialized = await asyncio.to_thread(self._read_snapshot, call, recipe)
        state = _InvocationState(materialized)
        snapshot_key = id(materialized.snapshot)
        self._remember(self._snapshots, snapshot_key, state, _CACHE_LIMIT)
        self._remember(
            self._invocations,
            self._invocation_key(call, recipe, materialized.snapshot),
            state,
            _CACHE_LIMIT,
        )
        self._prune_tickets()
        return materialized.snapshot

    async def eligibility(
        self,
        scope: ContextScope,
        snapshot: ContextSnapshot,
        recipe: GameplayRecipe,
    ) -> EligibilityTicket:
        state = self._snapshots.get(id(snapshot))
        if (
            state is None
            or state.materialized.snapshot is not snapshot
            or state.materialized.recipe != recipe
        ):
            raise ContextError("context_snapshot_unavailable")
        expected_scope = self._scope(state.materialized.call, snapshot, recipe.consumer or "")
        if scope != expected_scope:
            raise ContextError("eligibility_scope_mismatch")
        try:
            identity = ContextIdentity(
                owner_id=scope.owner_id,
                world_id=scope.world_id,
                worldline_id=scope.worldline_id,
                subject_id=self._optional_scope_id(scope.subject_id),
                session_id=self._optional_scope_id(scope.session_id),
                consumer=ContextConsumer(scope.consumer),
                world_revision=snapshot.world_revision,
                world_tick=snapshot.world_tick,
                ancestor_limits=snapshot.ancestor_limits,
            )
            eligible = issue_eligibility(
                identity,
                tuple(projected.fact for projected in state.materialized.facts),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ContextVisibilityError):
                raise ContextError(exc.code) from None
            raise ContextError("invalid_context_eligibility") from None

        ticket = EligibilityTicket(scope=scope, token=secrets.token_urlsafe(32))
        state.eligibility = eligible
        self._tickets[ticket.token] = _IssuedTicket(ticket, state, eligible)
        if len(self._tickets) > _TICKET_LIMIT:
            self._tickets.pop(next(iter(self._tickets)))
        return ticket

    async def authorize(self, request: ContextInput, recipe: GameplayRecipe) -> AuthorizationView:
        if not isinstance(request, ContextInput) or not isinstance(recipe, GameplayRecipe):
            raise ContextError("invalid_gameplay_context_request")
        state = self._invocations.get(self._request_key(request, recipe))
        if state is None or state.eligibility is None:
            raise ContextError("context_snapshot_unavailable")
        materialized = state.materialized
        snapshot = materialized.snapshot
        if (
            recipe.consumer != request.scope.consumer
            or request.world_revision != snapshot.world_revision
            or request.story_revision != snapshot.story_revision
        ):
            raise ContextError("authorization_snapshot_mismatch")

        projection_by_source = {
            projected.evidence.source_id: projected for projected in materialized.facts
        }
        candidate_facts: list[ContextFact] = []
        evidence_fingerprints: dict[str, str] = {}
        for candidate in request.evidence:
            projected = projection_by_source.get(candidate.source_id)
            if projected is None:
                # Retrieval can narrow the pre-authorized set but cannot mint a
                # new source or create a grant for an unknown source_id.
                continue
            if candidate != projected.evidence:
                raise ContextError("context_source_changed")
            candidate_facts.append(projected.fact)
            evidence_fingerprints[candidate.source_id] = candidate.fingerprint

        try:
            authorization: ContextAuthorization = authorize_candidates(
                state.eligibility, candidate_facts
            )
        except ContextVisibilityError as exc:
            raise ContextError(exc.code) from None
        grants = frozenset(
            evidence_fingerprints[source.source_id]
            for source in authorization.sources
            if source.source_id in evidence_fingerprints
        )
        return AuthorizationView(
            scope=request.scope,
            world_revision=snapshot.world_revision,
            story_revision=snapshot.story_revision,
            world_tick=snapshot.world_tick,
            grants=grants,
            ancestor_limits=snapshot.ancestor_limits,
        )

    async def _load_facet(
        self,
        facet: ContextFacet,
        call: GameplayCall,
        snapshot: ContextSnapshot,
        recipe: GameplayRecipe,
        ticket: EligibilityTicket,
    ) -> tuple[Evidence, ...]:
        issued = self._tickets.get(ticket.token)
        if (
            issued is None
            or issued.ticket is not ticket
            or issued.state.materialized.snapshot is not snapshot
            or issued.state.materialized.call != call
            or issued.state.materialized.recipe != recipe
            or ticket.scope != self._scope(call, snapshot, recipe.consumer or "")
        ):
            raise ContextError("invalid_context_eligibility")

        eligible_by_id = {source.source_id: source for source in issued.eligibility.sources}
        selected = [
            projected for projected in issued.state.materialized.facts if facet in projected.facets
        ]
        # Story-only recipes (for example narrative compilation) consume the
        # same committed event rows without causing duplicate candidates in
        # recipes that already request the World facet.
        if facet == ContextFacet.STORY and ContextFacet.WORLD not in recipe.facets:
            selected.extend(
                projected
                for projected in issued.state.materialized.facts
                if ContextFacet.WORLD in projected.facets
            )

        try:
            narrowed = authorize_candidates(
                issued.eligibility,
                tuple(projected.fact for projected in selected),
            )
        except ContextVisibilityError as exc:
            raise ContextError(exc.code) from None
        authorized_ids = narrowed.source_ids
        return tuple(
            projected.evidence
            for projected in selected
            if projected.evidence.source_id in eligible_by_id
            and projected.evidence.source_id in authorized_ids
            and eligible_by_id[projected.evidence.source_id].fingerprint
            == projected.fact.fingerprint
        )

    def _read_snapshot(self, call: GameplayCall, recipe: GameplayRecipe) -> _MaterializedSnapshot:
        with closing(connect(self._database.paths.world, readonly=True)) as connection:
            connection.execute("BEGIN")
            try:
                meta = connection.execute(
                    "SELECT revision FROM world_meta WHERE singleton=1"
                ).fetchone()
                if meta is None:
                    raise ContextError("world_snapshot_unavailable")
                world_revision = self._require_natural(meta["revision"])
                session = self._read_session(connection, call)
                if (
                    session is not None
                    and self._require_natural(session["committed_world_revision"]) > world_revision
                ):
                    raise ContextError("invalid_context_snapshot")
                rows = self._read_committed_rows(connection, call, session, world_revision)
                connection.execute("ROLLBACK")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

        story_revision = (
            self._require_natural(session["story_revision"]) if session is not None else 0
        )
        world_tick = story_revision
        policy_revision = _POLICY_REVISION
        lineage_digest = digest({"worldline_id": call.worldline_id, "ancestor_limits": []})
        snapshot = ContextSnapshot(
            world_revision=world_revision,
            story_revision=story_revision,
            world_tick=world_tick,
            policy_revision=policy_revision,
            lineage_digest=lineage_digest,
            ancestor_limits=(),
            cache_dimensions=tuple(
                sorted(
                    self._cache_dimensions(
                        call,
                        world_revision,
                        story_revision,
                        session,
                        lineage_digest,
                    ).items()
                )
            ),
        )
        facts = self._materialize_facts(call, snapshot, rows)
        return _MaterializedSnapshot(call, recipe, snapshot, facts)

    def _read_session(self, connection, call: GameplayCall) -> dict[str, object] | None:
        if call.session_id == "-":
            return None
        row = connection.execute(
            "SELECT id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "story_revision,status,story_state_json,committed_world_revision "
            "FROM story_sessions WHERE id=?",
            (call.session_id,),
        ).fetchone()
        if row is None:
            raise ContextError("gameplay_session_not_found")
        session = self._row_dict(row)
        if session["world_id"] != call.world_id or session["worldline_id"] != call.worldline_id:
            raise ContextError("context_session_scope_mismatch")
        try:
            story_state = parse_json(session["story_state_json"])
        except TypeError, ValueError:
            raise ContextError("invalid_context_snapshot") from None
        if not isinstance(story_state, dict):
            raise ContextError("invalid_context_snapshot")
        session["story_state"] = story_state
        bootstrap_row = connection.execute(
            "SELECT scenario_id,content_version,content_digest,bootstrap_json "
            "FROM story_session_bootstraps WHERE session_id=?",
            (call.session_id,),
        ).fetchone()
        if bootstrap_row is None:
            session["bootstrap"] = {}
        else:
            bootstrap = self._row_dict(bootstrap_row)
            try:
                bootstrap_payload = parse_json(bootstrap["bootstrap_json"])
            except TypeError, ValueError:
                raise ContextError("invalid_context_snapshot") from None
            if not isinstance(bootstrap_payload, dict):
                raise ContextError("invalid_context_snapshot")
            session["bootstrap"] = {
                "scenario_id": bootstrap["scenario_id"],
                "content_version": bootstrap["content_version"],
                "content_digest": bootstrap["content_digest"],
                "payload": bootstrap_payload,
            }
        return session

    def _read_committed_rows(
        self,
        connection,
        call: GameplayCall,
        session: dict[str, object] | None,
        world_revision: int,
    ) -> _CommittedRows:
        if session is None:
            return _CommittedRows()
        session_id = call.session_id
        turn_knowledge = self._select_rows(
            connection,
            "SELECT k.id,k.character_id,k.proposition_id,k.ordinal,k.payload_json,"
            "k.committed_world_revision,d.story_revision "
            "FROM turn_knowledge_changes AS k "
            "JOIN story_state_deltas AS d ON d.id=k.state_delta_id "
            "JOIN turn_transactions AS t ON t.id=k.turn_id "
            "WHERE k.session_id=? AND k.committed_world_revision IS NOT NULL "
            "AND k.committed_world_revision<=? "
            "AND d.session_id=k.session_id "
            "AND d.committed_world_revision=k.committed_world_revision "
            "AND t.session_id=k.session_id "
            "AND t.committed_world_revision=k.committed_world_revision "
            "ORDER BY k.committed_world_revision,d.story_revision,k.ordinal,k.id",
            (session_id, world_revision),
        )
        episode_knowledge = self._select_rows(
            connection,
            "SELECT k.episode_id,k.artifact_id AS id,k.ordinal,k.payload_json,"
            "k.committed_world_revision,e.world_id,e.worldline_id "
            "FROM episode_knowledge_changes AS k "
            "JOIN episodes AS e ON e.id=k.episode_id "
            "WHERE e.session_id=? AND e.world_id=? AND e.worldline_id=? "
            "AND e.committed_world_revision<=? "
            "AND k.committed_world_revision IS NOT NULL "
            "AND k.committed_world_revision<=? "
            "ORDER BY k.committed_world_revision,k.ordinal,k.artifact_id",
            (
                session_id,
                session["world_id"],
                session["worldline_id"],
                world_revision,
                world_revision,
            ),
        )
        turn_events = self._select_rows(
            connection,
            "SELECT w.id,w.event_type,w.ordinal,w.payload_json,"
            "w.committed_world_revision,d.story_revision "
            "FROM turn_world_events AS w "
            "JOIN story_state_deltas AS d ON d.id=w.state_delta_id "
            "JOIN turn_transactions AS t ON t.id=w.turn_id "
            "WHERE w.session_id=? AND w.committed_world_revision IS NOT NULL "
            "AND w.committed_world_revision<=? "
            "AND d.session_id=w.session_id "
            "AND d.committed_world_revision=w.committed_world_revision "
            "AND t.session_id=w.session_id "
            "AND t.committed_world_revision=w.committed_world_revision "
            "ORDER BY w.committed_world_revision,d.story_revision,w.ordinal,w.id",
            (session_id, world_revision),
        )
        episode_events = self._select_rows(
            connection,
            "SELECT w.episode_id,w.artifact_id AS id,w.ordinal,w.payload_json,"
            "w.committed_world_revision,e.world_id,e.worldline_id "
            "FROM episode_world_events AS w "
            "JOIN episodes AS e ON e.id=w.episode_id "
            "WHERE e.session_id=? AND e.world_id=? AND e.worldline_id=? "
            "AND e.committed_world_revision<=? "
            "AND w.committed_world_revision IS NOT NULL "
            "AND w.committed_world_revision<=? "
            "ORDER BY w.committed_world_revision,w.ordinal,w.artifact_id",
            (
                session_id,
                session["world_id"],
                session["worldline_id"],
                world_revision,
                world_revision,
            ),
        )
        episode_memories = self._select_rows(
            connection,
            "SELECT m.episode_id,m.artifact_id AS id,m.ordinal,m.character_id,"
            "m.payload_json,m.committed_world_revision,e.world_id,e.worldline_id "
            "FROM character_episode_memories AS m "
            "JOIN episodes AS e ON e.id=m.episode_id "
            "WHERE e.session_id=? AND e.world_id=? AND e.worldline_id=? "
            "AND e.committed_world_revision<=? "
            "AND m.committed_world_revision IS NOT NULL "
            "AND m.committed_world_revision<=? "
            "ORDER BY m.committed_world_revision,m.ordinal,m.artifact_id",
            (
                session_id,
                session["world_id"],
                session["worldline_id"],
                world_revision,
                world_revision,
            ),
        )
        return _CommittedRows(
            turn_knowledge,
            episode_knowledge,
            turn_events,
            episode_events,
            episode_memories,
        )

    def _materialize_facts(
        self,
        call: GameplayCall,
        snapshot: ContextSnapshot,
        rows: _CommittedRows,
    ) -> tuple[_ProjectedFact, ...]:
        knowledge: dict[tuple[str, str], tuple[int, int, int, dict[str, object]]] = {}
        for row in rows.turn_knowledge:
            payload = self._json_object(row["payload_json"])
            character_id = self._require_text(row["character_id"])
            proposition_id = self._require_text(row["proposition_id"])
            if (
                payload.get("character_id") != character_id
                or payload.get("proposition_id") != proposition_id
            ):
                raise ContextError("invalid_context_snapshot")
            self._consider_knowledge(
                knowledge,
                character_id,
                proposition_id,
                row["committed_world_revision"],
                row["story_revision"],
                row["ordinal"],
                payload,
            )
        for row in rows.episode_knowledge:
            payload = self._json_object(row["payload_json"])
            character_id = self._require_text(payload.get("character_id"))
            proposition_id = self._require_text(payload.get("proposition_id"))
            self._consider_knowledge(
                knowledge,
                character_id,
                proposition_id,
                row["committed_world_revision"],
                0,
                row["ordinal"],
                payload,
            )

        projected: list[_ProjectedFact] = []
        for (character_id, proposition_id), (revision, story_revision, _, payload) in sorted(
            knowledge.items()
        ):
            status = payload.get("status")
            if status == "revoked":
                continue
            if status not in {
                "confirmed",
                "probable",
                "uncertain",
                "contradicted",
            }:
                raise ContextError("invalid_context_snapshot")
            certainty = payload.get("certainty")
            source_ref = payload.get("source_ref")
            if source_ref is None:
                source = payload.get("source")
                source_ref = source.get("ref") if isinstance(source, dict) else None
            if (
                type(certainty) not in (int, float)
                or not 0 <= certainty <= 1
                or not isinstance(source_ref, str)
                or not source_ref.strip()
            ):
                raise ContextError("invalid_context_snapshot")
            normalized = {
                "character_id": character_id,
                "proposition_id": proposition_id,
                "certainty": certainty,
                "source_ref": source_ref,
                "status": status,
            }
            model_content = {
                "proposition_id": proposition_id,
                "certainty": certainty,
                "status": status,
            }
            hidden = self._hidden_flag(payload)
            projected.append(
                self._projection(
                    call=call,
                    source_id=self._stable_source_id("knowledge", character_id, proposition_id),
                    source_revision=revision,
                    kind="character_knowledge",
                    layer=Layer.HISTORY,
                    sequence=story_revision,
                    session_id=call.session_id,
                    subject_id=None,
                    available_at_tick=story_revision,
                    committed_world_revision=revision,
                    content=normalized,
                    model_content=model_content,
                    known_by=(character_id,),
                    public=False,
                    disclosed_to_owner=False,
                    hidden=hidden,
                    facets=frozenset({ContextFacet.CHARACTER}),
                )
            )

        events: dict[str, tuple[int, int, Mapping[str, object]]] = {}
        for row in rows.turn_events + rows.episode_events:
            event_id = self._require_text(row["id"])
            revision = self._require_natural(row["committed_world_revision"])
            ordinal = self._require_natural(row["ordinal"])
            current = events.get(event_id)
            if current is None or (revision, ordinal) > (current[0], current[1]):
                events[event_id] = (revision, ordinal, row)

        for event_id, (revision, ordinal, row) in sorted(events.items()):
            payload = self._json_object(row["payload_json"])
            visibility = payload.get("visibility")
            if not isinstance(visibility, dict) or type(visibility.get("public")) is not bool:
                # Unknown visibility cannot become an authorization grant.
                continue
            known_by = visibility.get("known_by", [])
            if (
                not isinstance(known_by, list)
                or any(not isinstance(subject, str) for subject in known_by)
                or len(set(known_by)) != len(known_by)
            ):
                continue
            stored_event_type = row.get("event_type")
            event_type = payload.get("event_type", stored_event_type)
            actors = payload.get("actors", [])
            targets = payload.get("targets", [])
            event_content = payload.get("payload", {})
            if (
                not isinstance(event_type, str)
                or (stored_event_type is not None and event_type != stored_event_type)
                or not isinstance(actors, list)
                or any(not isinstance(actor, str) for actor in actors)
                or not isinstance(targets, list)
                or any(not isinstance(target, str) for target in targets)
                or not isinstance(event_content, dict)
            ):
                continue
            content = {
                "event_type": event_type,
                "actors": actors,
                "targets": targets,
                "payload": event_content,
            }
            hidden = self._hidden_flag(payload) or self._hidden_flag(event_content)
            story_revision = self._require_natural(row.get("story_revision", 0))
            projected.append(
                self._projection(
                    call=call,
                    source_id=self._stable_source_id("world-event", event_id),
                    source_revision=revision,
                    kind="world_event",
                    layer=Layer.HISTORY,
                    sequence=story_revision,
                    session_id=call.session_id,
                    subject_id=None,
                    available_at_tick=story_revision,
                    committed_world_revision=revision,
                    content=content,
                    model_content=content,
                    known_by=tuple(known_by),
                    public=visibility["public"],
                    # No current persisted owner-disclosure field exists for
                    # these sources; only explicit public status grants owners.
                    disclosed_to_owner=False,
                    hidden=hidden,
                    facets=frozenset({ContextFacet.WORLD}),
                )
            )

        for row in rows.episode_memories:
            payload = self._json_object(row["payload_json"])
            character_id = self._require_text(row["character_id"])
            episode_id = self._require_text(row["episode_id"])
            artifact_id = self._require_text(row["id"])
            revision = self._require_natural(row["committed_world_revision"])
            content = {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "id",
                    "schema_version",
                    "worldline_id",
                    "character_id",
                    "revision",
                    "source_ids",
                }
            }
            projected.append(
                self._projection(
                    call=call,
                    source_id=self._stable_source_id("episode-memory", episode_id, artifact_id),
                    source_revision=revision,
                    kind="character_episode_memory",
                    layer=Layer.RECALL,
                    sequence=None,
                    session_id=call.session_id,
                    subject_id=character_id,
                    available_at_tick=snapshot.world_tick,
                    committed_world_revision=revision,
                    content=payload,
                    model_content=content,
                    known_by=(character_id,),
                    public=False,
                    disclosed_to_owner=False,
                    hidden=self._hidden_flag(payload),
                    facets=frozenset({ContextFacet.MEMORY}),
                )
            )
        return tuple(projected)

    def _projection(
        self,
        *,
        call: GameplayCall,
        source_id: str,
        source_revision: int,
        kind: str,
        layer: Layer,
        sequence: int | None,
        session_id: str | None,
        subject_id: str | None,
        available_at_tick: int,
        committed_world_revision: int,
        content: dict[str, object],
        model_content: dict[str, object],
        known_by: tuple[str, ...],
        public: bool,
        disclosed_to_owner: bool,
        hidden: bool,
        facets: frozenset[ContextFacet],
    ) -> _ProjectedFact:
        fact_content = canonical_json(content)
        model_content_json = canonical_json(model_content)
        fact = ContextFact(
            source_id=source_id,
            source_revision=source_revision,
            owner_id=call.owner_id,
            world_id=call.world_id,
            worldline_id=call.worldline_id,
            session_id=session_id,
            subject_id=subject_id,
            committed_world_revision=committed_world_revision,
            available_at_tick=available_at_tick,
            content_json=fact_content,
            known_by_subject_ids=known_by,
            public=public,
            disclosed_to_owner=disclosed_to_owner,
            hidden=hidden,
        )
        evidence = Evidence(
            source_id=source_id,
            source_revision=source_revision,
            kind=kind,
            layer=layer,
            content_json=model_content_json,
            world_id=call.world_id,
            worldline_id=call.worldline_id,
            subject_id=subject_id,
            available_at_tick=available_at_tick,
            committed_revision=committed_world_revision,
            sequence=sequence,
        )
        return _ProjectedFact(fact, evidence, facets)

    @staticmethod
    def _consider_knowledge(
        knowledge: dict[tuple[str, str], tuple[int, int, int, dict[str, object]]],
        character_id: str,
        proposition_id: str,
        committed_revision: object,
        story_revision: object,
        ordinal: object,
        payload: dict[str, object],
    ) -> None:
        revision = SQLiteGameplayContextRepository._require_natural(committed_revision)
        story = SQLiteGameplayContextRepository._require_natural(story_revision)
        order = SQLiteGameplayContextRepository._require_natural(ordinal)
        key = character_id, proposition_id
        candidate = revision, story, order, payload
        current = knowledge.get(key)
        if current is None or candidate[:3] > current[:3]:
            knowledge[key] = candidate

    @staticmethod
    def _hidden_flag(payload: Mapping[str, object]) -> bool:
        value = payload.get("hidden")
        if value is None:
            return False
        if type(value) is not bool:
            raise ContextError("invalid_context_snapshot")
        return value

    @staticmethod
    def _cache_dimensions(
        call: GameplayCall,
        world_revision: int,
        story_revision: int,
        session: dict[str, object] | None,
        lineage_digest: str,
    ) -> dict[str, str]:
        state = session.get("story_state", {}) if session is not None else {}
        bootstrap = session.get("bootstrap", {}) if session is not None else {}
        scene = state.get("scene", {}) if isinstance(state, dict) else {}
        bootstrap = bootstrap if isinstance(bootstrap, dict) else {}
        scene = scene if isinstance(scene, dict) else {}
        checkpoint = digest(
            {
                "story_revision": story_revision,
                "story_state": state,
                "lineage_digest": lineage_digest,
            }
        )
        content_digest = bootstrap.get("content_digest")
        content_version = bootstrap.get("content_version")
        story_seed = session.get("story_seed_id") if session is not None else None
        return {
            "content_pack": str(content_digest or content_version or "no-content-pack"),
            "character_core": (call.subject_id if call.subject_id != "-" else "no-character"),
            "story_seed": str(story_seed or "no-story-seed"),
            "checkpoint": checkpoint,
            "scene": str(scene.get("id") or "no-scene"),
            "world_checkpoint": str(world_revision),
            "spoiler_profile": _POLICY_REVISION,
            "era": str(bootstrap.get("era") or "unspecified-era"),
            "sequence_profile": str(bootstrap.get("sequence_profile") or "unspecified-sequence"),
            "episode_seed": str(story_seed or "no-episode-seed"),
            "narrative_dna": str(
                bootstrap.get("narrative_dna_revision") or content_digest or "none"
            ),
            "voice_persona": str(bootstrap.get("voice_persona_revision") or "none"),
            "episode": str(call.session_id if call.session_id != "-" else "no-episode"),
        }

    @staticmethod
    def _scope(call: GameplayCall, snapshot: ContextSnapshot, consumer: str) -> ContextScope:
        return ContextScope(
            owner_id=call.owner_id,
            world_id=call.world_id,
            worldline_id=call.worldline_id,
            consumer=consumer,
            subject_id=call.subject_id,
            session_id=call.session_id,
            policy_revision=snapshot.policy_revision,
            lineage_digest=snapshot.lineage_digest,
        )

    @staticmethod
    def _optional_scope_id(value: str) -> str | None:
        return None if value == "-" else value

    @classmethod
    def _invocation_key(
        cls,
        call: GameplayCall,
        recipe: GameplayRecipe,
        snapshot: ContextSnapshot,
    ) -> tuple[object, ...]:
        return (
            call.request_id,
            recipe.mode.value,
            cls._scope(call, snapshot, recipe.consumer or ""),
            snapshot.world_revision,
            snapshot.story_revision,
        )

    @classmethod
    def _request_key(cls, request: ContextInput, recipe: GameplayRecipe) -> tuple[object, ...]:
        return (
            request.request_id,
            recipe.mode.value,
            request.scope,
            request.world_revision,
            request.story_revision,
        )

    @staticmethod
    def _remember(
        cache: OrderedDict[Any, _InvocationState],
        key: Any,
        state: _InvocationState,
        limit: int,
    ) -> None:
        cache[key] = state
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def _prune_tickets(self) -> None:
        while len(self._tickets) > _TICKET_LIMIT:
            self._tickets.pop(next(iter(self._tickets)))

    @staticmethod
    def _row_dict(row) -> dict[str, object]:
        # sqlite3.Row is iterable over values, so its explicit key list is
        # required here (unlike a normal dict).
        return {key: row[key] for key in row.keys()}  # noqa: SIM118

    @classmethod
    def _select_rows(
        cls, connection, query: str, parameters: tuple[object, ...]
    ) -> tuple[Mapping[str, object], ...]:
        return tuple(
            MappingProxyType(cls._row_dict(row))
            for row in connection.execute(query, parameters).fetchall()
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, object]:
        try:
            parsed = parse_json(value)
        except TypeError, ValueError:
            raise ContextError("invalid_context_snapshot") from None
        if not isinstance(parsed, dict):
            raise ContextError("invalid_context_snapshot")
        return parsed

    @staticmethod
    def _require_text(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ContextError("invalid_context_snapshot")
        return value

    @staticmethod
    def _require_natural(value: object) -> int:
        if type(value) is not int or value < 0:
            raise ContextError("invalid_context_snapshot")
        return value

    @staticmethod
    def _stable_source_id(prefix: str, *parts: str) -> str:
        value = f"{prefix}:{':'.join(parts)}"
        if len(value) <= 256:
            return value
        return f"{prefix}:{digest(list(parts))}"
