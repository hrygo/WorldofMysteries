"""W-V05 disclosure-safe DisplayText -> SpokenText compilation.

This boundary consumes already-disclosed display text plus explicitly authorized,
versioned pronunciation anchors. It has no access to hidden/canonical facts and
never invents pronunciation semantics from model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from contracts import NarrativeBlock, TurnStatus, TurnTransaction


SemanticCategory = Literal["proper_name", "term", "number", "unit", "negation"]


class AudioDisclosureError(ValueError):
    """Display/spoken mapping cannot be proven safe."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _bounded(value: str, field: str, *, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or len(value) > limit
    ):
        raise AudioDisclosureError(f"invalid_{field}")
    return value


@dataclass(frozen=True, slots=True)
class SemanticAnchor:
    """Trusted semantic identity for one exact DisplayText span.

    allowed_spoken_forms is supplied by an authorized pronunciation source.
    The compiler only verifies membership; it never guesses equivalence.
    """

    anchor_id: str
    category: SemanticCategory
    semantic_key: str
    start: int
    end: int
    source_text: str
    allowed_spoken_forms: frozenset[str]

    def __post_init__(self) -> None:
        _bounded(self.anchor_id, "anchor_id", limit=128)
        if self.category not in {
            "proper_name", "term", "number", "unit", "negation"
        }:
            raise AudioDisclosureError("invalid_semantic_category")
        semantic_key = _bounded(self.semantic_key, "semantic_key", limit=256)
        if not semantic_key.startswith(f"{self.category}:"):
            raise AudioDisclosureError("semantic_key_category_mismatch")
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or self.start < 0
            or self.end <= self.start
        ):
            raise AudioDisclosureError("invalid_semantic_span")
        _bounded(self.source_text, "source_text", limit=512)
        try:
            forms = frozenset(
                _bounded(value, "allowed_spoken_form", limit=512)
                for value in self.allowed_spoken_forms
            )
        except TypeError:
            raise AudioDisclosureError("invalid_allowed_spoken_forms") from None
        if not forms:
            raise AudioDisclosureError("missing_allowed_spoken_forms")
        # Negation changes are too semantically dangerous for pronunciation
        # substitution. Keep the exact disclosed token unchanged.
        if self.category == "negation" and forms != frozenset({self.source_text}):
            raise AudioDisclosureError("negation_spoken_form_must_be_exact")
        object.__setattr__(self, "allowed_spoken_forms", forms)


@dataclass(frozen=True, slots=True)
class PronunciationRule:
    """One versioned request to render an authorized semantic anchor differently."""

    rule_id: str
    anchor_id: str
    dictionary_revision: str
    spoken_text: str

    def __post_init__(self) -> None:
        _bounded(self.rule_id, "rule_id", limit=128)
        _bounded(self.anchor_id, "anchor_id", limit=128)
        _bounded(self.dictionary_revision, "dictionary_revision", limit=128)
        _bounded(self.spoken_text, "spoken_text", limit=512)


@dataclass(frozen=True, slots=True)
class SpokenSpanMapping:
    anchor_id: str
    category: SemanticCategory
    semantic_key: str
    display_start: int
    display_end: int
    spoken_start: int
    spoken_end: int
    source_text: str
    spoken_text: str
    rule_id: str
    dictionary_revision: str


@dataclass(frozen=True, slots=True)
class AudioDisclosure:
    display_text: str
    spoken_text: str
    dictionary_revision: str
    mappings: tuple[SpokenSpanMapping, ...]


class SpokenTextCompiler:
    """Compile only explicit, semantically anchored pronunciation changes.

    This compiler assumes DisplayText has already crossed the audible-disclosure
    authorization boundary. It is not itself an authorization service.
    """

    def compile(
        self,
        *,
        display_text: str,
        dictionary_revision: str,
        semantic_anchors: tuple[SemanticAnchor, ...],
        pronunciation_rules: tuple[PronunciationRule, ...],
    ) -> AudioDisclosure:
        _bounded(display_text, "display_text", limit=4096)
        revision = _bounded(
            dictionary_revision, "dictionary_revision", limit=128
        )

        anchors_by_id: dict[str, SemanticAnchor] = {}
        ordered_anchors = sorted(
            semantic_anchors, key=lambda item: (item.start, item.end, item.anchor_id)
        )
        previous_end = -1
        for anchor in ordered_anchors:
            if not isinstance(anchor, SemanticAnchor):
                raise AudioDisclosureError("invalid_semantic_anchor")
            if anchor.anchor_id in anchors_by_id:
                raise AudioDisclosureError("duplicate_semantic_anchor")
            if anchor.start < previous_end:
                raise AudioDisclosureError("overlapping_semantic_anchors")
            if anchor.end > len(display_text):
                raise AudioDisclosureError("semantic_anchor_out_of_bounds")
            if display_text[anchor.start:anchor.end] != anchor.source_text:
                raise AudioDisclosureError("semantic_anchor_source_drift")
            anchors_by_id[anchor.anchor_id] = anchor
            previous_end = anchor.end

        rule_by_anchor: dict[str, PronunciationRule] = {}
        rule_ids: set[str] = set()
        for rule in pronunciation_rules:
            if not isinstance(rule, PronunciationRule):
                raise AudioDisclosureError("invalid_pronunciation_rule")
            if rule.rule_id in rule_ids:
                raise AudioDisclosureError("duplicate_pronunciation_rule")
            rule_ids.add(rule.rule_id)
            if rule.dictionary_revision != revision:
                raise AudioDisclosureError("pronunciation_revision_mismatch")
            anchor = anchors_by_id.get(rule.anchor_id)
            if anchor is None:
                raise AudioDisclosureError("pronunciation_anchor_missing")
            if rule.anchor_id in rule_by_anchor:
                raise AudioDisclosureError("multiple_rules_for_semantic_anchor")
            if rule.spoken_text not in anchor.allowed_spoken_forms:
                raise AudioDisclosureError("spoken_form_not_authorized")
            if anchor.category == "negation" and rule.spoken_text != anchor.source_text:
                raise AudioDisclosureError("negation_semantics_changed")
            rule_by_anchor[rule.anchor_id] = rule

        pieces: list[str] = []
        mappings: list[SpokenSpanMapping] = []
        display_cursor = 0
        spoken_cursor = 0

        for anchor in ordered_anchors:
            rule = rule_by_anchor.get(anchor.anchor_id)
            if rule is None:
                continue

            prefix = display_text[display_cursor:anchor.start]
            pieces.append(prefix)
            spoken_cursor += len(prefix)

            spoken_start = spoken_cursor
            pieces.append(rule.spoken_text)
            spoken_cursor += len(rule.spoken_text)
            mappings.append(
                SpokenSpanMapping(
                    anchor_id=anchor.anchor_id,
                    category=anchor.category,
                    semantic_key=anchor.semantic_key,
                    display_start=anchor.start,
                    display_end=anchor.end,
                    spoken_start=spoken_start,
                    spoken_end=spoken_cursor,
                    source_text=anchor.source_text,
                    spoken_text=rule.spoken_text,
                    rule_id=rule.rule_id,
                    dictionary_revision=revision,
                )
            )
            display_cursor = anchor.end

        pieces.append(display_text[display_cursor:])
        spoken_text = "".join(pieces)
        _bounded(spoken_text, "spoken_text", limit=4096)

        return AudioDisclosure(
            display_text=display_text,
            spoken_text=spoken_text,
            dictionary_revision=revision,
            mappings=tuple(mappings),
        )


