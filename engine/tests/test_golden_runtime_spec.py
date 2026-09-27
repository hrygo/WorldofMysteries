"""Executable consistency checks for the Golden 001 five-turn test specification.

These checks validate test inputs and expected-state coverage only. They do not
run the five-turn Engine workflow or claim M5 runtime acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"

EXPECTED_ASSERTION_IDS = tuple(f"G{number:03d}" for number in range(1, 13))
EXPECTED_FAILURE_CHECKPOINTS = (
    "after advice",
    "after action intent",
    "after resolver before commit",
    "immediately after commit",
    "after beat plan",
    "after narrative",
    "during finalization transaction",
    "after finalization commit before projection",
)
RUNTIME_ASSERTION_TEST_TARGETS = {
    "G001": "test_runtime_secret_04_stays_hidden_through_all_turns",
    "G002": "test_committed_outcomes_never_label_morris_as_culprit",
    "G003": "test_reasoner_context_never_exceeds_sequence_9_abilities",
    "G004": "test_player_hypothesis_never_becomes_world_truth_without_evidence",
    "G005": "test_turn4_advice_is_reinterpreted_by_character_reasoner",
    "G006": "test_closure_does_not_add_major_conflict",
    "G007": "test_episode_retains_unresolved_mystery_threads",
    "G008": "test_private_world_writeback_never_enters_public_projection",
    "G009": "test_narrative_regeneration_does_not_change_committed_story_state",
    "G010": "test_audio_regeneration_does_not_change_narrative_or_story_state",
    "G011": "test_retrieval_rejects_unauthorized_hidden_knowledge",
    "G012": "test_episode_finalization_is_atomic_on_storage_failure",
}
RUNTIME_FAILURE_TEST_TARGETS = dict(
    zip(
        EXPECTED_FAILURE_CHECKPOINTS,
        (
            "test_restart_after_advice_reuses_durable_advice",
            "test_restart_after_action_intent_reuses_durable_proposal",
            "test_restart_after_resolver_before_commit_commits_once",
            "test_restart_immediately_after_commit_returns_existing_result",
            "test_restart_after_beat_plan_resumes_expression",
            "test_restart_after_narrative_reuses_persisted_block",
            "test_finalization_transaction_rolls_back_all_domain_writes",
            "test_restart_after_finalization_commit_rebuilds_projection_once",
        ),
    )
)
MOCK_SUFFIXES = (
    "action_intent",
    "beat_plan",
    "narrative_block",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assertion_entries(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("scenario: golden_001\n")
    return re.findall(
        r"(?m)^- id: (G\d{3})\n  rule: ([a-z0-9_]+)$",
        text,
    )


def test_golden_canonical_content_matches_runtime_bundle_copies():
    """The runtime pack mirrors scenario facts from fixtures/golden_001."""
    for filename in ("seed.json", "world.json", "character.json", "expected_episode.json"):
        assert _read_json(FIXTURES / filename) == _read_json(RUNTIME / filename)

    canonical_knowledge = {
        path.name: _read_json(path)
        for path in sorted((FIXTURES / "knowledge").glob("*.json"))
    }
    runtime_knowledge = {
        path.name: _read_json(path)
        for path in sorted((RUNTIME / "knowledge").glob("*.json"))
    }
    assert runtime_knowledge == canonical_knowledge


def test_golden_assertion_registry_covers_g001_through_g012_once():
    canonical = FIXTURES / "assertions.yaml"
    runtime_copy = RUNTIME / "assertions.yaml"
    assert runtime_copy.read_text(encoding="utf-8") == canonical.read_text(
        encoding="utf-8"
    )

    entries = _assertion_entries(canonical)
    assertion_ids = [identifier for identifier, _ in entries]
    rules = [rule for _, rule in entries]
    assert tuple(assertion_ids) == EXPECTED_ASSERTION_IDS
    assert len(set(assertion_ids)) == len(EXPECTED_ASSERTION_IDS)
    assert all(rules)


def test_runtime_trace_matrix_targets_every_assertion_and_failure_checkpoint():
    assert set(RUNTIME_ASSERTION_TEST_TARGETS) == set(EXPECTED_ASSERTION_IDS)
    assert len(set(RUNTIME_ASSERTION_TEST_TARGETS.values())) == len(
        EXPECTED_ASSERTION_IDS
    )
    assert tuple(RUNTIME_FAILURE_TEST_TARGETS.keys()) == EXPECTED_FAILURE_CHECKPOINTS
    assert len(set(RUNTIME_FAILURE_TEST_TARGETS.values())) == len(
        EXPECTED_FAILURE_CHECKPOINTS
    )
    assert all(name.startswith("test_") for name in RUNTIME_ASSERTION_TEST_TARGETS.values())
    assert all(name.startswith("test_") for name in RUNTIME_FAILURE_TEST_TARGETS.values())


def test_golden_runtime_contains_five_linked_turn_inputs_and_mock_outputs():
    advice_files = sorted((FIXTURES / "turns").glob("*_advice.json"))
    assert [path.name for path in advice_files] == [
        f"{turn:02d}_advice.json" for turn in range(1, 6)
    ]

    for suffix in MOCK_SUFFIXES:
        files = sorted((RUNTIME / "mock").glob(f"*_{suffix}.json"))
        assert [path.name for path in files] == [
            f"{turn:02d}_{suffix}.json" for turn in range(1, 6)
        ]

    for turn in range(1, 6):
        sequence = f"{turn:02d}"
        advice = _read_json(FIXTURES / "turns" / f"{sequence}_advice.json")
        action = _read_json(RUNTIME / "mock" / f"{sequence}_action_intent.json")
        beat = _read_json(RUNTIME / "mock" / f"{sequence}_beat_plan.json")
        narrative = _read_json(RUNTIME / "mock" / f"{sequence}_narrative_block.json")

        assert advice["id"] in action["evidence_ids"]
        assert action["turn_id"] == f"turn_g001_{sequence}"
        assert beat["story_session_id"] == "session_golden_001"
        assert narrative["story_session_id"] == "session_golden_001"
        assert beat["source_story_revision"] == turn
        assert narrative["source_story_revision"] == turn


def test_five_committed_state_fixtures_have_sequential_revisions_and_keep_secret_04_hidden():
    for turn in range(1, 6):
        sequence = f"{turn:02d}"
        committed = _read_json(
            RUNTIME / "expected" / f"{sequence}_committed_state.json"
        )
        summary = _read_json(FIXTURES / "turns" / f"{sequence}_expected.json")

        # Summary-level expected outcomes and committed-state snapshots have
        # different shapes and must not be substituted for one another.
        assert "adherence" in summary
        if turn < 5:
            assert "outcome" in summary
        else:
            assert summary["closure"] is True
            assert summary["forbid_new_major_conflict"] is True
        assert "story_revision" not in summary
        assert committed["turn"] == turn
        assert committed["story_revision"] == turn
        assert committed["secrets"]["secret_04"] == "hidden"


def test_episode_expectation_matches_the_fifth_committed_state():
    episode = _read_json(FIXTURES / "expected_episode.json")
    turn_five = _read_json(RUNTIME / "expected" / "05_committed_state.json")

    assert episode == _read_json(RUNTIME / "expected_episode.json")
    assert episode["ending"]["type"] == "partial_truth"
    assert episode["secret_states"] == turn_five["secrets"]
    assert episode["discovered_clue_ids"] == turn_five["clues"]
    assert set(episode["unresolved_threads"]) == {
        "jonathan_current_location",
        "occult_group_identity",
    }


def test_turn_four_reinterpretation_and_sequence_nine_fixture_are_pinned():
    character = _read_json(FIXTURES / "character.json")
    turn_four_summary = _read_json(FIXTURES / "turns" / "04_expected.json")
    turn_four_intent = _read_json(RUNTIME / "mock" / "04_action_intent.json")

    assert character["identity"]["sequence"] == 9
    assert turn_four_summary["adherence"] == "reinterpret"
    assert turn_four_intent["adherence"] == "reinterpret"


def test_golden_runtime_spec_lists_all_eight_failure_checkpoints_in_order():
    readme = (RUNTIME / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"## 6\. Failure Checkpoints\s+.*?```text\n(.*?)\n```",
        readme,
        flags=re.DOTALL,
    )
    assert match is not None
    checkpoints = tuple(
        line.strip() for line in match.group(1).splitlines() if line.strip()
    )
    assert checkpoints == EXPECTED_FAILURE_CHECKPOINTS
    assert len(set(checkpoints)) == 8
