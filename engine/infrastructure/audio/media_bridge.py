"""Bridge verified SpeechRail Realtime TTS PCM into the W-V01 media stream.

This module owns media-plane delivery only.  It does not choose text, voices,
performance, or Domain state.  The caller supplies an already-authorized
``RealtimeTTSRequest`` and an authenticated ``MediaOpenHeader``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from dataclasses import dataclass
from typing import Literal

from .media_protocol import (
    MediaCancelHeader,
    MediaCancelReason,
    MediaChunkHeader,
    MediaCreditHeader,
    MediaCreditWindow,
    MediaEndHeader,
    MediaErrorHeader,
    MediaOpenHeader,
    MediaProtocolError,
    read_media_frame,
    write_media_frame,
)
from .realtime_tts import (
    REALTIME_TTS_SAMPLE_RATE,
    RealtimeTTSChunk,
    RealtimeTTSRequest,
    RealtimeTTSTerminal,
    SpeechRailRealtimeTTSAdapter,
    SpeechRailRealtimeTTSError,
)


MediaPeerStopKind = Literal["cancel", "error", "disconnected"]


class RealtimeTTSMediaBridgeError(RuntimeError):
    """Provider/media composition failed before a valid media END."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class MediaPeerStop:
    kind: MediaPeerStopKind
    code: str | None = None
    reason: str | None = None


