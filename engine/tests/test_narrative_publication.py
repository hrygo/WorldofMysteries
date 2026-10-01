"""Post-COMMIT narrative publication and player-visible expression tests."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from application.audio_disclosure import AudioDisclosureAuthorizer
from contracts import (
    BaseRevisions,
    NarrativeBlock,
    StateDelta,
    TurnStatus,
    TurnTransaction,
)
from contracts.models import NarrativeSegment
from infrastructure.database_manager import StorageError


def _turn(
    *,
    status: TurnStatus = TurnStatus.COMMITTED,
    narrative_block_id: str | None = None,
) -> TurnTransaction:
    return TurnTransaction(
        schema_version="1.0",
        id="turn-1",
        session_id="session-1",
        idempotency_key="input-1",
        status=status,
        base_revisions=BaseRevisions(world=2, character=3, story=3),
        state_delta_id="delta-1",
        committed_story_revision=4,
        narrative_block_id=narrative_block_id,
    )


def _narrative(
    *,
    block_id: str = "narrative-1",
    segments: tuple[NarrativeSegment, ...] | None = None,
) -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id=block_id,
        story_session_id="session-1",
        source_story_revision=4,
        scene_id="scene-1",
        segments=list(
            segments
            or (
                NarrativeSegment(type="narration", text="雨落在诊所的窗外。"),
                NarrativeSegment(
                    type="character",
                    speaker_id="protagonist-1",
                    text="我先看看预约簿。",
                    speech_intent="observe",
                ),
            )
        ),
        source_state_delta_id="delta-1",
    )


def _delta(*, hidden_fact: str | None = None) -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-1",
            "turn_id": "turn-1",
            "outcome": "clean_success",
            "story_delta": (
                {"secret_state_updates": {hidden_fact: "hidden"}}
                if hidden_fact is not None
                else {}
            ),
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


class MemoryNarrativeRepository:
    """Small stateful fake that mirrors the existing read/publish port."""

    def __init__(
        self,
        *,
        turn: TurnTransaction | None = None,
        narrative: NarrativeBlock | None = None,
        world_revision: int = 8,
    ) -> None:
        self.turn = turn or _turn()
        self.narrative = narrative
        self.world_revision = world_revision
        self.publish_calls = 0

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        if self.turn.id != turn_id:
            raise StorageError("TurnTransaction not found")
        return self.turn

    async def load_narrative_block(self, narrative_block_id: str) -> NarrativeBlock:
        if self.narrative is None or self.narrative.id != narrative_block_id:
            raise StorageError("NarrativeBlock not found")
        return self.narrative

    async def publish(self, *, turn_id: str, narrative: NarrativeBlock):
        if self.turn.id != turn_id:
            raise StorageError("TurnTransaction not found")
        if self.narrative is not None:
            if self.narrative != narrative:
                raise StorageError("Turn already has a different NarrativeBlock")
            return SimpleNamespace(
                turn=self.turn, narrative=self.narrative, replayed=True
            )
        self.publish_calls += 1
        self.narrative = narrative
        self.turn = self.turn.model_copy(
            update={
                "status": TurnStatus.NARRATIVE_READY,
                "narrative_block_id": narrative.id,
            }
        )
        return SimpleNamespace(
            turn=self.turn, narrative=narrative, replayed=False
        )


def _committed_source(
    *,
    state_delta: StateDelta | None = None,
    present_character_ids=None,
):
    from application.narrative_publication import CommittedNarrativeSource

    return CommittedNarrativeSource(
        turn_id="turn-1",
        session_id="session-1",
        story_revision=4,
        state_delta_id="delta-1",
        state_delta=state_delta or _delta(),
        scene_id="scene-1",
        protagonist_id="protagonist-1",
        disclosed_facts="已提交结果：预约簿缺少一页。",
        input_turn_id="input-1",
        source_store_revision=8,
        present_character_ids=present_character_ids,
    )


def _live_narrative_worker(payload, source):
    from ai.authorized_live_execution import AuthorizedLiveExecution
    from ai.live_turn_workers import LiveNarrativeCompiler
    from ai.openai_compatible import (
        ModelEndpointConfig,
        OpenAICompatibleChatTransport,
    )
    from ai.prompt_renderer import PromptRenderer
    from application.gameplay_context import GameplayContextCoordinator
    from application.turn_context_binding import AuthorizedTurnContextBinding

    transport = OpenAICompatibleChatTransport(
        ModelEndpointConfig(
            base_url="http://127.0.0.1:1",
            api_key="test-only",
            model="test-model",
        )
    )
    execution = AuthorizedLiveExecution(
        coordinator=GameplayContextCoordinator(
            snapshot=object(),
            authorization=object(),
            profiles=object(),
        ),
        renderer=PromptRenderer(b"r" * 32),
        transport=transport,
        validate_proposal=lambda _proposal, _request: True,
    )
    binding = AuthorizedTurnContextBinding(
        turn_id=source.turn_id,
        stage="narrative",
        input_turn_id=source.input_turn_id,
        source_store_revision=source.source_store_revision,
        source_story_revision=source.story_revision,
        policy_revision="policy-v1",
        content_digest="a" * 64,
        lineage_digest="lineage-v1",
        manifest=(),
    )

    async def return_proposal(
        _call,
        _budget,
        *,
        binding_identity,
        expected_binding,
        schema_overrides=None,
    ):
        assert binding_identity.stage == "narrative"
        assert binding_identity.turn_id == source.turn_id
        # The narrative compiler must state the non-empty speech bound to the
        # provider, otherwise the model answers with narration only and the turn
        # can never be delivered as audio.
        assert schema_overrides == {"properties.speech": {"minLength": 1}}
        return SimpleNamespace(
            proposal=lambda: dict(payload),
            context_binding=binding,
        )

    execution.execute = return_proposal
    bootstrap = SimpleNamespace(
        content_digest="a" * 64,
        initial_session=SimpleNamespace(
            protagonist_id=source.protagonist_id,
            world_id="world-1",
            worldline_id="line-1",
        ),
    )
    return LiveNarrativeCompiler(execution, bootstrap), binding, transport


class CountingCompiler:
    def __init__(self, candidate=None):
        from application.narrative_publication import NarrativeCandidate

        self.candidate = candidate or NarrativeCandidate(
            narration="雨落在诊所的窗外。",
            speech="我先看看预约簿。",
        )
        self.calls: list[str] = []

    async def compile(self, *, committed: str):
        self.calls.append(committed)
        return self.candidate


@pytest.mark.asyncio
async def test_existing_persisted_narrative_is_reused_without_model_call():
    from application.narrative_publication import CommittedNarrativeService

    stored = _narrative(
        segments=(
            NarrativeSegment(
                type="narration",
                text="旧单段叙事的第一句。\n旧单段叙事的第二句。",
            ),
        )
    )
    repository = MemoryNarrativeRepository(
        turn=_turn(
            status=TurnStatus.NARRATIVE_READY,
            narrative_block_id=stored.id,
        ),
        narrative=stored,
    )
    compiler = CountingCompiler()
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )

    result = await service.ensure(turn_id="turn-1", source=None)

    assert result == stored
    assert len(result.segments) == 1
    assert result.segments[0].text == "旧单段叙事的第一句。\n旧单段叙事的第二句。"
    assert compiler.calls == []
    assert repository.publish_calls == 0


@pytest.mark.asyncio
async def test_repeated_ensure_is_idempotent_and_does_not_advance_world_revision():
    from application.narrative_publication import CommittedNarrativeService

    repository = MemoryNarrativeRepository(world_revision=8)
    compiler = CountingCompiler()
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )
    source = _committed_source()

    first = await service.ensure(turn_id="turn-1", source=source)
    second = await service.ensure(turn_id="turn-1", source=source)

    assert first == second == repository.narrative
    assert compiler.calls == [source.disclosed_facts]
    assert repository.publish_calls == 1
    assert repository.world_revision == 8


@pytest.mark.asyncio
async def test_concurrent_ensure_calls_share_one_bounded_single_flight():
    from application.narrative_publication import (
        CommittedNarrativeService,
        NarrativeCandidate,
        NarrativePublicationError,
    )

    class BlockingCompiler:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def compile(self, *, committed: str):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return NarrativeCandidate(
                narration="雨落在诊所的窗外。",
                speech="我先看看预约簿。",
            )

    repository = MemoryNarrativeRepository()
    compiler = BlockingCompiler()
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
        max_single_flight_turns=1,
    )
    source = _committed_source()

    first = asyncio.create_task(service.ensure(turn_id="turn-1", source=source))
    await compiler.started.wait()
    waiters = [
        asyncio.create_task(service.ensure(turn_id="turn-1", source=source))
        for _ in range(5)
    ]
    compiler.release.set()

    results = await asyncio.gather(first, *waiters)

    assert all(result == results[0] for result in results)
    assert compiler.calls == 1
    assert repository.publish_calls == 1


@pytest.mark.asyncio
async def test_candidate_publishes_narration_then_character_with_trusted_speaker():
    from application.narrative_publication import CommittedNarrativeService

    repository = MemoryNarrativeRepository()
    compiler = CountingCompiler()
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )

    block = await service.ensure(turn_id="turn-1", source=_committed_source())

    assert [(segment.type, segment.text) for segment in block.segments] == [
        ("narration", "雨落在诊所的窗外。"),
        ("character", "我先看看预约簿。"),
    ]
    assert block.segments[0].speaker_id is None
    assert block.segments[1].speaker_id == "protagonist-1"
    assert not hasattr(compiler.candidate, "speaker_id")


@pytest.mark.asyncio
async def test_compiler_receives_only_the_disclosed_summary_not_hidden_delta_fields():
    from application.narrative_publication import CommittedNarrativeService

    repository = MemoryNarrativeRepository()
    compiler = CountingCompiler()
    source = _committed_source(state_delta=_delta(hidden_fact="secret_hidden_0"))
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )

    await service.ensure(turn_id="turn-1", source=source)

    assert compiler.calls == [source.disclosed_facts]
    assert "secret_hidden_0" not in compiler.calls[0]


@pytest.mark.asyncio
async def test_publish_conflict_reuses_same_turn_block_without_overwriting_text():
    from application.narrative_publication import CommittedNarrativeService

    class RacingRepository(MemoryNarrativeRepository):
        async def publish(self, *, turn_id: str, narrative: NarrativeBlock):
            self.narrative = _narrative(
                block_id="narrative-published-by-peer",
                segments=(
                    NarrativeSegment(
                        type="narration",
                        text="另一个进程先发布的叙事。",
                    ),
                ),
            )
            self.turn = self.turn.model_copy(
                update={
                    "status": TurnStatus.NARRATIVE_READY,
                    "narrative_block_id": self.narrative.id,
                }
            )
            raise StorageError("Turn already has a different NarrativeBlock")

    repository = RacingRepository()
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=CountingCompiler(),
    )

    result = await service.ensure(turn_id="turn-1", source=_committed_source())

    assert result.id == "narrative-published-by-peer"
    assert result.segments[0].text == "另一个进程先发布的叙事。"
    assert repository.narrative == result


@pytest.mark.asyncio
async def test_publish_failure_without_durable_winner_is_not_swallowed():
    class FailingRepository(MemoryNarrativeRepository):
        async def publish(self, *, turn_id: str, narrative: NarrativeBlock):
            raise RuntimeError("storage unavailable")

    repository = FailingRepository()
    compiler = CountingCompiler()
    from application.narrative_publication import CommittedNarrativeService

    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await service.ensure(turn_id="turn-1", source=_committed_source())

    assert repository.turn.narrative_block_id is None
    assert compiler.calls == ["已提交结果：预约簿缺少一页。"]


@pytest.mark.asyncio
async def test_model_cannot_bind_a_narrative_to_an_arbitrary_speaker():
    from application.narrative_publication import (
        NarrativeCandidate,
        NarrativePublicationError,
    )

    source = _committed_source()
    compiler, _binding, transport = _live_narrative_worker(
        {
            "narration": "雨落在诊所的窗外。",
            "speech": "我先看看预约簿。",
            "speaker_id": "hidden-character-0",
        },
        source,
    )
    try:
        with pytest.raises(
            NarrativePublicationError,
            match="narrative_model_invalid",
        ):
            await compiler.compile(
                committed=source.disclosed_facts,
                source=source,
            )
    finally:
        await transport.aclose()

    with pytest.raises(TypeError):
        NarrativeCandidate(
            narration="雨落在诊所的窗外。",
            speech="我先看看预约簿。",
            speaker_id="hidden-character-0",
        )


@pytest.mark.asyncio
async def test_live_candidate_requires_character_speech():
    from application.narrative_publication import (
        CommittedNarrativeService,
        NarrativeCandidate,
        NarrativePublicationError,
    )

    repository = MemoryNarrativeRepository()
    source = _committed_source()
    # A committed turn must be speakable: the delivery stage refuses a block with
    # no character segment, so a narration-only result is a dead end rather than
    # a valid outcome. The model must say what the character actually says.
    silent, _, silent_transport = _live_narrative_worker(
        {"narration": "雨落在诊所的窗外。"}, source
    )
    try:
        with pytest.raises(NarrativePublicationError, match="missing_character_speech"):
            await silent.compile(committed=source.disclosed_facts, source=source)
    finally:
        await silent_transport.aclose()

    compiler, binding, transport = _live_narrative_worker(
        {"narration": "雨落在诊所的窗外。", "speech": "你还没问，我先不说。"},
        source,
    )
    try:
        candidate = await compiler.compile(
            committed=source.disclosed_facts,
            source=source,
        )
    finally:
        await transport.aclose()
    assert candidate == NarrativeCandidate(
        narration="雨落在诊所的窗外。",
        speech="你还没问，我先不说。",
        context_binding=binding,
    )
    compiler = CountingCompiler(candidate=candidate)
    service = CommittedNarrativeService(
        reads=repository,
        publisher=repository,
        compiler=compiler,
    )

    block = await service.ensure(turn_id="turn-1", source=_committed_source())

    assert [(segment.type, segment.text) for segment in block.segments] == [
        ("narration", "雨落在诊所的窗外。"),
        ("character", "你还没问，我先不说。"),
    ]


class MemoryPublicIdentityReader:
    async def display_name(self, *, session_id: str, speaker_id: str) -> str | None:
        if (session_id, speaker_id) == ("session-1", "protagonist-1"):
            return "克莱恩"
        return None


@pytest.mark.asyncio
async def test_story_expression_get_projects_only_persisted_disclosed_segments():
    from application.story_expression import StoryExpressionQueryService

    repository = MemoryNarrativeRepository(
        turn=_turn(
            status=TurnStatus.NARRATIVE_READY,
            narrative_block_id="narrative-1",
        ),
        narrative=_narrative(),
    )
    service = StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=MemoryPublicIdentityReader(),
    )

    result = await service.get(session_id="session-1", turn_id="turn-1")

    assert result.model_dump(mode="json", exclude_none=True) == {
        "schema_version": "1.0",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "narrative_state": "ready",
        "segments": [
            {"type": "narration", "text": "雨落在诊所的窗外。"},
            {
                "type": "character",
                "speaker_display_name": "克莱恩",
                "text": "我先看看预约簿。",
            },
        ],
    }


@pytest.mark.asyncio
async def test_story_expression_get_returns_pending_without_persisted_failure():
    from application.story_expression import StoryExpressionQueryService

    repository = MemoryNarrativeRepository()
    service = StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=MemoryPublicIdentityReader(),
    )

    result = await service.get(session_id="session-1", turn_id="turn-1")

    assert result.narrative_state == "pending"
    assert result.segments == []
    assert result.reason is None


@pytest.mark.asyncio
async def test_story_expression_get_reports_only_explicit_capability_unavailability():
    from application.story_expression import StoryExpressionQueryService

    repository = MemoryNarrativeRepository()
    service = StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=MemoryPublicIdentityReader(),
        capability_unavailable_reason="narrative_model_unavailable",
    )

    result = await service.get(session_id="session-1", turn_id="turn-1")

    assert result.narrative_state == "unavailable"
    assert result.reason == "narrative_model_unavailable"
    assert result.segments == []


@pytest.mark.asyncio
async def test_story_expression_get_hides_unmapped_speaker_identity():
    from application.story_expression import StoryExpressionQueryService

    repository = MemoryNarrativeRepository(
        turn=_turn(
            status=TurnStatus.NARRATIVE_READY,
            narrative_block_id="narrative-1",
        ),
        narrative=_narrative(
            segments=(
                NarrativeSegment(
                    type="character",
                    speaker_id="hidden-character-0",
                    text="我先看看预约簿。",
                ),
            )
        ),
    )
    service = StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=MemoryPublicIdentityReader(),
    )

    result = await service.get(session_id="session-1", turn_id="turn-1")

    assert result.narrative_state == "ready"
    assert result.segments[0].type == "character"
    assert result.segments[0].speaker_display_name is None
    assert "hidden-character-0" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_story_expression_get_rejects_a_turn_from_another_session():
    from application.story_expression import (
        StoryExpressionError,
        StoryExpressionQueryService,
    )

    repository = MemoryNarrativeRepository()
    service = StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=MemoryPublicIdentityReader(),
    )

    with pytest.raises(StoryExpressionError, match="turn_session_mismatch"):
        await service.get(session_id="session-other", turn_id="turn-1")


def test_a_source_can_carry_who_is_in_the_room():
    """The roster is the fact that lets anyone but the protagonist speak.

    Until the committed source carries this, publication has exactly one
    identity to bind and the supply chain can only ever hear one voice — no
    matter how many characters the world knows about.
    """
    source = _committed_source(
        present_character_ids=("klein-visible", "audrey-presentation")
    )
    assert source.present_character_ids == (
        "klein-visible",
        "audrey-presentation",
    )


def test_declaring_nobody_and_declaring_nothing_are_different_facts():
    """An empty scene is an answer; an unasked question is not.

    ``()`` says the world placed nobody here, and the block should carry
    narration alone. ``None`` says this source has no roster to give, which
    is the state every source predating the roster is in. Collapsing them
    would let "nobody is here" pass as "we have not looked yet", and the
    first must never be mistaken for the second.
    """
    assert _committed_source().present_character_ids is None
    assert _committed_source(present_character_ids=()).present_character_ids == ()


def test_the_protagonist_is_not_required_to_be_in_the_room():
    """Whether the player's character speaks is a product decision.

    The roster is a fact about the scene, and the scene may be staged without
    the protagonist in it. Making membership mandatory would answer that
    question here, in a dataclass, with no way to say otherwise.
    """
    source = _committed_source(present_character_ids=("audrey-presentation",))
    assert "protagonist-1" not in source.present_character_ids


def test_a_roster_is_normalised_to_bounded_identifiers():
    assert _committed_source(
        present_character_ids=["  klein-visible  "]
    ).present_character_ids == ("klein-visible",)


@pytest.mark.parametrize(
    "roster",
    [
        # A duplicate means the projection is ambiguous about who is present.
        # Deduplicating would hide that from whoever debugs a scene that cast
        # the wrong person, while still letting the roster through as if it
        # were well-formed.
        ("klein-visible", "klein-visible"),
        ("klein-visible", "  klein-visible  "),
        # Same character, two spellings: still two entries for one person.
        ["klein-visible", ""],
        ["klein-visible", "   "],
        ["klein-visible", None],
        ["klein-visible", 7],
        ["klein-visible", "x" * 257],
        ["klein-visible", "with\x00nul"],
        "klein-visible",
        7,
    ],
)
def test_an_unusable_roster_is_refused(roster):
    from application.narrative_publication import NarrativePublicationError

    with pytest.raises(NarrativePublicationError):
        _committed_source(present_character_ids=roster)


# --- turn_scene_roster: whose scene is this? --------------------------------


def _story_state(revision, active):
    return SimpleNamespace(
        revision=revision,
        scene=SimpleNamespace(active_character_ids=active),
    )


def test_the_roster_is_read_when_the_state_is_still_the_turns_own():
    from application.narrative_publication import turn_scene_roster

    assert turn_scene_roster(
        story_state=_story_state(4, ["klein", "audrey"]),
        committed_story_revision=4,
    ) == ("klein", "audrey")


def test_a_state_that_has_moved_on_yields_no_roster():
    """The load-bearing one.

    ``story_state_json`` holds only the current state of a session. A durable
    post-COMMIT job may run after later turns have moved the roster on, and
    reading it then would cast this turn with whoever is in the room *now* —
    silently, because every value read would be internally consistent. Declining
    is the only answer that cannot be wrong.
    """
    from application.narrative_publication import turn_scene_roster

    assert (
        turn_scene_roster(
            story_state=_story_state(9, ["someone_else"]),
            committed_story_revision=4,
        )
        is None
    )


def test_a_state_one_revision_behind_is_also_refused():
    """Not "greater than" — any disagreement means it is not this turn's state."""
    from application.narrative_publication import turn_scene_roster

    assert (
        turn_scene_roster(
            story_state=_story_state(3, ["klein"]),
            committed_story_revision=4,
        )
        is None
    )


