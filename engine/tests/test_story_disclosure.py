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

from application.story_disclosure import disclosed_turn_facts
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


def _bootstrap(clue_display_names: dict[str, str]):
    return SimpleNamespace(
        presentation=SimpleNamespace(clue_display_names=clue_display_names)
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
