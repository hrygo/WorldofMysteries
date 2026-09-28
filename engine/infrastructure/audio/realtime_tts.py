"""SpeechRail Realtime 4.0.0 incremental TTS protocol state machine.

This module owns protocol correctness, request correlation and streamed PCM
integrity.  It deliberately does not own a WebSocket implementation or device
playback: a transport is injected, and each validated PCM chunk is handed to
an async sink (normally the Engine MediaBridge).

Wire shape, pinned by ``fixtures/speechrail_contract``:

* one ``session.update`` with nested ``audio.input`` and an explicit
  ``speechrail.task``; no flat ``input_audio_format``, no ``render_receipts``;
* one ``speechrail.tts.start`` per utterance, then zero-based
  ``speechrail.tts.append_text`` segments, then ``speechrail.tts.finish_text``;
* exactly one terminal: ``completed``, ``cancelled`` or ``failed``;
* the render receipt is read over REST after a successful terminal.

Backpressure is deliberate: the sink is awaited inline, so a slow media peer
stalls the provider reader rather than buffering unbounded PCM.  Cancellation
therefore arrives on a different task (see ``media_bridge``) and wakes the
credit waiters instead of racing this loop.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

from .config import AudioProviderConfig
from .media_protocol import MEDIA_MAX_PAYLOAD_BYTES
from .render_receipts import (
    RenderReceiptError,
    RenderReceiptReader,
    create_render_receipt_reader,
)


REALTIME_TTS_SAMPLE_RATE = 24_000
REALTIME_TTS_CHANNELS = 1
REALTIME_TTS_BYTES_PER_FRAME = 2
REALTIME_WIRE_TASK = "render"

# The wire revision is a bounded tag, not a git object id.  A 40-character hex
# commit stays valid; ``rev-2026-09-27.a`` does too.
WIRE_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# The service proves what it handed to the transport.  It never proves what a
# speaker played, so this boundary must not be renamed into a delivery claim.
RECEIPT_INTEGRITY_BOUNDARY = "pcm16_after_transport_send"
RECEIPT_ID = re.compile(r"^rr_[0-9a-f]{32}$")

_DEFAULT_MAX_APPEND_CODEPOINTS = 512
_DEFAULT_MAX_PENDING_CODEPOINTS = 1024
_DEFAULT_MAX_TOTAL_CODEPOINTS = 8192
_TERMINAL_DEADLINE_SECONDS = 20.0
_HANDSHAKE_DEADLINE_SECONDS = 15.0

RealtimeTTSStatus = Literal["completed", "failed", "cancelled"]
RealtimeTTSPhase = Literal[
    "disconnected",
    "connecting",
    "ready",
    "starting",
    "streaming",
    "finishing",
    "verifying_receipt",
    "cancelling",
    "completed",
    "cancelled",
    "failed",
    "closed",
]

# Codepoints that must not start a new append segment: breaking between a base
# character and its combining mark, ZWJ continuation or variation selector
# would preserve the characters but split a grapheme cluster.
_CONTINUATION_CODEPOINTS = frozenset(
    [0xFE0E, 0xFE0F, 0x200D]
    + list(range(0x0300, 0x0370))
    + list(range(0x1AB0, 0x1AC0))
    + list(range(0x1DC0, 0x1E00))
    + list(range(0x20D0, 0x2100))
    + list(range(0xFE20, 0xFE30))
)


class SpeechRailRealtimeTTSError(RuntimeError):
    """The current-only TTS stream violated or failed its public contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@runtime_checkable