def test_no_state_at_all_yields_no_roster():
    from application.narrative_publication import turn_scene_roster

    assert turn_scene_roster(
        story_state=None, committed_story_revision=4
    ) is None


def test_a_world_that_declares_no_roster_is_not_told_the_scene_is_empty():
    from application.narrative_publication import turn_scene_roster

    assert (
        turn_scene_roster(
            story_state=_story_state(4, None),
            committed_story_revision=4,
        )
        is None
    )


def test_an_empty_scene_is_carried_as_an_empty_roster():
    """The world saying "nobody is here" is a fact, and survives the trip."""
    from application.narrative_publication import turn_scene_roster

    assert (
        turn_scene_roster(
            story_state=_story_state(4, []),
            committed_story_revision=4,
        )
        == ()
    )


def test_the_roster_is_normalised_on_the_way_in():
    from application.narrative_publication import turn_scene_roster

    assert turn_scene_roster(
        story_state=_story_state(4, ["  klein  "]),
        committed_story_revision=4,
    ) == ("klein",)


def test_a_roster_the_publication_layer_refuses_is_not_silently_accepted():
    from application.narrative_publication import (
        NarrativePublicationError,
        turn_scene_roster,
    )

    with pytest.raises(NarrativePublicationError):
        turn_scene_roster(
            story_state=_story_state(4, ["klein", "klein"]),
            committed_story_revision=4,
        )


