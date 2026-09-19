"""Bounded binary media-channel primitives for Voice-First W-V01.

The authoritative JSON header schema lives in
contracts/protocol/engine_media.schema.json.  This module owns the Engine-side
runtime checks that JSON Schema alone cannot express: frame prefix limits,
payload/frame math, one-time grant validation, credit and stream continuity.

It deliberately does not open microphones, select speakers, call SpeechRail,
or mutate Domain state.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


MEDIA_PROTOCOL_VERSION = "1.0"
MEDIA_MAX_HEADER_BYTES = 16 * 1024
MEDIA_MAX_PAYLOAD_BYTES = 256 * 1024
MEDIA_MAX_CREDIT_BYTES = 8 * 1024 * 1024
MEDIA_PCM16_MONO_BYTES_PER_FRAME = 2
MEDIA_TICKET_HEX_LENGTH = 64

MediaDirection = Literal["app_to_engine", "engine_to_app"]
MediaCancelReason = Literal[
    "user_stop", "superseded", "session_closed", "timeout", "shutdown"
]


class MediaProtocolError(RuntimeError):
    """A media peer violated the public framing/session contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaFormat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate: Literal[16000, 24000, 48000]
    channels: Literal[1] = 1


class MediaOpenHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["open"] = "open"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    engine_epoch: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    ticket: str = Field(
        min_length=MEDIA_TICKET_HEX_LENGTH,
        max_length=MEDIA_TICKET_HEX_LENGTH,
        pattern=r"^[0-9a-f]{64}$",
        repr=False,
    )
    direction: MediaDirection
    format: MediaFormat
    max_payload_bytes: int = Field(
        ge=2, le=MEDIA_MAX_PAYLOAD_BYTES, multiple_of=2
    )
    initial_credit_bytes: int = Field(
        ge=0, le=MEDIA_MAX_CREDIT_BYTES, multiple_of=2
    )


class MediaChunkHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["chunk"] = "chunk"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    sequence: int = Field(ge=0, le=2**63 - 1)
    offset_frames: int = Field(ge=0, le=2**63 - 1)
    frame_count: int = Field(ge=1, le=131072)
    payload_bytes: int = Field(ge=2, le=MEDIA_MAX_PAYLOAD_BYTES, multiple_of=2)


class MediaCreditHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["credit"] = "credit"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    credit_bytes: int = Field(ge=2, le=MEDIA_MAX_CREDIT_BYTES, multiple_of=2)


class MediaEndHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["end"] = "end"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    total_frames: int = Field(ge=0, le=2**63 - 1)
    total_bytes: int = Field(ge=0, le=2**63 - 1, multiple_of=2)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class MediaCancelHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cancel"] = "cancel"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    reason: MediaCancelReason


class MediaErrorHeader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["error"] = "error"
    protocol_version: Literal["1.0"] = MEDIA_PROTOCOL_VERSION
    stream_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=0, le=2**63 - 1)
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(max_length=512)
    retryable: bool


MediaHeader = Annotated[
    Union[
        MediaOpenHeader,
        MediaChunkHeader,
        MediaCreditHeader,
        MediaEndHeader,
        MediaCancelHeader,
        MediaErrorHeader,
    ],
    Field(discriminator="kind"),
]
_MEDIA_HEADER_ADAPTER = TypeAdapter(MediaHeader)
_CONTROL_TYPES = (
    MediaOpenHeader,
    MediaCreditHeader,
    MediaEndHeader,
    MediaCancelHeader,
    MediaErrorHeader,
)


def parse_media_header(value: object) -> MediaHeader:
    try:
        return _MEDIA_HEADER_ADAPTER.validate_python(value)
    except ValidationError:
        raise MediaProtocolError("media_header_invalid") from None


def _validate_payload_length(header: MediaHeader, payload_length: int) -> None:
    if payload_length < 0 or payload_length > MEDIA_MAX_PAYLOAD_BYTES:
        raise MediaProtocolError("media_payload_too_large")
    if isinstance(header, _CONTROL_TYPES):
        if payload_length:
            raise MediaProtocolError("media_control_payload_forbidden")
        return
    if payload_length != header.payload_bytes:
        raise MediaProtocolError("media_payload_length_mismatch")
    if payload_length != header.frame_count * MEDIA_PCM16_MONO_BYTES_PER_FRAME:
        raise MediaProtocolError("media_frame_count_mismatch")


