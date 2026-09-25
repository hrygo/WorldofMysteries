"""Application validation and snapshot behavior for durable Story Session Open."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenError,
    StorySessionOpenResult,
    StorySessionOpenService,
    StorySessionSnapshot,
)
from contracts import StorySession, StorySessionStatus, StoryState


def session(
    *,
    status: str = "active",
    story_revision: int = 0,
    turn: int = 0,
    base_story_revision: int = 0,
    state_session_id: str = "session-1",
    world_time: str | None = "1349-06-12T21:45:00",
    last_state_delta_id: str | None = None,
) -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": state_session_id,
            "revision": story_revision,
            "turn": turn,
            "phase": "opening",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["player-1"],
            },
            "world_time": world_time,
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {"secret-1": "hidden"},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": last_state_delta_id,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-1",
            "world_id": "world-1",
            "worldline_id": "line-1",
            "protagonist_id": "player-1",
            "story_seed_id": "seed-1",
            "base_revisions": {
                "world": 10,
                "character": 4,
                "story": base_story_revision,
            },
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": status,
        }
    )


def session_with_omitted_optional_state_fields() -> StorySession:
    payload = session().model_dump(mode="json")
    state = payload["story_state"]
    for field in ("active_conflicts", "discovered_clue_ids", "local_state"):
        state.pop(field)
    return StorySession.model_validate(payload)


def command(
    initial_session: StorySession | None = None,
    *,
    expected_revision: int = 0,
) -> OpenStorySessionCommand:
    return OpenStorySessionCommand(
        initial_session=initial_session or session(),
        open_request_id="open-1",
        store_expected_revision=expected_revision,
        request_id="request-1",
        trace_id="trace-1",
    )


class OpenPort:
    def __init__(self) -> None:
        self.opened: list[OpenStorySessionCommand] = []
        self.loads: list[str] = []
        self.snapshot: StorySessionSnapshot | None = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def open_session(self, value: OpenStorySessionCommand) -> StorySessionOpenResult:
        self.opened.append(value)
        self.entered.set()
        await self.release.wait()
        snapshot = StorySessionSnapshot(
            session=value.initial_session,
            observed_store_revision=value.store_expected_revision + 1,
        )
        return StorySessionOpenResult(
            snapshot=snapshot,
            opened_store_revision=value.store_expected_revision + 1,
            replayed=False,
        )

    async def load_snapshot(self, session_id: str) -> StorySessionSnapshot:
        self.loads.append(session_id)
        if self.snapshot is None:
            raise StorySessionOpenError("story_session_not_found")
        return self.snapshot


@pytest.mark.parametrize(
    ("initial", "expected_code"),
    [
        (session(status="suspended"), "invalid_initial_session"),
        (session(story_revision=1), "invalid_initial_session"),
        (session(turn=1), "invalid_initial_session"),
        (session(base_story_revision=1), "invalid_initial_session"),
        (session(state_session_id="other-session"), "invalid_initial_session"),
        (session(last_state_delta_id="delta-1"), "invalid_initial_session"),
    ],
)
async def test_open_rejects_non_initial_sessions_before_port(initial, expected_code):
    port = OpenPort()
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.open(command(initial))

    assert raised.value.code == expected_code
    assert port.opened == []


@pytest.mark.parametrize(
    "world_time",
    [None, "", "   ", "x\x00y", "x" * 257],
)
async def test_open_rejects_missing_or_invalid_world_time_before_port(world_time):
    port = OpenPort()
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.open(command(session(world_time=world_time)))

    assert raised.value.code == "invalid_world_time"
    assert port.opened == []


async def test_open_accepts_nonempty_world_time_without_timezone():
    port = OpenPort()
    port.release.set()
    service = StorySessionOpenService(port)

    result = await service.open(command(session(world_time="1349-06-12T21:45:00")))

    assert result.snapshot.session.story_state.world_time == "1349-06-12T21:45:00"
    assert len(port.opened) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("world_id", "   "),
        ("worldline_id", "line\x00one"),
        ("protagonist_id", "p" * 257),
        ("story_seed_id", ""),
    ],
)
async def test_open_rejects_invalid_domain_identity_before_port(field, value):
    initial = session().model_copy(update={field: value})
    port = OpenPort()
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.open(command(initial))

    assert raised.value.code == "invalid_open_identity"
    assert port.opened == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("open_request_id", " "),
        ("request_id", "request\x00one"),
        ("trace_id", "t" * 257),
    ],
)
async def test_open_rejects_invalid_request_identity_before_port(field, value):
    port = OpenPort()
    service = StorySessionOpenService(port)
    invalid = replace(command(), **{field: value})

    with pytest.raises(StorySessionOpenError) as raised:
        await service.open(invalid)

    assert raised.value.code == "invalid_open_identity"
    assert port.opened == []


@pytest.mark.parametrize("expected_revision", [True, -1, 2**63 - 1, "0"])
async def test_open_rejects_invalid_expected_revision_before_port(expected_revision):
    port = OpenPort()
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.open(command(expected_revision=expected_revision))

    assert raised.value.code == "invalid_store_expected_revision"
    assert port.opened == []


async def test_open_freezes_nested_initial_session_before_first_await():
    original = session()
    port = OpenPort()
    service = StorySessionOpenService(port)
    task = asyncio.create_task(service.open(command(original)))

    await port.entered.wait()
    original.story_state.scene.id = "mutated-scene"
    original.story_state.secret_states["secret-1"] = "revealed"
    port.release.set()
    await task

    assert port.opened[0].initial_session.story_state.scene.id == "scene-1"
    assert port.opened[0].initial_session.story_state.secret_states["secret-1"] == "hidden"
    assert port.opened[0].initial_session is not original


async def test_open_accepts_initial_session_with_omitted_optional_state_fields():
    initial = session_with_omitted_optional_state_fields()
    port = OpenPort()
    port.release.set()
    service = StorySessionOpenService(port)

    result = await service.open(command(initial))

    frozen_state = result.snapshot.session.story_state
    assert frozen_state.active_conflicts is None
    assert frozen_state.discovered_clue_ids is None
    assert frozen_state.local_state is None
    assert not {
        "active_conflicts",
        "discovered_clue_ids",
        "local_state",
    } & frozen_state.model_fields_set


@pytest.mark.parametrize(
    "status",
    [
        StorySessionStatus.ACTIVE,
        StorySessionStatus.SUSPENDED,
        StorySessionStatus.CLOSING,
        StorySessionStatus.FINALIZED,
        StorySessionStatus.CANCELLED,
        StorySessionStatus.RECOVERY_REQUIRED,
    ],
)
async def test_recover_returns_authoritative_status_without_reactivation(status):
    port = OpenPort()
    authoritative = session(status=status.value)
    port.snapshot = StorySessionSnapshot(
        session=authoritative,
        observed_store_revision=27,
    )
    service = StorySessionOpenService(port)

    recovered = await service.recover("session-1")

    assert recovered == port.snapshot
    assert recovered.session.status is status
    assert port.loads == ["session-1"]
    assert port.opened == []


async def test_recover_accepts_snapshot_with_omitted_optional_state_fields():
    port = OpenPort()
    authoritative = session_with_omitted_optional_state_fields()
    port.snapshot = StorySessionSnapshot(
        session=authoritative,
        observed_store_revision=27,
    )
    service = StorySessionOpenService(port)

    recovered = await service.recover("session-1")

    assert recovered.session.story_state.active_conflicts is None
    assert recovered.session.story_state.discovered_clue_ids is None
    assert recovered.session.story_state.local_state is None
    assert not {
        "active_conflicts",
        "discovered_clue_ids",
        "local_state",
    } & recovered.session.story_state.model_fields_set


async def test_recover_rejects_snapshot_for_a_different_session():
    port = OpenPort()
    port.snapshot = StorySessionSnapshot(
        session=session().model_copy(update={"id": "other-session"}),
        observed_store_revision=1,
    )
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.recover("session-1")

    assert raised.value.code == "story_session_identity_mismatch"
    assert port.opened == []


@pytest.mark.parametrize("session_id", ["", "   ", "x\x00y", "x" * 257])
async def test_recover_rejects_invalid_session_id_before_port(session_id):
    port = OpenPort()
    service = StorySessionOpenService(port)

    with pytest.raises(StorySessionOpenError) as raised:
        await service.recover(session_id)

    assert raised.value.code == "invalid_open_identity"
    assert port.loads == []
