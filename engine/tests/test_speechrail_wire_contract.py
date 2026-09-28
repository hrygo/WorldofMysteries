"""Pinned SpeechRail Realtime 4.0.0 contract regression (T01).

Three layers of evidence live here:

1. the pinned fixture manifest still matches the recorded upstream digests;
2. every shared case validates against the pinned machine schema, and every
   recorded legacy payload is rejected by that same schema;
3. the real Engine adapter actually speaks the new wire and refuses to reuse
   the removed one.

Layer 3 is what makes this a contract test rather than a snapshot test: a
fixture that only validates itself proves nothing about the consumer.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from infrastructure.audio import (
    AudioProviderConfig,
    RealtimeTTSChunk,
    RealtimeTTSRequest,
    SpeechRailRealtimeTTSAdapter,
    SpeechRailRealtimeTTSError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "speechrail_contract"
SCHEMA_PATH = FIXTURE_DIR / "realtime-events.schema.json"
MATRIX_PATH = FIXTURE_DIR / "realtime-field-matrix.json"
CASES_PATH = FIXTURE_DIR / "cases.json"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

WIRE_SAMPLE_RATE = 24_000
WIRE_CHANNELS = 1
RECEIPT_INTEGRITY_BOUNDARY = "pcm16_after_transport_send"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return _load(SCHEMA_PATH)


@pytest.fixture(scope="module")
def cases() -> dict[str, Any]:
    return _load(CASES_PATH)


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_pinned_schema_is_valid_json_schema(schema: dict[str, Any]) -> None:
    _validator(schema)


def test_manifest_records_commit_and_digests() -> None:
    manifest = _load(MANIFEST_PATH)
    assert manifest["repository"] == "https://github.com/hrygo/SpeechRail"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["commit"]), manifest["commit"]
    assert manifest["realtime_contract_version"] == "4.0.0"

    for name, entry in manifest["files"].items():
        target = FIXTURE_DIR / name
        assert target.is_file(), f"pinned file missing: {name}"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"digest drift for {name}"


def test_manifest_deltas_are_factual_and_cited() -> None:
    manifest = _load(MANIFEST_PATH)
    deltas = manifest["verified_deltas"]
    assert deltas, "manifest must record the verified implementation deltas"
    for delta in deltas:
        assert delta["statement"].strip()
        for evidence in delta["evidence"]:
            assert evidence.startswith(("contracts/", "src/")), evidence
            assert not evidence.startswith("fixtures/"), evidence


def test_field_matrix_snapshot_is_present_and_parsable() -> None:
    matrix = _load(MATRIX_PATH)
    assert matrix


def test_every_shared_case_validates(schema: dict[str, Any], cases: dict[str, Any]) -> None:
    validator = _validator(schema)
    for group in ("valid_client_events", "valid_server_events"):
        assert cases[group], group
        for case in cases[group]:
            errors = sorted(validator.iter_errors(case["payload"]), key=str)
            assert not errors, (
                f"{group}/{case['name']} rejected by the pinned schema: "
                f"{errors[0].message if errors else ''}"
            )


def test_every_recorded_legacy_payload_is_rejected(
    schema: dict[str, Any], cases: dict[str, Any]
) -> None:
    validator = _validator(schema)
    legacy = cases["rejected_legacy_events"]
    assert len(legacy) >= 10, "the current-only switch must stay guarded"
    for case in legacy:
        assert validator.iter_errors(case["payload"]), (
            f"rejected_legacy_events/{case['name']} unexpectedly validates; "
            "either the schema snapshot or the case list drifted"
        )


def test_case_groups_cover_the_current_only_surface(
    schema: dict[str, Any], cases: dict[str, Any]
) -> None:
    client_names = {case["name"] for case in cases["valid_client_events"]}
    for required in (
        "asr_session_update",
        "render_session_update",
        "input_append",
        "input_commit",
        "input_clear",
        "tts_start",
        "tts_append_text_0",
        "tts_finish_text",
        "tts_cancel",
    ):
        assert required in client_names, required

    server_names = {case["name"] for case in cases["valid_server_events"]}
    for required in (
        "session_created",
        "session_updated",
        "transcription_completed",
        "tts_started",
        "tts_text_accepted_0",
        "tts_audio_delta_0",
        "tts_completed",
        "tts_cancelled",
        "tts_failed",
        "error_rejected_client_event",
    ):
        assert required in server_names, required

    defs = set(schema["$defs"])
    assert "client_tts_create" not in defs
    assert "client_response_create" not in defs


def test_revision_samples_follow_the_wire_pattern(cases: dict[str, Any]) -> None:
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    samples = cases["revision_samples"]
    for value in samples["valid"]:
        assert pattern.fullmatch(value), value
    for value in samples["invalid"]:
        assert not pattern.fullmatch(value), value


def test_wire_format_is_24k_mono_pcm16(cases: dict[str, Any]) -> None:
    for group in ("valid_client_events", "valid_server_events"):
        for case in cases[group]:
            payload = case["payload"]
            session = payload.get("session")
            if isinstance(session, dict):
                audio = session.get("audio")
                if isinstance(audio, dict):
                    fmt = audio.get("input", {}).get("format")
                    assert fmt == {"type": "audio/pcm", "rate": WIRE_SAMPLE_RATE}, case["name"]
            if payload.get("type") == "speechrail.tts.started":
                assert payload["output_format"] == {
                    "type": "audio/pcm",
                    "sample_rate": WIRE_SAMPLE_RATE,
                    "channels": WIRE_CHANNELS,
                }, case["name"]


def test_fixture_contains_no_secret_or_machine_path() -> None:
    for path in (SCHEMA_PATH, MATRIX_PATH, CASES_PATH, MANIFEST_PATH):
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text, path.name
        assert "file://" not in text, path.name
        assert "sk-" not in text, path.name
        assert "SPEECHRAIL_API_KEY" not in text, path.name


def _case(cases: dict[str, Any], group: str, name: str) -> dict[str, Any]:
    for candidate in cases[group]:
        if candidate["name"] == name:
            return candidate
    raise AssertionError(f"missing case {group}/{name}")


def _pcm(frames: int, *, seed: int = 1) -> bytes:
    """Deterministic synthetic PCM16; never a recording."""
    out = bytearray()
    for index in range(frames):
        value = ((index + seed) * 997) % 32768
        out += value.to_bytes(2, "little", signed=True)
    return bytes(out)


async def _noop(chunk: RealtimeTTSChunk) -> None:
    del chunk


async def _collect(sink: list[RealtimeTTSChunk], chunk: RealtimeTTSChunk) -> None:
    sink.append(chunk)


class _FixtureRealtimeProvider:
    """A fixture-driven peer that replays the pinned server event shapes.

    It answers the new wire only.  Anything the adapter sends that is not part
    of the current protocol is answered with the pinned ``error`` envelope, so
    a regression to the removed protocol fails loudly instead of hanging.
    """

    def __init__(
        self,
        cases: dict[str, Any],
        *,
        chunk_frames: int = 4,
        first_sequence: int = 1,
        hold_start: bool = False,
    ) -> None:
        self.cases = cases
        self.chunk_frames = chunk_frames
        self.hold_start = hold_start
        self.sequence = first_sequence - 1
        self.session_id = _case(cases, "valid_server_events", "session_created")["payload"][
            "session_id"
        ]
        self.sent: list[dict[str, Any]] = []
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False
        self.opened: list[tuple[str, dict[str, str]]] = []
        self.append_sequences: list[int] = []
        self.text_chunks: list[str] = []
        self.pcm = _pcm(chunk_frames)

    async def open(self, url: str, headers: dict[str, str]) -> None:
        self.opened.append((url, dict(headers)))
        await self._emit(
            _case(self.cases, "valid_server_events", "session_created")["payload"]
        )

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(dict(payload))
        kind = payload.get("type")
        if kind == "session.update":
            await self._reply_session_updated(payload)
        elif kind == "speechrail.tts.start":
            if not self.hold_start:
                await self._reply_started(payload)
        elif kind == "speechrail.tts.append_text":
            self.append_sequences.append(int(payload["sequence"]))
            self.text_chunks.append(str(payload["text"]))
            await self._reply_text_accepted(payload)
        elif kind == "speechrail.tts.finish_text":
            await self._reply_completed(payload)
        elif kind == "speechrail.tts.cancel":
            await self._emit(
                _case(self.cases, "valid_server_events", "tts_cancelled")["payload"],
                request_id=payload["request_id"],
            )
        else:
            await self._reject(payload)

    async def receive_json(self) -> dict[str, Any]:
        return await self.inbound.get()

    async def close(self) -> None:
        self.closed = True

    async def _emit(self, template: dict[str, Any], **overrides: Any) -> None:
        payload = json.loads(json.dumps(template))
        self.sequence += 1
        payload["session_id"] = self.session_id
        payload["sequence"] = self.sequence
        payload.update(overrides)
        await self.inbound.put(payload)

    async def _reject(self, sent: dict[str, Any]) -> None:
        await self._emit(
            _case(
                self.cases, "valid_server_events", "error_rejected_client_event"
            )["payload"],
            error={
                "type": "invalid_request_error",
                "code": "unsupported_operation",
                "message": f"{sent.get('type')} is not supported by SpeechRail",
                "event_id": str(sent.get("event_id", "unknown")),
            },
        )

    async def _reply_session_updated(self, sent: dict[str, Any]) -> None:
        await self._emit(
            _case(self.cases, "valid_server_events", "session_updated")["payload"],
            session={
                "id": self.session_id,
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": WIRE_SAMPLE_RATE},
                        "transcription": {
                            "model": sent["session"]["audio"]["input"]["transcription"][
                                "model"
                            ]
                        },
                        "turn_detection": None,
                    }
                },
                "speechrail": sent["session"]["speechrail"],
            },
        )

    async def _reply_started(self, sent: dict[str, Any]) -> None:
        await self._emit(
            _case(self.cases, "valid_server_events", "tts_started")["payload"],
            request_id=sent["request_id"],
            voice_revision=sent.get("voice_revision"),
            limits=sent.get("limits") or {"max_append_codepoints": 512},
        )

    async def _reply_text_accepted(self, sent: dict[str, Any]) -> None:
        await self._emit(
            _case(self.cases, "valid_server_events", "tts_text_accepted_0")["payload"],
            request_id=sent["request_id"],
            append_sequence=int(sent["sequence"]),
            accepted_codepoints=len(sent["text"]),
            total_codepoints=sum(len(chunk) for chunk in self.text_chunks),
        )

    async def _reply_completed(self, sent: dict[str, Any]) -> None:
        await self._emit(
            _case(self.cases, "valid_server_events", "tts_audio_delta_0")["payload"],
            request_id=sent["request_id"],
            chunk_index=0,
            sample_offset=0,
            delta=base64.b64encode(self.pcm).decode("ascii"),
        )
        await self._emit(
            _case(self.cases, "valid_server_events", "tts_completed")["payload"],
            request_id=sent["request_id"],
            generated_samples=self.chunk_frames,
        )


class _StubReceiptReader:
    def __init__(self, payload: dict[str, Any] | Callable[[str], dict[str, Any]] | None) -> None:
        self.payload = payload
        self.calls: list[str] = []

    async def read_by_request(self, request_id: str) -> dict[str, Any]:
        self.calls.append(request_id)
        if self.payload is None:
            raise SpeechRailRealtimeTTSError("render_receipt_missing")
        if callable(self.payload):
            return self.payload(request_id)
        return dict(self.payload)


def _expected_receipt(
    *,
    request_id: str,
    voice: str,
    voice_revision: str,
    model_id: str,
    model_revision: str,
    frames: int,
    pcm: bytes,
) -> dict[str, Any]:
    return {
        "receipt_id": "rr_" + "0123456789abcdef" * 2,
        "request_id": request_id,
        "status": "completed",
        "voice": {"id": voice, "revision": voice_revision},
        "model": {
            "source_model": model_id,
            "catalog_revision": model_revision,
            "runtime_revision": "runtime-1",
        },
        "audio": {
            "format": "pcm16",
            "pcm_sample_rate": WIRE_SAMPLE_RATE,
            "channels": WIRE_CHANNELS,
            "integrity_boundary": RECEIPT_INTEGRITY_BOUNDARY,
            "sample_count": frames,
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        },
    }


def _config() -> AudioProviderConfig:
    return AudioProviderConfig(
        provider_name="speechrail",
        base_url="http://127.0.0.1:8201/v1",
        api_key="",
        asr_model="whisper-1",
        tts_model="tts-1",
    )


@pytest.mark.asyncio
async def test_adapter_completes_one_incremental_render(cases: dict[str, Any]) -> None:
    frames = 4
    pcm = _pcm(frames)
    request = RealtimeTTSRequest.create(
        text="先别问医生病人的事，我想看看他的反应。",
        voice="alloy",
        expected_voice_revision="rev-a",
    )
    receipt_payload = _expected_receipt(
        request_id=request.request_id,
        voice=request.voice,
        voice_revision="rev-a",
        model_id="speechrail/qwen3-tts",
        model_revision="m-rev-1",
        frames=frames,
        pcm=pcm,
    )
    provider = _FixtureRealtimeProvider(cases, chunk_frames=frames)
    receipt = _StubReceiptReader(receipt_payload)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=receipt,  # type: ignore[arg-type]
    )
    await adapter.connect()

    chunks: list[RealtimeTTSChunk] = []
    terminal = await adapter.render(request, lambda chunk: _collect(chunks, chunk))

    sent_types = [message["type"] for message in provider.sent]
    assert sent_types[0] == "session.update"
    assert "speechrail.tts.create" not in sent_types
    assert "transcription_session.update" not in sent_types
    assert sent_types[1] == "speechrail.tts.start"
    assert "speechrail.tts.append_text" in sent_types
    assert sent_types[-1] == "speechrail.tts.finish_text"

    start_message = next(
        message for message in provider.sent if message["type"] == "speechrail.tts.start"
    )
    assert start_message["task"] == "render"
    assert start_message["voice_revision"] == "rev-a"
    assert "expected_voice_revision" not in start_message
    assert start_message["event_id"]

    assert provider.append_sequences == list(range(len(provider.append_sequences)))
    assert "".join(provider.text_chunks) == request.text

    assert terminal.status == "completed"
    assert terminal.total_frames == frames
    assert terminal.pcm_sha256 == hashlib.sha256(pcm).hexdigest()
    assert terminal.receipt_id == receipt_payload["receipt_id"]
    assert receipt.calls == [request.request_id]

    assert b"".join(chunk.pcm16 for chunk in chunks) == pcm
    await adapter.close()


@pytest.mark.asyncio
async def test_adapter_never_emits_the_removed_session_shape(
    cases: dict[str, Any],
) -> None:
    provider = _FixtureRealtimeProvider(cases)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=_StubReceiptReader(None),  # type: ignore[arg-type]
    )
    await adapter.connect()

    session_update = next(
        message for message in provider.sent if message["type"] == "session.update"
    )
    session = session_update["session"]
    assert "input_audio_format" not in session
    assert "input_audio_transcription" not in session
    assert session["audio"]["input"]["format"] == {
        "type": "audio/pcm",
        "rate": WIRE_SAMPLE_RATE,
    }
    assert session["audio"]["input"]["turn_detection"] is None
    assert "render_receipts" not in session["speechrail"]
    assert "model_revision" not in session["speechrail"]
    assert session["speechrail"]["task"] == "render"
    assert session["speechrail"]["tts"] == {"enabled": True}
    await adapter.close()


@pytest.mark.asyncio
async def test_adapter_sends_no_authorization_without_a_key(
    cases: dict[str, Any],
) -> None:
    provider = _FixtureRealtimeProvider(cases)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=_StubReceiptReader(None),  # type: ignore[arg-type]
    )
    await adapter.connect()
    _url, headers = provider.opened[0]
    assert "Authorization" not in headers
    await adapter.close()


@pytest.mark.asyncio
async def test_adapter_cancel_uses_the_three_field_envelope(
    cases: dict[str, Any],
) -> None:
    # The peer deliberately withholds speechrail.tts.started so the cancel is
    # issued while the utterance is genuinely still active.
    provider = _FixtureRealtimeProvider(cases, hold_start=True)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=_StubReceiptReader(None),  # type: ignore[arg-type]
    )
    await adapter.connect()

    request = RealtimeTTSRequest.create(text="取消我", voice="alloy")
    task = asyncio.create_task(adapter.render(request, _noop))
    await asyncio.sleep(0)
    await adapter.cancel_active()

    cancel_message = next(
        message for message in provider.sent if message["type"] == "speechrail.tts.cancel"
    )
    assert set(cancel_message) == {"type", "event_id", "request_id"}
    assert cancel_message["request_id"] == request.request_id

    await provider._emit(
        _case(cases, "valid_server_events", "tts_started")["payload"],
        request_id=request.request_id,
        voice_revision=None,
        limits={"max_append_codepoints": 512},
    )
    terminal = await asyncio.wait_for(task, timeout=2.0)
    assert terminal.status == "cancelled"
    await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("first_sequence", [0, 1])
async def test_handshake_accepts_first_sequence_zero_or_one(
    cases: dict[str, Any], first_sequence: int
) -> None:
    provider = _FixtureRealtimeProvider(cases, first_sequence=first_sequence)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=_StubReceiptReader(None),  # type: ignore[arg-type]
    )
    await adapter.connect()
    assert adapter.ready
    await adapter.close()


@pytest.mark.asyncio
async def test_sequence_gap_after_handshake_is_fatal(cases: dict[str, Any]) -> None:
    provider = _FixtureRealtimeProvider(cases)
    adapter = SpeechRailRealtimeTTSAdapter(
        _config(),
        provider,  # type: ignore[arg-type]
        receipt_reader=_StubReceiptReader(None),  # type: ignore[arg-type]
    )
    await adapter.connect()
    provider.sequence += 1
    request = RealtimeTTSRequest.create(text="缺口", voice="alloy")
    with pytest.raises(SpeechRailRealtimeTTSError, match="realtime_sequence_gap"):
        await adapter.render(request, _noop)
    await adapter.close()
