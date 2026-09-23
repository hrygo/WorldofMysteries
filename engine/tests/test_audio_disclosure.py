"""W-V05 disclosure-safe DisplayText/SpokenText mapping tests."""
from __future__ import annotations

import pytest

from application.audio_disclosure import (
    AudioDisclosureAuthorizer,
    AudioDisclosureError,
    SpokenTextCompiler,
    PronunciationRule,
    SemanticAnchor,
)

from contracts import (
    BaseRevisions,
    NarrativeBlock,
    NarrativeSegment,
    TurnStatus,
    TurnTransaction,
)


def _anchor(
    anchor_id: str,
    category: str,
    semantic_key: str,
    display: str,
    source: str,
    *,
    allowed: frozenset[str],
) -> SemanticAnchor:
    start = display.index(source)
    return SemanticAnchor(
        anchor_id=anchor_id,
        category=category,
        semantic_key=semantic_key,
        start=start,
        end=start + len(source),
        source_text=source,
        allowed_spoken_forms=allowed,
    )


def _rule(
    rule_id: str,
    anchor_id: str,
    spoken: str,
    *,
    revision: str = "pron-v1",
) -> PronunciationRule:
    return PronunciationRule(
        rule_id=rule_id,
        anchor_id=anchor_id,
        dictionary_revision=revision,
        spoken_text=spoken,
    )


def test_versioned_name_and_number_pronunciation_keep_semantic_mapping():
    display = "周明瑞在2026年回到廷根。"
    anchors = (
        _anchor(
            "name-zhou",
            "proper_name",
            "proper_name:zhou-mingrui",
            display,
            "周明瑞",
            allowed=frozenset({"Zhou Mingrui"}),
        ),
        _anchor(
            "number-year",
            "number",
            "number:2026",
            display,
            "2026",
            allowed=frozenset({"二零二六"}),
        ),
    )

    compiled = SpokenTextCompiler().compile(
        display_text=display,
        dictionary_revision="pron-v1",
        semantic_anchors=anchors,
        pronunciation_rules=(
            _rule("rule-name", "name-zhou", "Zhou Mingrui"),
            _rule("rule-year", "number-year", "二零二六"),
        ),
    )

    assert compiled.display_text == display
    assert compiled.spoken_text == "Zhou Mingrui在二零二六年回到廷根。"
    assert [item.semantic_key for item in compiled.mappings] == [
        "proper_name:zhou-mingrui",
        "number:2026",
    ]
    assert all(item.dictionary_revision == "pron-v1" for item in compiled.mappings)
    for item in compiled.mappings:
        assert (
            compiled.spoken_text[item.spoken_start:item.spoken_end]
            == item.spoken_text
        )


def test_quantity_and_unit_may_only_use_preapproved_semantic_forms():
    display = "药剂需要5kg材料。"
    anchors = (
        _anchor(
            "qty",
            "number",
            "number:5",
            display,
            "5",
            allowed=frozenset({"五"}),
        ),
        _anchor(
            "unit",
            "unit",
            "unit:kg",
            display,
            "kg",
            allowed=frozenset({"公斤"}),
        ),
    )

    compiled = SpokenTextCompiler().compile(
        display_text=display,
        dictionary_revision="pron-v1",
        semantic_anchors=anchors,
        pronunciation_rules=(
            _rule("qty-rule", "qty", "五"),
            _rule("unit-rule", "unit", "公斤"),
        ),
    )
    assert compiled.spoken_text == "药剂需要五公斤材料。"

    with pytest.raises(AudioDisclosureError, match="spoken_form_not_authorized"):
        SpokenTextCompiler().compile(
            display_text=display,
            dictionary_revision="pron-v1",
            semantic_anchors=anchors,
            pronunciation_rules=(
                _rule("wrong-unit", "unit", "磅"),
            ),
        )


def test_negation_cannot_be_authorized_to_change_meaning():
    with pytest.raises(
        AudioDisclosureError, match="negation_spoken_form_must_be_exact"
    ):
        SemanticAnchor(
            anchor_id="neg",
            category="negation",
            semantic_key="negation:not",
            start=0,
            end=1,
            source_text="不",
            allowed_spoken_forms=frozenset({"不", "要"}),
        )

    display = "不要开门。"
    anchor = _anchor(
        "neg",
        "negation",
        "negation:not",
        display,
        "不",
        allowed=frozenset({"不"}),
    )
    compiled = SpokenTextCompiler().compile(
        display_text=display,
        dictionary_revision="pron-v1",
        semantic_anchors=(anchor,),
        pronunciation_rules=(),
    )
    assert compiled.spoken_text == display
    assert compiled.mappings == ()


