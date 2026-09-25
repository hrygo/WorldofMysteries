"""Authorization-aware W-V07 dry AudioTake single-flight coordinator.

Only provider rendering/publication is shared. Every subscriber remains an
independent delivery authority and generation/domain execution. Authorization is
checked before cache lookup and again before returning a take.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .audio_take_store import (
    DryRenderRecipe,
    PublishedAudioTake,
    RenderOutcome,
)


AuthorizationStage = Literal["before_lookup", "before_delivery"]
AuthorizationCheck = Callable[[AuthorizationStage], Awaitable[bool]]


class AudioTakeRenderCoordinatorError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RenderedPCM:
    outcome: RenderOutcome
    pcm16: bytes


RenderProducer = Callable[[], Awaitable[RenderedPCM]]


class AudioTakeStorePort(Protocol):
    def render_key(self, recipe: DryRenderRecipe) -> str: ...

    async def load(self, render_key: str) -> PublishedAudioTake | None: ...

    async def publish_pcm(
        self,
        recipe: DryRenderRecipe,
        outcome: RenderOutcome,
        pcm16: bytes,
    ) -> PublishedAudioTake: ...


@dataclass(slots=True)
class _Flight:
    task: asyncio.Task[PublishedAudioTake]
    recipe_json: str
    waiters: dict[int, str]


class AudioTakeRenderCoordinator:
    """Bounded single-flight for one world-scoped private RenderKey."""

    def __init__(
        self,
        store: AudioTakeStorePort,
        *,
        max_flights: int = 32,
        max_waiters_per_flight: int = 16,
    ) -> None:
        if max_flights < 1 or max_waiters_per_flight < 1:
            raise ValueError("invalid audio take single-flight limits")
        self._store = store
        self._max_flights = max_flights
        self._max_waiters_per_flight = max_waiters_per_flight
        self._flights: dict[str, _Flight] = {}
        self._next_waiter = 0
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        *,
        subscriber_id: str,
        recipe: DryRenderRecipe,
        authorize: AuthorizationCheck,
        render: RenderProducer,
    ) -> PublishedAudioTake:
        """Return a fresh-authorized cached/shared take for one subscriber."""
        if not isinstance(subscriber_id, str) or not subscriber_id.strip():
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_subscriber")
        if not isinstance(recipe, DryRenderRecipe):
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_recipe")
        if not callable(authorize) or not callable(render):
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_callbacks")

        await self._require_authorized(authorize, "before_lookup")
        render_key = self._store.render_key(recipe)

        cached = await self._store.load(render_key)
        if cached is not None:
            await self._require_authorized(authorize, "before_delivery")
            return cached

        task: asyncio.Task[PublishedAudioTake] | None = None
        waiter_token: int | None = None
        cached_after_lock: PublishedAudioTake | None = None

        async with self._lock:
            flight = self._flights.get(render_key)
            if flight is None:
                # Close the miss->flight race while holding the creation lock.
                cached_after_lock = await self._store.load(render_key)
                if cached_after_lock is None:
                    if len(self._flights) >= self._max_flights:
                        raise AudioTakeRenderCoordinatorError(
                            "audio_take_singleflight_capacity"
                        )
                    task = asyncio.create_task(self._produce(recipe, render))
                    task.add_done_callback(self._observe_task)
                    flight = _Flight(
                        task=task,
                        recipe_json=recipe.canonical_json(),
                        waiters={},
                    )
                    self._flights[render_key] = flight
            if cached_after_lock is None:
                assert flight is not None
                if flight.recipe_json != recipe.canonical_json():
                    raise AudioTakeRenderCoordinatorError(
                        "audio_take_render_key_collision"
                    )
                if subscriber_id in flight.waiters.values():
                    raise AudioTakeRenderCoordinatorError(
                        "duplicate_audio_take_subscriber"
                    )
                if len(flight.waiters) >= self._max_waiters_per_flight:
                    raise AudioTakeRenderCoordinatorError(
                        "audio_take_singleflight_waiter_capacity"
                    )
                self._next_waiter += 1
                waiter_token = self._next_waiter
                flight.waiters[waiter_token] = subscriber_id
                task = flight.task

        if cached_after_lock is not None:
            await self._require_authorized(authorize, "before_delivery")
            return cached_after_lock

        assert task is not None and waiter_token is not None
        try:
            take = await asyncio.shield(task)
            await self._require_authorized(authorize, "before_delivery")
            return take
        finally:
            await self._leave(render_key, waiter_token, task)

    async def _produce(
        self,
        recipe: DryRenderRecipe,
        render: RenderProducer,
    ) -> PublishedAudioTake:
        rendered = await render()
        if not isinstance(rendered, RenderedPCM):
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_render_result")
        if not isinstance(rendered.outcome, RenderOutcome):
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_render_outcome")
        if not isinstance(rendered.pcm16, (bytes, bytearray)):
            raise AudioTakeRenderCoordinatorError("invalid_audio_take_render_pcm")
        return await self._store.publish_pcm(
            recipe,
            rendered.outcome,
            bytes(rendered.pcm16),
        )

    async def _leave(
        self,
        render_key: str,
        waiter_token: int,
        task: asyncio.Task[PublishedAudioTake],
    ) -> None:
        async with self._lock:
            flight = self._flights.get(render_key)
            if flight is None or flight.task is not task:
                return
            flight.waiters.pop(waiter_token, None)
            if flight.waiters:
                return
            self._flights.pop(render_key, None)
            if not task.done():
                task.cancel()

    @staticmethod
    async def _require_authorized(
        authorize: AuthorizationCheck,
        stage: AuthorizationStage,
    ) -> None:
        try:
            allowed = await authorize(stage)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise AudioTakeRenderCoordinatorError(
                "audio_take_authorization_unavailable"
            ) from exc
        if allowed is not True:
            raise AudioTakeRenderCoordinatorError("audio_take_not_authorized")

    @staticmethod
    def _observe_task(task: asyncio.Task[PublishedAudioTake]) -> None:
        if task.cancelled():
            return
        with contextlib.suppress(Exception):
            task.exception()

    async def snapshot(self) -> dict[str, int]:
        """Bounded operational counters; never exposes private RenderKeys."""
        async with self._lock:
            return {
                "active_flights": len(self._flights),
                "active_waiters": sum(
                    len(flight.waiters) for flight in self._flights.values()
                ),
                "max_flights": self._max_flights,
                "max_waiters_per_flight": self._max_waiters_per_flight,
            }
