"""story.storybook.get IPC edge (PRD §20.1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.storybook_projection import StoryBookProjectionError
from infrastructure.database_schema import StorageError
from infrastructure.story_runtime import (
    _STORYBOOK_ERROR_CODES,
    _StoryBookEpisodeAdapter,
    _StoryBookNarrativeAdapter,
    _storybook_handler,
    _validate_storybook_payload,
)


class _FakeService:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def story_book(self, session_id):
        if self._error is not None:
            raise self._error
        return {**self._result, "echo_session": session_id}


# ---- payload validation -------------------------------------------------


def _valid_payload(session_id="session-1"):
    return {"schema_version": "1.0", "session_id": session_id}


def test_validate_accepts_a_well_formed_payload():
    assert _validate_storybook_payload(_valid_payload()) == "session-1"


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing fields
        {"schema_version": "1.0"},  # no session_id
        {"session_id": "s"},  # no version
        {**_valid_payload(), "extra": 1},  # unexpected key
        {**_valid_payload(), "schema_version": "2.0"},  # wrong version
        {**_valid_payload(), "session_id": ""},  # empty
        {**_valid_payload(), "session_id": "   "},  # blank
        {**_valid_payload(), "session_id": 5},  # wrong type
        {**_valid_payload(), "session_id": "x" * 300},  # too long
        {**_valid_payload(), "session_id": "bad\x00id"},  # NUL
        "not-a-mapping",
    ],
)
def test_validate_rejects_malformed_payloads(payload):
    with pytest.raises(Exception) as exc:
        _validate_storybook_payload(payload)
    assert getattr(exc.value, "code", None) == "schema_invalid"


# ---- handler: schema gate, delegation, error mapping -------------------


@pytest.mark.asyncio
async def test_handler_rejects_bad_payload_before_touching_the_service():
    service = _FakeService(result={"episode_id": "e"})
    handler = _storybook_handler(service)
    assert await handler({}, {"schema_version": "1.0"}) == (None, "schema_invalid", False)


@pytest.mark.asyncio
async def test_handler_returns_the_book_for_a_valid_request():
    service = _FakeService(result={"episode_id": "e"})
    handler = _storybook_handler(service)
    payload, code, retryable = await handler({}, _valid_payload("session-9"))
    assert code is None and retryable is False
    assert payload == {"episode_id": "e", "echo_session": "session-9"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "projection_code,expected",
    [
        ("storybook_not_finalized", "story_session_not_active"),
        ("storybook_session_unknown", "story_session_not_active"),
        ("storybook_chapter_missing", "storage_failure"),
        ("storybook_has_no_chapters", "storage_failure"),
        ("something_unmapped", "service_unavailable"),
    ],
)
async def test_handler_maps_projection_errors_to_public_codes(projection_code, expected):
    service = _FakeService(error=StoryBookProjectionError(projection_code))
    handler = _storybook_handler(service)
    assert await handler({}, _valid_payload()) == (None, expected, False)


# ---- adapters: StorageError becomes a normal "not there yet" ----------


@pytest.mark.asyncio
async def test_episode_adapter_maps_storage_error_to_none():
    class _Repo:
        async def load_by_session(self, session_id):
            raise StorageError("not finalized")

    assert await _StoryBookEpisodeAdapter(_Repo()).load_finalized_episode("s") is None


@pytest.mark.asyncio
async def test_episode_adapter_carries_the_episode_and_its_artifacts():
    """PRD §20 reads the Episode's artifacts out of the same committed snapshot."""
    episode = object()
    artifacts = SimpleNamespace(
        character_events=({"id": "c1", "change": {"character_id": "x"}},),
        relationship_events=(),
        knowledge_changes=({"proposition_id": "fact.p", "certainty": 1},),
        world_events=(),
        memories=(),
    )

    class _Result:
        pass

    _Result.episode = episode
    _Result.artifacts = artifacts

    class _Repo:
        async def load_by_session(self, session_id):
            return _Result()

    bundle = await _StoryBookEpisodeAdapter(_Repo()).load_finalized_episode("s")

    assert bundle.episode is episode
    assert bundle.artifacts.character_events == artifacts.character_events
    assert bundle.artifacts.knowledge_changes == artifacts.knowledge_changes
    # Memories are not a Story Book section; they must not be smuggled in.
    assert not hasattr(bundle.artifacts, "memories")


@pytest.mark.asyncio
async def test_narrative_adapter_maps_storage_error_to_none():
    class _Repo:
        async def load_narrative_block(self, block_id):
            raise StorageError("not found")

    assert await _StoryBookNarrativeAdapter(_Repo()).load_narrative_block("b") is None


@pytest.mark.asyncio
async def test_narrative_adapter_passes_through_a_block():
    block = object()

    class _Repo:
        async def load_narrative_block(self, block_id):
            return block

    assert await _StoryBookNarrativeAdapter(_Repo()).load_narrative_block("b") is block


def test_error_code_table_covers_every_projection_code():
    # A new projection code must not silently degrade to service_unavailable.
    assert _STORYBOOK_ERROR_CODES.keys() >= {
        "storybook_session_unknown",
        "storybook_not_finalized",
        "storybook_has_no_chapters",
        "storybook_chapter_missing",
    }
