"""W-V05 disclosure-safe DisplayText/SpokenText mapping tests."""
from __future__ import annotations

import pytest

from application.audio_disclosure import (
    AudioDisclosureError,
    AudioDisclosureService,
    PronunciationRule,
    SemanticAnchor,
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

    compiled = AudioDisclosureService().compile(
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

    compiled = AudioDisclosureService().compile(
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
        AudioDisclosureService().compile(
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
    compiled = AudioDisclosureService().compile(
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
        AudioDisclosureService().compile(
            display_text=display,
            dictionary_revision="pron-v1",
            semantic_anchors=(anchor,),
            pronunciation_rules=(_rule("missing", "other", "Tingen"),),
        )

    with pytest.raises(AudioDisclosureError, match="pronunciation_revision_mismatch"):
        AudioDisclosureService().compile(
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
        AudioDisclosureService().compile(
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
        AudioDisclosureService().compile(
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
    service = AudioDisclosureService()
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