class RealtimeTTSTransport(Protocol):
    """Minimal JSON WebSocket port used by the protocol state machine."""

    async def open(self, url: str, headers: Mapping[str, str]) -> None: ...

    async def send_json(self, payload: Mapping[str, object]) -> None: ...

    async def receive_json(self) -> Mapping[str, object]: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RealtimeTTSRequest:
    """One sealed utterance submitted as a single application call."""

    text: str
    voice: str
    request_id: str
    speed: float = 1.0
    expected_voice_revision: str | None = None
    expected_model_revision: str | None = None

    @classmethod
    def create(
        cls,
        *,
        text: str,
        voice: str,
        speed: float = 1.0,
        expected_voice_revision: str | None = None,
        expected_model_revision: str | None = None,
    ) -> "RealtimeTTSRequest":
        return cls(
            text=text,
            voice=voice,
            request_id=f"wom-tts-{uuid4().hex}",
            speed=speed,
            expected_voice_revision=expected_voice_revision,
            expected_model_revision=expected_model_revision,
        )

    def validate(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise SpeechRailRealtimeTTSError("tts_request_invalid")
        if not self.text.strip() or len(self.text) > 4096:
            raise SpeechRailRealtimeTTSError("tts_request_invalid")
        if not self.voice.strip() or len(self.voice) > 128:
            raise SpeechRailRealtimeTTSError("tts_request_invalid")
        if isinstance(self.speed, bool) or not math.isfinite(self.speed):
            raise SpeechRailRealtimeTTSError("tts_request_invalid")
        if not 0.25 <= self.speed <= 4.0:
            raise SpeechRailRealtimeTTSError("tts_request_invalid")
        for revision in (
            self.expected_voice_revision,
            self.expected_model_revision,
        ):
            if revision is not None and not WIRE_REVISION.fullmatch(revision):
                raise SpeechRailRealtimeTTSError("tts_request_invalid")


@dataclass(frozen=True, slots=True)
class RealtimeTTSChunk:
    """One validated PCM chunk, correlated by task and plan rather than item."""

    task_id: str
    plan_id: str
    request_id: str
    sequence: int
    chunk_index: int
    offset_frames: int
    frame_count: int
    pcm16: bytes
    sample_rate: int = REALTIME_TTS_SAMPLE_RATE
    channels: int = REALTIME_TTS_CHANNELS


@dataclass(frozen=True, slots=True)
class RealtimeTTSTerminal:
    """The single terminal of one utterance."""

    request_id: str
    task_id: str
    plan_id: str
    status: RealtimeTTSStatus
    total_frames: int
    total_bytes: int
    pcm_sha256: str
    voice_revision: str | None
    receipt_id: str | None


@dataclass(frozen=True, slots=True)
class _TextLimits:
    max_append: int
    max_pending: int
    max_total: int

    @classmethod
    def from_event(cls, value: object) -> "_TextLimits":
        if not isinstance(value, Mapping):
            return cls(
                max_append=_DEFAULT_MAX_APPEND_CODEPOINTS,
                max_pending=_DEFAULT_MAX_PENDING_CODEPOINTS,
                max_total=_DEFAULT_MAX_TOTAL_CODEPOINTS,
            )

        def _positive(name: str, default: int) -> int:
            raw = value.get(name)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
                return default
            return raw

        return cls(
            max_append=_positive(
                "max_append_codepoints", _DEFAULT_MAX_APPEND_CODEPOINTS
            ),
            max_pending=_positive(
                "max_pending_codepoints", _DEFAULT_MAX_PENDING_CODEPOINTS
            ),
            max_total=_positive(
                "max_total_codepoints", _DEFAULT_MAX_TOTAL_CODEPOINTS
            ),
        )

    @property
    def segment(self) -> int:
        return max(1, min(self.max_append, self.max_pending))


RealtimeTTSChunkSink = Callable[[RealtimeTTSChunk], Awaitable[None]]


def _required_string(value: object, *, code: str = "realtime_invalid_envelope") -> str:
    if not isinstance(value, str) or not value:
        raise SpeechRailRealtimeTTSError(code)
    return value


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _event_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def split_text_segments(text: str, limit: int) -> list[str]:
    """Split sealed text into append segments without altering any codepoint.

    The text arrives already committed and sealed; this only chooses where to
    cut it.  A cut is never placed between a base codepoint and a following
    combining mark, ZWJ or variation selector.
    """
    if limit < 1:
        raise ValueError("segment limit must be positive")
    segments: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + limit, length)
        if end < length:
            # Pull the cut back over a trailing continuation run so the cluster
            # stays with its base character.
            while end > start + 1 and ord(text[end - 1]) in _CONTINUATION_CODEPOINTS:
                end -= 1
        if end == start:
            # The whole window is continuation codepoints; emit one codepoint
            # rather than looping forever.  The content is preserved.
            end = start + 1
        segments.append(text[start:end])
        start = end
    return segments


