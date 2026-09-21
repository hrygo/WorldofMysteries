"""SpeechRail 3.x current-only Realtime TTS protocol state machine.

This module owns protocol correctness, response correlation and streamed PCM
integrity.  It deliberately does not own a WebSocket implementation or device
playback: a transport is injected, and each validated PCM chunk is handed to an
async sink (normally the Engine MediaBridge).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

from .config import AudioProviderConfig
from .media_protocol import MEDIA_MAX_PAYLOAD_BYTES


REALTIME_TTS_SAMPLE_RATE = 24_000
REALTIME_TTS_CHANNELS = 1
REALTIME_TTS_BYTES_PER_FRAME = 2

RealtimeTTSStatus = Literal["completed", "failed", "cancelled"]


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
    text: str
    voice: str
    request_id: str
    speed: float = 1.0
    expected_voice_revision: str | None = None

    @classmethod
    def create(
        cls,
        *,
        text: str,
        voice: str,
        speed: float = 1.0,
        expected_voice_revision: str | None = None,
    ) -> "RealtimeTTSRequest":
        return cls(
            text=text,
            voice=voice,
            request_id=f"wom-tts-{uuid4().hex}",
            speed=speed,
            expected_voice_revision=expected_voice_revision,
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


@dataclass(frozen=True, slots=True)
class RealtimeTTSChunk:
    response_id: str
    item_id: str
    sequence: int
    offset_frames: int
    frame_count: int
    pcm16: bytes
    sample_rate: int = REALTIME_TTS_SAMPLE_RATE
    channels: int = REALTIME_TTS_CHANNELS


@dataclass(frozen=True, slots=True)
class RealtimeTTSTerminal:
    request_id: str
    response_id: str
    status: RealtimeTTSStatus
    total_frames: int
    total_bytes: int
    pcm_sha256: str
    voice_revision: str | None
    receipt_id: str | None


RealtimeTTSChunkSink = Callable[[RealtimeTTSChunk], Awaitable[None]]


def _required_string(value: object, *, code: str = "realtime_invalid_envelope") -> str:
    if not isinstance(value, str) or not value:
        raise SpeechRailRealtimeTTSError(code)
    return value


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


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
    query = urlencode({"model": config.asr_model})
    return urlunsplit((ws_scheme, parsed.netloc, f"{path}/realtime", query, ""))


class SpeechRailRealtimeTTSAdapter:
    """One SpeechRail current-only Realtime connection.

    One TTS response may be active at a time, matching the SpeechRail 3.x
    contract. Provider cancellation is intentionally separate from local device
    stop; callers must invalidate/stop local playback before awaiting cancel.
    """

    def __init__(
        self,
        config: AudioProviderConfig,
        transport: RealtimeTTSTransport,
    ) -> None:
        self._config = config
        self._transport = transport
        self._ready = False
        self._session_id: str | None = None
        self._last_sequence = 0
        self._active_request_id: str | None = None
        self._active_response_id: str | None = None
        self._active_item_id: str | None = None
        self._render_receipts_enabled = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def connect(
        self,
        *,
        expected_model_revision: str | None = None,
        enable_render_receipts: bool = True,
    ) -> None:
        if self._ready:
            raise SpeechRailRealtimeTTSError("realtime_invalid_state")
        if expected_model_revision is not None and (
            len(expected_model_revision) != 40
            or any(ch not in "0123456789abcdef" for ch in expected_model_revision)
        ):
            raise SpeechRailRealtimeTTSError("realtime_invalid_configuration")

        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        try:
            await self._transport.open(_realtime_url(self._config), headers)
            created = await self._receive()
            if created["type"] != "session.created":
                raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")

            speechrail: dict[str, object] = {"tts": {"enabled": True}}
            if enable_render_receipts:
                speechrail["render_receipts"] = {"enabled": True}
            if expected_model_revision is not None:
                speechrail["model_revision"] = {"expected": expected_model_revision}

            await self._transport.send_json(
                {
                    "type": "transcription_session.update",
                    "event_id": f"wom-tts-session-{uuid4().hex}",
                    "session": {
                        "type": "transcription",
                        "input_audio_format": "pcm16",
                        "input_audio_transcription": {"model": self._config.asr_model},
                        "turn_detection": None,
                        "speechrail": speechrail,
                    },
                }
            )
            updated = await self._receive()
            if updated["type"] != "transcription_session.updated":
                raise SpeechRailRealtimeTTSError("realtime_invalid_handshake")
            session = _optional_mapping(updated.get("session"))
            extension = _optional_mapping(session.get("speechrail")) if session else None
            tts = _optional_mapping(extension.get("tts")) if extension else None
            if tts is None or tts.get("enabled") is not True:
                raise SpeechRailRealtimeTTSError("tts_not_enabled")
            receipts = _optional_mapping(extension.get("render_receipts")) if extension else None
            self._render_receipts_enabled = bool(receipts and receipts.get("enabled") is True)
            if enable_render_receipts and not self._render_receipts_enabled:
                raise SpeechRailRealtimeTTSError("render_receipts_not_enabled")
            self._ready = True
        except BaseException:
            await self._reset_and_close()
            raise

    async def close(self) -> None:
        await self._reset_and_close()

    async def cancel_active(self) -> None:
        request_id = self._active_request_id
        if request_id is None:
            raise SpeechRailRealtimeTTSError("tts_not_active")
        payload: dict[str, object] = {
            "type": "speechrail.tts.cancel",
            "request_id": request_id,
        }
        if self._active_response_id is not None:
            payload["response_id"] = self._active_response_id
        await self._transport.send_json(payload)

    async def render(
        self,
        request: RealtimeTTSRequest,
        on_chunk: RealtimeTTSChunkSink,
    ) -> RealtimeTTSTerminal:
        if not self._ready:
            raise SpeechRailRealtimeTTSError("realtime_not_connected")
        if self._active_request_id is not None:
            raise SpeechRailRealtimeTTSError("tts_in_progress")
        request.validate()

        self._active_request_id = request.request_id
        self._active_response_id = None
        self._active_item_id = None
        total_frames = 0
        total_bytes = 0
        hasher = hashlib.sha256()
        audio_done = False
        response_created_seen = False

        payload: dict[str, object] = {
            "type": "speechrail.tts.create",
            "request_id": request.request_id,
            "text": request.text,
            "voice": request.voice,
            "speed": request.speed,
        }
        if request.expected_voice_revision is not None:
            payload["expected_voice_revision"] = request.expected_voice_revision

        try:
            await self._transport.send_json(payload)
            while True:
                event = await self._receive()
                event_type = str(event["type"])

                if event_type == "error":
                    error = _optional_mapping(event.get("error"))
                    code = _required_string(
                        error.get("code") if error else None, code="server_error"
                    )
                    error_request = error.get("request_id") if error else None
                    if error_request is not None and error_request != request.request_id:
                        raise SpeechRailRealtimeTTSError("realtime_response_mismatch")
                    raise SpeechRailRealtimeTTSError(code)

                if event_type == "response.created":
                    if response_created_seen:
                        raise SpeechRailRealtimeTTSError("realtime_duplicate_response")
                    response = _optional_mapping(event.get("response"))
                    response_id = _required_string(response.get("id") if response else None)
                    self._active_response_id = response_id
                    response_created_seen = True
                    continue

                if event_type == "response.output_item.added":
                    self._require_response(event)
                    item = _optional_mapping(event.get("item"))
                    item_id = _required_string(item.get("id") if item else None)
                    if self._active_item_id is not None and self._active_item_id != item_id:
                        raise SpeechRailRealtimeTTSError("realtime_item_mismatch")
                    self._active_item_id = item_id
                    continue

                if event_type in {
                    "response.content_part.added",
                    "response.content_part.done",
                    "response.output_audio_transcript.delta",
                    "response.output_audio_transcript.done",
                    "response.output_audio.done",
                }:
                    self._require_response_and_item(event)
                    if event_type == "response.output_audio.done":
                        audio_done = True
                    continue

                if event_type == "response.output_audio.delta":
                    self._require_response_and_item(event)
                    pcm = self._decode_pcm_delta(event.get("delta"))
                    frame_count = len(pcm) // REALTIME_TTS_BYTES_PER_FRAME
                    chunk = RealtimeTTSChunk(
                        response_id=self._active_response_id or "",
                        item_id=self._active_item_id or "",
                        sequence=int(event["sequence"]),
                        offset_frames=total_frames,
                        frame_count=frame_count,
                        pcm16=pcm,
                    )
                    await on_chunk(chunk)
                    total_frames += frame_count
                    total_bytes += len(pcm)
                    hasher.update(pcm)
                    continue

                if event_type == "response.output_item.done":
                    self._require_response(event)
                    item = _optional_mapping(event.get("item"))
                    item_id = _required_string(item.get("id") if item else None)
                    if self._active_item_id is None or item_id != self._active_item_id:
                        raise SpeechRailRealtimeTTSError("realtime_item_mismatch")
                    continue

                if event_type == "response.done":
                    response = _optional_mapping(event.get("response"))
                    response_id = _required_string(response.get("id") if response else None)
                    if self._active_response_id is None or response_id != self._active_response_id:
                        raise SpeechRailRealtimeTTSError("realtime_response_mismatch")
                    status = response.get("status") if response else None
                    if status not in {"completed", "failed", "cancelled"}:
                        raise SpeechRailRealtimeTTSError("realtime_invalid_terminal")
                    extension = _optional_mapping(event.get("speechrail"))
                    if extension is None or extension.get("kind") != "tts":
                        raise SpeechRailRealtimeTTSError("realtime_invalid_terminal")
                    if extension.get("request_id") != request.request_id:
                        raise SpeechRailRealtimeTTSError("realtime_response_mismatch")

                    digest = hasher.hexdigest()
                    receipt_id = None
                    if status == "completed":
                        if not response_created_seen or self._active_item_id is None:
                            raise SpeechRailRealtimeTTSError("realtime_incomplete_response")
                        if not audio_done or total_frames <= 0:
                            raise SpeechRailRealtimeTTSError("realtime_incomplete_audio")
                        receipt_id = self._validate_receipt(
                            extension.get("render_receipt"),
                            request=request,
                            response_id=response_id,
                            total_frames=total_frames,
                            digest=digest,
                        )
                    return RealtimeTTSTerminal(
                        request_id=request.request_id,
                        response_id=response_id,
                        status=status,
                        total_frames=total_frames,
                        total_bytes=total_bytes,
                        pcm_sha256=digest,
                        voice_revision=(
                            extension.get("voice_revision")
                            if isinstance(extension.get("voice_revision"), str)
                            else None
                        ),
                        receipt_id=receipt_id,
                    )

                # Current SpeechRail may add lifecycle/diagnostic events. Unknown
                # response.* events are fail-closed so a future audio wire cannot
                # be silently mistaken for this contract; unrelated ASR facts may
                # coexist on the same session and are ignored here.
                if event_type.startswith("response."):
                    raise SpeechRailRealtimeTTSError("realtime_unsupported_response_event")
        finally:
            self._active_request_id = None
            self._active_response_id = None
            self._active_item_id = None

    async def _receive(self) -> dict[str, object]:
        raw = await self._transport.receive_json()
        event = dict(raw)
        event_type = _required_string(event.get("type"))
        event_id = _required_string(event.get("event_id"))
        session_id = _required_string(event.get("session_id"))
        sequence = event.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise SpeechRailRealtimeTTSError("realtime_invalid_envelope")
        expected = self._last_sequence + 1
        if sequence != expected:
            raise SpeechRailRealtimeTTSError("realtime_sequence_gap")
        if self._session_id is None:
            self._session_id = session_id
        elif self._session_id != session_id:
            raise SpeechRailRealtimeTTSError("realtime_session_mismatch")
        self._last_sequence = sequence
        event["type"] = event_type
        event["event_id"] = event_id
        event["session_id"] = session_id
        return event

    def _require_response(self, event: Mapping[str, object]) -> None:
        response_id = _required_string(event.get("response_id"))
        if self._active_response_id is None or response_id != self._active_response_id:
            raise SpeechRailRealtimeTTSError("realtime_response_mismatch")

    def _require_response_and_item(self, event: Mapping[str, object]) -> None:
        self._require_response(event)
        item_id = _required_string(event.get("item_id"))
        if self._active_item_id is None or item_id != self._active_item_id:
            raise SpeechRailRealtimeTTSError("realtime_item_mismatch")

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

    def _validate_receipt(
        self,
        value: object,
        *,
        request: RealtimeTTSRequest,
        response_id: str,
        total_frames: int,
        digest: str,
    ) -> str | None:
        if not self._render_receipts_enabled:
            return None
        receipt = _optional_mapping(value)
        if receipt is None:
            raise SpeechRailRealtimeTTSError("render_receipt_missing")
        receipt_id = _required_string(receipt.get("receipt_id"), code="render_receipt_invalid")
        if receipt.get("status") != "completed":
            raise SpeechRailRealtimeTTSError("render_receipt_invalid")
        if receipt.get("request_id") not in {None, request.request_id}:
            raise SpeechRailRealtimeTTSError("render_receipt_mismatch")
        if receipt.get("response_id") not in {None, response_id}:
            raise SpeechRailRealtimeTTSError("render_receipt_mismatch")

        audio = _optional_mapping(receipt.get("audio"))
        if audio is None:
            raise SpeechRailRealtimeTTSError("render_receipt_invalid")
        if (
            audio.get("format") != "pcm16"
            or audio.get("pcm_sample_rate") != REALTIME_TTS_SAMPLE_RATE
            or audio.get("channels") != REALTIME_TTS_CHANNELS
            or audio.get("integrity_boundary") != "pcm16_after_websocket_send"
            or audio.get("sample_count") != total_frames
            or audio.get("pcm_sha256") != digest
        ):
            raise SpeechRailRealtimeTTSError("render_receipt_mismatch")
        return receipt_id

    async def _reset_and_close(self) -> None:
        self._ready = False
        self._session_id = None
        self._last_sequence = 0
        self._active_request_id = None
        self._active_response_id = None
        self._active_item_id = None
        self._render_receipts_enabled = False
        await self._transport.close()
