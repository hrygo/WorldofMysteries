"""Tests for the shared post-COMMIT disclosure projection.

This logic used to exist twice — once in ``story_runtime`` and once in the
scenario post-COMMIT handlers — so it was tested twice by two suites, each of
which passed on its own. These tests pin the behaviour both copies must keep,
now that there is one copy both call.
"""
from __future__ import annotations

import ast
from types import SimpleNamespace
from pathlib import Path

from application.story_initialization import (
    GOLDEN_CHARACTER_DISPLAY_NAMES,
    GOLDEN_CLUE_DISPLAY_NAMES,
)
from application.story_disclosure import (
    disclosed_castable_roster,
    disclosed_turn_facts,
)
from contracts import StateDelta

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def test_no_production_module_reimplements_the_disclosure_projection():
    """Guard the merge, not only the behaviour.

    Two copies is how this leaked in the first place: each suite exercised its
    own copy, each passed, and nothing compared them. Behaviour tests cannot
    catch a third copy appearing tomorrow — the third copy would simply not be
    called by these tests, so the paths that do call it would stay green while
    it sat there diverging.

    The identifying mark is not a function name — a re-implementation called
    anything still has to render the same turn summary. It is the pair: the
    function reads the display-name table *and* builds the outcome line. The
    display-name read alone is not enough, because
    ``story_initialization._validate_presentation`` reads that table to compare
    it against the golden values, and flagging a validator would make this
    guard cry wolf on correct code.
    """
    offenders: list[str] = []
    for package in ("application", "infrastructure"):
        for module in sorted((ENGINE_ROOT / package).rglob("*.py")):
            if module.name == "story_disclosure.py":
                continue
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                reads_names = any(
                    isinstance(child, ast.Attribute)
                    and child.attr == "clue_display_names"
                    for child in ast.walk(node)
                )
                renders_turn_summary = any(
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and "结果判定" in child.value
                    for child in ast.walk(node)
                )
                if reads_names and renders_turn_summary:
                    offenders.append(
                        f"{module.relative_to(ENGINE_ROOT)}:{node.lineno} {node.name}"
                    )

    assert not offenders, (
        "已披露事实投影被重新实现；请改为调用 "
        f"application.story_disclosure.disclosed_turn_facts：{offenders}"
    )


def test_both_post_commit_paths_call_the_shared_projection():
    """The merge is only real if both callers actually moved."""
    for relative in (
        "infrastructure/story_runtime.py",
        "infrastructure/scenarios/post_commit_handlers.py",
    ):
        source = (ENGINE_ROOT / relative).read_text(encoding="utf-8")
        assert "disclosed_turn_facts" in source, f"{relative} 未调用共享投影"


def _bootstrap(
    clue_display_names: dict[str, str],
    character_display_names: dict[str, str] | None = None,
):
    return SimpleNamespace(
        presentation=SimpleNamespace(
            clue_display_names=clue_display_names,
            character_display_names=character_display_names or {},
        )
    )


def _delta(
    *,
    outcome: str = "clean_success",
    clue_ids_add: list[str] | None = None,
    scene_id: str | None = None,
    world_time_delta_minutes: float | None = None,
) -> StateDelta:
    story_delta: dict = {}
    if clue_ids_add is not None:
        story_delta["clue_ids_add"] = clue_ids_add
    if scene_id is not None:
        story_delta["scene_id"] = scene_id
    if world_time_delta_minutes is not None:
        story_delta["world_time_delta_minutes"] = world_time_delta_minutes
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta_disclosure_01",
            "turn_id": "turn_disclosure_01",
            "outcome": outcome,
            "story_delta": story_delta,
            "character_deltas": [
                {"character_id": "npc_doctor_morris", "patches": [], "evidence_ids": []}
            ],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


def test_the_outcome_is_always_disclosed():
    assert disclosed_turn_facts(
        delta=_delta(outcome="success_with_cost"),
        bootstrap=_bootstrap({}),
    ) == "结果判定：success_with_cost"


def test_a_clue_is_disclosed_by_its_public_label():
    text = disclosed_turn_facts(
        delta=_delta(clue_ids_add=["clue_doctor_pause"]),
        bootstrap=_bootstrap({"clue_doctor_pause": "医生的停顿"}),
    )

    assert "医生的停顿" in text
    assert "clue_doctor_pause" not in text


def test_a_clue_without_a_public_label_is_omitted_rather_than_disclosed_by_id():
    """The fail-closed half of the projection.

    Omitting is the whole point: this is a post-COMMIT path, so a missing
    label cannot fail the turn, and emitting the canonical id instead would
    turn "we have no public name for this" into a disclosure of the very
    identifier the projection exists to withhold.
    """
    text = disclosed_turn_facts(
        delta=_delta(clue_ids_add=["clue_hidden", "clue_doctor_pause"]),
        bootstrap=_bootstrap({"clue_doctor_pause": "医生的停顿"}),
    )

    assert "clue_hidden" not in text
    assert "医生的停顿" in text


def test_no_canonical_identifier_reaches_the_narrator():
    canonical = ["clue_a", "clue_b", "clue_c"]
    text = disclosed_turn_facts(
        delta=_delta(clue_ids_add=canonical),
        bootstrap=_bootstrap({}),
    )

    for clue_id in canonical:
        assert clue_id not in text