def _realtime_url(config: AudioProviderConfig) -> str:
    parsed = urlsplit(config.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")
    if parsed.query:
        raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")

    host = parsed.hostname.lower()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and not loopback:
        raise SpeechRailRealtimeTTSError("realtime_insecure_remote_endpoint")

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    # The key travels in the Authorization header; the query carries only the
    # requested ASR alias.
    query = urlencode({"model": config.asr_model})
    return urlunsplit((ws_scheme, parsed.netloc, f"{path}/realtime", query, ""))


class SpeechRailRealtimeTTSAdapter:
    """One SpeechRail current-only Realtime connection.

    One TTS utterance may be active at a time, matching the SpeechRail 4.x
    contract.  Provider cancellation is intentionally separate from local
    device stop; callers must invalidate/stop local playback before awaiting
    cancel.
    """

    def __init__(
        self,
        config: AudioProviderConfig,
        transport: RealtimeTTSTransport,
        *,
        receipt_reader: RenderReceiptReader | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._receipt_reader = receipt_reader or create_render_receipt_reader(config)
        self._phase: RealtimeTTSPhase = "disconnected"
        self._session_id: str | None = None
        self._last_sequence: int | None = None
        self._active_request_id: str | None = None
        self._active_task_id: str | None = None
        self._active_plan_id: str | None = None
        self._expected_model_id: str | None = None
        self._expected_model_revision: str | None = None
        self._require_receipt = True

    @property
    def ready(self) -> bool:
        return self._phase == "ready"

    @property
    def phase(self) -> RealtimeTTSPhase:
        return self._phase

    # -- connection ---------------------------------------------------------

    async def connect(
        self,
        *,
        expected_model_id: str | None = None,
        expected_model_revision: str | None = None,
        require_render_receipt: bool = True,
    ) -> None:
        if self._phase not in {"disconnected", "closed"}:
            raise SpeechRailRealtimeTTSError("realtime_invalid_state")
        if expected_model_id is not None and (
            not isinstance(expected_model_id, str)
            or not expected_model_id.strip()
            or len(expected_model_id) > 256
            or "\x00" in expected_model_id
        ):
            raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")
        if expected_model_revision is not None and not WIRE_REVISION.fullmatch(
            expected_model_revision
        ):
            raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")

        self._phase = "connecting"
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        try:
            try:
                await asyncio.wait_for(
                    self._transport.open(_realtime_url(self._config), headers),
                    timeout=_HANDSHAKE_DEADLINE_SECONDS,
                )
                created = await asyncio.wait_for(
                    self._receive(), timeout=_HANDSHAKE_DEADLINE_SECONDS
                )
            except TimeoutError as exc:
                # A silent or mismatched peer must not park the Engine.
                raise SpeechRailRealtimeTTSError("realtime_handshake_timeout") from exc
            if created["type"] != "session.created":
                raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")

            await self._transport.send_json({
                "type": "session.update",
                "event_id": _event_id("wom-tts-session"),
                "session": {
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {
                                "type": "audio/pcm",
                                "rate": REALTIME_TTS_SAMPLE_RATE,
                            },
                            "transcription": {"model": self._config.asr_model},
                            "turn_detection": None,
                        }
                    },
                    "speechrail": {
                        "task": REALTIME_WIRE_TASK,
                        "tts": {"enabled": True},
                        "alignment": {"enabled": False},
                        "diarization": {"enabled": False},
                    },
                },
            })
            try:
                updated = await asyncio.wait_for(
                    self._receive(), timeout=_HANDSHAKE_DEADLINE_SECONDS
                )
            except TimeoutError as exc:
                raise SpeechRailRealtimeTTSError("realtime_handshake_timeout") from exc
            if updated["type"] != "session.updated":
                raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")
            self._verify_effective_session(updated)

            self._expected_model_id = expected_model_id
            self._expected_model_revision = expected_model_revision
            self._require_receipt = require_render_receipt
            self._phase = "ready"
        except BaseException:
            await self._reset_and_close()
            raise

    def _verify_effective_session(self, event: Mapping[str, object]) -> None:
        session = _optional_mapping(event.get("session"))
        if session is None:
            raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")
        audio = _optional_mapping(session.get("audio"))
        audio_input = _optional_mapping(audio.get("input")) if audio else None
        if audio_input is None:
            raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")
        wire_format = _optional_mapping(audio_input.get("format"))
        if (
            wire_format is None
            or wire_format.get("type") != "audio/pcm"
            or wire_format.get("rate") != REALTIME_TTS_SAMPLE_RATE
        ):
            raise SpeechRailRealtimeTTSError("realtime_unsupported_audio_format")
        extension = _optional_mapping(session.get("speechrail"))
        tts = _optional_mapping(extension.get("tts")) if extension else None
        if tts is None or tts.get("enabled") is not True:
            raise SpeechRailRealtimeTTSError("tts_not_enabled")

    async def close(self) -> None:
        await self._reset_and_close()

    async def cancel_active(self) -> None:
        request_id = self._active_request_id
        if request_id is None or self._phase in {
            "disconnected",
            "closed",
            "completed",
            "cancelled",
            "failed",
        }:
            raise SpeechRailRealtimeTTSError("tts_not_active")
        self._phase = "cancelling"
        await self._transport.send_json({
            "type": "speechrail.tts.cancel",
            "event_id": _event_id("wom-tts-cancel"),
            "request_id": request_id,
        })

    # -- rendering ----------------------------------------------------------

    async def render(
        self,
        request: RealtimeTTSRequest,
        on_chunk: RealtimeTTSChunkSink,
    ) -> RealtimeTTSTerminal:
        # The concurrency guard is checked first: while an utterance is
        # streaming the phase has already left "ready", and reporting a
        # connection failure there would hide the real cause.
        if self._active_request_id is not None:
            raise SpeechRailRealtimeTTSError("tts_in_progress")
        if self._phase != "ready":
            raise SpeechRailRealtimeTTSError("realtime_not_connected")
        request.validate()

        self._active_request_id = request.request_id
        self._active_task_id = None
        self._active_plan_id = None
        self._phase = "starting"

        hasher = hashlib.sha256()
        total_frames = 0
        total_bytes = 0
        next_chunk_index = 0
        limits = _TextLimits.from_event(None)
        segments: list[str] = []
        last_acked: int | None = None
        finish_sent = False
        voice_revision: str | None = None

        try:
            start_message: dict[str, object] = {
                "type": "speechrail.tts.start",
                "event_id": _event_id("wom-tts-start"),
                "request_id": request.request_id,
                "task": REALTIME_WIRE_TASK,
                "voice": request.voice,
                "speed": request.speed,
            }
            if request.expected_voice_revision is not None:
                start_message["voice_revision"] = request.expected_voice_revision
            model_revision = (
                request.expected_model_revision or self._expected_model_revision
            )
            if model_revision is not None:
                start_message["expected_model_revision"] = model_revision
            await self._transport.send_json(start_message)

            while True:
                try:
                    event = await asyncio.wait_for(
                        self._receive(), timeout=_TERMINAL_DEADLINE_SECONDS
                    )
                except TimeoutError as exc:
                    self._phase = "failed"
                    raise SpeechRailRealtimeTTSError("realtime_terminal_timeout") from exc
                kind = str(event["type"])

                if kind == "error":
                    raise self._error_for(event, request.request_id)

                if kind == "speechrail.tts.started":
                    self._require_request(event, request.request_id)
                    self._active_task_id = _required_string(event.get("task_id"))
                    self._active_plan_id = _required_string(event.get("plan_id"))
                    voice_revision = _optional_str(event.get("voice_revision"))
                    self._verify_output_format(event.get("output_format"))
                    limits = _TextLimits.from_event(event.get("limits"))
                    if len(request.text) > limits.max_total:
                        raise SpeechRailRealtimeTTSError("tts_request_invalid")
                    segments = split_text_segments(request.text, limits.segment)
                    self._phase = "streaming"
                    await self._send_append(request.request_id, segments[0], 0)
                    continue

                if kind == "speechrail.tts.text_accepted":
                    self._require_task(event)
                    append_sequence = event.get("append_sequence")
                    if (
                        isinstance(append_sequence, bool)
                        or not isinstance(append_sequence, int)
                        or append_sequence < 0
                    ):
                        raise SpeechRailRealtimeTTSError("tts_sequence_invalid")
                    expected_append = 0 if last_acked is None else last_acked + 1
                    if append_sequence != expected_append:
                        raise SpeechRailRealtimeTTSError("tts_sequence_invalid")
                    if append_sequence >= len(segments):
                        raise SpeechRailRealtimeTTSError("tts_sequence_invalid")
                    accepted = event.get("accepted_codepoints")
                    if (
                        isinstance(accepted, bool)
                        or not isinstance(accepted, int)
                        or accepted != len(segments[append_sequence])
                    ):
                        raise SpeechRailRealtimeTTSError("tts_sequence_invalid")
                    last_acked = append_sequence
                    if append_sequence + 1 < len(segments):
                        await self._send_append(
                            request.request_id,
                            segments[append_sequence + 1],
                            append_sequence + 1,
                        )
                    else:
                        self._phase = "finishing"
                        finish_sent = True
                        await self._transport.send_json({
                            "type": "speechrail.tts.finish_text",
                            "event_id": _event_id("wom-tts-finish"),
                            "request_id": request.request_id,
                            "last_sequence": append_sequence,
                        })
                    continue

                if kind == "speechrail.tts.audio.delta":
                    self._require_task(event)
                    chunk_index = event.get("chunk_index")
                    if (
                        isinstance(chunk_index, bool)
                        or not isinstance(chunk_index, int)
                        or chunk_index != next_chunk_index
                    ):
                        raise SpeechRailRealtimeTTSError("realtime_invalid_audio")
                    sample_offset = event.get("sample_offset")
                    if (
                        isinstance(sample_offset, bool)
                        or not isinstance(sample_offset, int)
                        or sample_offset != total_frames
                    ):
                        raise SpeechRailRealtimeTTSError("realtime_invalid_audio")
                    pcm = self._decode_pcm_delta(event.get("delta"))
                    frame_count = len(pcm) // REALTIME_TTS_BYTES_PER_FRAME
                    await on_chunk(RealtimeTTSChunk(
                        task_id=self._active_task_id or "",
                        plan_id=self._active_plan_id or "",
                        request_id=request.request_id,
                        sequence=int(event["sequence"]),
                        chunk_index=chunk_index,
                        offset_frames=total_frames,
                        frame_count=frame_count,
                        pcm16=pcm,
                    ))
                    total_frames += frame_count
                    total_bytes += len(pcm)
                    hasher.update(pcm)
                    next_chunk_index += 1
                    continue

                if kind == "speechrail.tts.completed":
                    self._require_task(event)
                    if not finish_sent:
                        raise SpeechRailRealtimeTTSError("realtime_incomplete_response")
                    generated = event.get("generated_samples")
                    if (
                        isinstance(generated, bool)
                        or not isinstance(generated, int)
                        or generated != total_frames
                        or total_frames <= 0
                    ):
                        raise SpeechRailRealtimeTTSError("realtime_incomplete_audio")
                    digest = hasher.hexdigest()
                    self._phase = "verifying_receipt"
                    receipt_id = await self._verify_receipt(
                        request=request,
                        total_frames=total_frames,
                        digest=digest,
                    )
                    self._phase = "completed"
                    return RealtimeTTSTerminal(
                        request_id=request.request_id,
                        task_id=self._active_task_id or "",
                        plan_id=self._active_plan_id or "",
                        status="completed",
                        total_frames=total_frames,
                        total_bytes=total_bytes,
                        pcm_sha256=digest,
                        voice_revision=voice_revision,
                        receipt_id=receipt_id,
                    )

                if kind == "speechrail.tts.cancelled":
                    self._require_task(event)
                    self._phase = "cancelled"
                    return RealtimeTTSTerminal(
                        request_id=request.request_id,
                        task_id=self._active_task_id or "",
                        plan_id=self._active_plan_id or "",
                        status="cancelled",
                        total_frames=total_frames,
                        total_bytes=total_bytes,
                        pcm_sha256=hasher.hexdigest(),
                        voice_revision=voice_revision,
                        receipt_id=None,
                    )

                if kind == "speechrail.tts.failed":
                    self._require_task(event)
                    error = _optional_mapping(event.get("error"))
                    code = _required_string(
                        error.get("code") if error else None,
                        code="tts_backend_failed",
                    )
                    self._phase = "failed"
                    raise SpeechRailRealtimeTTSError(code)

                # ASR facts and disabled auxiliary events may share the
                # session; they must not be mistaken for a TTS lifecycle event.
                if kind.startswith("speechrail.tts."):
                    raise SpeechRailRealtimeTTSError("realtime_unsupported_tts_event")
        finally:
            self._active_request_id = None
            self._active_task_id = None
            self._active_plan_id = None

    async def _send_append(self, request_id: str, text: str, sequence: int) -> None:
        await self._transport.send_json({
            "type": "speechrail.tts.append_text",
            "event_id": _event_id("wom-tts-append"),
            "request_id": request_id,
            "sequence": sequence,
            "text": text,
        })

    def _require_request(self, event: Mapping[str, object], request_id: str) -> None:
        event_request = _optional_str(event.get("request_id"))
        if event_request is not None and event_request != request_id:
            raise SpeechRailRealtimeTTSError("realtime_response_mismatch")

    def _require_task(
        self, event: Mapping[str, object], request_id: str | None = None
    ) -> None:
        self._require_request(event, request_id or self._active_request_id or "")
        task_id = _optional_str(event.get("task_id"))
        if self._active_task_id is not None and task_id != self._active_task_id:
            raise SpeechRailRealtimeTTSError("realtime_response_mismatch")

    @staticmethod
    def _verify_output_format(value: object) -> None:
        wire_format = _optional_mapping(value)
        if (
            wire_format is None
            or wire_format.get("type") != "audio/pcm"
            or wire_format.get("sample_rate") != REALTIME_TTS_SAMPLE_RATE
            or wire_format.get("channels") != REALTIME_TTS_CHANNELS
        ):
            raise SpeechRailRealtimeTTSError("realtime_unsupported_audio_format")

    @staticmethod
    def _error_for(
        event: Mapping[str, object], request_id: str
    ) -> SpeechRailRealtimeTTSError:
        """Correlate one error envelope without parsing its free-text message."""
        envelope_request = _optional_str(event.get("request_id"))
        error = _optional_mapping(event.get("error"))
        error_request = _optional_str(error.get("request_id")) if error else None
        rejected_event = _optional_str(error.get("event_id")) if error else None
        if (
            envelope_request is not None
            and envelope_request not in {request_id, rejected_event}
        ):
            raise SpeechRailRealtimeTTSError("realtime_response_mismatch")
        code = _required_string(
            error.get("code") if error else None, code="server_error"
        )
        return SpeechRailRealtimeTTSError(code)

    async def _verify_receipt(
        self,
        *,
        request: RealtimeTTSRequest,
        total_frames: int,
        digest: str,
    ) -> str | None:
        if not self._require_receipt:
            return None
        try:
            receipt = await self._receipt_reader.read_by_request(request.request_id)
        except RenderReceiptError as exc:
            raise SpeechRailRealtimeTTSError(exc.code) from exc
        return self._check_receipt(
            receipt,
            request=request,
            total_frames=total_frames,
            digest=digest,
        )

    def _check_receipt(
        self,
        receipt: Mapping[str, object],
        *,
        request: RealtimeTTSRequest,
        total_frames: int,
        digest: str,
    ) -> str:
        receipt_id = _required_string(
            receipt.get("receipt_id"), code="render_receipt_invalid"
        )
        if not RECEIPT_ID.fullmatch(receipt_id):
            raise SpeechRailRealtimeTTSError("render_receipt_invalid")
        if receipt.get("request_id") not in {None, request.request_id}:
            raise SpeechRailRealtimeTTSError("render_receipt_mismatch")
        if receipt.get("status") != "completed":
            raise SpeechRailRealtimeTTSError("render_receipt_incomplete")

        voice = _optional_mapping(receipt.get("voice"))
        if request.expected_voice_revision is not None:
            if (
                voice is None
                or voice.get("id") != request.voice
                or voice.get("revision") != request.expected_voice_revision
            ):
                raise SpeechRailRealtimeTTSError("render_receipt_voice_mismatch")

        model = _optional_mapping(receipt.get("model"))
        if self._expected_model_id is not None and (
            model is None or model.get("source_model") != self._expected_model_id
        ):
            raise SpeechRailRealtimeTTSError("render_receipt_model_id_mismatch")
        expected_model_revision = (
            request.expected_model_revision or self._expected_model_revision
        )
        if expected_model_revision is not None and (
            model is None or model.get("catalog_revision") != expected_model_revision
        ):
            raise SpeechRailRealtimeTTSError("render_receipt_model_mismatch")

        audio = _optional_mapping(receipt.get("audio"))
        if audio is None:
            raise SpeechRailRealtimeTTSError("render_receipt_invalid")
        if (
            audio.get("format") != "pcm16"
            or audio.get("pcm_sample_rate") != REALTIME_TTS_SAMPLE_RATE
            or audio.get("channels") != REALTIME_TTS_CHANNELS
            or audio.get("integrity_boundary") != RECEIPT_INTEGRITY_BOUNDARY
            or audio.get("sample_count") != total_frames
            or audio.get("pcm_sha256") != digest
        ):
            raise SpeechRailRealtimeTTSError("render_receipt_mismatch")
        return receipt_id

    # -- transport ----------------------------------------------------------

    async def _receive(self) -> dict[str, object]:
        raw = await self._transport.receive_json()
        event = dict(raw)
        event_type = _required_string(event.get("type"))
        event_id = _required_string(event.get("event_id"))
        session_id = _required_string(event.get("session_id"))
        sequence = event.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise SpeechRailRealtimeTTSError("realtime_invalid_envelope")
        if self._last_sequence is None:
            # The wire schema floors the sequence at 0 while the pinned service
            # starts at 1; accept either first value, then demand continuity.
            if sequence not in {0, 1}:
                raise SpeechRailRealtimeTTSError("realtime_sequence_gap")
        elif sequence != self._last_sequence + 1:
            raise SpeechRailRealtimeTTSError("realtime_sequence_gap")
        if self._session_id is None:
            self._session_id = session_id
        elif self._session_id != session_id:
            raise SpeechRailRealtimeTTSError("realtime_session_mismatch")
        self._last_sequence = sequence
        event["type"] = event_type
        event["event_id"] = event_id
        event["session_id"] = session_id
        event["sequence"] = sequence
        return event

    @staticmethod
    def _decode_pcm_delta(value: object) -> bytes:
        if not isinstance(value, str) or not value:
            raise SpeechRailRealtimeTTSError("realtime_invalid_audio")
        try:
            pcm = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise SpeechRailRealtimeTTSError("realtime_invalid_audio") from None
        if (
            not pcm
            or len(pcm) % REALTIME_TTS_BYTES_PER_FRAME != 0
            or len(pcm) > MEDIA_MAX_PAYLOAD_BYTES
        ):
            raise SpeechRailRealtimeTTSError("realtime_invalid_audio")
        return pcm

    async def _reset_and_close(self) -> None:
        self._phase = "closed"
        self._session_id = None
        self._last_sequence = None
        self._active_request_id = None
        self._active_task_id = None
        self._active_plan_id = None
        self._expected_model_id = None
        self._expected_model_revision = None
        try:
            await self._transport.close()
        except Exception:
            pass


