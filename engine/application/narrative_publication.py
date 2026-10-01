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
class NarrativeLine:
    """One proposed line of dialogue, attributed by **public label**.

    The speaker is a label, never a canonical id. The model is given labels
    only — that is the whole point of the disclosure projection — so it cannot
    propose an id even if it wanted to. Turning a label into the id a voice
    binds to is the publication layer's job, against the trusted roster.

    A character may speak more than once in a turn, so duplicate speakers are
    legitimate here. What is not legitimate is a speaker absent from the
    roster, and that is refused at binding time rather than filtered.
    """

    speaker: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "speaker",
            _bounded_text(self.speaker, field="line_speaker", limit=256),
        )
        object.__setattr__(
            self,
            "text",
            _bounded_text(self.text, field="line_text", limit=_MAX_NARRATIVE_CHARS),
        )


@dataclass(frozen=True, slots=True)
class NarrativeCandidate:
    """Model-produced expression with narration and dialogue kept distinct.

    Who speaks is named by public label in ``lines``; only the trusted
    committed source may turn a label into a bound speaker, and only for
    someone its castable roster admits.

    ``speech`` is a **migration seam**, not a second way to say the same thing.
    It is the pre-D3 single-unattributed-line shape and is honoured only when
    the source declares no castable roster at all. Once a roster exists the
    legacy field is refused, so the two shapes can never both apply. Removal
    slice: VF-83D, after VF-83C switches the model onto ``lines``.
    """

    narration: str
    lines: tuple[NarrativeLine, ...] = ()
    speech: str = ""
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
        if not isinstance(self.lines, tuple) or any(
            not isinstance(line, NarrativeLine) for line in self.lines
        ):
            raise NarrativePublicationError("invalid_narrative_candidate")
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

    #: Who may be *heard*, as ``(canonical_id, public_label)`` pairs — the
    #: world roster above, narrowed by ADR-006 D5.
    #:
    #: This is a second field rather than a replacement, and the two are not
    #: redundant. ``present_character_ids`` is a world fact: who was in the
    #: room, protagonist included. This is a presentation fact: who the
    #: publication layer may bind a voice to, which excludes the protagonist
    #: (product setting) and anyone without a public name (semantic
    #: authorisation). Collapsing them would erase the distinction ADR-006 D5
    #: is built on, and would leave no record that the protagonist *was*
    #: present.
    #:
    #: The model is given labels only, so a line it proposes can be bound back
    #: to a canonical id through this table alone. That is why it travels with
    #: the source rather than being re-derived at publication time: the
    #: publication layer would otherwise need the bootstrap's name table, and a
    #: second reader of it is a second unreviewed source of who is called what.
    #:
    #: Same three states as ``present_character_ids``: ``None`` means no roster
    #: was declared at all, ``()`` means the world declared one and it cast
    #: nobody, and a non-empty tuple is authoritative.
    castable_character_labels: tuple[tuple[str, str], ...] | None = None

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
        if self.castable_character_labels is not None:
            object.__setattr__(
                self,
                "castable_character_labels",
                _castable_labels(self.castable_character_labels),
            )
            # The castable roster claims to be the world roster, narrowed. If it
            # is not, something upstream invented a speaker who was never in the
            # room — and nothing downstream would report it, because every id
            # would still resolve. That is the whole failure mode this design
            # exists to prevent, so it is refused at construction.
            if self.present_character_ids is not None:
                absent = {
                    character_id
                    for character_id, _ in self.castable_character_labels
                } - set(self.present_character_ids)
                if absent:
                    raise NarrativePublicationError("castable_outside_scene")


def _castable_labels(value: object) -> tuple[tuple[str, str], ...]:
    """Normalise ``(canonical_id, public_label)`` pairs, refusing ambiguity.

    Two labels for one character, or one id wearing two labels, both mean the
    projection is ambiguous about who is speaking. Binding a line to the wrong
    one would cast the wrong person's voice, so neither is collapsed or
    resolved here — the roster is refused and the turn keeps its historical
    single-speaker behaviour.
    """
    if not isinstance(value, (tuple, list)):
        raise NarrativePublicationError("invalid_castable_character_labels")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise NarrativePublicationError("invalid_castable_character_labels")
        character_id = _bounded_text(
            item[0], field="castable_character", limit=256
        )
        label = _bounded_text(item[1], field="castable_label", limit=256)
        pairs.append((character_id, label))
    if len({character_id for character_id, _ in pairs}) != len(pairs):
        raise NarrativePublicationError("duplicate_castable_character")
    if len({label for _, label in pairs}) != len(pairs):
        raise NarrativePublicationError("duplicate_castable_label")
    return tuple(pairs)


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


