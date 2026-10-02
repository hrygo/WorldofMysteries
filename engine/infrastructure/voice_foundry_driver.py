"""Move supply tasks forward while nobody is waiting on a person (VF-48).

``VoiceFoundryWorker.advance`` had exactly one caller: the ``retry`` command.
That made a casting runnable from a test and from nowhere else — a task could
be registered, and then sat at ``requested`` until somebody explicitly asked
it to move. A player never asks for that, so nothing would ever happen.

This drives the stages that are not a person's to decide. It never touches
``awaiting_selection`` or ``awaiting_review``: those are the two stages where
the worker's own contract says a person is the bottleneck, and a background
loop that raced them would be spending the listener's attention without them.

Polling rather than an event is deliberate. A cast is minutes of provider
time spread over several durable steps, and the whole value of this loop is
that it also runs after a restart — whatever stage a task was left in is the
stage the driver picks it up from, with no replay log to reconstruct.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from application.voice_foundry import VoiceFoundryWorker

from .voice_foundry_repository import SQLiteVoiceFoundryRepository

#: The stages this driver owns. Everything else is either waiting on a person
#: or finished, and ``advance`` would decline both — but declining costs a
#: database read and a slot, and a page of finished tasks would otherwise sit
#: in front of the work that actually needs doing.
DRIVER_STAGES: tuple[str, ...] = (
    "requested",
    "previewing",
    "provisioning",
    "validating",
)


class VoiceFoundryDriver:
    """Advance unattended supply tasks, one durable step at a time."""

    def __init__(
        self,
        *,
        repository: SQLiteVoiceFoundryRepository,
        worker: VoiceFoundryWorker,
        poll_interval_seconds: float = 2.0,
        batch_size: int = 4,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("voice_foundry_driver_poll_interval_must_be_positive")
        if batch_size < 1:
            raise ValueError("voice_foundry_driver_batch_must_not_be_empty")
        self._repository = repository
        self._worker = worker
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._sleep = sleeper or asyncio.sleep
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def request_stop(self) -> None:
        self._stop_event.set()

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("voice_foundry_driver_cannot_be_restarted")
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._serve())

    async def stop(self) -> None:
        if self._task is None:
            return
        self.request_stop()
        await self._task
        self._task = None

    async def run_once(self) -> int:
        """Advance what can be advanced; return how many steps actually ran.

        Single-pass on purpose: it is the shape tests drive, and the loop is
        only this method plus a sleep. A pass that changed nothing means every
        task in the window is waiting on a person or already finished, and the
        caller should idle rather than spin.
        """
        if self._task is not None and asyncio.current_task() is not self._task:
            raise RuntimeError("voice_foundry_driver_already_running")
        if self._stop_event.is_set():
            return 0
        advanced = 0
        for stage in DRIVER_STAGES:
            if self._stop_event.is_set():
                break
            tasks = await self._repository.load_tasks_page(
                page_size=self._batch_size, stage=stage
            )
            for task in tasks:
                if self._stop_event.is_set():
                    break
                step = await self._worker.advance(task.task_id)
                if step.slot_consumed:
                    advanced += 1
        return advanced

    async def _serve(self) -> None:
        try:
            while not self._stop_event.is_set():
                advanced = await self.run_once()
                if advanced == 0 and not self._stop_event.is_set():
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._poll_interval_seconds,
                        )
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            self.request_stop()
            raise


__all__ = ["DRIVER_STAGES", "VoiceFoundryDriver"]