class EngineRealtimeTTSMediaStream:
    """One authenticated Engine -> App W-V01 media stream.

    Provider PCM may arrive in chunks larger than the negotiated media grant;
    this class re-chunks it while preserving sample continuity.  CREDIT is
    consumed before every write and replenished only from peer CREDIT frames.
    """

    def __init__(
        self,
        opened: MediaOpenHeader,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if (
            opened.direction != "engine_to_app"
            or opened.format.codec != "pcm_s16le"
            or opened.format.sample_rate != REALTIME_TTS_SAMPLE_RATE
            or opened.format.channels != 1
        ):
            raise RealtimeTTSMediaBridgeError("media_bridge_invalid_open")
        self._opened = opened
        self._reader = reader
        self._writer = writer
        self._credit = MediaCreditWindow(opened.initial_credit_bytes)
        self._credit_changed = asyncio.Condition()
        self._peer_stop = asyncio.Event()
        self._peer_stop_value: MediaPeerStop | None = None
        self._control_task: asyncio.Task[None] | None = None
        self._sequence = 0
        self._offset_frames = 0
        self._total_bytes = 0
        self._digest = hashlib.sha256()
        self._provider_offset_frames = 0
        self._terminal_sent = False
        self._closed = False

    @property
    def total_frames(self) -> int:
        return self._offset_frames

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def pcm_sha256(self) -> str:
        return self._digest.hexdigest()

    async def start(self) -> None:
        if self._control_task is not None or self._closed:
            raise RealtimeTTSMediaBridgeError("media_bridge_invalid_state")
        self._control_task = asyncio.create_task(self._receive_control())

    async def push(self, chunk: RealtimeTTSChunk) -> None:
        if self._closed or self._terminal_sent:
            raise RealtimeTTSMediaBridgeError("media_bridge_terminal")
        if self._control_task is None:
            raise RealtimeTTSMediaBridgeError("media_bridge_not_started")
        if (
            chunk.sample_rate != REALTIME_TTS_SAMPLE_RATE
            or chunk.channels != 1
            or chunk.frame_count <= 0
            or len(chunk.pcm16) != chunk.frame_count * 2
            or chunk.offset_frames != self._provider_offset_frames
        ):
            raise RealtimeTTSMediaBridgeError("media_bridge_invalid_chunk")

        self._provider_offset_frames += chunk.frame_count
        maximum = self._opened.max_payload_bytes
        start = 0
        while start < len(chunk.pcm16):
            end = min(start + maximum, len(chunk.pcm16))
            # W-V01 payload limits are even; keep this defensive if the contract changes.
            if (end - start) % 2:
                end -= 1
            if end <= start:
                raise RealtimeTTSMediaBridgeError("media_bridge_invalid_chunk")
            payload = chunk.pcm16[start:end]
            await self._reserve_credit(len(payload))
            header = MediaChunkHeader(
                stream_id=self._opened.stream_id,
                generation=self._opened.generation,
                sequence=self._sequence,
                offset_frames=self._offset_frames,
                frame_count=len(payload) // 2,
                payload_bytes=len(payload),
            )
            try:
                await write_media_frame(self._writer, header, payload)
            except (ConnectionError, OSError) as exc:
                raise RealtimeTTSMediaBridgeError("media_bridge_disconnected") from exc
            self._sequence += 1
            self._offset_frames += header.frame_count
            self._total_bytes += len(payload)
            self._digest.update(payload)
            start = end

    async def finish_completed(self, terminal: RealtimeTTSTerminal) -> None:
        if self._terminal_sent or self._closed:
            raise RealtimeTTSMediaBridgeError("media_bridge_terminal")
        self._raise_if_peer_stopped()
        if (
            terminal.status != "completed"
            or terminal.total_frames != self._offset_frames
            or terminal.total_bytes != self._total_bytes
            or terminal.pcm_sha256 != self._digest.hexdigest()
        ):
            raise RealtimeTTSMediaBridgeError("media_bridge_terminal_mismatch")
        header = MediaEndHeader(
            stream_id=self._opened.stream_id,
            generation=self._opened.generation,
            total_frames=self._offset_frames,
            total_bytes=self._total_bytes,
            sha256=self._digest.hexdigest(),
        )
        try:
            await write_media_frame(self._writer, header)
        except (ConnectionError, OSError) as exc:
            raise RealtimeTTSMediaBridgeError("media_bridge_disconnected") from exc
        self._terminal_sent = True

    async def send_cancel(self, reason: MediaCancelReason = "superseded") -> None:
        if self._terminal_sent or self._closed or self._peer_stop.is_set():
            return
        header = MediaCancelHeader(
            stream_id=self._opened.stream_id,
            generation=self._opened.generation,
            reason=reason,
        )
        with contextlib.suppress(ConnectionError, OSError):
            await write_media_frame(self._writer, header)
        self._terminal_sent = True

    async def send_error(self, code: str) -> None:
        if self._terminal_sent or self._closed or self._peer_stop.is_set():
            return
        safe_code = code[:128] or "tts_failed"
        header = MediaErrorHeader(
            stream_id=self._opened.stream_id,
            generation=self._opened.generation,
            code=safe_code,
            message="The TTS media stream failed.",
            retryable=False,
        )
        with contextlib.suppress(ConnectionError, OSError):
            await write_media_frame(self._writer, header)
        self._terminal_sent = True

    @property
    def peer_stopped(self) -> bool:
        return self._peer_stop.is_set()

    async def wait_peer_stop(self) -> MediaPeerStop:
        await self._peer_stop.wait()
        assert self._peer_stop_value is not None
        return self._peer_stop_value

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        task = self._control_task
        self._control_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        async with self._credit_changed:
            self._credit_changed.notify_all()

    async def _reserve_credit(self, payload_bytes: int) -> None:
        async with self._credit_changed:
            while self._credit.available_bytes < payload_bytes:
                self._raise_if_peer_stopped()
                if self._closed:
                    raise RealtimeTTSMediaBridgeError("media_bridge_disconnected")
                await self._credit_changed.wait()
            self._raise_if_peer_stopped()
            try:
                self._credit.consume(payload_bytes)
            except MediaProtocolError as exc:
                raise RealtimeTTSMediaBridgeError(exc.code) from exc

    async def _receive_control(self) -> None:
        try:
            while not self._closed and not self._terminal_sent:
                header, payload = await read_media_frame(self._reader)
                if payload:
                    raise RealtimeTTSMediaBridgeError("media_control_payload_forbidden")
                if isinstance(header, MediaCreditHeader):
                    self._require_identity(header.stream_id, header.generation)
                    async with self._credit_changed:
                        try:
                            self._credit.grant(header.credit_bytes)
                        except MediaProtocolError as exc:
                            raise RealtimeTTSMediaBridgeError(exc.code) from exc
                        self._credit_changed.notify_all()
                    continue
                if isinstance(header, MediaCancelHeader):
                    self._require_identity(header.stream_id, header.generation)
                    await self._record_peer_stop(
                        MediaPeerStop(kind="cancel", reason=header.reason)
                    )
                    return
                if isinstance(header, MediaErrorHeader):
                    self._require_identity(header.stream_id, header.generation)
                    await self._record_peer_stop(
                        MediaPeerStop(kind="error", code=header.code)
                    )
                    return
                raise RealtimeTTSMediaBridgeError("media_bridge_invalid_control")
        except asyncio.CancelledError:
            raise
        except RealtimeTTSMediaBridgeError as exc:
            await self._record_peer_stop(MediaPeerStop(kind="error", code=exc.code))
        except (MediaProtocolError, EOFError, ConnectionError, OSError) as exc:
            code = exc.code if isinstance(exc, MediaProtocolError) else None
            await self._record_peer_stop(MediaPeerStop(kind="disconnected", code=code))

    async def _record_peer_stop(self, stop: MediaPeerStop) -> None:
        if self._peer_stop.is_set():
            return
        self._peer_stop_value = stop
        self._peer_stop.set()
        async with self._credit_changed:
            self._credit_changed.notify_all()

    def _raise_if_peer_stopped(self) -> None:
        if self._peer_stop_value is None:
            return
        if self._peer_stop_value.kind == "cancel":
            raise RealtimeTTSMediaBridgeError("media_peer_cancelled")
        if self._peer_stop_value.kind == "error" and self._peer_stop_value.code:
            raise RealtimeTTSMediaBridgeError(self._peer_stop_value.code)
        raise RealtimeTTSMediaBridgeError("media_bridge_disconnected")

    def _require_identity(self, stream_id: str, generation: int) -> None:
        if stream_id != self._opened.stream_id or generation != self._opened.generation:
            raise RealtimeTTSMediaBridgeError("media_stream_identity_mismatch")


async def render_realtime_tts_to_media(
    adapter: SpeechRailRealtimeTTSAdapter,
    request: RealtimeTTSRequest,
    opened: MediaOpenHeader,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> RealtimeTTSTerminal:
    """Render one sealed TTS request into one authenticated media stream.

    A peer CANCEL never waits behind PCM backpressure: the control reader is a
    separate task and triggers provider cancellation.  Media END is emitted only
    after the provider terminal has already been validated as completed.
    """

    stream = EngineRealtimeTTSMediaStream(opened, reader, writer)
    await stream.start()
    peer_task = asyncio.create_task(stream.wait_peer_stop())

    async def deliver_chunk(chunk: RealtimeTTSChunk) -> None:
        # Keep the provider reader alive long enough to send and observe
        # speechrail.tts.cancel.  A media peer stop wakes credit waiters; that
        # wake-up must not make adapter.render unwind and clear its active
        # request before the provider cancel control event is sent.
        if stream.peer_stopped:
            return
        try:
            await stream.push(chunk)
        except RealtimeTTSMediaBridgeError:
            if stream.peer_stopped:
                return
            raise

    render_task = asyncio.create_task(adapter.render(request, deliver_chunk))
    try:
        done, _ = await asyncio.wait(
            {render_task, peer_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if peer_task in done:
            stop = await peer_task
            if not render_task.done():
                with contextlib.suppress(SpeechRailRealtimeTTSError):
                    await adapter.cancel_active()
            if not render_task.done():
                try:
                    return await render_task
                except RealtimeTTSMediaBridgeError:
                    raise
            return await render_task

        terminal = await render_task
        if terminal.status == "completed":
            await stream.finish_completed(terminal)
        elif terminal.status == "cancelled":
            await stream.send_cancel("superseded")
        else:
            await stream.send_error("tts_provider_failed")
        return terminal
    except SpeechRailRealtimeTTSError as exc:
        await stream.send_error(exc.code)
        raise
    except RealtimeTTSMediaBridgeError:
        if not render_task.done():
            with contextlib.suppress(SpeechRailRealtimeTTSError):
                await adapter.cancel_active()
        raise
    finally:
        peer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await peer_task
        if not render_task.done():
            render_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await render_task
        await stream.close()