def _bound_dialogue(
    *,
    source: CommittedNarrativeSource,
    candidate: NarrativeCandidate,
) -> list[tuple[str, str]]:
    """Bind proposed lines to the speakers the trusted roster admits.

    The model may only name a **public label**; this is where a label becomes
    the canonical id a voice binds to, and the roster is the only thing that
    makes that conversion legitimate.

    Every refusal here is a refusal to publish, never a silent drop. A line
    naming someone outside the roster is not "dialogue we chose not to say" —
    it is a proposal to put words in a mouth the world did not open, and
    dropping it would publish a block that silently disagrees with the model
    about what was said.

    Three roster states, three answers:

    * ``None`` — the world declared no castable roster. Nothing is authorised,
      so no label can be bound; the pre-D3 single ``speech`` is honoured
      instead, bound to the protagonist. This is the migration seam and it is
      wrong under ADR-006 D5; VF-83D removes it with the model-side switch.
    * ``()`` — the world declared a roster and it casts nobody. Narration
      only. Any proposed dialogue is a contradiction of what the world said.
    * non-empty — authoritative. Every line must resolve, and at least one
      line is required so a committed turn stays speakable.
    """
    roster = source.castable_character_labels

    if roster is None:
        if candidate.lines:
            raise NarrativePublicationError("speaker_without_roster")
        if not candidate.speech:
            return []
        return [(source.protagonist_id, candidate.speech)]

    if not roster:
        if candidate.lines or candidate.speech:
            raise NarrativePublicationError("speaker_not_castable")
        return []

    if candidate.speech:
        # A roster exists, so the legacy unattributed line has nowhere to bind.
        # Honouring it would put every turn's dialogue on the protagonist
        # regardless of who the world put in the room.
        raise NarrativePublicationError("legacy_speech_without_roster")
    if not candidate.lines:
        raise NarrativePublicationError("missing_character_speech")

    by_label = {label: character_id for character_id, label in roster}
    dialogue: list[tuple[str, str]] = []
    for line in candidate.lines:
        character_id = by_label.get(line.speaker)
        if character_id is None:
            raise NarrativePublicationError("speaker_not_castable")
        # D5 already removed the protagonist from the castable roster upstream.
        # Re-checking here costs one comparison and closes the last path by
        # which the player-avatar could acquire a cast voice.
        if character_id == source.protagonist_id:
            raise NarrativePublicationError("protagonist_not_castable")
        dialogue.append((character_id, line.text))
    return dialogue


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
            # The roster is part of the source's identity because it decides who
            # the block may speak for. Two attempts at one turn that disagree
            # about the roster are not retries of the same publication — they
            # would bind different voices — so they are refused rather than
            # raced (ADR-006 D2, §4.1).
            "present_character_ids": (
                None
                if source.present_character_ids is None
                else list(source.present_character_ids)
            ),
            "castable_character_labels": (
                None
                if source.castable_character_labels is None
                else [list(pair) for pair in source.castable_character_labels]
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def turn_scene_roster(
    *,
    story_state: object,
    committed_story_revision: int,
) -> tuple[str, ...] | None:
    """The scene roster *as of one turn*, or ``None`` when it cannot be known.

    Two different questions are answered here and they must not be confused.

    **Whose scene is this?** ``story_state_json`` holds only the *current*
    state of a session, never its history. A post-COMMIT job may run long after
    the turn it serves, by which point later turns have moved the roster on.
    Reading it then would attribute this turn's speech to whoever is in the
    room *now* — and nothing would report an error, because every value read
    would be internally consistent. So the roster is taken only when the state
    is provably the one this turn committed, and declined otherwise.

    **Does the world declare a roster at all?** ``None`` and ``()`` stay
    distinct: an empty scene is an assertion, an absent roster is the absence of
    one. Both end up as ``None`` here only in the first case above — a
    declined read is indistinguishable from a world that never said, and both
    mean "publication keeps its historical single-speaker behaviour" rather
    than "nobody may speak".

    The caller supplies the state, so this stays a pure function: which frozen
    state a given post-COMMIT job is allowed to see is that job's judgement, and
    burying it here would make the unsafe read look like a safe one.
    """
    if story_state is None:
        return None
    revision = getattr(story_state, "revision", None)
    if revision != committed_story_revision:
        return None
    scene = getattr(story_state, "scene", None)
    active = getattr(scene, "active_character_ids", None)
    if active is None:
        return None
    if not isinstance(active, (tuple, list)):
        return None
    return _character_roster(active)


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

        dialogue = _bound_dialogue(source=source, candidate=candidate)
        identity = {
            "turn_id": turn.id,
            "session_id": turn.session_id,
            "story_revision": turn.committed_story_revision,
            "state_delta_id": turn.state_delta_id,
            "narration": candidate.narration,
            # The *bound* dialogue, not the proposal: two attempts that agree
            # on the words but disagree on who says them publish under
            # different identities, because they are different blocks.
            "dialogue": [[speaker_id, text] for speaker_id, text in dialogue],
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
        for speaker_id, text in dialogue:
            segments.append(
                NarrativeSegment(
                    type="character",
                    speaker_id=speaker_id,
                    text=text,
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
    "NarrativeLine",
    "NarrativePublicationError",
    "NarrativePublishPort",
    "NarrativeReadPort",
]
