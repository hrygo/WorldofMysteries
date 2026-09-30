"""Publish immutable narrative only after a turn has committed.

AI workers return :class:`NarrativeCandidate` values. This Application service
owns speaker binding and the post-COMMIT publication port; it always reuses an
existing block before invoking a compiler so deterministic/frozen expression
cannot be published a second time.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from contracts import NarrativeBlock, StateDelta, TurnStatus, TurnTransaction
from contracts.models import NarrativeSegment

from .turn_context_binding import (
    AuthorizedTurnContextBinding,
    TurnContextBindingError,
    TurnContextBindingPort,
)

_MAX_NARRATIVE_CHARS = 1200
_MAX_COMMITTED_SOURCE_CHARS = 32_768
_MAX_SINGLE_FLIGHT_TURNS = 64
_PUBLISHED_STATUSES = frozenset(
    {
        TurnStatus.NARRATIVE_READY,
        TurnStatus.AUDIO_READY,
        TurnStatus.DELIVERED,
    }
)
_PUBLISHABLE_STATUSES = frozenset(
    {TurnStatus.COMMITTED, TurnStatus.BEAT_READY}
)


class NarrativePublicationError(RuntimeError):
    """A committed turn cannot be safely expressed or published."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _bounded_text(
    value: object,
    *,
    field: str,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str) or "\x00" in value or len(value) > limit:
        raise NarrativePublicationError(f"invalid_{field}")
    text = value.strip()
    if not text and not allow_empty:
        raise NarrativePublicationError(f"invalid_{field}")
    return text


def _character_roster(value: object) -> tuple[str, ...]:
    """Normalise a declared roster of who may speak this turn.

    A duplicate is refused rather than collapsed. Two entries for one
    character mean the projection is ambiguous about who is present, and
    silently deduplicating would hide that from whoever has to debug a scene
    that cast the wrong person — while still letting the roster through as
    if it were well-formed.
    """
    if not isinstance(value, (tuple, list)):
        raise NarrativePublicationError("invalid_present_character_ids")
    roster = tuple(
        _bounded_text(item, field="present_character_ids", limit=256)
        for item in value
    )
    if len(set(roster)) != len(roster):
        raise NarrativePublicationError("duplicate_present_character")
    return roster


@dataclass(frozen=True, slots=True)
class NarrativeCandidate:
    """Model-produced expression with narration and dialogue kept distinct.

    The speaker is intentionally absent: only the trusted committed source may
    bind a character segment. A missing/blank speech value means there is no
    dialogue to publish or send to audio.
    """

    narration: str
    speech: str
    context_binding: AuthorizedTurnContextBinding | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "narration",
            _bounded_text(
                self.narration,
                field="narration",
                limit=_MAX_NARRATIVE_CHARS,
            ),
        )
        object.__setattr__(
            self,
            "speech",
            _bounded_text(
                self.speech,
                field="speech",
                limit=_MAX_NARRATIVE_CHARS,
                allow_empty=True,
            ),
        )
        if self.context_binding is not None and not isinstance(
            self.context_binding, AuthorizedTurnContextBinding
        ):
            raise NarrativePublicationError("invalid_context_binding")