def test_two_attempts_that_disagree_about_the_roster_are_not_the_same_publication():
    """The roster decides who the block may speak for.

    Two attempts at one turn that disagree about it are not retries — they would
    bind different voices to the same text. They must be refused rather than
    raced, which is only true if the roster is part of the source's identity.
    """
    assert _flights_key(
        _committed_source(present_character_ids=("klein",))
    ) != _flights_key(_committed_source(present_character_ids=("klein", "audrey")))
    assert _flights_key(
        _committed_source(present_character_ids=("klein",))
    ) == _flights_key(_committed_source(present_character_ids=("klein",)))
    # Declining a roster is a different publication from declaring one, too:
    # the first casts a single speaker, the second may cast several.
    assert _flights_key(_committed_source()) != _flights_key(
        _committed_source(present_character_ids=())
    )


def _flights_key(source):
    from application.narrative_publication import _source_key

    return _source_key(source)


# --- castable_character_labels ----------------------------------------------


def _source_with_castable(value):
    from application.narrative_publication import CommittedNarrativeSource

    return CommittedNarrativeSource(
        turn_id="turn-1",
        session_id="session-1",
        story_revision=4,
        state_delta_id="delta-1",
        state_delta=_delta(),
        scene_id="scene-1",
        protagonist_id="protagonist-1",
        disclosed_facts="已提交结果：预约簿缺少一页。",
        input_turn_id="input-1",
        source_store_revision=8,
        castable_character_labels=value,
    )


