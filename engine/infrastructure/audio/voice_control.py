"""Strict Engine-side control primitives for one sealed voice render.

The authoritative wire schema is contracts/protocol/voice_render_control.schema.json
(PR #99). This module deliberately stays below Domain orchestration: callers must
prove that the referenced speech unit is committed/sealed before registration.

No media ticket, hidden identity, display text, prompt/context or reference audio
is retained here.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator


class VoiceRenderControlError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VoiceRenderControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    speech_unit_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    story_revision: StrictInt = Field(ge=0)
    narrative_block_id: str = Field(min_length=1, max_length=128)
    segment_index: StrictInt = Field(ge=0)
    performance_plan_id: str = Field(min_length=1, max_length=128)
    spoken_text: str = Field(min_length=1, max_length=4096)
    voice_id: str = Field(min_length=1, max_length=128)
    expected_voice_revision: str = Field(min_length=1, max_length=128)
    expected_model_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    media_stream_id: str = Field(min_length=1, max_length=128)
    generation: StrictInt = Field(ge=0)
    speed: StrictFloat = Field(ge=0.25, le=4.0)
    language: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def reject_blank_execution_fields(self) -> "VoiceRenderControlRequest":
        for value in (
            self.speech_unit_id,
            self.turn_id,
            self.narrative_block_id,
            self.performance_plan_id,
            self.spoken_text,
            self.voice_id,
            self.expected_voice_revision,
            self.media_stream_id,
        ):
            if not value.strip():
                raise ValueError("voice render execution fields must not be blank")
        if self.language is not None and not self.language.strip():
            raise ValueError("voice render language must not be blank")
        return self

    def provider_tts_fields(self) -> dict[str, object]:
        return {
            "text": self.spoken_text,
            "voice": self.voice_id,
            "speed": float(self.speed),
            "expected_voice_revision": self.expected_voice_revision,
        }


class VoiceRenderAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    render_id: str = Field(min_length=1, max_length=128)
    speech_unit_id: str = Field(min_length=1, max_length=128)
    media_stream_id: str = Field(min_length=1, max_length=128)
    generation: StrictInt = Field(ge=0)
    state: str = Field(pattern=r"^accepted$")


@dataclass(frozen=True, slots=True)
class PendingVoiceRender:
    render_id: str
    request: VoiceRenderControlRequest
    expires_at: float


class PendingVoiceRenderRegistry:
    """Bounded one-time association between control request and media grant."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        ttl_seconds: float = 10.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1 or ttl_seconds <= 0 or ttl_seconds > 30:
            raise ValueError("invalid pending voice render registry limits")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock or time.monotonic
        self._entries: dict[str, PendingVoiceRender] = {}

    def register(
        self,
        value: VoiceRenderControlRequest | Mapping[str, object],
    ) -> VoiceRenderAccepted:
        request = value if isinstance(value, VoiceRenderControlRequest) else VoiceRenderControlRequest.model_validate(value)
        now = self._clock()
        self._discard_expired(now)
        if request.media_stream_id in self._entries:
            raise VoiceRenderControlError("voice_render_stream_already_registered")
        if len(self._entries) >= self._max_entries:
            raise VoiceRenderControlError("voice_render_registry_capacity")

        render_id = f"render_{secrets.token_hex(12)}"
        self._entries[request.media_stream_id] = PendingVoiceRender(
            render_id=render_id,
            request=request,
            expires_at=now + self._ttl_seconds,
        )
        return VoiceRenderAccepted(
            schema_version="1.0",
            render_id=render_id,
            speech_unit_id=request.speech_unit_id,
            media_stream_id=request.media_stream_id,
            generation=request.generation,
            state="accepted",
        )

    def consume(self, media_stream_id: str, generation: int) -> PendingVoiceRender:
        if not media_stream_id or generation < 0:
            raise VoiceRenderControlError("voice_render_invalid_identity")
        self._discard_expired(self._clock())
        pending = self._entries.pop(media_stream_id, None)
        if pending is None:
            raise VoiceRenderControlError("voice_render_not_found")
        if pending.request.generation != generation:
            raise VoiceRenderControlError("voice_render_generation_mismatch")
        return pending

    def discard(self, media_stream_id: str) -> None:
        self._entries.pop(media_stream_id, None)

    def _discard_expired(self, now: float) -> None:
        expired = [
            stream_id
            for stream_id, pending in self._entries.items()
            if pending.expires_at <= now
        ]
        for stream_id in expired:
            self._entries.pop(stream_id, None)

    def __len__(self) -> int:
        self._discard_expired(self._clock())
        return len(self._entries)