def encode_media_frame(header: MediaHeader, payload: bytes = b"") -> bytes:
    parsed = parse_media_header(header.model_dump(mode="json", exclude_none=True))
    _validate_payload_length(parsed, len(payload))
    header_bytes = json.dumps(
        parsed.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not header_bytes or len(header_bytes) > MEDIA_MAX_HEADER_BYTES:
        raise MediaProtocolError("media_header_too_large")
    return struct.pack(">II", len(header_bytes), len(payload)) + header_bytes + payload


async def read_media_frame(
    reader: asyncio.StreamReader,
) -> tuple[MediaHeader, bytes]:
    try:
        prefix = await reader.readexactly(8)
    except asyncio.IncompleteReadError:
        raise MediaProtocolError("media_frame_incomplete") from None

    header_length, payload_length = struct.unpack(">II", prefix)
    if header_length < 2 or header_length > MEDIA_MAX_HEADER_BYTES:
        raise MediaProtocolError("media_header_too_large")
    if payload_length > MEDIA_MAX_PAYLOAD_BYTES:
        raise MediaProtocolError("media_payload_too_large")

    try:
        header_bytes = await reader.readexactly(header_length)
    except asyncio.IncompleteReadError:
        raise MediaProtocolError("media_frame_incomplete") from None

    try:
        raw_header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MediaProtocolError("media_header_invalid") from None
    header = parse_media_header(raw_header)
    _validate_payload_length(header, payload_length)

    try:
        payload = await reader.readexactly(payload_length)
    except asyncio.IncompleteReadError:
        raise MediaProtocolError("media_frame_incomplete") from None
    return header, payload


async def write_media_frame(
    writer: asyncio.StreamWriter,
    header: MediaHeader,
    payload: bytes = b"",
) -> None:
    writer.write(encode_media_frame(header, payload))
    await writer.drain()


@dataclass(frozen=True, slots=True, repr=False)
class MediaGrant:
    """Grant metadata retained without the bearer ticket itself."""

    stream_id: str
    trace_id: str
    engine_epoch: str
    generation: int
    direction: MediaDirection
    format: MediaFormat
    max_payload_bytes: int
    initial_credit_bytes: int
    expires_at: float


class MediaGrantStore:
    """Bounded one-time media grants.

    Raw tickets are returned only to the authenticated control caller. The store
    retains SHA-256(ticket-bytes) keys so ordinary object inspection does not
    reveal a reusable bearer credential.
    """

    def __init__(
        self,
        *,
        max_entries: int = 128,
        max_ttl_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1 or max_ttl_seconds <= 0:
            raise ValueError("invalid media grant store limits")
        self._max_entries = max_entries
        self._max_ttl_seconds = max_ttl_seconds
        self._clock = clock or time.monotonic
        self._grants: dict[bytes, MediaGrant] = {}

    @staticmethod
    def _ticket_digest(ticket: str) -> bytes:
        if len(ticket) != MEDIA_TICKET_HEX_LENGTH:
            raise MediaProtocolError("media_ticket_invalid")
        try:
            raw = bytes.fromhex(ticket)
        except ValueError:
            raise MediaProtocolError("media_ticket_invalid") from None
        if len(raw) != 32:
            raise MediaProtocolError("media_ticket_invalid")
        return hashlib.sha256(raw).digest()

    def _discard_expired(self, now: float) -> None:
        expired = [
            digest for digest, grant in self._grants.items()
            if grant.expires_at <= now
        ]
        for digest in expired:
            self._grants.pop(digest, None)

    def mint(
        self,
        *,
        stream_id: str,
        trace_id: str,
        engine_epoch: str,
        generation: int,
        direction: MediaDirection,
        format: MediaFormat,
        max_payload_bytes: int = 64 * 1024,
        initial_credit_bytes: int = 256 * 1024,
        ttl_seconds: float = 10.0,
    ) -> tuple[str, MediaGrant]:
        now = self._clock()
        self._discard_expired(now)
        if not 0 < ttl_seconds <= self._max_ttl_seconds:
            raise ValueError("invalid media grant ttl")
        # Reuse the public header validator for shared bounds without minting a
        # real ticket into retained state.
        template = MediaOpenHeader(
            stream_id=stream_id,
            trace_id=trace_id,
            engine_epoch=engine_epoch,
            generation=generation,
            ticket="0" * MEDIA_TICKET_HEX_LENGTH,
            direction=direction,
            format=format,
            max_payload_bytes=max_payload_bytes,
            initial_credit_bytes=initial_credit_bytes,
        )
        if len(self._grants) >= self._max_entries:
            raise MediaProtocolError("media_grant_capacity")

        grant = MediaGrant(
            stream_id=template.stream_id,
            trace_id=template.trace_id,
            engine_epoch=template.engine_epoch,
            generation=template.generation,
            direction=template.direction,
            format=template.format,
            max_payload_bytes=template.max_payload_bytes,
            initial_credit_bytes=template.initial_credit_bytes,
            expires_at=now + ttl_seconds,
        )
        while True:
            ticket = secrets.token_hex(32)
            digest = self._ticket_digest(ticket)
            if digest not in self._grants:
                self._grants[digest] = grant
                return ticket, grant

    def consume(self, header: MediaOpenHeader) -> MediaGrant:
        digest = self._ticket_digest(header.ticket)
        grant = self._grants.pop(digest, None)
        if grant is None:
            raise MediaProtocolError("media_ticket_invalid")
        if grant.expires_at <= self._clock():
            raise MediaProtocolError("media_ticket_expired")

        expected = (
            grant.stream_id,
            grant.trace_id,
            grant.engine_epoch,
            grant.generation,
            grant.direction,
            grant.format,
            grant.max_payload_bytes,
            grant.initial_credit_bytes,
        )
        actual = (
            header.stream_id,
            header.trace_id,
            header.engine_epoch,
            header.generation,
            header.direction,
            header.format,
            header.max_payload_bytes,
            header.initial_credit_bytes,
        )
        # The ticket is burned on any mismatch, preventing iterative probing.
        if not hmac.compare_digest(repr(expected), repr(actual)):
            raise MediaProtocolError("media_grant_mismatch")
        return grant

    def __len__(self) -> int:
        self._discard_expired(self._clock())
        return len(self._grants)


class MediaCreditWindow:
    """Bounded sender-side credit in raw PCM payload bytes."""

    def __init__(self, initial_bytes: int) -> None:
        if (
            initial_bytes < 0
            or initial_bytes > MEDIA_MAX_CREDIT_BYTES
            or initial_bytes % 2
        ):
            raise ValueError("invalid initial media credit")
        self._available = initial_bytes

    @property
    def available_bytes(self) -> int:
        return self._available

    def grant(self, credit_bytes: int) -> None:
        if (
            credit_bytes <= 0
            or credit_bytes > MEDIA_MAX_CREDIT_BYTES
            or credit_bytes % 2
            or self._available + credit_bytes > MEDIA_MAX_CREDIT_BYTES
        ):
            raise MediaProtocolError("media_credit_invalid")
        self._available += credit_bytes

    def consume(self, payload_bytes: int) -> None:
        if payload_bytes <= 0 or payload_bytes % 2:
            raise MediaProtocolError("media_payload_length_invalid")
        if payload_bytes > self._available:
            raise MediaProtocolError("media_credit_exhausted")
        self._available -= payload_bytes


class MediaReceiveState:
    """Validate one opened PCM stream without retaining its payload."""

    def __init__(self, opened: MediaOpenHeader) -> None:
        self._stream_id = opened.stream_id
        self._generation = opened.generation
        self._max_payload_bytes = opened.max_payload_bytes
        self._expected_sequence = 0
        self._expected_offset_frames = 0
        self._total_bytes = 0
        self._digest = hashlib.sha256()
        self._ended = False

    @property
    def total_frames(self) -> int:
        return self._expected_offset_frames

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def accept_chunk(self, header: MediaChunkHeader, payload: bytes) -> None:
        if self._ended:
            raise MediaProtocolError("media_stream_terminal")
        if (
            header.stream_id != self._stream_id
            or header.generation != self._generation
        ):
            raise MediaProtocolError("media_stream_identity_mismatch")
        if header.sequence != self._expected_sequence:
            raise MediaProtocolError("media_chunk_sequence_mismatch")
        if header.offset_frames != self._expected_offset_frames:
            raise MediaProtocolError("media_chunk_offset_mismatch")
        if header.payload_bytes > self._max_payload_bytes:
            raise MediaProtocolError("media_payload_too_large")
        _validate_payload_length(header, len(payload))

        self._expected_sequence += 1
        self._expected_offset_frames += header.frame_count
        self._total_bytes += len(payload)
        self._digest.update(payload)

    def accept_end(self, header: MediaEndHeader) -> None:
        if self._ended:
            raise MediaProtocolError("media_stream_terminal")
        if (
            header.stream_id != self._stream_id
            or header.generation != self._generation
        ):
            raise MediaProtocolError("media_stream_identity_mismatch")
        if (
            header.total_frames != self._expected_offset_frames
            or header.total_bytes != self._total_bytes
            or header.total_bytes
            != header.total_frames * MEDIA_PCM16_MONO_BYTES_PER_FRAME
        ):
            raise MediaProtocolError("media_stream_totals_mismatch")
        if header.sha256 is not None and not hmac.compare_digest(
            header.sha256, self._digest.hexdigest()
        ):
            raise MediaProtocolError("media_stream_digest_mismatch")
        self._ended = True