def test_a_castable_roster_carries_ids_and_labels_together():
    """The model is given labels; only this table can bind them back to ids."""
    assert _source_with_castable(
        [("klein", "克莱恩"), ("audrey", "奥黛丽")]
    ).castable_character_labels == (("klein", "克莱恩"), ("audrey", "奥黛丽"))


def test_castable_pairs_are_normalised():
    assert _source_with_castable(
        [["  klein  ", "  克莱恩  "]]
    ).castable_character_labels == (("klein", "克莱恩"),)


def test_nobody_castable_is_still_an_answer():
    assert _source_with_castable([]).castable_character_labels == ()


def test_no_castable_roster_declared_is_not_the_same_as_nobody():
    """The distinction the publication layer will branch on."""
    assert _source_with_castable(None).castable_character_labels is None
    assert _source_with_castable([]).castable_character_labels == ()


@pytest.mark.parametrize(
    "value",
    [
        # One character wearing two names: a line could bind either way.
        [("klein", "克莱恩"), ("klein", "克莱")],
        # Two characters sharing one name: a line naming it binds to nobody in
        # particular, and picking the first would cast the wrong person's voice.
        [("klein", "克莱恩"), ("audrey", "克莱恩")],
        # Same id, different spellings — still two entries for one person.
        [("klein", "克莱恩"), ("  klein  ", "克莱")],
        ["klein-克莱恩"],
        [("klein",)],
        [("klein", "克莱恩", "extra")],
        [("klein", "")],
        [("klein", "   ")],
        [("klein", 7)],
        [(7, "克莱恩")],
        [("klein", "with\x00nul")],
        [("x" * 257, "克莱恩")],
        [("klein", "y" * 257)],
        "klein",
        7,
    ],
)
def test_an_unusable_castable_roster_is_refused(value):
    """Every one of these would bind a voice to the wrong character."""
    from application.narrative_publication import NarrativePublicationError

    with pytest.raises(NarrativePublicationError):
        _source_with_castable(value)


