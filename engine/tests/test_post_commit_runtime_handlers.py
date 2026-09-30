from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from application.narrative_publication import CommittedNarrativeService
from application.post_commit_work import (
    PostCommitKind,
    PostCommitResultState,
    PostCommitWorkSource,
)
from contracts import StateDelta
from infrastructure.scenarios.post_commit_handlers import (
    ScenarioAudioPrepareHandler,
    ScenarioNarrativePublishHandler,
)


def _source(kind: PostCommitKind) -> PostCommitWorkSource:
    return PostCommitWorkSource(
        job_id=f"turn-1:{kind.value}:recipe-1",
        turn_id="turn-1",
        session_id="session-1",
        kind=kind,
        recipe_revision="rules:recipe-1",
        source_story_revision=1,
        source_world_revision=4,
        input_digest="a" * 64,
    )


def _delta() -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-1",
            "turn_id": "turn-1",
            "outcome": "clean_success",
            "story_delta": {
                "scene_id": "scene-at-turn-one",
                "world_time_delta_minutes": 5,
                "clue_ids_add": [
                    "clue_turn_one",
                    "clue_with_no_display_name",
                ],
            },
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


@pytest.mark.asyncio
async def test_live_narrative_rebuild_uses_the_job_delta_after_later_session_changes(
    monkeypatch,
):
    source = _source(PostCommitKind.NARRATIVE_PUBLISH)
    delta = _delta()
    turn = SimpleNamespace(
        id=source.turn_id,
        session_id=source.session_id,
        committed_story_revision=source.source_story_revision,
        state_delta_id=delta.id,
        narrative_block_id=None,
        # A real turn's key is the derived ``turn-input:<digest>`` form, never
        # the input id. Using the input id here would let a lookup by the wrong
        # identity still succeed and hide the defect this test exists to catch.
        idempotency_key="turn-input:0123456789abcdef",
    )
    bootstrap = SimpleNamespace(
        presentation=SimpleNamespace(
            clue_display_names={"clue_turn_one": "第一轮发现"},
        ),
        initial_session=SimpleNamespace(protagonist_id="protagonist-1"),
    )
    frozen_input = SimpleNamespace(
        input_turn_id="input-turn-one",
        session_id=source.session_id,
        turn_id=source.turn_id,
        raw_input="第一轮原话",
    )

    class Database:
        async def read_world(self, _sql, _parameters):
            return [{"committed_world_revision": source.source_world_revision}]

    class Story:
        latest_session_reads = 0

        async def load_turn(self, _turn_id):
            return turn

        async def load_delta(self, _delta_id):
            return delta

        async def load_session(self, _session_id):
            self.latest_session_reads += 1
            return SimpleNamespace(
                story_state=SimpleNamespace(
                    local_state={"scene_id": "scene-from-turn-two"},
                    discovered_clue_ids=["clue_turn_two"],
                )
            )

    class Bootstraps:
        async def require(self, _session_id):
            return bootstrap

    class Advice:
        """Mirrors the real repository: two distinct lookup routes."""

        async def load_input(self, input_turn_id):
            if input_turn_id != frozen_input.input_turn_id:
                return None
            return frozen_input

        async def load_input_for_turn(self, turn_id):
            if turn_id != frozen_input.turn_id:
                return None
            return frozen_input

    class Workers:
        def narrative_compiler(self, _bootstrap):
            return object()

    class Narratives:
        pass

    captured = []
    narrative = SimpleNamespace(
        id="narrative-1",
        story_session_id=source.session_id,
        source_story_revision=source.source_story_revision,
        source_state_delta_id=delta.id,
    )

    async def capture_source(_service, *, turn_id, source):
        assert turn_id == source.turn_id
        captured.append(source)
        return narrative

    monkeypatch.setattr(CommittedNarrativeService, "ensure", capture_source)
    story = Story()
    handler = ScenarioNarrativePublishHandler(
        database=Database(),
        story=story,
        bootstraps=Bootstraps(),
        advice=Advice(),
        narratives=Narratives(),
        beat_plans=object(),
        expression=object(),
        workers=Workers(),
        frozen_expression=False,
    )

    result = await handler.execute(source)

    assert result.state is PostCommitResultState.SUCCEEDED
    assert result.result_ref == "narrative:narrative-1"
    assert len(captured) == 1
    committed_source = captured[0]
    assert committed_source.state_delta is delta
    assert committed_source.scene_id == "scene-at-turn-one"
    assert committed_source.disclosed_facts == (
        "结果判定：clean_success\n"
        "玩家发现了：第一轮发现\n"
        "场景转为：scene-at-turn-one\n"
        "世界时间推进：5 分钟"
    )
    assert "clue_with_no_display_name" not in committed_source.disclosed_facts
    assert frozen_input.raw_input not in committed_source.disclosed_facts
    assert "scene-from-turn-two" not in committed_source.disclosed_facts
    assert "clue_turn_two" not in committed_source.disclosed_facts
    assert story.latest_session_reads == 0


