"""Story Book loading service (PRD §20.1)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.storybook_projection import StoryBookProjectionError
from application.storybook_service import StoryBookService
from contracts import Episode, NarrativeBlock, SecretState
from contracts.models import NarrativeSegment


def _bootstrap(names: dict[str, str]):
    # The service only reads ``presentation.character_display_names``; a stub
    # keeps this test focused on the assembly logic rather than the whole
    # bootstrap fixture.
    return SimpleNamespace(
        presentation=SimpleNamespace(character_display_names=names)
    )


def _block(block_id: str) -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id=block_id,
        story_session_id="session-1",
        source_story_revision=1,
        scene_id="consultation_room",
        segments=[
            NarrativeSegment(type="narration", text="雨落在诊所的窗外。"),
            NarrativeSegment(
                type="character", speaker_id="char_morris", text="你还没有回答。"
            ),
        ],
    )


def _episode(block_ids: list[str] | None) -> Episode:
    return Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode_session-1",
            "world_id": "world-1",
            "worldline_id": "worldline-1",
            "protagonist_ids": ["char_evelyn"],
            "title": "哈维诊所的停顿",
            "start_world_time": "1349-06-12T21:40:00",
            "ending": {"type": "partial_truth", "main_problem": None},
            "secret_states": {"secret_01": SecretState.PARTIAL},
            "unresolved_threads": [],
            **({"narrative_block_ids": block_ids} if block_ids is not None else {}),
        }
    )


class _Ports:
    def __init__(self, *, bootstrap, episode, blocks):
        self._bootstrap = bootstrap
        self._episode = episode
        self._blocks = blocks

    class _Boot:
        def __init__(self, outer): self._o = outer
        async def load(self, session_id): return self._o._bootstrap

    class _Epi:
        def __init__(self, outer): self._o = outer
        async def load_finalized_episode(self, session_id): return self._o._episode

    class _Nar:
        def __init__(self, outer): self._o = outer
        async def load_narrative_block(self, block_id): return self._o._blocks.get(block_id)

    def service(self):
        return StoryBookService(
            bootstraps=self._Boot(self),
            episodes=self._Epi(self),
            narratives=self._Nar(self),
        )


async def _happy(names):
    return _Ports(
        bootstrap=_bootstrap(names),
        episode=_episode(["b1"]),
        blocks={"b1": _block("b1")},
    ).service()


@pytest.mark.asyncio
async def test_service_assembles_storybook_and_resolves_speaker():
    svc = await _happy({"char_morris": "莫里斯医生"})
    book = await svc.story_book("session-1")
    assert book["episode_id"] == "episode_session-1"
    assert [c["block_id"] for c in book["chapters"]] == ["b1"]
    assert book["chapters"][0]["segments"][1]["speaker"] == "莫里斯医生"


@pytest.mark.asyncio
async def test_service_speaker_fails_closed_without_public_label():
    svc = await _happy({})
    book = await svc.story_book("session-1")
    assert book["chapters"][0]["segments"][1]["speaker"] is None
    assert "char_morris" not in str(book)


@pytest.mark.asyncio
async def test_unknown_session_is_rejected():
    svc = _Ports(bootstrap=None, episode=_episode(["b1"]), blocks={}).service()
    with pytest.raises(StoryBookProjectionError) as exc:
        await svc.story_book("session-x")
    assert exc.value.code == "storybook_session_unknown"


@pytest.mark.asyncio
async def test_unfinalized_session_is_rejected():
    svc = _Ports(bootstrap=_bootstrap({}), episode=None, blocks={}).service()
    with pytest.raises(StoryBookProjectionError) as exc:
        await svc.story_book("session-1")
    assert exc.value.code == "storybook_not_finalized"


@pytest.mark.asyncio
async def test_missing_chapter_is_rejected():
    svc = _Ports(bootstrap=_bootstrap({}), episode=_episode(["b1"]), blocks={}).service()
    with pytest.raises(StoryBookProjectionError) as exc:
        await svc.story_book("session-1")
    assert exc.value.code == "storybook_chapter_missing"
