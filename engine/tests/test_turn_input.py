"""W-V09 finalized Story input and ControlIntent routing tests."""
from __future__ import annotations

from dataclasses import replace

import pytest

from application.turn_input import (
    ControlIntent,
    ControlIntentKind,
    FinalizedStoryInput,
    InputCommandRouter,
    RoutedControlIntent,
    StoryInputCommandError,
    StoryTurnInputService,
    TurnInputCommand,
    TurnInputReceipt,
    TurnInputStatus,
)
from contracts import (
    BaseRevisions,
    InputMode,
    StorySession,
    StoryState,
)


def session(*, story_revision: int = 3, status: str = "active") -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session-1",
            "revision": story_revision,
            "turn": story_revision,
            "phase": "discovery",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["npc-1"],
            },
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-1",
            "world_id": "world-1",
            "worldline_id": "line-1",
            "protagonist_id": "player",
            "story_seed_id": "seed-1",
            "base_revisions": {"world": 10, "character": 4, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": status,
        }
    )


class SessionPort:
    def __init__(self) -> None:
        self.current = session()
        self.loads = 0

    async def load_session(self, session_id: str) -> StorySession:
        self.loads += 1
        assert session_id == self.current.id
        return self.current


class IntakePort:
    def __init__(self) -> None:
        self.records: dict[str, TurnInputReceipt] = {}
        self.received: list[TurnInputCommand] = []
        self.cancelled: list[str] = []

    async def load(self, input_turn_id: str):
        return self.records.get(input_turn_id)

    async def receive(self, command: TurnInputCommand):
        self.received.append(command)
        receipt = TurnInputReceipt(
            input_turn_id=command.input_turn_id,
            session_id=command.session_id,
            turn_id=command.turn_id,
            idempotency_key=command.idempotency_key,
            input_mode=command.input_mode,
            input_sha256=command.input_sha256,
            base_revisions=command.base_revisions,
            status=TurnInputStatus.RECEIVED,
            committed_world_revision=None,
        )
        self.records[command.input_turn_id] = receipt
        return receipt

    async def cancel(self, input_turn_id: str):
        self.cancelled.append(input_turn_id)
        current = self.records[input_turn_id]
        updated = replace(current, status=TurnInputStatus.CANCELLED)
        self.records[input_turn_id] = updated
        return updated


class ControlPort:
    def __init__(self) -> None:
        self.values = []

    async def execute(self, intent):
        self.values.append(intent)


def voice_input(*, text="调查那扇门。"):
    return FinalizedStoryInput(
        input_turn_id="input-turn-1",
        session_id="session-1",
        input_mode=InputMode.VOICE,
        raw_input=text,
    )


async def test_first_receive_freezes_current_story_revision_and_stable_identity():
    sessions = SessionPort()
    intake = IntakePort()
    service = StoryTurnInputService(sessions=sessions, intake=intake)

    receipt = await service.receive(voice_input())

    assert receipt.status is TurnInputStatus.RECEIVED
    assert receipt.base_revisions == BaseRevisions(world=10, character=4, story=3)
    assert receipt.turn_id.startswith("turn_")
    assert receipt.idempotency_key.startswith("turn-input:")
    assert len(intake.received) == 1
    assert sessions.loads == 1


async def test_lost_ack_recovers_frozen_command_before_reading_newer_session():
    sessions = SessionPort()
    intake = IntakePort()
    service = StoryTurnInputService(sessions=sessions, intake=intake)

    first = await service.receive(voice_input())
    sessions.current = session(story_revision=9)
    recovered = await service.receive(voice_input())

    assert recovered.replayed
    assert recovered.turn_id == first.turn_id
    assert recovered.base_revisions.story == 3
    assert sessions.loads == 1
    assert len(intake.received) == 1


async def test_same_input_turn_with_changed_text_or_mode_fails_before_session_lookup():
    sessions = SessionPort()
    intake = IntakePort()
    service = StoryTurnInputService(sessions=sessions, intake=intake)
    await service.receive(voice_input())

    with pytest.raises(StoryInputCommandError, match="input_turn_identity_conflict"):
        await service.receive(voice_input(text="篡改输入"))

    with pytest.raises(StoryInputCommandError, match="input_turn_identity_conflict"):
        await service.receive(
            FinalizedStoryInput(
                input_turn_id="input-turn-1",
                session_id="session-1",
                input_mode=InputMode.TEXT,
                raw_input="调查那扇门。",
            )
        )
    assert sessions.loads == 1


async def test_inactive_session_cannot_admit_new_story_input():
    sessions = SessionPort()
    sessions.current = session(status="suspended")
    service = StoryTurnInputService(sessions=sessions, intake=IntakePort())

    with pytest.raises(StoryInputCommandError, match="story_session_not_active"):
        await service.receive(voice_input())


async def test_control_intents_never_touch_story_intake_or_session():
    sessions = SessionPort()
    intake = IntakePort()
    controls = ControlPort()
    router = InputCommandRouter(
        story=StoryTurnInputService(sessions=sessions, intake=intake),
        controls=controls,
    )

    for value in (
        ControlIntent(ControlIntentKind.STOP),
        ControlIntent(ControlIntentKind.CONTINUE),
        ControlIntent(ControlIntentKind.SET_VOLUME, volume=0.35),
    ):
        routed = await router.route(value)
        assert isinstance(routed, RoutedControlIntent)

    assert sessions.loads == 0
    assert intake.received == []
    assert len(controls.values) == 3


async def test_story_input_and_control_routes_are_mutually_exclusive():
    sessions = SessionPort()
    intake = IntakePort()
    controls = ControlPort()
    router = InputCommandRouter(
        story=StoryTurnInputService(sessions=sessions, intake=intake),
        controls=controls,
    )

    receipt = await router.route(voice_input())
    assert isinstance(receipt, TurnInputReceipt)
    assert len(intake.received) == 1
    assert controls.values == []


def test_set_volume_is_bounded_and_other_controls_carry_no_volume():
    with pytest.raises(StoryInputCommandError, match="invalid_control_volume"):
        ControlIntent(ControlIntentKind.SET_VOLUME, volume=1.5)
    with pytest.raises(StoryInputCommandError, match="unexpected_control_volume"):
        ControlIntent(ControlIntentKind.STOP, volume=0.5)
