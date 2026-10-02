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


# The evidence identity carried by render control 2.0. Kept as one tuple
# because it is one fact: which review authorised this render, and the exact
# model artifact that review heard.
EVIDENCE_PIN_FIELDS = (
    "evidence_id",
    "evidence_digest",
    "expected_model_artifact_revision",
    "expected_model_catalog_revision",
)


class VoiceRenderControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    # 1.0 is replay-only: units sealed before the evidence rollout carry no
    # evidence identity. 2.0 is the version new renders must use.
    schema_version: str = Field(pattern=r"^[12]\.0$")
    speech_unit_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    story_revision: StrictInt = Field(ge=0)
    narrative_block_id: str = Field(min_length=1, max_length=128)
    segment_index: StrictInt = Field(ge=0)
    performance_plan_id: str = Field(min_length=1, max_length=128)
    spoken_text: str = Field(min_length=1, max_length=4096)
    voice_id: str = Field(min_length=1, max_length=128)
    expected_voice_revision: str = Field(min_length=1, max_length=128)
    # Provider artifact revision, carried as a wire revision rather than a git
    # sha: a 40-character hex commit stays valid, a tagged artifact does too.
    expected_model_revision: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
    )
    # The evidence identity a human approved, plus the exact model artifact
    # that review heard. Required on 2.0, absent on 1.0.
    evidence_id: str | None = Field(default=None, min_length=1, max_length=128)
    evidence_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_model_artifact_revision: str | None = Field(
        default=None, min_length=1, max_length=128
    )
    expected_model_catalog_revision: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
    )
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

    @model_validator(mode="after")
    def require_evidence_pins_on_v2(self) -> "VoiceRenderControlRequest":
        """A 2.0 render must be attributable to a listening review.

        Each pin is required on its own: an identifier without a digest is not
        a checked reference, and a catalogue revision is not the artifact a
        human heard. Half the identity is an unattributable render, so it is
        refused rather than completed with a blank.
        """
        if self.schema_version != "2.0":
            return self
        missing = [
            name for name in EVIDENCE_PIN_FIELDS if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                "voice render control 2.0 requires evidence pins: "
                + ", ".join(missing)
            )
        for value in (self.evidence_id, self.expected_model_artifact_revision):
            if value is not None and not value.strip():
                raise ValueError("voice render evidence pins must not be blank")
        return self

    def provider_tts_fields(self) -> dict[str, object]:
        """Project this application control request onto the SpeechRail wire.

        This is the single conversion point between the Engine's application
        field names and the provider's ``speechrail.tts.start`` fields.  The
        provider renamed ``expected_voice_revision`` to ``voice_revision``; the
        rename stops here instead of propagating into the IPC contract, the
        sealed unit or the voice binding store.

        The evidence pins are deliberately *not* projected. They answer "which
        review authorised this render", which is an Engine-side attribution
        question; the provider is not asked to validate them and its request
        models forbid unknown fields. Sending them upstream would invent a
        contract that does not exist.
        """
        fields: dict[str, object] = {
            "task": "render",
            "voice": self.voice_id,
            "voice_revision": self.expected_voice_revision,
            "speed": float(self.speed),
        }
        if self.expected_model_revision is not None:
            fields["expected_model_revision"] = self.expected_model_revision
        return fields

    def provider_tts_text(self) -> str:
        """The sealed spoken text the caller owns; never rewritten here."""
        return self.spoken_text


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

    def clear(self) -> None:
        """Drop every pending association at engine shutdown."""
        self._entries.clear()

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