@pytest.mark.asyncio
async def test_audio_handler_never_seals_before_narrative_artifact_exists():
    source = _source(PostCommitKind.AUDIO_PREPARE)
    delta = _delta()
    turn = SimpleNamespace(
        id=source.turn_id,
        session_id=source.session_id,
        committed_story_revision=source.source_story_revision,
        state_delta_id=delta.id,
        narrative_block_id=None,
    )

    class Database:
        async def read_world(self, _sql, _parameters):
            return [{"committed_world_revision": source.source_world_revision}]

        async def post_commit_job_write(self, _apply):
            raise AssertionError("audio must not persist a result without narrative")

    class Story:
        async def load_turn(self, _turn_id):
            return turn

        async def load_delta(self, _delta_id):
            return delta

    class Bootstraps:
        async def require(self, _session_id):
            return SimpleNamespace()

    class Narratives:
        async def load_narrative_block(self, _narrative_id):
            raise AssertionError("turn does not identify a narrative artifact")

    handler = ScenarioAudioPrepareHandler(
        database=Database(),
        story=Story(),
        bootstraps=Bootstraps(),
        narratives=Narratives(),
        bindings=object(),
        voice=object(),
        audio_config=object(),
        voice_id="approved-voice",
        dictionary_revision="dictionary-1",
        fetch_json=None,
    )

    result = await handler.execute(source)

    assert result.state is PostCommitResultState.BLOCKED
    assert result.reason_code == "dependency_unavailable"


class _RecordingTrigger:
    """Stands in for the casting trigger so the audio job can be watched."""

    def __init__(self, fails: bool = False) -> None:
        self.scopes: list[object] = []
        self.spoken_lines: list[tuple[str, ...]] = []
        self.fails = fails

    async def ensure(self, scope, *, spoken_lines=(), display_name="", request_id=None):
        self.scopes.append(scope)
        self.spoken_lines.append(tuple(spoken_lines))
        if self.fails:
            raise RuntimeError("supply is down")
        return SimpleNamespace(requested=True, awaiting_person=False)


