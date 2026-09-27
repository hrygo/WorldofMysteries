"""Layer-B live integration against a running SpeechRail service.

The pinned fixture and the wire regression prove the contract is *written*
correctly.  They cannot prove a running service still emits it.  This module
closes that gap: it drives a real ``/v1/realtime`` socket end to end and
checks the same invariants the fixture asserts, against observed events.

It is opt-in and never part of any gate profile.  Without ``WOM_LIVE_BASE_URL``
every test skips, so the default local run and CI stay hermetic::

    WOM_LIVE_BASE_URL=http://127.0.0.1:8201/v1 \
    WOM_LIVE_API_KEY=... \
      uv run --extra dev pytest tests/test_speechrail_live_contract.py -v

The credential is read from the environment and never written to a report.
Pass ``WOM_LIVE_REPORT=<path>`` to persist a redacted evidence record of the
observed wire vocabulary.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest

from infrastructure.audio import (
    RECEIPT_INTEGRITY_BOUNDARY,
    AudioProviderConfig,
    RealtimeTTSChunk,
    RealtimeTTSRequest,
    SpeechRailRealtimeTTSAdapter,
    StdlibJSONWebSocketTransport,
)
from infrastructure.audio.render_receipts import receipt_url

_BASE_URL = os.getenv("WOM_LIVE_BASE_URL", "").strip()
_API_KEY = os.getenv("WOM_LIVE_API_KEY", "").strip()
_REPORT = os.getenv("WOM_LIVE_REPORT", "").strip()

pytestmark = pytest.mark.skipif(
    not _BASE_URL,
    reason="WOM_LIVE_BASE_URL not set; layer-B live integration is opt-in",
)

# A short sealed utterance keeps the run bounded: the point is the contract,
# not a long-form listening sample.
_LIVE_TEXT = "塔罗会正在苏醒。"
_LIVE_VOICE = os.getenv("WOM_LIVE_VOICE", "aiden")


@pytest.fixture(scope="module")
def live_config() -> AudioProviderConfig:
    return AudioProviderConfig(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        asr_model=os.getenv("WOM_LIVE_ASR_MODEL", "whisper-1"),
    )


@pytest.fixture(scope="module")
def observed() -> dict[str, Any]:
    """Run one real render and record what the service actually emitted."""
    return asyncio.run(_run_live_render())


async def _run_live_render() -> dict[str, Any]:
    config = AudioProviderConfig(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        asr_model=os.getenv("WOM_LIVE_ASR_MODEL", "whisper-1"),
    )
    transport = StdlibJSONWebSocketTransport(timeout_seconds=60.0)
    adapter = SpeechRailRealtimeTTSAdapter(config, transport)
    chunks: list[RealtimeTTSChunk] = []

    async def sink(chunk: RealtimeTTSChunk) -> None:
        chunks.append(chunk)

    record: dict[str, Any] = {"base_url": _BASE_URL, "voice": _LIVE_VOICE}
    try:
        await adapter.connect(require_render_receipt=True)
        record["phase_after_connect"] = adapter.phase
        request = RealtimeTTSRequest.create(text=_LIVE_TEXT, voice=_LIVE_VOICE)
        terminal = await adapter.render(request, sink)
    finally:
        await adapter.close()

    record.update({
        "status": terminal.status,
        "request_id": request.request_id,
        "task_id": terminal.task_id,
        "plan_id": terminal.plan_id,
        "total_frames": terminal.total_frames,
        "total_bytes": terminal.total_bytes,
        "pcm_sha256": terminal.pcm_sha256,
        "voice_revision": terminal.voice_revision,
        "receipt_id": terminal.receipt_id,
        "chunk_count": len(chunks),
        "chunk_frame_counts": [c.frame_count for c in chunks],
        "chunk_offsets": [c.offset_frames for c in chunks],
        "single_task": len({c.task_id for c in chunks}) == 1,
        "single_plan": len({c.plan_id for c in chunks}) == 1,
    })
    return record


def _write_report(payload: dict[str, Any]) -> None:
    if not _REPORT:
        return
    path = Path(_REPORT)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Defence in depth: the record is meant to be committable.
    assert _API_KEY not in json.dumps(payload)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def test_live_service_advertises_the_pinned_capability_schema() -> None:
    """The service must still speak ``effective_capabilities_v1``."""
    request = Request(f"{_BASE_URL}/speechrail/capabilities")
    if _API_KEY:
        request.add_header("Authorization", f"Bearer {_API_KEY}")
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    assert payload["schema_version"] == "effective_capabilities_v1"
    assert payload["realtime"]["websocket_path"] == "/v1/realtime"


def test_live_handshake_reaches_ready(observed: dict[str, Any]) -> None:
    assert observed["phase_after_connect"] == "ready"


def test_live_render_completes_with_audio(observed: dict[str, Any]) -> None:
    assert observed["status"] == "completed"
    assert observed["total_frames"] > 0
    assert observed["total_bytes"] == observed["total_frames"] * 2


def test_live_chunks_are_contiguous_and_single_task(observed: dict[str, Any]) -> None:
    """``sample_offset`` must be gapless: a hole would be a silent dropout."""
    offsets = observed["chunk_offsets"]
    assert offsets == sorted(offsets)
    assert offsets[0] == 0
    assert sum(observed["chunk_frame_counts"]) == observed["total_frames"]
    assert observed["single_task"] is True
    assert observed["single_plan"] is True


def test_live_receipt_proves_transport_boundary_only(observed: dict[str, Any]) -> None:
    """The receipt is a transport fact, never a delivery fact."""
    assert observed["receipt_id"] is not None
    assert RECEIPT_INTEGRITY_BOUNDARY == "pcm16_after_transport_send"


def test_live_receipt_digest_matches_streamed_pcm(
    observed: dict[str, Any],
    live_config: AudioProviderConfig,
) -> None:
    """Re-read the receipt over REST and confirm it matches what we received."""
    request = Request(receipt_url(live_config.base_url, observed["request_id"]))
    if _API_KEY:
        request.add_header("Authorization", f"Bearer {_API_KEY}")
    with urlopen(request, timeout=30) as response:
        receipt = json.loads(response.read())
    assert receipt["receipt_id"] == observed["receipt_id"]
    assert receipt["status"] == "completed"
    audio = receipt["audio"]
    assert audio["pcm_sample_rate"] == 24_000
    assert audio["channels"] == 1
    assert audio["sample_count"] == observed["total_frames"]
    assert audio["pcm_sha256"] == observed["pcm_sha256"]
    assert audio["integrity_boundary"] == RECEIPT_INTEGRITY_BOUNDARY


def test_live_report_is_written_when_requested(observed: dict[str, Any]) -> None:
    _write_report(observed)
    if not _REPORT:
        pytest.skip("WOM_LIVE_REPORT not set")


async def _raw_session_update(session: dict[str, Any]) -> dict[str, Any]:
    """Drive the socket directly so a *malformed* session can be sent.

    The adapter pins the correct shape, so rejection can only be observed
    below its level.  A service that accepts everything would still pass every
    positive test above; these two are what make the evidence mean something.
    """
    config = AudioProviderConfig(base_url=_BASE_URL, api_key=_API_KEY)
    headers = {"Authorization": f"Bearer {_API_KEY}"} if _API_KEY else {}
    transport = StdlibJSONWebSocketTransport(timeout_seconds=30.0)
    from infrastructure.audio.realtime_tts import _realtime_url

    await transport.open(_realtime_url(config), headers)
    try:
        created = await transport.receive_json()
        assert created["type"] == "session.created"
        await transport.send_json({"type": "session.update", "session": session})
        return dict(await transport.receive_json())
    finally:
        await transport.close()


def _session(*, rate: int, task: str = "render") -> dict[str, Any]:
    return {
        "type": "transcription",
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": rate},
                "transcription": {"model": "whisper-1"},
                "turn_detection": None,
            }
        },
        "speechrail": {
            "task": task,
            "tts": {"enabled": True},
            "alignment": {"enabled": False},
            "diarization": {"enabled": False},
        },
    }


def test_live_service_rejects_non_24k_session() -> None:
    """16 kHz was valid pre-4.0; the pinned contract must refuse it."""
    reply = asyncio.run(_raw_session_update(_session(rate=16_000)))
    assert reply["type"] == "error", f"expected rejection, got {reply['type']}"


def test_live_service_accepts_the_pinned_24k_session() -> None:
    """The control for the test above: 24 kHz must be accepted."""
    reply = asyncio.run(_raw_session_update(_session(rate=24_000)))
    assert reply["type"] == "session.updated", reply
    audio_input = reply["session"]["audio"]["input"]
    assert audio_input["format"]["rate"] == 24_000