@dataclass(frozen=True, slots=True)
class AuthorizedAudioSegment:
    """Exact post-COMMIT narrative segment authorized for audible rendering."""

    turn_id: str
    story_session_id: str
    narrative_block_id: str
    story_revision: int
    state_delta_id: str
    segment_index: int
    speaker_id: str | None
    display_text: str
    speech_intent: str | None


class AudioDisclosurePort(Protocol):
    """Read-only authoritative source for committed turn + sealed narrative."""

    async def load_turn(self, turn_id: str) -> TurnTransaction: ...

    async def load_narrative_block(self, narrative_block_id: str) -> NarrativeBlock: ...


class AudioDisclosureAuthorizer:
    """Bind audible disclosure to one exact post-COMMIT narrative segment.

    There is deliberately no default/fake production port. A host must inject a
    real authoritative implementation; missing or inconsistent evidence fails
    closed before casting/TTS.
    """

    _AUDIBLE_STATUSES = frozenset(
        {TurnStatus.NARRATIVE_READY, TurnStatus.AUDIO_READY, TurnStatus.DELIVERED}
    )

    def __init__(self, port: AudioDisclosurePort) -> None:
        self._port = port

    async def authorize(
        self,
        *,
        turn_id: str,
        expected_story_revision: int,
        segment_index: int,
    ) -> AuthorizedAudioSegment:
        _bounded(turn_id, "turn_id", limit=128)
        if (
            type(expected_story_revision) is not int
            or expected_story_revision < 0
        ):
            raise AudioDisclosureError("invalid_expected_story_revision")
        if type(segment_index) is not int or segment_index < 0:
            raise AudioDisclosureError("invalid_segment_index")

        turn = await self._port.load_turn(turn_id)
        if not isinstance(turn, TurnTransaction) or turn.id != turn_id:
            raise AudioDisclosureError("turn_identity_mismatch")
        if turn.status not in self._AUDIBLE_STATUSES:
            raise AudioDisclosureError("turn_not_narrative_ready")
        if turn.committed_story_revision != expected_story_revision:
            raise AudioDisclosureError("story_revision_not_committed")
        if turn.state_delta_id is None:
            raise AudioDisclosureError("turn_missing_committed_delta")
        if turn.narrative_block_id is None:
            raise AudioDisclosureError("turn_missing_narrative_block")

        block = await self._port.load_narrative_block(turn.narrative_block_id)
        if not isinstance(block, NarrativeBlock):
            raise AudioDisclosureError("invalid_narrative_block")
        if block.id != turn.narrative_block_id:
            raise AudioDisclosureError("narrative_identity_mismatch")
        if block.story_session_id != turn.session_id:
            raise AudioDisclosureError("narrative_session_mismatch")
        if block.source_story_revision != expected_story_revision:
            raise AudioDisclosureError("narrative_story_revision_mismatch")
        if block.source_state_delta_id != turn.state_delta_id:
            raise AudioDisclosureError("narrative_state_delta_mismatch")
        if segment_index >= len(block.segments):
            raise AudioDisclosureError("narrative_segment_out_of_bounds")

        segment = block.segments[segment_index]
        _bounded(segment.text, "display_text", limit=4096)
        return AuthorizedAudioSegment(
            turn_id=turn.id,
            story_session_id=turn.session_id,
            narrative_block_id=block.id,
            story_revision=expected_story_revision,
            state_delta_id=turn.state_delta_id,
            segment_index=segment_index,
            speaker_id=segment.speaker_id,
            display_text=segment.text,
            speech_intent=segment.speech_intent,
        )