def test_the_castable_roster_is_part_of_the_publication_identity():
    """Two attempts disagreeing about who may speak are not retries.

    They would bind different voices to the same text, so they must be refused
    rather than raced.
    """
    from application.narrative_publication import _source_key

    def key(value):
        return _source_key(_source_with_castable(value))

    assert key([("klein", "克莱恩")]) != key([("klein", "克莱恩"), ("audrey", "奥黛丽")])
    assert key([("klein", "克莱恩")]) == key([("klein", "克莱恩")])
    # Same cast, different spelling of a name: still a different publication.
    assert key([("klein", "克莱恩")]) != key([("klein", "克莱")])
    # Declining a roster differs from declaring one that casts nobody.
    assert key(None) != key([])


def test_the_world_roster_and_the_castable_roster_are_both_carried():
    """Not redundant: one is who was there, the other is who may be heard.

    Collapsing them would erase ADR-006 D5's distinction and leave no record
    that the protagonist was present but deliberately not cast.
    """
    from application.narrative_publication import CommittedNarrativeSource

    source = CommittedNarrativeSource(
        turn_id="turn-1",
        session_id="session-1",
        story_revision=4,
        state_delta_id="delta-1",
        state_delta=_delta(),
        scene_id="scene-1",
        protagonist_id="protagonist-1",
        disclosed_facts="已提交结果：预约簿缺少一页。",
        input_turn_id="input-1",
        source_store_revision=8,
        present_character_ids=("protagonist-1", "klein"),
        castable_character_labels=(("klein", "克莱恩"),),
    )

    assert "protagonist-1" in source.present_character_ids
    assert all(
        character_id != "protagonist-1"
        for character_id, _ in source.castable_character_labels
    )