async def _audio_handler_around_a_missing_voice(monkeypatch, trigger):
    """An audio job that gets all the way to resolving a voice, and fails there."""
    from infrastructure.scenarios import post_commit_handlers as handlers_module
    from infrastructure.voice_binding_resolver import VoiceBindingResolutionError
    from contracts.models import StorySession

    source = _source(PostCommitKind.AUDIO_PREPARE)
    delta = _delta()
    turn = SimpleNamespace(
        id=source.turn_id,
        session_id=source.session_id,
        committed_story_revision=source.source_story_revision,
        state_delta_id=delta.id,
        narrative_block_id="narrative-1",
    )
    narrative = SimpleNamespace(
        id="narrative-1",
        story_session_id=source.session_id,
        source_story_revision=source.source_story_revision,
        source_state_delta_id=delta.id,
        segments=[],
    )

    class Database:
        async def read_world(self, sql, _parameters):
            if "post_commit_job_results" in sql:
                return []
            if "narrative_blocks" in sql:
                return [
                    {
                        "payload_json": json.dumps(
                            {
                                "segments": [
                                    {
                                        "type": "character",
                                        "speaker_id": "victor-osborn",
                                        "text": "今天雾很大，街角那盏煤气灯又坏了，巷子尽头一点光都没有。",
                                    },
                                    {
                                        "type": "character",
                                        "speaker_id": "victor-osborn",
                                        "text": "你说的是哪一班？我记得是三点的，可那时钟早就停了吧。",
                                    },
                                    {
                                        "type": "narration",
                                        "speaker_id": None,
                                        "text": "雾没有散。",
                                    },
                                    {
                                        "type": "character",
                                        "speaker_id": "somebody-else",
                                        "text": "这一句不属于他，不该被拿去铸造他的声音。",
                                    },
                                ]
                            }
                        )
                    }
                ]
            return [{"committed_world_revision": source.source_world_revision}]

        async def post_commit_job_write(self, _apply):
            raise AssertionError("a blocked audio job must not persist a result")

    class Story:
        async def load_turn(self, _turn_id):
            return turn

        async def load_delta(self, _delta_id):
            return delta

        async def load_session(self, _session_id):
            return StorySession.model_construct(
                id=source.session_id,
                world_id="world-1",
                worldline_id="line-1",
                protagonist_id="victor-osborn",
            )

    class Bootstraps:
        async def require(self, _session_id):
            return SimpleNamespace()

    class Narratives:
        async def load_narrative_block(self, _narrative_id):
            return narrative

    async def no_voice(**_kwargs):
        raise VoiceBindingResolutionError("voice_binding_not_reviewed")

    monkeypatch.setattr(handlers_module, "resolve_voice_runtime", no_voice)

    handler = handlers_module.ScenarioAudioPrepareHandler(
        database=Database(),
        story=Story(),
        bootstraps=Bootstraps(),
        narratives=Narratives(),
        bindings=object(),
        voice=object(),
        audio_config=object(),
        voice_id="approved-voice",
        dictionary_revision="dictionary-1",
        fetch_json=None,
        supply_trigger=trigger,
    )
    return handler, source


@pytest.mark.asyncio
async def test_a_voiceless_speaker_starts_being_cast_without_changing_the_audio(
    monkeypatch,
):
    """First appearance: casting starts, and the segment still falls back.

    The blocked result is the point. Supply runs beside the story, never in
    front of it — the text for this turn was published before this job was
    ever scheduled.
    """
    trigger = _RecordingTrigger()
    handler, source = await _audio_handler_around_a_missing_voice(monkeypatch, trigger)

    result = await handler.execute(source)

    assert result.state is PostCommitResultState.BLOCKED
    assert result.reason_code == "voice_binding_not_reviewed"
    assert len(trigger.scopes) == 1
    assert trigger.scopes[0].presentation_identity == "victor-osborn"
    # Only this speaker's own published words. Narration is not his, and
    # another character's line is not his either — a brief composed from
    # either would tune a voice on text its owner never spoke.
    assert trigger.spoken_lines == [
        (
            "今天雾很大，街角那盏煤气灯又坏了，巷子尽头一点光都没有。",
            "你说的是哪一班？我记得是三点的，可那时钟早就停了吧。",
        )
    ]


@pytest.mark.asyncio
async def test_a_supply_chain_that_is_down_leaves_the_audio_exactly_as_it_was(
    monkeypatch,
):
    """A casting that cannot start must not become a story failure."""
    trigger = _RecordingTrigger(fails=True)
    handler, source = await _audio_handler_around_a_missing_voice(monkeypatch, trigger)

    result = await handler.execute(source)

    assert result.state is PostCommitResultState.BLOCKED
    assert result.reason_code == "voice_binding_not_reviewed"
    assert len(trigger.scopes) == 1