def test_unanchored_or_stale_pronunciation_rule_fails_closed():
    display = "廷根"
    anchor = _anchor(
        "name",
        "proper_name",
        "proper_name:tingen",
        display,
        "廷根",
        allowed=frozenset({"Tingen"}),
    )

    with pytest.raises(AudioDisclosureError, match="pronunciation_anchor_missing"):
        SpokenTextCompiler().compile(
            display_text=display,
            dictionary_revision="pron-v1",
            semantic_anchors=(anchor,),
            pronunciation_rules=(_rule("missing", "other", "Tingen"),),
        )

    with pytest.raises(AudioDisclosureError, match="pronunciation_revision_mismatch"):
        SpokenTextCompiler().compile(
            display_text=display,
            dictionary_revision="pron-v2",
            semantic_anchors=(anchor,),
            pronunciation_rules=(_rule("stale", "name", "Tingen"),),
        )


def test_anchor_source_drift_is_rejected_before_any_spoken_text_is_built():
    display = "克莱恩走进房间。"
    anchor = SemanticAnchor(
        anchor_id="name",
        category="proper_name",
        semantic_key="proper_name:klein",
        start=0,
        end=3,
        source_text="周明瑞",
        allowed_spoken_forms=frozenset({"Klein"}),
    )

    with pytest.raises(AudioDisclosureError, match="semantic_anchor_source_drift"):
        SpokenTextCompiler().compile(
            display_text=display,
            dictionary_revision="pron-v1",
            semantic_anchors=(anchor,),
            pronunciation_rules=(),
        )


def test_overlapping_semantic_anchors_are_rejected_as_ambiguous():
    display = "2026年"
    anchors = (
        SemanticAnchor(
            anchor_id="year",
            category="number",
            semantic_key="number:2026",
            start=0,
            end=4,
            source_text="2026",
            allowed_spoken_forms=frozenset({"二零二六"}),
        ),
        SemanticAnchor(
            anchor_id="overlap",
            category="term",
            semantic_key="term:year-fragment",
            start=2,
            end=5,
            source_text="26年",
            allowed_spoken_forms=frozenset({"二六年"}),
        ),
    )

    with pytest.raises(AudioDisclosureError, match="overlapping_semantic_anchors"):
        SpokenTextCompiler().compile(
            display_text=display,
            dictionary_revision="pron-v1",
            semantic_anchors=anchors,
            pronunciation_rules=(),
        )


def test_rule_order_cannot_change_spoken_output():
    display = "周明瑞在2026年。"
    name = _anchor(
        "name",
        "proper_name",
        "proper_name:zhou-mingrui",
        display,
        "周明瑞",
        allowed=frozenset({"Zhou Mingrui"}),
    )
    year = _anchor(
        "year",
        "number",
        "number:2026",
        display,
        "2026",
        allowed=frozenset({"二零二六"}),
    )
    service = SpokenTextCompiler()
    first = service.compile(
        display_text=display,
        dictionary_revision="pron-v1",
        semantic_anchors=(name, year),
        pronunciation_rules=(
            _rule("name-rule", "name", "Zhou Mingrui"),
            _rule("year-rule", "year", "二零二六"),
        ),
    )
    second = service.compile(
        display_text=display,
        dictionary_revision="pron-v1",
        semantic_anchors=(year, name),
        pronunciation_rules=(
            _rule("year-rule", "year", "二零二六"),
            _rule("name-rule", "name", "Zhou Mingrui"),
        ),
    )
    assert first == second



class MemoryDisclosurePort:
    def __init__(self, turn: TurnTransaction, block: NarrativeBlock):
        self.turn = turn
        self.block = block
        self.requested_blocks: list[str] = []

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        return self.turn

    async def load_narrative_block(self, narrative_block_id: str) -> NarrativeBlock:
        self.requested_blocks.append(narrative_block_id)
        return self.block


