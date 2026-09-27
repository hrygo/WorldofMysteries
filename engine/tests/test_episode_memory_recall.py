"""T5b authorized Episode Memory recall and hidden-fact rejection."""
from __future__ import annotations

from dataclasses import replace

import pytest
from test_memory_return_durable import _build_finalized

from application.context_plan import ContextError, ContextInput, Evidence, Layer
from application.episode_memory_recall import (
    EpisodeMemoryRecallService,
    MemoryRecallCommand,
)
from infrastructure.episode_finalization_repository import (
    SQLiteEpisodeFinalizationRepository,
)

SUBJECT = "char_evelyn_gray"


def _command(session_id: str, world_revision: int) -> MemoryRecallCommand:
    return MemoryRecallCommand(
        session_id=session_id,
        subject_id=SUBJECT,
        owner_id="player",
        world_revision=world_revision,
        story_revision=5,
        world_tick=5,
        epoch_id="epoch-recall",
        request_id="req-recall",
    )


@pytest.mark.asyncio
async def test_authorized_episode_memory_is_recalled_for_its_subject(tmp_path):
    database, _paths, opened, _finalized = await _build_finalized(tmp_path)
    try:
        service = EpisodeMemoryRecallService(
            episodes=SQLiteEpisodeFinalizationRepository(database)
        )
        world_revision = (await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ))[0]["revision"]
        result = await service.recall(_command(opened.session.session_id, world_revision))

        # The subject's committed episode memory is recalled exactly once.
        assert len(result.evidence) == 1
        memory = result.evidence[0]
        assert memory.source_id == "memory_golden_five_turn"
        assert memory.subject_id == SUBJECT
        assert memory.layer is Layer.HISTORY
        # Only the recalled memory is granted; the grant is exactly its fingerprint.
        assert result.view.grants == frozenset({memory.fingerprint})
        # The compiled plan carries the memory into the ordered evidence.
        assert memory in result.plan.ordered_evidence
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_recall_grants_nothing_for_an_unknown_subject(tmp_path):
    database, _paths, opened, _finalized = await _build_finalized(tmp_path)
    try:
        service = EpisodeMemoryRecallService(
            episodes=SQLiteEpisodeFinalizationRepository(database)
        )
        world_revision = (await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ))[0]["revision"]
        command = _command(opened.session.session_id, world_revision)
        result = await service.recall(
            replace(command, subject_id="char_stranger")
        )
        # A subject with no committed memory receives an empty, harmless plan.
        assert result.evidence == ()
        assert result.view.grants == frozenset()
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_hidden_fact_is_never_granted_and_cannot_be_smuggled(tmp_path):
    database, _paths, opened, _finalized = await _build_finalized(tmp_path)
    try:
        service = EpisodeMemoryRecallService(
            episodes=SQLiteEpisodeFinalizationRepository(database)
        )
        world_revision = (await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ))[0]["revision"]
        result = await service.recall(_command(opened.session.session_id, world_revision))

        # No granted evidence leaks the still-hidden secret.
        hidden = 'the_true_organizer_is_known'
        assert all(hidden not in item.content_json for item in result.evidence)

        # Smuggling an unauthorized hidden-fact evidence into a request is rejected.
        smuggled = Evidence(
            "hidden-secret", 1, "secret", Layer.HISTORY,
            '{"fact":"the_true_organizer_is_known"}',
            world_id="world_001", worldline_id="wl_main",
            subject_id=SUBJECT, committed_revision=1, sequence=99,
        )
        assert smuggled.fingerprint not in result.view.grants
        bad_request = ContextInput(
            result.view.scope,
            result.view.world_revision,
            result.view.story_revision,
            "epoch-recall",
            result.evidence + (smuggled,),
            '{"task":"recall"}',
            "req-bad",
        )
        with pytest.raises(ContextError, match="evidence_not_authorized"):
            service._compiler.compile(bad_request, result.view, result.plan.profile)
    finally:
        await database.close()
