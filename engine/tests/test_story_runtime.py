"""Real product runtime: trusted content artifact, durable chain and real IPC."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket as socket_module
import sqlite3 as stdlib_sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from application.scenario_policy import ScenarioPolicyError
from application.story_initialization import (
    GOLDEN_CLUE_DISPLAY_NAMES,
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
)
from application.story_session_facade import StoryFacadeError, SubmitAdviceCommand
from contracts.envelope import EngineIPCEnvelope
from infrastructure.database_manager import DatabasePaths
from infrastructure.ipc_framing import encode_frame, read_frame, write_frame
from infrastructure.ipc_server import LocalIPCServer
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_content_repository import StoryContentError
from infrastructure.story_runtime import (
    ENGINEERING_WORLD_ID,
    StoryRuntime,
    StoryRuntimeConfig,
    load_five_turn_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME_FIXTURES = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"
# The runtime resolves the five-turn catalog from the module-relative packaged
# content, so the test emits it with the same build code the packager runs.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from build_story_content import write_episode_artifacts, write_five_turn_directory

CONTROL_SCHEMA = json.loads(
    (ROOT / "contracts" / "protocol" / "story_session_control.schema.json").read_text(
        encoding="utf-8"
    )
)
EXPRESSION_SCHEMA = json.loads(
    (
        ROOT
        / "contracts"
        / "protocol"
        / "story_expression_control.schema.json"
    ).read_text(encoding="utf-8")
)
TOKEN = "b" * 64
SYSTEM_ONLY_HEALTH = {
    "transport_ready": True,
    "world_ready": False,
    "model_ready": False,
    "voice_ready": False,
}
RUNTIME_HEALTH = dict(SYSTEM_ONLY_HEALTH, world_ready=True)
STORY_CAPABILITIES = (
    "story.advice.get",
    "story.advice.submit",
    "story.entry.get",
    "story.expression.get",
    "story.session.get",
    "story.session.open",
    "story.turn.submit",
)
_PRODUCT_LAUNCHER = (
    "import asyncio, sys\n"
    "from infrastructure.ipc_server import _run, read_bootstrap_token\n"
    "from infrastructure.sqlite_runtime import sqlite3\n"
    "from infrastructure.story_runtime import StoryRuntime, StoryRuntimeConfig\n"
    "socket_path, token_fd, data_root, content = (\n"
    "    sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]\n"
    ")\n"
    "config = StoryRuntimeConfig.for_data_root(data_root, content_path=content)\n"
    "async def loader():\n"
    "    return await StoryRuntime.open(\n"
    "        config, expected_sqlite_version=sqlite3.sqlite_version\n"
    "    )\n"
    "token = read_bootstrap_token(token_fd)\n"
    "asyncio.run(_run(socket_path, token, None, runtime_loader=loader))\n"
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_digest"}
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _bundle_payload() -> dict:
    """Mirror the frozen engineering content until the build script owns it."""
    advice = _read(FIXTURES / "turns" / "01_advice.json")
    advice["input_mode"] = "text"
    advice["raw_input"] = SUPPORTED_ADVICE
    payload = {
        "scenario_id": GOLDEN_SCENARIO_ID,
        "content_version": "1",
        "policy_version": "golden001-opening-policy",
        "seed": _read(FIXTURES / "seed.json"),
        "world": _read(FIXTURES / "world.json"),
        "character": _read(FIXTURES / "character.json"),
        "knowledge": [
            _read(path) for path in sorted((FIXTURES / "knowledge").glob("*.json"))
        ],
        "presentation": {
            "scenario_title": "不存在的预约",
            "scene_display_name": "哈维诊所 · 诊室",
            "clue_display_names": dict(GOLDEN_CLUE_DISPLAY_NAMES),
        },
        "advice_template": advice,
        "action_intent_template": _read(
            RUNTIME_FIXTURES / "mock" / "01_action_intent.json"
        ),
    }
    payload["content_digest"] = _canonical_digest(payload)
    return payload


def _write_content_artifact(path: Path) -> Path:
    payload = _bundle_payload()
    with stdlib_sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE scenario_bundles("
            "scenario_id TEXT PRIMARY KEY, content_version TEXT NOT NULL, "
            "content_digest TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO scenario_bundles VALUES (?,?,?,?)",
            (
                payload["scenario_id"],
                payload["content_version"],
                payload["content_digest"],
                json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            ),
        )
        connection.commit()
    write_five_turn_directory(path.parent, payload["seed"])
    write_episode_artifacts(path.parent)
    return path


@pytest.fixture
def content_artifact(tmp_path: Path) -> Path:
    return _write_content_artifact(tmp_path / "canon.db")


@pytest.fixture
def socket_path():
    # macOS sockaddr_un is length limited; keep the socket path short.
    with tempfile.TemporaryDirectory(prefix="wom-story-") as directory:
        yield Path(directory).resolve() / "engine.sock"


def _world_path(root: Path) -> Path:
    return DatabasePaths.for_world(root, ENGINEERING_WORLD_ID).world


async def _open_runtime(root: Path, content: Path) -> StoryRuntime:
    return await StoryRuntime.open(
        StoryRuntimeConfig.for_data_root(root, content_path=content),
        expected_sqlite_version=sqlite3.sqlite_version,
    )


@pytest.mark.asyncio
async def test_story_runtime_rejects_unknown_but_well_formed_content_digest(
    tmp_path: Path,
):
    content_artifact = _write_content_artifact(tmp_path / "canon.db")
    payload = _bundle_payload()
    payload["presentation"]["scenario_title"] = "未经注册的新内容"
    payload["content_digest"] = _canonical_digest(payload)
    with stdlib_sqlite3.connect(content_artifact) as connection:
        connection.execute(
            "UPDATE scenario_bundles SET content_digest=?, payload_json=? "
            "WHERE scenario_id=?",
            (
                payload["content_digest"],
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                GOLDEN_SCENARIO_ID,
            ),
        )
        connection.commit()

    config = StoryRuntimeConfig.for_data_root(
        tmp_path / "app-support",
        content_path=content_artifact,
    )
    with pytest.raises(ScenarioPolicyError, match="unknown_scenario_identity"):
        await StoryRuntime.open(
            config,
            expected_sqlite_version=sqlite3.sqlite_version,
        )


def _committed_delivery_case(*, narrative=None):
    from contracts import BaseRevisions, StateDelta, TurnStatus, TurnTransaction

    delta = StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-1",
            "turn_id": "turn-1",
            "outcome": "clean_success",
            "story_delta": {
                "scene_id": "consultation_room",
                "secret_state_updates": {"secret_hidden_0": "revealed"},
            },
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )
    turn = TurnTransaction(
        schema_version="1.0",
        id="turn-1",
        session_id="session-1",
        idempotency_key="input-1",
        status=TurnStatus.COMMITTED,
        base_revisions=BaseRevisions(world=1, character=1, story=0),
        state_delta_id=delta.id,
        committed_story_revision=1,
    )

    class NarrativeRepository:
        def __init__(self):
            self.turn = turn
            self.narrative = narrative
            self.load_turn_calls = 0
            self.publish_calls = 0

        async def load_turn(self, turn_id):
            assert turn_id == self.turn.id
            self.load_turn_calls += 1
            return self.turn

        async def load_narrative_block(self, narrative_block_id):
            assert self.narrative is not None
            assert narrative_block_id == self.narrative.id
            return self.narrative

        async def publish(self, *, turn_id, narrative):
            assert turn_id == self.turn.id
            assert self.narrative is None
            self.publish_calls += 1
            self.narrative = narrative
            self.turn = self.turn.model_copy(
                update={
                    "status": TurnStatus.NARRATIVE_READY,
                    "narrative_block_id": narrative.id,
                }
            )

    class FirstTurnWithNarrativeCompiler:
        def __init__(self):
            from application.narrative_publication import NarrativeCandidate

            self.candidate = NarrativeCandidate(
                narration="诊室里的雨声渐渐停了。",
                speech="我先看看预约簿。",
            )
            self.compile_calls = []

        def narrative_compiler(self, _bootstrap):
            return self

        async def compile(self, *, committed):
            self.compile_calls.append(committed)
            return self.candidate

    snapshot = SimpleNamespace(
        session=SimpleNamespace(protagonist_id="protagonist-1"),
        bootstrap=SimpleNamespace(
            presentation=SimpleNamespace(clue_display_names={})
        ),
    )
    result = SimpleNamespace(
        turn=turn,
        delta=delta,
        session=SimpleNamespace(protagonist_id="protagonist-1"),
    )
    command = SimpleNamespace(
        session_id="session-1",
        raw_input="我想看看预约簿。",
    )
    return NarrativeRepository(), FirstTurnWithNarrativeCompiler(), snapshot, result, command


@pytest.mark.asyncio
async def test_live_turn_without_voice_still_publishes_readable_narrative():
    from application.audio_disclosure import AudioDisclosureAuthorizer
    from application.story_expression import StoryExpressionQueryService
    from infrastructure.story_runtime import _DeliveryCoordinator

    repository, first_turn, snapshot, result, command = _committed_delivery_case()

    class Query:
        async def session(self, _session_id):
            return snapshot

    coordinator = _DeliveryCoordinator(
        query=Query(),
        narratives=repository,
        bindings=object(),
        voice=None,
        audio_config=None,
        voice_id=None,
        workers=first_turn,
        fetch_json=None,
    )

    delivery = await coordinator.after_commit(command, result, None)

    assert delivery.state == "unavailable"
    assert delivery.reason == "voice_not_configured"
    assert repository.narrative is not None
    assert [
        (segment.type, segment.text)
        for segment in repository.narrative.segments
    ] == [
        ("narration", "诊室里的雨声渐渐停了。"),
        ("character", "我先看看预约簿。"),
    ]
    assert repository.publish_calls == 1
    assert len(first_turn.compile_calls) == 1
    assert "secret_hidden_0" not in first_turn.compile_calls[0]

    class IdentityReader:
        async def display_name(self, *, session_id, speaker_id):
            if (session_id, speaker_id) == ("session-1", "protagonist-1"):
                return "克莱恩"
            return None

    expression = await StoryExpressionQueryService(
        reads=repository,
        disclosure=AudioDisclosureAuthorizer(repository),
        identities=IdentityReader(),
    ).get(session_id="session-1", turn_id="turn-1")
    assert expression.narrative_state == "ready"
    assert [
        (segment.type, segment.text) for segment in expression.segments
    ] == [
        ("narration", "诊室里的雨声渐渐停了。"),
        ("character", "我先看看预约簿。"),
    ]


@pytest.mark.asyncio
async def test_voice_binding_failure_keeps_already_published_narrative(monkeypatch):
    from infrastructure import story_runtime
    from infrastructure.audio.config import AudioProviderConfig
    from infrastructure.story_runtime import _DeliveryCoordinator
    from infrastructure.voice_binding_resolver import VoiceBindingResolutionError

    repository, first_turn, snapshot, result, command = _committed_delivery_case()

    class Query:
        async def session(self, _session_id):
            return snapshot

    async def fail_binding(**_kwargs):
        assert repository.narrative is not None
        assert repository.turn.narrative_block_id == repository.narrative.id
        raise VoiceBindingResolutionError("voice_binding_conflicts_with_provider")

    monkeypatch.setattr(story_runtime, "resolve_voice_runtime", fail_binding)
    coordinator = _DeliveryCoordinator(
        query=Query(),
        narratives=repository,
        bindings=object(),
        voice=object(),
        audio_config=AudioProviderConfig(),
        voice_id="klein-approved",
        workers=first_turn,
        fetch_json=None,
    )

    delivery = await coordinator.after_commit(command, result, None)

    assert delivery.state == "unavailable"
    assert delivery.reason == "voice_binding_conflicts_with_provider"
    assert repository.publish_calls == 1
    assert len(first_turn.compile_calls) == 1


@pytest.mark.asyncio
async def test_narrative_publish_failure_returns_unavailable_after_domain_commit():
    from contracts import TurnStatus
    from infrastructure.story_runtime import _DeliveryCoordinator

    repository, first_turn, snapshot, result, command = _committed_delivery_case()
    committed_turn = result.turn

    async def fail_publish(**_kwargs):
        raise RuntimeError("storage unavailable")

    repository.publish = fail_publish

    class Query:
        async def session(self, _session_id):
            return snapshot

    coordinator = _DeliveryCoordinator(
        query=Query(),
        narratives=repository,
        bindings=object(),
        voice=None,
        audio_config=None,
        voice_id=None,
        workers=first_turn,
        fetch_json=None,
    )

    delivery = await coordinator.after_commit(command, result, None)

    assert delivery.state == "unavailable"
    assert delivery.reason == "narrative_unavailable"
    assert result.turn is committed_turn
    assert repository.turn.status is TurnStatus.COMMITTED
    assert repository.turn.narrative_block_id is None


@pytest.mark.asyncio
async def test_fixed_turn_reuses_existing_narrative_without_second_publication():
    from contracts import NarrativeBlock, TurnStatus
    from contracts.models import NarrativeSegment
    from infrastructure.story_runtime import _DeliveryCoordinator

    block = NarrativeBlock(
        schema_version="1.0",
        id="narrative-fixed",
        story_session_id="session-1",
        source_story_revision=1,
        scene_id="consultation_room",
        segments=[
            NarrativeSegment(type="narration", text="固定模式的既有旁白。")
        ],
        source_state_delta_id="delta-1",
    )
    repository, _live_first_turn, snapshot, result, command = (
        _committed_delivery_case(narrative=block)
    )
    repository.turn = repository.turn.model_copy(
        update={
            "status": TurnStatus.NARRATIVE_READY,
            "narrative_block_id": block.id,
        }
    )

    class Query:
        async def session(self, _session_id):
            return snapshot

    coordinator = _DeliveryCoordinator(
        query=Query(),
        narratives=repository,
        bindings=object(),
        voice=None,
        audio_config=None,
        voice_id=None,
        workers=SimpleNamespace(narrative_compiler=lambda _bootstrap: None),
        fetch_json=None,
    )

    delivery = await coordinator.after_commit(command, result, None)

    assert delivery.state == "unavailable"
    assert delivery.reason == "voice_not_configured"
    assert repository.narrative is block
    assert repository.load_turn_calls == 1
    assert repository.publish_calls == 0


def _count_world_commits(root: Path) -> int:
    with stdlib_sqlite3.connect(
        f"file:{_world_path(root)}?mode=ro", uri=True
    ) as connection:
        return connection.execute("SELECT count(*) FROM domain_commits").fetchone()[0]


def _request(
    method: str, body: dict, request_id: str, *, idempotency_key: str | None = None
) -> dict:
    wire = {
        "kind": "request",
        "protocol_version": "1.0",
        "request_id": request_id,
        "trace_id": "trace-story",
        "method": method,
        "payload": body,
    }
    if idempotency_key is not None:
        wire["idempotency_key"] = idempotency_key
    return EngineIPCEnvelope.model_validate(wire).model_dump()


def _handshake_request(token: str) -> dict:
    return _request(
        "system.handshake",
        {
            "app_version": "0.1.0",
            "app_build": "test",
            "supported_protocols": ["1.0"],
            "session_token": token,
        },
        "req-hello",
    )


async def _handshake(reader, writer) -> dict:
    await write_frame(writer, _handshake_request(TOKEN))
    hello = await read_frame(reader)
    assert hello["status"] == "ok"
    return hello


async def _call(
    reader,
    writer,
    method: str,
    body: dict,
    request_id: str,
    *,
    idempotency_key: str | None = None,
) -> dict:
    await write_frame(
        writer, _request(method, body, request_id, idempotency_key=idempotency_key)
    )
    return await read_frame(reader)


def _validate(name: str, value: dict) -> None:
    Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": CONTROL_SCHEMA["$defs"],
            "$ref": f"#/$defs/{name}",
        }
    ).validate(value)


def _validate_expression(value: dict) -> None:
    Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": EXPRESSION_SCHEMA["$defs"],
            "$ref": "#/$defs/expression_get_response",
        }
    ).validate(value)


def _entry_body() -> dict:
    return {"schema_version": "1.0", "scenario_id": GOLDEN_SCENARIO_ID}


def _open_body(open_request_id: str, expected_store_revision: int) -> dict:
    return {
        "schema_version": "1.0",
        "scenario_id": GOLDEN_SCENARIO_ID,
        "open_request_id": open_request_id,
        "expected_store_revision": expected_store_revision,
    }


def _submit_body(
    session_id: str, input_turn_id: str, raw_input: str = SUPPORTED_ADVICE
) -> dict:
    return {
        "schema_version": "1.0",
        "session_id": session_id,
        "input_turn_id": input_turn_id,
        "raw_input": raw_input,
        "expected_story_revision": 0,
        "expected_store_revision": 1,
    }


def _advice_body(session_id: str, input_turn_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "session_id": session_id,
        "input_turn_id": input_turn_id,
    }


async def _start_server(socket: Path, runtime: StoryRuntime) -> LocalIPCServer:
    server = LocalIPCServer(
        socket,
        TOKEN,
        request_handlers=runtime.request_handlers,
        health_provider=runtime.health,
    )
    await server.start()
    return server


async def _close(server, reader, writer) -> None:
    if writer is not None:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
    if server is not None:
        await server.close()


async def _open_and_submit(runtime: StoryRuntime, socket: Path) -> tuple[str, dict]:
    server = await _start_server(socket, runtime)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket)
        await _handshake(reader, writer)
        opened = await _call(
            reader, writer, "story.session.open", _open_body("open_request_1", 0),
            "req-open", idempotency_key="open_request_1",
        )
        assert opened["status"] == "ok"
        session_id = opened["payload"]["session"]["session_id"]
        submitted = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_1"),
            "req-submit", idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        return session_id, submitted["payload"]["receipt"]
    finally:
        await _close(server, reader, writer)


@pytest.mark.asyncio
async def test_story_runtime_serves_public_first_turn_over_real_ipc(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        capabilities = set(hello["payload"]["capabilities"])
        assert {"system.health", "system.shutdown"} <= capabilities
        assert set(runtime.capabilities) <= capabilities

        health = await _call(reader, writer, "system.health", {}, "req-health")
        assert health["payload"] == RUNTIME_HEALTH

        entry = await _call(reader, writer, "story.entry.get", _entry_body(), "req-entry")
        assert entry["status"] == "ok"
        _validate("entry_get_response", entry["payload"])
        assert entry["payload"]["supported_advice"] == [SUPPORTED_ADVICE]
        assert entry["payload"]["observed_store_revision"] == 0
        assert "session" not in entry["payload"]

        opened = await _call(
            reader, writer, "story.session.open", _open_body("open_request_1", 0),
            "req-open", idempotency_key="open_request_1",
        )
        assert opened["status"] == "ok"
        _validate("session_open_response", opened["payload"])
        assert opened["payload"]["opened_store_revision"] == 1
        view = opened["payload"]["session"]
        assert view["turn"] == 0 and view["story_revision"] == 0
        assert view["can_submit"] is True
        session_id = view["session_id"]

        fetched = await _call(
            reader, writer, "story.session.get",
            {"schema_version": "1.0", "session_id": session_id}, "req-get",
        )
        _validate("session_get_response", fetched["payload"])
        assert fetched["payload"]["session"] == view

        unsupported = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_unsupported", "换一句别的话"),
            "req-unsupported", idempotency_key="input_turn_unsupported",
        )
        assert unsupported["status"] == "error"
        assert unsupported["error"]["code"] == "deterministic_input_unsupported"
        assert unsupported["error"]["retryable"] is False
        assert _count_world_commits(root) == 1

        submitted = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_1"),
            "req-submit", idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        _validate("advice_submit_response", submitted["payload"])
        receipt = submitted["payload"]["receipt"]
        assert receipt["status"] == "committed"
        assert receipt["committed_store_revision"] == 2
        assert receipt["committed_story_revision"] == 1
        assert submitted["payload"]["session"]["turn"] == 1
        assert submitted["payload"]["session"]["can_submit"] is True
        assert submitted["payload"]["delivery"]["state"] == "unavailable"
        assert submitted["payload"]["delivery"]["reason"] == "voice_not_configured"
        assert submitted["payload"]["session"]["discovered_clues"] == [
            {"id": "clue_doctor_pause", "display_name": "医生的停顿"}
        ]
        expression = await _call(
            reader,
            writer,
            "story.expression.get",
            {
                "schema_version": "1.0",
                "session_id": session_id,
                "turn_id": receipt["turn_id"],
            },
            "req-expression",
        )
        assert expression["status"] == "ok"
        _validate_expression(expression["payload"])
        assert expression["payload"]["narrative_state"] == "ready"
        assert expression["payload"]["segments"]
        assert "speaker_id" not in json.dumps(
            expression["payload"], ensure_ascii=False
        )

        expression_extra = await _call(
            reader,
            writer,
            "story.expression.get",
            {
                "schema_version": "1.0",
                "session_id": session_id,
                "turn_id": receipt["turn_id"],
                "extra": "rejected",
            },
            "req-expression-extra",
        )
        assert expression_extra["status"] == "error"
        assert expression_extra["error"]["code"] == "schema_invalid"

        stored = await _call(
            reader, writer, "story.advice.get",
            _advice_body(session_id, "input_turn_1"), "req-advice",
        )
        _validate("advice_get_response", stored["payload"])
        assert stored["payload"]["found"] is True
        assert stored["payload"]["receipt"] == receipt
        assert stored["payload"]["replayed"] is True

        replayed = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_1"),
            "req-submit-replay", idempotency_key="input_turn_1",
        )
        assert replayed["payload"]["replayed"] is True
        assert replayed["payload"]["receipt"] == receipt
        assert _count_world_commits(root) == 2

        missing = await _call(
            reader, writer, "story.advice.get",
            _advice_body(session_id, "input_turn_missing"), "req-advice-missing",
        )
        assert missing["payload"]["found"] is False
        assert "receipt" not in missing["payload"]
        assert "session" not in missing["payload"]

        closed_turn = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_2"),
            "req-turn-2", idempotency_key="input_turn_2",
        )
        assert closed_turn["status"] == "error"
        # A second turn is now legitimate, so the stale expected revisions in the
        # reused submit body are rejected before any turn-limit or commit.
        assert closed_turn["error"]["code"] == "revision_conflict"
        assert closed_turn["error"]["retryable"] is False

        key_mismatch = await _call(
            reader, writer, "story.session.open", _open_body("open_request_2", 2),
            "req-open-mismatch", idempotency_key="open_request_other",
        )
        assert key_mismatch["error"]["code"] == "schema_invalid"

        unknown_field = await _call(
            reader, writer, "story.session.get",
            {"schema_version": "1.0", "session_id": session_id, "extra": 1}, "req-extra",
        )
        assert unknown_field["error"]["code"] == "schema_invalid"

        unknown_session = await _call(
            reader, writer, "story.session.get",
            {"schema_version": "1.0", "session_id": "session_unknown"}, "req-unknown",
        )
        assert unknown_session["error"]["code"] == "authorization_denied"

        bool_revision = await _call(
            reader, writer, "story.session.open", _open_body("open_request_bool", True),
            "req-bool", idempotency_key="open_request_bool",
        )
        assert bool_revision["error"]["code"] == "schema_invalid"

        transcript = json.dumps(
            [entry, opened, fetched, submitted, stored, replayed], ensure_ascii=False
        )
        assert "secret_" not in transcript
        assert "hidden_truth" not in transcript
    finally:
        await _close(server, reader, writer)
        await runtime.close()


@pytest.mark.asyncio
async def test_story_runtime_reopens_same_durable_session(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    session_id, receipt = await _open_and_submit(runtime, socket_path)
    await runtime.close()
    assert _count_world_commits(root) == 2

    reopened = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, reopened)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        await _handshake(reader, writer)
        entry = await _call(reader, writer, "story.entry.get", _entry_body(), "req-entry")
        assert entry["payload"]["session"]["session_id"] == session_id
        assert entry["payload"]["session"]["turn"] == 1
        assert entry["payload"]["session"]["can_submit"] is True
        assert entry["payload"]["session"]["discovered_clues"] == [
            {"id": "clue_doctor_pause", "display_name": "医生的停顿"}
        ]

        stored = await _call(
            reader, writer, "story.advice.get",
            _advice_body(session_id, "input_turn_1"), "req-advice",
        )
        assert stored["payload"]["found"] is True
        assert stored["payload"]["receipt"] == receipt

        replayed = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_1"),
            "req-replay", idempotency_key="input_turn_1",
        )
        assert replayed["status"] == "ok"
        assert replayed["payload"]["replayed"] is True

        second_turn = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_2"),
            "req-turn-2", idempotency_key="input_turn_2",
        )
        assert second_turn["status"] == "error"
        assert second_turn["error"]["code"] == "revision_conflict"
        assert _count_world_commits(root) == 2
    finally:
        await _close(server, reader, writer)
        await reopened.close()


@pytest.mark.asyncio
async def test_story_runtime_requires_content_artifact(tmp_path: Path):
    root = tmp_path / "app-support"
    with pytest.raises(StoryContentError):
        await StoryRuntime.open(
            StoryRuntimeConfig.for_data_root(root, content_path=tmp_path / "canon.db"),
            expected_sqlite_version=sqlite3.sqlite_version,
        )
    assert not _world_path(root).exists()


@pytest.mark.asyncio
async def test_orphan_session_without_bootstrap_fails_closed(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    session_id = ""
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        await _handshake(reader, writer)
        opened = await _call(
            reader, writer, "story.session.open", _open_body("open_request_1", 0),
            "req-open", idempotency_key="open_request_1",
        )
        session_id = opened["payload"]["session"]["session_id"]
    finally:
        await _close(server, reader, writer)
        await runtime.close()

    # Legacy v9 shape: a durable session without its frozen bootstrap.
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "DELETE FROM story_session_bootstraps WHERE session_id=?", (session_id,)
        )
        connection.commit()

    reopened = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, reopened)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        await _handshake(reader, writer)
        entry = await _call(reader, writer, "story.entry.get", _entry_body(), "req-entry")
        assert entry["status"] == "error"
        assert entry["error"]["code"] == "recovery_required"
        assert entry["error"]["retryable"] is False

        fetched = await _call(
            reader, writer, "story.session.get",
            {"schema_version": "1.0", "session_id": session_id}, "req-get",
        )
        assert fetched["error"]["code"] == "recovery_required"
    finally:
        await _close(server, reader, writer)
        await reopened.close()


def _recv_exact(client, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = client.recv(count - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return data


def _socket_receive(client) -> dict:
    size = struct.unpack("!I", _recv_exact(client, 4))[0]
    assert 0 < size <= 1024 * 1024
    return json.loads(_recv_exact(client, size))


def test_product_cli_without_content_stays_system_only(tmp_path: Path, socket_path: Path):
    token = "c" * 64
    read_fd, write_fd = os.pipe()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "infrastructure.ipc_server",
            "--socket",
            str(socket_path),
            "--token-fd",
            str(read_fd),
            "--data-root",
            str(tmp_path / "app-support"),
            "--content-artifact",
            str(tmp_path / "missing-canon.db"),
        ],
        cwd=ROOT,
        env=env,
        pass_fds=(read_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(read_fd)
    os.write(write_fd, token.encode())
    os.close(write_fd)

    client = None
    output = (b"", b"")
    try:
        deadline = time.monotonic() + 10
        while True:
            assert process.poll() is None
            try:
                client = socket_module.socket(
                    socket_module.AF_UNIX, socket_module.SOCK_STREAM
                )
                client.settimeout(2)
                client.connect(str(socket_path))
                break
            except (OSError, EOFError):
                if client is not None:
                    client.close()
                    client = None
                assert time.monotonic() <= deadline, "Engine did not become ready"
                time.sleep(0.02)

        client.sendall(encode_frame(_handshake_request(token)))
        hello = _socket_receive(client)
        assert hello["status"] == "ok"
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
        }

        client.sendall(encode_frame(_request("system.health", {}, "req-health")))
        health = _socket_receive(client)
        assert health["payload"] == SYSTEM_ONLY_HEALTH
    finally:
        if client is not None:
            client.close()
        if process.poll() is None:
            process.terminate()
        output = process.communicate(timeout=5)

    assert not _world_path(tmp_path / "app-support").exists()
    assert all(token.encode() not in stream for stream in output)


def _spawn_product_engine(
    socket: Path, data_root: Path, content: Path, token: str
) -> tuple[subprocess.Popen, bytes, int]:
    """Start a real Engine process using the packaged entrypoint wiring.

    Production locates the signed ``_wom_sqlite3`` driver; developer machines
    only have stdlib sqlite3, so the launcher injects the local driver version
    exactly like the other durable tests. Transport, repositories, facade and
    shutdown order are the real implementations.
    """
    read_fd, write_fd = os.pipe()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "engine"))
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _PRODUCT_LAUNCHER,
            str(socket),
            str(read_fd),
            str(data_root),
            str(content),
        ],
        cwd=ROOT,
        env=env,
        pass_fds=(read_fd,),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(read_fd)
    return process, token.encode(), write_fd


def _product_client(socket: Path, process: subprocess.Popen, token: str):
    deadline = time.monotonic() + 10
    while True:
        assert process.poll() is None, process.communicate()[1]
        client = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        client.settimeout(3)
        try:
            client.connect(str(socket))
        except OSError:
            client.close()
            assert time.monotonic() <= deadline, "Engine did not become ready"
            time.sleep(0.02)
            continue
        client.sendall(encode_frame(_handshake_request(token)))
        hello = _socket_receive(client)
        assert hello["status"] == "ok"
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
            *STORY_CAPABILITIES,
        }
        return client


def _call_socket(client, method: str, body: dict, request_id: str, **kwargs) -> dict:
    client.sendall(encode_frame(_request(method, body, request_id, **kwargs)))
    return _socket_receive(client)


def _stop_product_engine(process: subprocess.Popen, token: str) -> None:
    if process.poll() is None:
        process.terminate()
    output = process.communicate(timeout=5)
    assert all(token.encode() not in stream for stream in output)


def test_product_cli_serves_first_turn_across_two_real_processes(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    data_root = tmp_path / "app-support"
    token = "d" * 64
    process, payload, write_fd = _spawn_product_engine(
        socket_path, data_root, content_artifact, token
    )
    os.write(write_fd, payload)
    os.close(write_fd)
    client = None
    session_id = ""
    receipt = None
    try:
        client = _product_client(socket_path, process, token)
        opened = _call_socket(
            client, "story.session.open", _open_body("open_request_1", 0),
            "req-open", idempotency_key="open_request_1",
        )
        assert opened["status"] == "ok"
        session_id = opened["payload"]["session"]["session_id"]
        submitted = _call_socket(
            client, "story.advice.submit", _submit_body(session_id, "input_turn_1"),
            "req-submit", idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        receipt = submitted["payload"]["receipt"]
    finally:
        if client is not None:
            client.close()
        _stop_product_engine(process, token)

    assert _world_path(data_root).exists()
    assert _count_world_commits(data_root) == 2

    second_socket = socket_path.with_name("engine-restart.sock")
    restarted, payload, write_fd = _spawn_product_engine(
        second_socket, data_root, content_artifact, token
    )
    os.write(write_fd, payload)
    os.close(write_fd)
    client = None
    try:
        client = _product_client(second_socket, restarted, token)
        entry = _call_socket(client, "story.entry.get", _entry_body(), "req-entry")
        assert entry["status"] == "ok"
        assert entry["payload"]["session"]["session_id"] == session_id
        assert entry["payload"]["session"]["turn"] == 1
        assert entry["payload"]["session"]["discovered_clues"] == [
            {"id": "clue_doctor_pause", "display_name": "医生的停顿"}
        ]
        stored = _call_socket(
            client, "story.advice.get", _advice_body(session_id, "input_turn_1"),
            "req-advice",
        )
        assert stored["payload"]["found"] is True
        assert stored["payload"]["receipt"] == receipt
        replayed = _call_socket(
            client, "story.advice.submit", _submit_body(session_id, "input_turn_1"),
            "req-replay", idempotency_key="input_turn_1",
        )
        assert replayed["payload"]["replayed"] is True
        assert _count_world_commits(data_root) == 2
    finally:
        if client is not None:
            client.close()
        _stop_product_engine(restarted, token)


@pytest.mark.asyncio
async def test_story_runtime_serves_all_five_turns_and_closes_after_fifth(tmp_path: Path):
    """The packaged runtime completes the fixed five-turn scenario end to end."""
    content = _write_content_artifact(tmp_path / "canon.db")
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content)
    try:
        # The catalog is resolved from the module-relative packaged content, not
        # the repository source tree.
        catalog = load_five_turn_catalog(content, _bundle_payload()["seed"])
        assert len(catalog.expression_templates) == 5
        facade = runtime._facade
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open-five-turn",
            expected_store_revision=0,
            request_id="req-open-five",
            trace_id="trace-open-five",
        )
        session_id = opened.session.session_id
        # Before any turn the client is offered the first fixed advice.
        entry = await facade.entry(GOLDEN_SCENARIO_ID)
        assert entry.supported_advice == [catalog.advice_templates[1].raw_input]
        for turn in range(1, 6):
            advice = catalog.advice_templates[turn]
            view = await facade.submit(
                SubmitAdviceCommand(
                    session_id=session_id,
                    input_turn_id=f"input_turn_{turn:02d}",
                    raw_input=advice.raw_input,
                    expected_story_revision=turn - 1,
                    expected_store_revision=turn,
                    request_id=f"req-turn-{turn:02d}",
                    trace_id=f"trace-turn-{turn:02d}",
                )
            )
            assert view.receipt.status == "committed"
            assert view.receipt.committed_story_revision == turn
            assert view.session.turn == turn
            # After each turn the client is offered exactly the next fixed
            # advice, so it can drive the whole scenario over IPC.
            entry = await facade.entry(GOLDEN_SCENARIO_ID)
            if turn < 5:
                assert entry.supported_advice == [
                    catalog.advice_templates[turn + 1].raw_input
                ]
            else:
                assert entry.supported_advice == []
        # After the fifth turn the fixed verification is closed.
        assert view.session.can_submit is False
        # A sixth turn is rejected: the packaged runtime finalizes the Episode
        # on the fifth COMMIT, so the session is no longer active.
        with pytest.raises(StoryFacadeError, match="story_session_not_active"):
            await facade.submit(
                SubmitAdviceCommand(
                    session_id=session_id,
                    input_turn_id="input_turn_06",
                    raw_input=catalog.advice_templates[5].raw_input,
                    expected_story_revision=5,
                    expected_store_revision=6,
                    request_id="req-turn-06",
                    trace_id="trace-turn-06",
                )
            )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_production_runtime_registers_post_commit_jobs_with_the_turn(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    """AO-03: the shipped assembly binds a committed turn to durable intents.

    The runtime is opened exactly as production opens it, so this exercises
    `_build_facade` rather than a hand-built facade. The intents must appear in
    the same world database as the turn, carrying the scenario's frozen recipe.
    """
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        await _handshake(reader, writer)
        opened = await _call(
            reader, writer, "story.session.open", _open_body("open_request_1", 0),
            "req-open", idempotency_key="open_request_1",
        )
        session_id = opened["payload"]["session"]["session_id"]
        assert _jobs(root) == []

        submitted = await _call(
            reader, writer, "story.advice.submit",
            _submit_body(session_id, "input_turn_1"),
            "req-submit", idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        assert submitted["payload"]["receipt"]["status"] == "committed"
    finally:
        await _close(server, reader, writer)
        await runtime.close()

    jobs = _jobs(root)
    # Turn 1 of the five-turn Golden scenario: narrative always, audio always,
    # and no Episode finalization before the scenario says the session ends.
    assert {row["kind"] for row in jobs} == {"narrative_publish", "audio_prepare"}
    assert all(row["session_id"] == session_id for row in jobs)
    assert all(row["turn_id"] for row in jobs)
    # This runtime is opened without a voice provider, so audio starts blocked
    # with a public reason and the text job is unaffected.
    by_kind = {row["kind"]: row for row in jobs}
    assert by_kind["narrative_publish"]["state"] == "pending"
    assert by_kind["audio_prepare"]["state"] == "blocked"
    assert by_kind["audio_prepare"]["last_error_code"] == "voice_not_configured"
    # The recipe is bound to the frozen rules revision of the trusted content:
    # both jobs share one rules prefix and differ only by their recipe name.
    rules_prefixes = {row["recipe_revision"].rsplit(":", 1)[0] for row in jobs}
    assert len(rules_prefixes) == 1
    assert {
        row["recipe_revision"].rsplit(":", 1)[1] for row in jobs
    } == {"narrative-publish-v1", "audio-prepare-v1"}
    for row in jobs:
        assert len(row["input_digest"]) == 64
        assert row["source_story_revision"] == 1


def _jobs(root: Path) -> list[dict]:
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        connection.row_factory = stdlib_sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT job_id,turn_id,session_id,kind,recipe_revision,"
                "source_story_revision,input_digest,state,last_error_code "
                "FROM post_commit_jobs ORDER BY kind"
            )
        ]