def _turn(
    *,
    status: TurnStatus = TurnStatus.NARRATIVE_READY,
    revision: int = 7,
    narrative_block_id: str | None = "narrative-1",
    state_delta_id: str | None = "delta-1",
) -> TurnTransaction:
    return TurnTransaction(
        schema_version="1.0",
        id="turn-1",
        session_id="session-1",
        idempotency_key="idem-1",
        status=status,
        base_revisions=BaseRevisions(world=3, character=4, story=6),
        state_delta_id=state_delta_id,
        committed_story_revision=revision,
        narrative_block_id=narrative_block_id,
    )


def _block(
    *,
    revision: int = 7,
    session_id: str = "session-1",
    state_delta_id: str | None = "delta-1",
    text: str = "克莱恩没有打开那扇门。",
) -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id="narrative-1",
        story_session_id=session_id,
        source_story_revision=revision,
        segments=[
            NarrativeSegment(
                type="character",
                speaker_id="klein-visible",
                text=text,
                speech_intent="cautious",
            )
        ],
        source_state_delta_id=state_delta_id,
    )


async def test_audio_authorizer_returns_only_exact_committed_narrative_segment():
    port = MemoryDisclosurePort(_turn(), _block())
    result = await AudioDisclosureAuthorizer(port).authorize(
        turn_id="turn-1",
        expected_story_revision=7,
        segment_index=0,
    )

    assert result.turn_id == "turn-1"
    assert result.story_session_id == "session-1"
    assert result.narrative_block_id == "narrative-1"
    assert result.story_revision == 7
    assert result.state_delta_id == "delta-1"
    assert result.speaker_id == "klein-visible"
    assert result.display_text == "克莱恩没有打开那扇门。"
    assert port.requested_blocks == ["narrative-1"]


@pytest.mark.parametrize(
    "status",
    [
        TurnStatus.COMMITTED,
        TurnStatus.BEAT_READY,
        TurnStatus.VALIDATED,
        TurnStatus.RECEIVED,
    ],
)
async def test_audio_authorizer_rejects_turn_before_narrative_ready(status):
    port = MemoryDisclosurePort(_turn(status=status), _block())

    with pytest.raises(AudioDisclosureError, match="turn_not_narrative_ready"):
        await AudioDisclosureAuthorizer(port).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )


async def test_audio_authorizer_binds_exact_committed_story_revision():
    port = MemoryDisclosurePort(_turn(revision=7), _block(revision=7))

    with pytest.raises(AudioDisclosureError, match="story_revision_not_committed"):
        await AudioDisclosureAuthorizer(port).authorize(
            turn_id="turn-1",
            expected_story_revision=8,
            segment_index=0,
        )

    port = MemoryDisclosurePort(_turn(revision=7), _block(revision=8))
    with pytest.raises(
        AudioDisclosureError, match="narrative_story_revision_mismatch"
    ):
        await AudioDisclosureAuthorizer(port).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )


async def test_audio_authorizer_rejects_cross_session_or_delta_narrative():
    cross_session = MemoryDisclosurePort(
        _turn(), _block(session_id="other-session")
    )
    with pytest.raises(AudioDisclosureError, match="narrative_session_mismatch"):
        await AudioDisclosureAuthorizer(cross_session).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )

    wrong_delta = MemoryDisclosurePort(
        _turn(), _block(state_delta_id="other-delta")
    )
    with pytest.raises(AudioDisclosureError, match="narrative_state_delta_mismatch"):
        await AudioDisclosureAuthorizer(wrong_delta).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )


async def test_audio_authorizer_fails_closed_without_durable_narrative_link():
    no_narrative = MemoryDisclosurePort(
        _turn(narrative_block_id=None), _block()
    )
    with pytest.raises(AudioDisclosureError, match="turn_missing_narrative_block"):
        await AudioDisclosureAuthorizer(no_narrative).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )

    no_delta = MemoryDisclosurePort(
        _turn(state_delta_id=None), _block()
    )
    with pytest.raises(AudioDisclosureError, match="turn_missing_committed_delta"):
        await AudioDisclosureAuthorizer(no_delta).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )


async def test_audio_authorizer_rejects_invalid_or_empty_segment():
    port = MemoryDisclosurePort(_turn(), _block())
    with pytest.raises(AudioDisclosureError, match="narrative_segment_out_of_bounds"):
        await AudioDisclosureAuthorizer(port).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=1,
        )

    empty = MemoryDisclosurePort(_turn(), _block(text=""))
    with pytest.raises(AudioDisclosureError, match="invalid_display_text"):
        await AudioDisclosureAuthorizer(empty).authorize(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
        )
