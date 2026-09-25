"""Bounded W-V07 dry AudioTake prefetch for already-sealed speech units.

Prefetch has no media/playback surface and cannot build narrative content. It only
maps an Engine-owned SealedSpeechUnit into a dry recipe and asks the authorization-
aware single-flight coordinator to fill/return the cache.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from application.speech_unit import SealedSpeechUnit
from .audio_take_coordinator import (
    AudioTakeRenderCoordinator,
    AuthorizationCheck,
    RenderProducer,
)
from .audio_take_store import DryRenderRecipe, PublishedAudioTake


class AudioTakePrefetchError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AudioTakePrefetchSnapshot:
    pending_units: int
    max_pending_units: int


class AudioTakePrefetchQueue:
    """At most two sealed future units may occupy prefetch slots."""

    ABSOLUTE_MAX_PENDING = 2

    def __init__(
        self,
        coordinator: AudioTakeRenderCoordinator,
        *,
        max_pending_units: int = 2,
    ) -> None:
        if (
            type(max_pending_units) is not int
            or max_pending_units < 1
            or max_pending_units > self.ABSOLUTE_MAX_PENDING
        ):
            raise ValueError("invalid audio take prefetch limit")
        self._coordinator = coordinator
        self._max_pending_units = max_pending_units
        self._pending_unit_ids: set[str] = set()
        self._lock = asyncio.Lock()

    async def prefetch(
        self,
        *,
        subscriber_id: str,
        unit: SealedSpeechUnit,
        authorize: AuthorizationCheck,
        render: RenderProducer,
    ) -> PublishedAudioTake:
        """Fill or read one dry take; never registers media or starts playback."""
        self._require_prefetchable(unit)
        recipe = self.recipe_for(unit)

        async with self._lock:
            if unit.unit_id in self._pending_unit_ids:
                raise AudioTakePrefetchError("audio_take_prefetch_duplicate_unit")
            if len(self._pending_unit_ids) >= self._max_pending_units:
                raise AudioTakePrefetchError("audio_take_prefetch_capacity")
            self._pending_unit_ids.add(unit.unit_id)

        try:
            return await self._coordinator.acquire(
                subscriber_id=f"prefetch:{subscriber_id}:{unit.unit_id}",
                recipe=recipe,
                authorize=authorize,
                render=render,
            )
        finally:
            async with self._lock:
                self._pending_unit_ids.discard(unit.unit_id)

    @staticmethod
    def recipe_for(unit: SealedSpeechUnit) -> DryRenderRecipe:
        AudioTakePrefetchQueue._require_prefetchable(unit)
        assert unit.model_revision is not None
        return DryRenderRecipe.build(
            provider_instance=unit.provider_instance,
            model_id=unit.model_id,
            model_revision=unit.model_revision,
            voice_id=unit.voice_id,
            voice_revision=unit.voice_revision,
            spoken_text=unit.spoken_text,
            pronunciation_revision=unit.pronunciation_revision,
            backend_fields=unit.backend.provider_fields(),
        )

    @staticmethod
    def _require_prefetchable(unit: SealedSpeechUnit) -> None:
        if not isinstance(unit, SealedSpeechUnit) or not unit.sealed:
            raise AudioTakePrefetchError("audio_take_prefetch_requires_sealed_unit")
        if not unit.spoken_text.strip():
            raise AudioTakePrefetchError("audio_take_prefetch_empty_spoken_text")
        if unit.model_revision is None:
            raise AudioTakePrefetchError("audio_take_prefetch_model_revision_unverified")
        if set(unit.backend.provider_fields()) != {"speed"}:
            raise AudioTakePrefetchError("audio_take_prefetch_backend_unrepresentable")

    async def snapshot(self) -> AudioTakePrefetchSnapshot:
        async with self._lock:
            return AudioTakePrefetchSnapshot(
                pending_units=len(self._pending_unit_ids),
                max_pending_units=self._max_pending_units,
            )
