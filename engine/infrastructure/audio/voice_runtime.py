"""Executable sealed voice render runtime.

This module never authorizes narrative content, identity, or performance. Those
choices must already be frozen in an Engine-owned SealedSpeechUnit. Authenticated
control requests may only attach one media stream identity to the exact sealed
recipe; any drift fails before SpeechRail is opened.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import time

from pydantic import ValidationError

from application.speech_unit import SealedSpeechUnit
from .media_bridge import RealtimeTTSMediaBridgeError, render_realtime_tts_to_media
from .media_protocol import MediaErrorHeader, MediaOpenHeader, write_media_frame
from .realtime_tts import (
    RealtimeTTSChunk,
    RealtimeTTSRequest,
    RealtimeTTSTerminal,
    SpeechRailRealtimeTTSAdapter,
    SpeechRailRealtimeTTSError,
    create_realtime_tts_adapter,
)
from .voice_control import (
    PendingVoiceRenderRegistry,
    VoiceRenderControlError,
    VoiceRenderControlRequest,
)


class VoiceRenderRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _SealedEntry:
    unit: SealedSpeechUnit
    expires_at: float


class SealedSpeechUnitRegistry:
    """Bounded Engine-owned handoff from Application sealing to execution."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        ttl_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1 or ttl_seconds <= 0 or ttl_seconds > 300:
            raise ValueError("invalid sealed SpeechUnit registry limits")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._entries: dict[str, _SealedEntry] = {}

    def publish(self, unit: SealedSpeechUnit) -> None:
        if not isinstance(unit, SealedSpeechUnit) or not unit.sealed:
            raise VoiceRenderRuntimeError("voice_render_unit_not_sealed")
        now = self._clock()
        self._discard_expired(now)
        existing = self._entries.get(unit.unit_id)
        if existing is not None:
            if existing.unit != unit:
                raise VoiceRenderRuntimeError("voice_render_unit_identity_conflict")
            self._entries[unit.unit_id] = _SealedEntry(
                unit=unit,
                expires_at=now + self._ttl_seconds,
            )
            return
        if len(self._entries) >= self._max_entries:
            raise VoiceRenderRuntimeError("voice_render_unit_registry_capacity")
        self._entries[unit.unit_id] = _SealedEntry(
            unit=unit,
            expires_at=now + self._ttl_seconds,
        )

    def peek(self, unit_id: str) -> SealedSpeechUnit:
        self._discard_expired(self._clock())
        entry = self._entries.get(unit_id)
        if entry is None:
            raise VoiceRenderRuntimeError("voice_render_unit_not_found")
        return entry.unit

    def consume(self, unit_id: str) -> SealedSpeechUnit:
        self._discard_expired(self._clock())
        entry = self._entries.pop(unit_id, None)
        if entry is None:
            raise VoiceRenderRuntimeError("voice_render_unit_not_found")
        return entry.unit

    def _discard_expired(self, now: float) -> None:
        expired = [
            unit_id
            for unit_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for unit_id in expired:
            self._entries.pop(unit_id, None)

    def __len__(self) -> int:
        self._discard_expired(self._clock())
        return len(self._entries)


AdapterFactory = Callable[[], SpeechRailRealtimeTTSAdapter]


class VoiceRenderRuntime:
    """Bind sealed speech to one pending media stream and execute it once."""

    def __init__(
        self,
        *,
        provider_instance: str,
        adapter_factory: AdapterFactory | None = None,
        sealed_units: SealedSpeechUnitRegistry | None = None,
        pending_ttl_seconds: float = 10.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not isinstance(provider_instance, str) or not provider_instance.strip():
            raise ValueError("provider_instance is required")
        if pending_ttl_seconds <= 0 or pending_ttl_seconds > 30:
            raise ValueError("invalid pending render ttl")
        self.provider_instance = provider_instance
        self._clock = clock or time.monotonic
        self._pending_ttl_seconds = pending_ttl_seconds
        self.sealed_units = sealed_units or SealedSpeechUnitRegistry(clock=self._clock)
        self._pending = PendingVoiceRenderRegistry(
            ttl_seconds=pending_ttl_seconds,
            clock=self._clock,
        )
        self._unit_reservations: dict[str, tuple[str, float]] = {}
        self._stream_units: dict[str, str] = {}
        self._adapter_factory = adapter_factory or create_realtime_tts_adapter
        self._control_lock = asyncio.Lock()

    def publish(self, unit: SealedSpeechUnit) -> None:
        if unit.provider_instance != self.provider_instance:
            raise VoiceRenderRuntimeError("voice_render_provider_instance_mismatch")
        self.sealed_units.publish(unit)

    async def handle_control(
        self,
        payload: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, str | None]:
        """Handle one authenticated voice.render request without provider I/O."""
        try:
            request = VoiceRenderControlRequest.model_validate(dict(payload))
        except (ValidationError, TypeError, ValueError):
            return None, "schema_invalid"

        try:
            async with self._control_lock:
                self._discard_expired_reservations()
                unit = self.sealed_units.peek(request.speech_unit_id)
                if unit.provider_instance != self.provider_instance:
                    raise VoiceRenderRuntimeError(
                        "voice_render_provider_instance_mismatch"
                    )
                self._require_exact_recipe(unit, request)
                if unit.unit_id in self._unit_reservations:
                    raise VoiceRenderRuntimeError("voice_render_unit_already_reserved")

                accepted = self._pending.register(request)
                expires_at = self._clock() + self._pending_ttl_seconds
                self._unit_reservations[unit.unit_id] = (
                    request.media_stream_id,
                    expires_at,
                )
                self._stream_units[request.media_stream_id] = unit.unit_id
                return accepted.model_dump(mode="json"), None
        except (VoiceRenderRuntimeError, VoiceRenderControlError) as exc:
            return None, exc.code

    async def media_handler(
        self,
        opened: MediaOpenHeader,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Consume one valid pending render and stream verified provider PCM."""
        self._discard_expired_reservations()
        try:
            pending = self._pending.consume(opened.stream_id, opened.generation)
        except VoiceRenderControlError as exc:
            self._release_stream(opened.stream_id)
            await self._send_media_error(opened, writer, exc.code)
            return

        unit_id = self._stream_units.get(opened.stream_id)
        if unit_id is None:
            await self._send_media_error(
                opened,
                writer,
                "voice_render_sealed_unit_missing",
            )
            return

        # Once a valid media OPEN consumes the pending render, the sealed unit
        # becomes single-use even if provider setup fails.
        self._release_stream(opened.stream_id)
        try:
            unit = self.sealed_units.consume(unit_id)
            self._require_exact_recipe(unit, pending.request)
        except VoiceRenderRuntimeError as exc:
            await self._send_media_error(opened, writer, exc.code)
            return

        try:
            adapter = self._adapter_factory()
        except Exception:
            await self._send_media_error(
                opened,
                writer,
                "tts_provider_unavailable",
            )
            return

        request = pending.request
        try:
            await adapter.connect(
                expected_model_id=unit.model_id,
                expected_model_revision=request.expected_model_revision,
                enable_render_receipts=True,
            )
        except (SpeechRailRealtimeTTSError, OSError, ValueError) as exc:
            code = (
                exc.code
                if isinstance(exc, SpeechRailRealtimeTTSError)
                else "tts_provider_unavailable"
            )
            await self._send_media_error(opened, writer, code)
            with contextlib.suppress(Exception):
                await adapter.close()
            return

        tts_request = RealtimeTTSRequest.create(
            text=request.spoken_text,
            voice=request.voice_id,
            speed=float(request.speed),
            expected_voice_revision=request.expected_voice_revision,
        )
        try:
            await render_realtime_tts_to_media(
                adapter,
                tts_request,
                opened,
                reader,
                writer,
            )
        except (SpeechRailRealtimeTTSError, RealtimeTTSMediaBridgeError):
            # The bridge emits a safe media terminal when provider execution
            # fails after streaming begins.
            pass
        finally:
            with contextlib.suppress(Exception):
                await adapter.close()

    @staticmethod
    def _require_exact_recipe(
        unit: SealedSpeechUnit,
        request: VoiceRenderControlRequest,
    ) -> None:
        expected = unit.render_recipe()
        actual = request.model_dump(mode="python")
        actual.pop("schema_version", None)
        actual.pop("media_stream_id", None)
        actual.pop("generation", None)
        if actual != expected:
            raise VoiceRenderRuntimeError("voice_render_recipe_mismatch")

    def _discard_expired_reservations(self) -> None:
        now = self._clock()
        expired = [
            (unit_id, stream_id)
            for unit_id, (stream_id, expires_at)
            in self._unit_reservations.items()
            if expires_at <= now
        ]
        for unit_id, stream_id in expired:
            self._unit_reservations.pop(unit_id, None)
            self._stream_units.pop(stream_id, None)
            self._pending.discard(stream_id)

    def _release_stream(self, stream_id: str) -> None:
        unit_id = self._stream_units.pop(stream_id, None)
        if unit_id is not None:
            self._unit_reservations.pop(unit_id, None)

    @staticmethod
    async def _send_media_error(
        opened: MediaOpenHeader,
        writer: asyncio.StreamWriter,
        code: str,
    ) -> None:
        header = MediaErrorHeader(
            stream_id=opened.stream_id,
            generation=opened.generation,
            code=code[:128] or "voice_render_failed",
            message="The sealed voice render could not be completed.",
            retryable=False,
        )
        with contextlib.suppress(ConnectionError, OSError):
            await write_media_frame(writer, header)