@dataclass(frozen=True, slots=True)
class CommittedNarrativeSource:
    """Public, committed facts and trusted identity for one turn.

    ``disclosed_facts`` must be prepared from that turn's committed increment
    through the existing player-disclosure projection. Hidden StateDelta fields
    and arbitrary model-generated speaker identifiers are not inputs.
    """

    turn_id: str
    session_id: str
    story_revision: int
    state_delta_id: str
    state_delta: StateDelta
    scene_id: str | None
    protagonist_id: str
    disclosed_facts: str
    input_turn_id: str | None = None
    source_store_revision: int | None = None
    #: Who is in the scene for this turn, when the world says so.
    #:
    #: Three states, and the difference between them is the whole point:
    #: ``None`` means this source declares no roster at all, and publication
    #: keeps its historical single-protagonist behaviour; ``()`` means the
    #: world says the scene is empty and the block should carry narration
    #: only; a non-empty tuple is authoritative and no one outside it can
    #: speak. Folding ``None`` and ``()`` together would make "nobody is here"
    #: indistinguishable from "we have not asked yet", and the first is a
    #: fact while the second is an absence of one.
    #:
    #: This is a presentation-layer fact about who may be heard, not world
    #: truth: it never advances the world revision. The roster it carries is
    #: already a projection of committed state, narrowed by what this turn is
    #: authorised to know (ADR-006 D2).
    present_character_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for field in ("turn_id", "session_id", "state_delta_id", "protagonist_id"):
            object.__setattr__(
                self,
                field,
                _bounded_text(
                    getattr(self, field),
                    field=field,
                    limit=256,
                ),
            )
        if (
            type(self.story_revision) is not int
            or self.story_revision < 0
        ):
            raise NarrativePublicationError("invalid_story_revision")
        if (
            not isinstance(self.state_delta, StateDelta)
            or self.state_delta.id != self.state_delta_id
            or self.state_delta.turn_id != self.turn_id
        ):
            raise NarrativePublicationError("committed_delta_binding_mismatch")
        if self.scene_id is not None:
            object.__setattr__(
                self,
                "scene_id",
                _bounded_text(self.scene_id, field="scene_id", limit=256),
            )
        if self.input_turn_id is not None:
            object.__setattr__(
                self,
                "input_turn_id",
                _bounded_text(
                    self.input_turn_id,
                    field="input_turn_id",
                    limit=256,
                ),
            )
        if self.source_store_revision is not None and (
            type(self.source_store_revision) is not int
            or self.source_store_revision < 0
        ):
            raise NarrativePublicationError("invalid_source_store_revision")
        object.__setattr__(
            self,
            "disclosed_facts",
            _bounded_text(
                self.disclosed_facts,
                field="committed_source",
                limit=_MAX_COMMITTED_SOURCE_CHARS,
            ),
        )
        if self.present_character_ids is not None:
            object.__setattr__(
                self,
                "present_character_ids",
                _character_roster(self.present_character_ids),
            )


class NarrativeCompilerPort(Protocol):
    async def compile(
        self,
        *,
        committed: str,
        source: CommittedNarrativeSource | None = None,
        expected_context_binding: AuthorizedTurnContextBinding | None = None,
    ) -> NarrativeCandidate: ...


class NarrativeReadPort(Protocol):
    """Read-only part of the existing authoritative narrative repository."""

    async def load_turn(self, turn_id: str) -> TurnTransaction: ...

    async def load_narrative_block(
        self, narrative_block_id: str
    ) -> NarrativeBlock: ...


class NarrativePublishPort(Protocol):
    """Post-COMMIT write port; never exposed to AI workers."""

    async def publish(
        self, *, turn_id: str, narrative: NarrativeBlock
    ) -> object: ...


