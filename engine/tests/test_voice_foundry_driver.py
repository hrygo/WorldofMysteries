"""The background half of voice supply: who moves a cast while nobody asks."""

from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio

from application.voice_foundry import VoiceFoundryWorker
from application.voice_foundry_ports import (
    PreviewRequest,
    PreviewResult,
)
from domain.voice_identity import VoiceBindingScope
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_foundry_driver import (
    DRIVER_STAGES,
    VoiceFoundryDriver,
)
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "foundry-driver-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def database(paths):
    db = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield db
    finally:
        await db.close()


class _Port:
    """Just enough provider to walk a task out of ``requested``."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def preview(self, request: PreviewRequest) -> PreviewResult:
        self.calls.append("preview")
        return PreviewResult(
            preview_id="preview-1",
            audio_digest="b" * 64,
            audio_bytes=16,
            duration_seconds=1.0,
            audio=b"RIFF----WAVEfake",
            recipe={"seed": request.seed},
            recipe_digest="c" * 64,
        )


def _spec(**overrides) -> VoiceFoundryTaskSpec:
    base = {
        "task_id": "task-1",
        "request_id": "request-1",
        "request_digest": "a" * 64,
        "authorization_ref": "authz-1",
        "scope": VoiceBindingScope(
            owner_id="player",
            world_id="foundry-driver-world",
            worldline_id="line-1",
            presentation_identity="klein-visible",
            phase="narrative",
            locale="zh-CN",
        ),
        "persona_revision": "persona-1",
        "usage": "dialogue",
        "provider_instance": "speechrail-local",
        "public_traits": ("低沉",),
        "voice_description": "克制而警觉的年轻男性声音。",
        "reference_text": "这是用于确认音色参考的完整句子，必须足够长以通过校验。",
        "validation_text": "这是用于跨文本复验的另一句完整文本，不能与参考文本相同。",
        "origin_kind": "content",
        "origin_ref": "npc:klein",
        "origin_revision": 1,
    }
    base.update(overrides)
    return VoiceFoundryTaskSpec(**base)


def _driver(repository, port, **kwargs) -> VoiceFoundryDriver:
    return VoiceFoundryDriver(
        repository=repository,
        worker=VoiceFoundryWorker(repository, port),
        **kwargs,
    )


async def test_a_registered_cast_moves_without_anybody_asking(database):
    """Intake used to be a dead end: a task could be created and never move.

    ``advance`` had exactly one caller — the retry command — so a player who
    never pressed Retry got a character who could never speak. This is the
    half that makes the intake mean anything.
    """
    repository = SQLiteVoiceFoundryRepository(database)
    port = _Port()
    await repository.register_task(_spec())

    assert await _driver(repository, port).run_once() == 1

    task = await repository.load_task("task-1")
    assert task.stage is not VoiceFoundryStage.REQUESTED
    assert port.calls == ["preview"]


async def test_the_driver_never_touches_a_stage_that_belongs_to_a_person(database):
    repository = SQLiteVoiceFoundryRepository(database)
    port = _Port()
    await repository.register_task(_spec())
    repository_task = await repository.load_task("task-1")
    await repository.set_stage(
        "task-1",
        expected_revision=repository_task.task_revision,
        stage="awaiting_selection",
        operation_status="confirmed",
        required_actions=("choose_candidate",),
    )

    assert await _driver(repository, port).run_once() == 0
    assert port.calls == []
    assert "awaiting_selection" not in DRIVER_STAGES


async def test_a_pass_that_moves_nothing_reports_zero_so_the_loop_idles(database):
    repository = SQLiteVoiceFoundryRepository(database)
    port = _Port()
    driver = _driver(repository, port)

    assert await driver.run_once() == 0


async def test_work_left_mid_cast_is_picked_up_after_a_restart(database):
    """The value of polling: the stage a task was left in is the whole record.

    Nothing has to be replayed or reconstructed — whatever step the previous
    process managed to commit is what this one continues from.
    """
    repository = SQLiteVoiceFoundryRepository(database)
    port = _Port()
    await repository.register_task(_spec())
    task = await repository.load_task("task-1")
    await repository.set_stage(
        "task-1",
        expected_revision=task.task_revision,
        stage="previewing",
        operation_status="prepared",
        required_actions=(),
    )

    driver = _driver(repository, port)
    assert await driver.run_once() == 1
    assert port.calls == ["preview"]


async def test_the_loop_advances_repeatedly_until_a_person_is_the_bottleneck(
    database,
):
    repository = SQLiteVoiceFoundryRepository(database)
    port = _Port()
    await repository.register_task(_spec())
    driver = _driver(repository, port)

    seen = []
    for _ in range(6):
        await driver.run_once()
        seen.append((await repository.load_task("task-1")).stage)
        if seen[-1] == VoiceFoundryStage.AWAITING_SELECTION:
            break

    assert seen[-1] == VoiceFoundryStage.AWAITING_SELECTION
    # It got there by asking the provider for previews, not by jumping.
    assert port.calls


async def test_start_and_stop_leave_no_task_running(database):
    repository = SQLiteVoiceFoundryRepository(database)
    driver = _driver(repository, _Port(), poll_interval_seconds=0.01)

    await driver.start()
    assert driver.is_running
    await driver.stop()
    assert not driver.is_running
    # Idempotent: stopping a driver that is already stopped is not an error.
    await driver.stop()


@pytest.mark.parametrize(
    "kwargs",
    [{"poll_interval_seconds": 0}, {"batch_size": 0}],
)
def test_a_driver_that_could_spin_or_starve_is_refused(kwargs):
    with pytest.raises(ValueError):
        VoiceFoundryDriver(
            repository=None,
            worker=None,
            **kwargs,
        )