def create_realtime_tts_adapter(
    config: AudioProviderConfig | None = None,
    transport: RealtimeTTSTransport | None = None,
    *,
    receipt_reader: RenderReceiptReader | None = None,
) -> SpeechRailRealtimeTTSAdapter:
    """Create the production current-only SpeechRail Realtime TTS adapter."""
    resolved = config or AudioProviderConfig.from_env()
    if transport is None:
        from .websocket_transport import StdlibJSONWebSocketTransport

        transport = StdlibJSONWebSocketTransport(timeout_seconds=resolved.timeout_seconds)
    return SpeechRailRealtimeTTSAdapter(
        resolved, transport, receipt_reader=receipt_reader
    )


__all__ = [
    "REALTIME_TTS_BYTES_PER_FRAME",
    "REALTIME_TTS_CHANNELS",
    "REALTIME_TTS_SAMPLE_RATE",
    "REALTIME_WIRE_TASK",
    "RECEIPT_INTEGRITY_BOUNDARY",
    "WIRE_REVISION",
    "RealtimeTTSChunk",
    "RealtimeTTSChunkSink",
    "RealtimeTTSPhase",
    "RealtimeTTSRequest",
    "RealtimeTTSStatus",
    "RealtimeTTSTerminal",
    "RealtimeTTSTransport",
    "SpeechRailRealtimeTTSAdapter",
    "SpeechRailRealtimeTTSError",
    "create_realtime_tts_adapter",
    "split_text_segments",
]
