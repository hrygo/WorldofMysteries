"""The silent half: noticing a voiceless first appearance (VF-51).

The contract these tests pin is narrow and entirely about restraint. Casting
has to start on its own — otherwise the automatic entry point does not exist —
and it has to shut up while it does, because the alternative is a dialogue
about voice casting every time a new character clears their throat.
"""

from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio

from application.voice_supply_trigger import VoiceSupplyTrigger
from domain.voice_identity import VoiceBindingScope
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_design_catalog import load_voice_design_catalog
from infrastructure.voice_foundry_repository import SQLiteVoiceFoundryRepository

#: A two-identity catalog. The shipped one has five; a policy test does not
#: need the whole cast to know what "not in the catalog" means.
CATALOG = load_voice_design_catalog()


def scope(identity: str = "victor-osborn") -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="trigger-world",
        worldline_id="line-1",
        presentation_identity=identity,
        phase="narrative",
        locale="zh-CN",
    )


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "trigger-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def repository(paths):
    database = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield SQLiteVoiceFoundryRepository(database)
    finally:
        await database.close()


class NothingBound:
    """No binding for any scope — this whole file is the voiceless path."""

    async def load_scope(self, _scope):
        return None


def trigger(repository, **kwargs) -> VoiceSupplyTrigger:
    from application.voice_foundry_service import VoiceSupplyService

    return VoiceSupplyTrigger(
        supply=VoiceSupplyService(
            repository=repository,
            bindings=NothingBound(),
        ),
        designs=CATALOG,
        provider_instance="speechrail-local",
        **kwargs,
    )


async def test_a_character_who_speaks_without_a_voice_starts_being_cast(
    repository,
):
    """The case that used to be a dead end: nobody pressed Retry, nobody spoke."""
    result = await trigger(repository).ensure(scope())

    assert result.requested is True
    tasks = await repository.load_scope_tasks(scope())
    assert len(tasks) == 1
    assert tasks[0].stage.value == "requested"


async def test_starting_a_casting_does_not_interrupt_the_player(repository):
    """Automatic is not the same as asking. Nothing is owed yet, so say nothing."""
    result = await trigger(repository).ensure(scope())

    assert result.awaiting_person is False
    assert result.reason_code is None


async def test_a_character_who_speaks_every_turn_opens_one_casting(repository):
    """Idempotence by derivation: the request id *is* what is being cast."""
    engine = trigger(repository)
    for _ in range(4):
        await engine.ensure(scope())

    tasks = await repository.load_scope_tasks(scope())
    assert len(tasks) == 1


async def test_a_task_already_waiting_on_somebody_is_not_reopened(repository):
    """A second request would buy a duplicate candidate for the same listener."""
    engine = trigger(repository)
    await engine.ensure(scope())
    task = (await repository.load_scope_tasks(scope()))[-1]
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage="awaiting_selection",
        operation_status="confirmed",
        required_actions=("select_candidate",),
    )

    result = await engine.ensure(scope())

    assert result.requested is False
    # Read from the record, not re-derived: this is the one condition that
    # earns the right to interrupt, and it is the record's to say.
    assert result.awaiting_person is True


async def test_a_character_nobody_wrote_a_brief_for_is_cast_from_what_they_said(
    repository,
):
    """The whole point: a new speaker is not mute.

    Before this, an identity missing from the catalog returned
    ``voice_design_absent`` and no task was ever opened — so the sixth
    character to appear in a world was permanently voiceless. Now the brief is
    composed from the lines they have already published.
    """
    target = scope("somebody-unwritten")
    result = await trigger(repository).ensure(
        target,
        spoken_lines=(
            "今天雾很大，街角那盏煤气灯又坏了，巷子尽头一点光都没有。",
            "你说的是哪一班？我记得是三点的，可那时钟早就停了吧。",
        ),
        display_name="路人",
    )

    assert result.requested is True
    tasks = await repository.load_scope_tasks(target)
    assert len(tasks) == 1
    assert tasks[0].voice_description != ""


async def test_a_character_who_has_spoken_once_is_not_cast_yet(repository):
    """Not enough published words to check a voice against, and it says so."""
    target = scope("somebody-unwritten")
    result = await trigger(repository).ensure(
        target, spoken_lines=("今天雾很大。",), display_name="路人"
    )

    assert result.requested is False
    assert result.reason_code == "voice_brief_insufficient_evidence"
    assert await repository.load_scope_tasks(target) == ()


async def test_a_catalog_brief_is_never_overwritten_by_a_composed_one(repository):
    """A voice a person listened to and signed is not re-decided by the system."""
    from infrastructure.voice_design_catalog import load_voice_design_catalog

    target = scope("victor-osborn")
    result = await trigger(repository).ensure(
        target,
        spoken_lines=("完全不同的另一套说法。", "而且是新的。"),
        display_name="维克多·奥斯本",
    )

    assert result.requested is True
    task = (await repository.load_scope_tasks(target))[-1]
    assert (
        task.voice_description
        == load_voice_design_catalog().get("victor-osborn").voice_description
    )


async def test_an_identity_that_already_has_a_voice_is_left_alone(repository):
    class Bound:
        async def load_scope(self, _scope):
            from domain.voice_identity import VoiceBinding

            return VoiceBinding(
                binding_id="binding-1",
                scope=scope(),
                persona=__import__(
                    "domain.voice_identity", fromlist=["VoicePersonaRevision"]
                ).VoicePersonaRevision("persona-1", 1),
                provider=__import__(
                    "domain.voice_identity", fromlist=["ProviderVoiceRevision"]
                ).ProviderVoiceRevision("speechrail-local", "voice-1", "rev-1"),
                status="active",
                assurance="content_addressed",
                evidence=None,
                binding_revision=1,
            )

    from application.voice_foundry_service import VoiceSupplyService

    engine = VoiceSupplyTrigger(
        supply=VoiceSupplyService(repository=repository, bindings=Bound()),
        designs=CATALOG,
        provider_instance="speechrail-local",
    )

    result = await engine.ensure(scope())

    assert result.requested is False
    assert result.awaiting_person is False


async def test_a_supply_chain_that_is_down_does_not_fail_the_turn(repository):
    """The text is already published; a casting that cannot start changes nothing."""

    class Broken:
        async def precheck(self, _scope):
            raise RuntimeError("database is gone")

    from application.voice_foundry_service import VoiceSupplyResult

    engine = VoiceSupplyTrigger(
        supply=Broken(),  # type: ignore[arg-type]
        designs=CATALOG,
        provider_instance="speechrail-local",
    )

    result = await engine.ensure(scope())

    assert result.requested is False
    assert result.reason_code == "voice_supply_trigger_failed"