def test_scene_and_world_time_are_disclosed_when_the_delta_moves_them():
    text = disclosed_turn_facts(
        delta=_delta(scene_id="back_alley", world_time_delta_minutes=15),
        bootstrap=_bootstrap({}),
    )

    assert "场景转为：back_alley" in text
    assert "世界时间推进：15" in text


def test_an_unchanged_scene_and_clock_add_no_lines():
    text = disclosed_turn_facts(
        delta=_delta(),
        bootstrap=_bootstrap({}),
    )

    assert text == "结果判定：clean_success"


# --- castable roster (ADR-006 D2 / D5) -------------------------------------


PROTAGONIST = "char_evelyn_gray"
NAMES = {
    # The protagonist is given a public label on purpose. Without one the
    # label filter would drop them first and the D5 exclusion would never be
    # exercised — the test would pass for the wrong reason, and removing the
    # exclusion entirely would leave it green.
    "char_evelyn_gray": "爱伦·格雷",
    "npc_doctor_morris": "莫里斯医生",
    "npc_jonathan_vale": "乔纳森·维尔",
}


def _roster(present, *, names=None):
    return disclosed_castable_roster(
        active_character_ids=present,
        protagonist_id=PROTAGONIST,
        character_display_names=NAMES if names is None else names,
    )


def test_the_protagonist_stays_otherwise_eligible_for_the_cast():
    """Fixture precondition for the D5 test below.

    ``test_the_player_avatar_is_never_cast`` proves one thing: the protagonist
    is dropped despite being present. It can only prove that while the
    protagonist would otherwise pass the label filter. Drop their entry from
    ``NAMES`` and the test keeps passing — for the wrong reason — while the
    exclusion it exists to guard is never exercised. This assertion is what
    stops that from happening quietly.
    """
    assert PROTAGONIST in NAMES, (
        "主角需要保留公开名，否则 D5 排除测试会退化为假阳性"
    )


def test_no_public_name_is_written_in_a_latin_script():
    """ADR-006 5.1 4: every public name is Tingen-style Chinese.

    These two tables are the only place a character's or a clue's public name
    is defined, and the public name is what the model is told to attribute a
    line to and what a voice is bound to. A name written in a Latin script
    therefore does not merely look wrong on screen: it asks the model to
    attribute lines to a spelling the world has no word for, and it makes the
    name unusable as a TTS speaker label.

    The emptiness precondition matters. Without it this test would pass
    trivially on a bundle whose tables had been emptied, which is exactly the
    state in which nothing is cast and no one notices the rule stopped being
    enforced.
    """
    assert GOLDEN_CHARACTER_DISPLAY_NAMES, "角色公开名表不应为空"
    assert GOLDEN_CLUE_DISPLAY_NAMES, "线索公开名表不应为空"

    offenders = {
        name: label
        for name, label in {
            **GOLDEN_CHARACTER_DISPLAY_NAMES,
            **GOLDEN_CLUE_DISPLAY_NAMES,
        }.items()
        if any(ch.isascii() and ch.isalpha() for ch in label)
    }
    assert not offenders, f"公开名不得使用拉丁字母: {offenders}"


def test_an_undeclared_roster_stays_undeclared():
    """``None`` means the world has not said who is here.

    It is not the same claim as an empty scene, and the projection must not
    turn "we have not asked" into "nobody is here".
    """
    assert _roster(None) is None


def test_an_empty_scene_yields_an_empty_roster_not_none():
    assert _roster([]) == ()


def test_the_player_avatar_is_never_cast():
    """ADR-006 D5: the player speaks in their own voice.

    The protagonist stays in the world roster — they are in the room — and is
    dropped only here, at the boundary between being present and being heard.
    """
    assert _roster([PROTAGONIST, "npc_doctor_morris"]) == (
        ("npc_doctor_morris", "莫里斯医生"),
    )


def test_a_character_with_no_public_label_is_omitted_rather_than_disclosed_by_id():
    """The authorization half, and the same fail-closed rule the clues obey."""
    assert _roster(["npc_stranger_with_no_label"]) == ()


def test_scene_order_is_preserved():
    assert _roster(["npc_jonathan_vale", "npc_doctor_morris"]) == (
        ("npc_jonathan_vale", "乔纳森·维尔"),
        ("npc_doctor_morris", "莫里斯医生"),
    )


def test_an_empty_label_table_casts_nobody():
    """A bundle written before this table existed keeps its old behaviour."""
    assert _roster(["npc_doctor_morris", "npc_jonathan_vale"], names={}) == ()


def test_the_projection_is_deterministic_for_the_same_committed_roster():
    """The property publication relies on.

    The roster is hashed into block identity, so if anything time-varying could
    reach this projection the same committed history would publish under two
    identities. It reads committed state and an immutable bootstrap, and
    nothing else — in particular nothing from the expression attempt.
    """
    present = [PROTAGONIST, "npc_doctor_morris", "npc_jonathan_vale"]

    assert _roster(present) == _roster(present)


def test_order_follows_the_scene_rather_than_the_caller():
    """Scene order is part of the committed fact, so it is preserved verbatim."""
    forward = _roster(["npc_doctor_morris", "npc_jonathan_vale"])
    backward = _roster(["npc_jonathan_vale", "npc_doctor_morris"])

    assert forward != backward
    assert [cid for cid, _ in forward] == ["npc_doctor_morris", "npc_jonathan_vale"]