def test_a_castable_roster_naming_someone_absent_is_refused():
    """The castable roster is a narrowing, and a narrowing cannot add.

    An id that is not in the world roster means a speaker was invented upstream.
    Every id would still resolve and every label would still bind, so nothing
    downstream would ever report it — the block would simply be voiced by
    someone who was never in the room.
    """
    from application.narrative_publication import (
        CommittedNarrativeSource,
        NarrativePublicationError,
    )

    with pytest.raises(NarrativePublicationError, match="castable_outside_scene"):
        CommittedNarrativeSource(
            turn_id="turn-1",
            session_id="session-1",
            story_revision=4,
            state_delta_id="delta-1",
            state_delta=_delta(),
            scene_id="scene-1",
            protagonist_id="protagonist-1",
            disclosed_facts="已提交结果：预约簿缺少一页。",
            input_turn_id="input-1",
            source_store_revision=8,
            present_character_ids=("klein",),
            castable_character_labels=(("klein", "克莱恩"), ("audrey", "奥黛丽")),
        )


def test_a_narrowed_roster_that_drops_everyone_is_fine():
    """D5 may legitimately leave nobody castable; that is not an error."""
    from application.narrative_publication import CommittedNarrativeSource

    source = CommittedNarrativeSource(
        turn_id="turn-1",
        session_id="session-1",
        story_revision=4,
        state_delta_id="delta-1",
        state_delta=_delta(),
        scene_id="scene-1",
        protagonist_id="protagonist-1",
        disclosed_facts="已提交结果：预约簿缺少一页。",
        input_turn_id="input-1",
        source_store_revision=8,
        present_character_ids=("protagonist-1",),
        castable_character_labels=(),
    )

    assert source.castable_character_labels == ()