def _source_key(source: CommittedNarrativeSource | None) -> str | None:
    if source is None:
        return None
    encoded = json.dumps(
        {
            "turn_id": source.turn_id,
            "session_id": source.session_id,
            "story_revision": source.story_revision,
            "state_delta_id": source.state_delta_id,
            "delta_turn_id": source.state_delta.turn_id,
            "scene_id": source.scene_id,
            "protagonist_id": source.protagonist_id,
            "disclosed_facts": source.disclosed_facts,
            "input_turn_id": source.input_turn_id,
            "source_store_revision": source.source_store_revision,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CommittedNarrativeService:
    """Read-first, idempotent publication for a committed turn.

    Existing NarrativeBlocks, including frozen deterministic blocks, are
    returned unchanged with zero compiler calls. A new block is composed only
    from a committed source; speaker identity comes from that trusted source.
    Same-process concurrent calls for a turn share one bounded single-flight.
    """

    def __init__(
        self,
        *,
        reads: NarrativeReadPort,
        publisher: NarrativePublishPort,
        compiler: NarrativeCompilerPort,
        context_bindings: TurnContextBindingPort | None = None,
        max_single_flight_turns: int = _MAX_SINGLE_FLIGHT_TURNS,
    ) -> None:
        if (
            type(max_single_flight_turns) is not int
            or not 1 <= max_single_flight_turns <= _MAX_SINGLE_FLIGHT_TURNS
        ):
            raise NarrativePublicationError("invalid_single_flight_limit")
        self._reads = reads
        self._publisher = publisher
        self._compiler = compiler
        self._context_bindings = context_bindings
        self._max_single_flight_turns = max_single_flight_turns
        self._flight_guard = asyncio.Lock()
        self._flights: dict[
            str, tuple[str | None, asyncio.Task[NarrativeBlock]]
        ] = {}

    async def ensure(
        self,
        *,
        turn_id: str,
        source: CommittedNarrativeSource | None,
    ) -> NarrativeBlock:
        _bounded_text(turn_id, field="turn_id", limit=256)
        if source is not None and not isinstance(source, CommittedNarrativeSource):
            raise NarrativePublicationError("invalid_committed_source")
        source_key = _source_key(source)

        async with self._flight_guard:
            entry = self._flights.get(turn_id)
            if entry is not None:
                active_source_key, task = entry
                if active_source_key != source_key:
                    raise NarrativePublicationError(
                        "conflicting_committed_narrative_source"
                    )
            else:
                if len(self._flights) >= self._max_single_flight_turns:
                    raise NarrativePublicationError(
                        "narrative_single_flight_capacity"
                    )
                task = asyncio.create_task(
                    self._ensure_and_release(turn_id, source, source_key)
                )
                self._flights[turn_id] = (source_key, task)
                task.add_done_callback(self._consume_background_exception)

        return await asyncio.shield(task)

    async def _ensure_and_release(
        self,
        turn_id: str,
        source: CommittedNarrativeSource | None,
        source_key: str | None,
    ) -> NarrativeBlock:
        try:
            return await self._ensure_once(turn_id=turn_id, source=source)
        finally:
            async with self._flight_guard:
                current = self._flights.get(turn_id)
                if current is not None and current == (source_key, asyncio.current_task()):
                    self._flights.pop(turn_id, None)

    @staticmethod
    def _consume_background_exception(task: asyncio.Task[NarrativeBlock]) -> None:
        if not task.cancelled():
            task.exception()

    async def _existing(
        self, *, turn: TurnTransaction
    ) -> NarrativeBlock | None:
        if turn.narrative_block_id is None:
            return None
        block = await self._reads.load_narrative_block(turn.narrative_block_id)
        self._validate_stored(turn=turn, block=block)
        return block

    @staticmethod
    def _validate_stored(
        *, turn: TurnTransaction, block: NarrativeBlock
    ) -> None:
        if not isinstance(block, NarrativeBlock):
            raise NarrativePublicationError("invalid_persisted_narrative")
        if (
            turn.status not in _PUBLISHED_STATUSES
            or turn.narrative_block_id != block.id
            or turn.committed_story_revision is None
            or turn.state_delta_id is None
            or block.story_session_id != turn.session_id
            or block.source_story_revision != turn.committed_story_revision
            or block.source_state_delta_id != turn.state_delta_id
        ):
            raise NarrativePublicationError("persisted_narrative_binding_mismatch")

    @staticmethod
    def _validate_source(
        *,
        turn_id: str,
        turn: TurnTransaction,
        source: CommittedNarrativeSource,
    ) -> None:
        if turn.id != turn_id:
            raise NarrativePublicationError("turn_identity_mismatch")
        if turn.status not in _PUBLISHABLE_STATUSES:
            raise NarrativePublicationError("narrative_requires_committed_turn")
        if (
            turn.committed_story_revision is None
            or turn.state_delta_id is None
            or source.turn_id != turn.id
            or source.session_id != turn.session_id
            or source.story_revision != turn.committed_story_revision
            or source.state_delta_id != turn.state_delta_id
            or source.state_delta.id != turn.state_delta_id
            or source.state_delta.turn_id != turn.id
        ):
            raise NarrativePublicationError("committed_source_binding_mismatch")

    @staticmethod
    def _block(
        *,
        turn: TurnTransaction,
        source: CommittedNarrativeSource,
        candidate: NarrativeCandidate,
    ) -> NarrativeBlock:
        if not isinstance(candidate, NarrativeCandidate):
            raise NarrativePublicationError("invalid_narrative_candidate")

        identity = {
            "turn_id": turn.id,
            "session_id": turn.session_id,
            "story_revision": turn.committed_story_revision,
            "state_delta_id": turn.state_delta_id,
            "narration": candidate.narration,
            "speech": candidate.speech,
        }
        block_id = "narrative_" + hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:32]
        segments = [
            NarrativeSegment(type="narration", text=candidate.narration)
        ]
        if candidate.speech:
            segments.append(
                NarrativeSegment(
                    type="character",
                    speaker_id=source.protagonist_id,
                    text=candidate.speech,
                )
            )
        try:
            return NarrativeBlock(
                schema_version="1.0",
                id=block_id,
                story_session_id=turn.session_id,
                source_story_revision=turn.committed_story_revision,
                scene_id=source.scene_id,
                segments=segments,
                source_state_delta_id=turn.state_delta_id,
            )
        except (TypeError, ValueError):
            raise NarrativePublicationError("invalid_narrative_block") from None

    async def _ensure_once(
        self,
        *,
        turn_id: str,
        source: CommittedNarrativeSource | None,
    ) -> NarrativeBlock:
        turn = await self._reads.load_turn(turn_id)
        if not isinstance(turn, TurnTransaction) or turn.id != turn_id:
            raise NarrativePublicationError("turn_identity_mismatch")

        existing = await self._existing(turn=turn)
        if existing is not None:
            return existing
        if source is None:
            raise NarrativePublicationError("committed_source_required")
        self._validate_source(turn_id=turn_id, turn=turn, source=source)

        expected_binding = None
        if self._context_bindings is not None:
            if source.input_turn_id is None or source.source_store_revision is None:
                raise NarrativePublicationError("committed_source_binding_mismatch")
            try:
                expected_binding = await self._context_bindings.load(
                    turn_id=source.turn_id,
                    stage="narrative",
                )
            except TurnContextBindingError as exc:
                raise NarrativePublicationError(exc.code) from None
            if expected_binding is not None and (
                expected_binding.stage != "narrative"
                or expected_binding.turn_id != source.turn_id
                or expected_binding.input_turn_id != source.input_turn_id
                or expected_binding.source_store_revision
                != source.source_store_revision
                or expected_binding.source_story_revision != source.story_revision
            ):
                raise NarrativePublicationError("context_stale")

        if self._context_bindings is None:
            candidate = await self._compiler.compile(
                committed=source.disclosed_facts
            )
        else:
            candidate = await self._compiler.compile(
                committed=source.disclosed_facts,
                source=source,
                expected_context_binding=expected_binding,
            )
            binding = candidate.context_binding
            if binding is None:
                raise NarrativePublicationError("context_binding_required")
            if (
                binding.stage != "narrative"
                or binding.turn_id != source.turn_id
                or binding.input_turn_id != source.input_turn_id
                or binding.source_store_revision != source.source_store_revision
                or binding.source_story_revision != source.story_revision
            ):
                raise NarrativePublicationError("context_stale")
            if expected_binding is not None and binding != expected_binding:
                raise NarrativePublicationError("context_stale")
            try:
                await self._context_bindings.save(binding)
            except TurnContextBindingError as exc:
                raise NarrativePublicationError(exc.code) from None
        block = self._block(
            turn=turn,
            source=source,
            candidate=candidate,
        )
        try:
            await self._publisher.publish(turn_id=turn_id, narrative=block)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Another process may have won the immutable turn slot. Re-read and
            # recover only if a valid durable block appeared on this turn. A
            # transient failure with no durable winner must still propagate.
            raced: NarrativeBlock | None = None
            try:
                raced_turn = await self._reads.load_turn(turn_id)
                if not isinstance(raced_turn, TurnTransaction):
                    raise NarrativePublicationError("invalid_persisted_turn")
                if raced_turn.narrative_block_id is not None:
                    raced = await self._existing(turn=raced_turn)
            except Exception as recovery_error:
                raise NarrativePublicationError(
                    "narrative_publish_recovery_failed"
                ) from recovery_error
            if raced is None:
                raise
            return raced

        persisted_turn = await self._reads.load_turn(turn_id)
        if not isinstance(persisted_turn, TurnTransaction):
            raise NarrativePublicationError("invalid_persisted_turn")
        persisted = await self._existing(turn=persisted_turn)
        if persisted is None:
            raise NarrativePublicationError("narrative_publish_not_durable")
        return persisted


__all__ = [
    "CommittedNarrativeService",
    "CommittedNarrativeSource",
    "NarrativeCandidate",
    "NarrativeCompilerPort",
    "NarrativePublicationError",
    "NarrativePublishPort",
    "NarrativeReadPort",
]
