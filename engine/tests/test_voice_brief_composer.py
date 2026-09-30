"""Composing a brief for a character nobody wrote one for (VF-56).

The contract is mostly about restraint. The composer may only read what the
character has already said out loud, must give the same character the same
voice forever, and must never let two characters share one.
"""

from __future__ import annotations

import pytest

from application.voice_brief_composer import (
    ComposedBrief,
    VoiceBriefComposer,
    VoiceBriefFacts,
    axis_slots,
)

LINES = (
    "今天雾很大，街角那盏煤气灯又坏了，巷子尽头一点光都没有。",
    "你说的是哪一班？我记得是三点的，可那时钟早就停了吧。",
)


def facts(identity: str = "npc-a", **overrides) -> VoiceBriefFacts:
    base = {
        "presentation_identity": identity,
        "display_name": "路人甲",
        "usage": "dialogue",
        "spoken_lines": LINES,
    }
    base.update(overrides)
    return VoiceBriefFacts(**base)


async def test_a_character_who_has_spoken_gets_a_brief():
    brief = await VoiceBriefComposer().compose(facts())
    assert brief is not None
    assert brief.origin == "composed"
    assert brief.reference_text == LINES[0]
    assert brief.validation_text == LINES[1]


async def test_the_character_reads_their_own_words():
    """The texts are lines they actually said.

    Inventing a third sentence would put words in this character's mouth that
    the world never gave them, and tuning a voice on text nobody speaks is
    work the cross-text check was built to catch.
    """
    brief = await VoiceBriefComposer().compose(facts())
    assert brief is not None
    assert set((brief.reference_text, brief.validation_text)) <= set(LINES)
    assert brief.reference_text != brief.validation_text


async def test_a_character_who_has_spoken_once_is_not_cast_yet():
    """Not a failure — a fact, and the audio falls back to a subtitle."""
    assert await VoiceBriefComposer().compose(
        facts(spoken_lines=("今天雾很大。",))
    ) is None
    assert await VoiceBriefComposer().compose(facts(spoken_lines=())) is None
    # Too short to be a read at all.
    assert await VoiceBriefComposer().compose(
        facts(spoken_lines=("嗯。", "啊。"))
    ) is None


async def test_two_identical_lines_are_not_two_lines():
    assert await VoiceBriefComposer().compose(
        facts(spoken_lines=(LINES[0], LINES[0]))
    ) is None


async def test_the_same_character_keeps_the_same_voice_forever():
    """Re-encountered next week, they must still sound like themselves."""
    first = await VoiceBriefComposer().compose(facts("npc-a"))
    later = await VoiceBriefComposer().compose(facts("npc-a"))
    assert first == later


async def test_two_characters_never_land_on_the_same_voice():
    """The one outcome acceptance 1 forbids outright."""
    composer = VoiceBriefComposer()
    taken: tuple[int, ...] = ()
    slots = []
    for index in range(len(axis_slots())):
        brief = await composer.compose(
            facts(f"npc-{index}", taken_slots=taken)
        )
        assert brief is not None
        assert brief.slot not in taken
        taken = taken + (brief.slot,)
        slots.append(brief.slot)
    assert len(set(slots)) == len(axis_slots())


async def test_a_taken_slot_is_stepped_over_rather_than_shared():
    composer = VoiceBriefComposer()
    first = await composer.compose(facts("npc-a"))
    assert first is not None
    second = await composer.compose(
        facts("npc-a", taken_slots=(first.slot,))
    )
    assert second is not None
    assert second.slot != first.slot


async def test_the_brief_carries_no_dossier():
    """A brief composed from spoken lines cannot leak unspoken ones.

    The facts type has nowhere to put a hidden identity or an unplayed plot
    beat, so the exclusion is structural rather than a rule someone has to
    remember while editing.
    """
    brief = await VoiceBriefComposer().compose(facts())
    assert brief is not None
    fields = set(ComposedBrief.__dataclass_fields__)
    assert fields == {
        "design_id",
        "presentation_identity",
        "usage",
        "public_traits",
        "voice_description",
        "reference_text",
        "validation_text",
        "slot",
        "design_revision",
        "origin",
    }


class _Refiner:
    def __init__(self, answer: str | None = None, fails: bool = False) -> None:
        self.answer = answer
        self.fails = fails
        self.seen: list[tuple[str, ...]] = []
        self.seen_texts: list[str] = []

    async def refine(self, *, presentation_identity, description, traits):
        self.seen.append(traits)
        self.seen_texts.append(description)
        if self.fails:
            raise RuntimeError("model is down")
        return self.answer


async def test_polish_changes_the_prose_and_nothing_else():
    plain = await VoiceBriefComposer().compose(facts())
    refiner = _Refiner(answer="一个雾夜里的本地人，嗓子被风吹得发哑。")
    polished = await VoiceBriefComposer(refiner=refiner).compose(facts())

    assert plain is not None and polished is not None
    assert polished.voice_description == "一个雾夜里的本地人，嗓子被风吹得发哑。"
    assert polished.reference_text == plain.reference_text
    assert polished.validation_text == plain.validation_text
    assert polished.public_traits == plain.public_traits
    assert polished.slot == plain.slot


async def test_a_model_that_is_down_or_empty_changes_nothing():
    plain = await VoiceBriefComposer().compose(facts())
    for refiner in (_Refiner(fails=True), _Refiner(answer=None), _Refiner(answer="   ")):
        degraded = await VoiceBriefComposer(refiner=refiner).compose(facts())
        assert plain is not None and degraded is not None
        assert degraded == plain


async def test_the_refiner_is_never_shown_the_texts():
    """It polishes a description. It has no reason to see what is being read."""
    refiner = _Refiner(answer="仍然合规。")
    brief = await VoiceBriefComposer(refiner=refiner).compose(facts())
    assert brief is not None
    for line in LINES:
        assert line not in refiner.seen_texts[0]
    assert len(refiner.seen) == 1
    assert len(refiner.seen_texts) == 1


@pytest.mark.parametrize("identity", ["", "   "])
async def test_an_identity_with_no_name_is_not_cast(identity):
    assert await VoiceBriefComposer().compose(facts(identity)) is None


async def test_a_composed_brief_is_always_castable_as_written():
    """The composer's filter and the repository's validator must agree.

    A composer that let through a line the repository later rejects turns
    "this character has not said enough yet" into a supply outage at the
    moment of registration — the least useful place to learn it.
    """
    from domain.voice_identity import VoiceBindingScope

    scope = VoiceBindingScope(
        owner_id="p",
        world_id="w",
        worldline_id="l",
        presentation_identity="npc-a",
        phase="narrative",
        locale="zh-CN",
    )
    brief = await VoiceBriefComposer().compose(facts())
    assert brief is not None
    spec = brief.task_spec(
        scope=scope,
        request_id="auto-test",
        persona_revision="persona-1",
        authorization_ref="auto:voice-supply",
        provider_instance="speechrail-local",
    )
    assert spec.validated() is not None
    assert spec.origin_ref == "voice_brief:composed:npc-a"
