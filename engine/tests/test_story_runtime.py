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
DURABLE_STORY_CAPABILITIES = (
    "story.advice.get",
    "story.advice.submit.v2",
    "story.entry.get",
    "story.expression.get",
    "story.session.get",
    "story.session.open",
    "story.turn.submit.v2",
    "story.turn.work.get",
    "story.turn.work.retry",
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


async def _open_runtime(
    root: Path,
    content: Path,
    *,
    durable_post_commit: bool = False,
) -> StoryRuntime:
    return await StoryRuntime.open(
        StoryRuntimeConfig.for_data_root(root, content_path=content),
        expected_sqlite_version=sqlite3.sqlite_version,
        durable_post_commit=durable_post_commit,
    )


@pytest.mark.asyncio
async def test_live_runtime_composes_authorized_workers_over_sqlite_context_ports(
    tmp_path: Path,
    content_artifact: Path,
):
    from ai.authorized_live_execution import AuthorizedLiveExecution
    from ai.live_turn_workers import LiveFirstTurnFactory, LiveTurnWorkerProfiles
    from ai.openai_compatible import (
        ModelEndpointConfig,
        OpenAICompatibleChatTransport,
    )
    from ai.prompt_renderer import PromptRenderer
    from application.gameplay_context import GameplayContextCoordinator, GameplayMode
    from infrastructure.gameplay_context_repository import (
        SQLiteGameplayContextRepository,
    )
    from infrastructure.story_runtime import (
        _BoundSQLitePlayerAdviceRepository,
        _SQLiteTurnContextBindingPort,
    )
    from infrastructure.turn_context_repository import SQLiteTurnContextRepository

    endpoint = ModelEndpointConfig(
        base_url="http://127.0.0.1:9/v1",
        api_key="test-only-key",
        model="test-live-model",
    )
    runtime = await StoryRuntime.open(
        StoryRuntimeConfig.for_data_root(
            tmp_path / "app-support",
            content_path=content_artifact,
        ),
        expected_sqlite_version=sqlite3.sqlite_version,
        model_endpoint=endpoint,
    )
    try:
        workers = runtime._workers
        assert isinstance(workers, LiveFirstTurnFactory)
        execution = workers._execution
        assert isinstance(execution, AuthorizedLiveExecution)

        coordinator = execution.coordinator
        assert isinstance(coordinator, GameplayContextCoordinator)
        gameplay_repository = coordinator.snapshot
        assert isinstance(gameplay_repository, SQLiteGameplayContextRepository)
        assert coordinator.authorization is gameplay_repository
        assert gameplay_repository._database is runtime._database
        assert set(coordinator._ports.values()) == {
            gameplay_repository.lore_port,
            gameplay_repository.world_port,
            gameplay_repository.character_port,
            gameplay_repository.story_port,
            gameplay_repository.memory_port,
        }
        assert all(port is not None for port in coordinator._ports.values())

        profiles = coordinator.profiles
        assert isinstance(profiles, LiveTurnWorkerProfiles)
        assert profiles.profile(
            GameplayMode.ADVICE_INTERPRETATION, "advice_interpreter"
        ).prompt_revision == "wom-live-interpreter-v2"
        assert profiles.profile(
            GameplayMode.CHARACTER_REASONING, "character_reasoner"
        ).prompt_revision == "wom-live-proposer-v2"
        assert profiles.profile(
            GameplayMode.NARRATIVE_COMPILATION, "narrative_compiler"
        ).prompt_revision == "wom-live-narrative-v2"

        assert isinstance(execution.renderer, PromptRenderer)
        assert isinstance(execution.transport, OpenAICompatibleChatTransport)
        assert execution.transport.config == endpoint

        facade = runtime._facade
        assert isinstance(facade._context_bindings, _SQLiteTurnContextBindingPort)
        assert isinstance(
            facade._context_bindings._repository,
            SQLiteTurnContextRepository,
        )
        assert isinstance(facade._advice, _BoundSQLitePlayerAdviceRepository)
        assert facade._advice._contexts is facade._context_bindings
    finally:
        await runtime.close()


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
        store_revision=2,
    )
    command = SimpleNamespace(
        session_id="session-1",
        input_turn_id="input-1",
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
        context_bindings=None,
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
        context_bindings=None,
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
        context_bindings=None,
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
        context_bindings=None,
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
async def test_production_runtime_defaults_to_synchronous_v1_without_jobs(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    """Legacy v1 keeps synchronous expression publication without scheduling jobs.

    The default is deliberately frozen at construction time: v1 owns settlement,
    while only the explicit v2 runtime delegates it to the durable worker.
    """
    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
            *STORY_CAPABILITIES,
        }
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
        assert submitted["payload"]["delivery"]["reason"] == "voice_not_configured"
    finally:
        await _close(server, reader, writer)
        await runtime.close()

    assert _jobs(root) == []
    assert _narrative_count(root) == 1


@pytest.mark.asyncio
async def test_v1_terminal_turn_publishes_expression_once_and_finalizes_episode(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
):
    from application.post_commit_expression import PostCommitExpressionService

    expression_publications = {}
    original_publish = PostCommitExpressionService.publish

    async def track_expression_publish(self, *, turn_number, commit):
        expression_publications[commit.turn_id] = (
            expression_publications.get(commit.turn_id, 0) + 1
        )
        return await original_publish(
            self,
            turn_number=turn_number,
            commit=commit,
        )

    monkeypatch.setattr(
        PostCommitExpressionService,
        "publish",
        track_expression_publish,
    )

    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        catalog = load_five_turn_catalog(content_artifact, _bundle_payload()["seed"])
        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
            *STORY_CAPABILITIES,
        }
        opened = await _call(
            reader,
            writer,
            "story.session.open",
            _open_body("open_v1_terminal", 0),
            "req-open-v1-terminal",
            idempotency_key="open_v1_terminal",
        )
        session_id = opened["payload"]["session"]["session_id"]

        for turn_number in range(1, 6):
            advice = catalog.advice_templates[turn_number]
            body = _submit_body(
                session_id,
                f"v1_terminal_input_{turn_number:02d}",
                advice.raw_input,
            )
            body["expected_story_revision"] = turn_number - 1
            body["expected_store_revision"] = turn_number
            submitted = await _call(
                reader,
                writer,
                "story.advice.submit",
                body,
                f"req-v1-terminal-turn-{turn_number:02d}",
                idempotency_key=f"v1_terminal_input_{turn_number:02d}",
            )
            assert submitted["status"] == "ok"
            assert (
                submitted["payload"]["receipt"]["committed_story_revision"]
                == turn_number
            )

        assert len(expression_publications) == 5
        assert set(expression_publications.values()) == {1}
        assert _episode_count(root) == 1
        assert _world_revision(root) == 7
        assert _jobs(root) == []
    finally:
        if server is not None:
            await _close(server, reader, writer)
        await runtime.close()


@pytest.mark.asyncio
async def test_durable_runtime_exposes_only_v2_submit_methods(
    tmp_path: Path, content_artifact: Path, socket_path: Path
):
    runtime = await StoryRuntime.open(
        StoryRuntimeConfig.for_data_root(
            tmp_path / "app-support",
            content_path=content_artifact,
        ),
        expected_sqlite_version=sqlite3.sqlite_version,
        durable_post_commit=True,
    )
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        assert runtime.capabilities == DURABLE_STORY_CAPABILITIES
        assert "story.advice.submit" not in runtime.request_handlers
        assert "story.turn.submit" not in runtime.request_handlers
        assert "story.advice.submit.v2" in runtime.request_handlers
        assert "story.turn.submit.v2" in runtime.request_handlers
        assert "story.turn.work.get" in runtime.request_handlers
        assert "story.turn.work.retry" in runtime.request_handlers

        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        assert set(DURABLE_STORY_CAPABILITIES) <= set(
            hello["payload"]["capabilities"]
        )

        missing_work = await _call(
            reader,
            writer,
            "story.turn.work.get",
            {"session_id": "session-missing", "turn_id": "turn-missing"},
            "req-work-get",
        )
        assert missing_work["error"]["code"] == "turn_not_found"
        missing_retry = await _call(
            reader,
            writer,
            "story.turn.work.retry",
            {
                "session_id": "session-missing",
                "turn_id": "turn-missing",
                "kind": "narrative_publish",
                "retry_request_id": "retry-missing",
            },
            "req-work-retry",
        )
        assert missing_retry["error"]["code"] == "turn_not_found"
    finally:
        await _close(server, reader, writer)
        await runtime.close()


@pytest.mark.parametrize(
    ("legacy_state", "expected_job_state", "expected_reason", "expected_unverifiable"),
    (
        ("artifact_present", "succeeded", None, 0),
        ("artifact_missing", "blocked", "legacy_recipe_unknown", 0),
        ("non_committed", None, None, 1),
    ),
    ids=("verified-artifact", "unknown-legacy-recipe", "unverifiable-turn"),
)
@pytest.mark.asyncio
async def test_durable_runtime_reconciles_legacy_post_commit_work_on_open(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
    legacy_state: str,
    expected_job_state: str | None,
    expected_reason: str | None,
    expected_unverifiable: int,
):
    from infrastructure.post_commit_reconciliation import PostCommitReconciler

    reports = []
    original_reconcile = PostCommitReconciler.reconcile

    async def capture_report(self):
        report = await original_reconcile(self)
        reports.append(report)
        return report

    monkeypatch.setattr(PostCommitReconciler, "reconcile", capture_report)

    root = tmp_path / "app-support"
    legacy_runtime = await _open_runtime(root, content_artifact)
    assert reports == []
    try:
        await _open_and_submit(legacy_runtime, socket_path)
    finally:
        await legacy_runtime.close()

    assert _jobs(root) == []
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        turn_id = connection.execute(
            "SELECT id FROM turn_transactions ORDER BY id LIMIT 1"
        ).fetchone()[0]
        if legacy_state == "artifact_missing":
            connection.execute(
                "UPDATE turn_transactions SET narrative_block_id=NULL WHERE id=?",
                (turn_id,),
            )
            connection.execute(
                "DELETE FROM narrative_blocks WHERE turn_id=?",
                (turn_id,),
            )
        elif legacy_state == "non_committed":
            connection.execute(
                "UPDATE turn_transactions SET status='reconcile_required' WHERE id=?",
                (turn_id,),
            )
        connection.commit()

    runtime = await _open_runtime(root, content_artifact, durable_post_commit=True)
    try:
        assert len(reports) == 1
        assert reports[0].unverifiable_turns == expected_unverifiable
        jobs = _jobs(root)
        assert all(job["kind"] != "audio_prepare" for job in jobs)
        if expected_job_state is None:
            assert jobs == []
        else:
            assert len(jobs) == 1
            assert jobs[0]["kind"] == "narrative_publish"
            assert jobs[0]["state"] == expected_job_state
            assert jobs[0]["last_error_code"] == expected_reason
    finally:
        await runtime.close()


@pytest.mark.parametrize("enabled", [False, True], ids=["default-v1", "opt-in-v2"])
def test_ipc_entrypoint_selects_runtime_mode_and_passes_switch_to_open(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
    enabled: bool,
):
    from infrastructure import ipc_server

    original_open = StoryRuntime.open.__func__
    open_calls = []
    runtime_observations = {}

    async def controlled_open(cls, config, **kwargs):
        open_calls.append(
            {
                "has_durable_post_commit": "durable_post_commit" in kwargs,
                "durable_post_commit": kwargs.get("durable_post_commit"),
            }
        )
        return await original_open(
            cls,
            config,
            expected_sqlite_version=sqlite3.sqlite_version,
            **kwargs,
        )

    async def inspect_loaded_runtime(
        path,
        token,
        parent_pid=None,
        *,
        runtime_loader=None,
    ):
        del path, parent_pid
        assert token == TOKEN
        assert runtime_loader is not None
        runtime = await runtime_loader()
        try:
            worker = runtime._post_commit_worker
            runtime_observations["capabilities"] = set(runtime.capabilities)
            runtime_observations["worker_present"] = worker is not None
            runtime_observations["worker_running"] = (
                worker is not None and worker.is_running
            )
            runtime_observations["jobs"] = _jobs(tmp_path / "cli-app-support")
            runtime_observations["health"] = runtime.health()
        finally:
            await runtime.close()

    monkeypatch.setattr(StoryRuntime, "open", classmethod(controlled_open))
    monkeypatch.setattr(ipc_server, "read_bootstrap_token", lambda _fd: TOKEN)
    monkeypatch.setattr(ipc_server, "_run", inspect_loaded_runtime)
    monkeypatch.setenv("WOM_MODEL_BASE_URL", "")
    monkeypatch.setenv("WOM_MODEL_NAME", "")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ipc_server",
            "--socket",
            str(socket_path),
            "--token-fd",
            "7",
            "--data-root",
            str(tmp_path / "cli-app-support"),
            "--content-artifact",
            str(content_artifact),
            *(
                ["--durable-post-commit"]
                if enabled
                else []
            ),
        ],
    )

    assert ipc_server.main() == 0
    assert open_calls == [
        {
            "has_durable_post_commit": True,
            "durable_post_commit": enabled,
        }
    ]
    capabilities = runtime_observations["capabilities"]
    v1_submit_methods = {"story.advice.submit", "story.turn.submit"}
    v2_submit_methods = {"story.advice.submit.v2", "story.turn.submit.v2"}
    assert runtime_observations["health"] == RUNTIME_HEALTH
    if enabled:
        assert v2_submit_methods <= capabilities
        assert v1_submit_methods.isdisjoint(capabilities)
        assert runtime_observations["worker_present"] is True
        assert runtime_observations["worker_running"] is True
    else:
        assert v1_submit_methods <= capabilities
        assert v2_submit_methods.isdisjoint(capabilities)
        assert capabilities == set(STORY_CAPABILITIES)
        assert runtime_observations["worker_present"] is False
        assert runtime_observations["worker_running"] is False
        assert runtime_observations["jobs"] == []


@pytest.mark.asyncio
async def test_durable_v2_returns_before_worker_publication_and_drains_before_db_close(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
):
    from application.post_commit_work import PostCommitKind
    from infrastructure.episode_settlement import ScenarioSettlement, SettlingCommitPort
    from infrastructure.post_commit_job_repository import SQLitePostCommitJobRepository
    from infrastructure.scenarios.post_commit_handlers import (
        ScenarioNarrativePublishHandler,
    )
    from infrastructure.story_session_repository import SQLiteStorySessionCommitPort

    entered = asyncio.Event()
    release = asyncio.Event()
    settlement_called = asyncio.Event()
    acknowledged = asyncio.Event()
    captured_sources = []
    stop_started = asyncio.Event()
    worker_stopped = asyncio.Event()
    database_close_started = asyncio.Event()

    original_execute = ScenarioNarrativePublishHandler.execute
    original_settle = ScenarioSettlement.settle
    original_complete = SQLitePostCommitJobRepository.complete

    async def hold_narrative(self, source):
        captured_sources.append(source)
        entered.set()
        await release.wait()
        return await original_execute(self, source)

    async def track_settlement(self, result):
        settlement_called.set()
        return await original_settle(self, result)

    async def track_complete(self, *args, **kwargs):
        result = await original_complete(self, *args, **kwargs)
        acknowledged.set()
        return result

    monkeypatch.setattr(ScenarioNarrativePublishHandler, "execute", hold_narrative)
    monkeypatch.setattr(ScenarioSettlement, "settle", track_settlement)
    monkeypatch.setattr(SQLitePostCommitJobRepository, "complete", track_complete)

    root = tmp_path / "app-support"
    runtime = await _open_runtime(
        root,
        content_artifact,
        durable_post_commit=True,
    )
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    runtime_closed = False
    try:
        assert isinstance(runtime._facade._story, SQLiteStorySessionCommitPort)
        assert not isinstance(runtime._facade._story, SettlingCommitPort)
        assert runtime._facade._after_commit is None
        assert runtime._post_commit_worker is not None
        assert runtime._post_commit_worker.is_running

        original_stop = runtime._post_commit_worker.stop
        original_database_close = runtime._database.close

        async def track_stop():
            stop_started.set()
            await original_stop()
            worker_stopped.set()

        async def track_database_close():
            assert worker_stopped.is_set()
            database_close_started.set()
            await original_database_close()

        runtime._post_commit_worker.stop = track_stop
        runtime._database.close = track_database_close

        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
            *DURABLE_STORY_CAPABILITIES,
        }
        opened = await _call(
            reader,
            writer,
            "story.session.open",
            _open_body("open_request_1", 0),
            "req-open",
            idempotency_key="open_request_1",
        )
        session_id = opened["payload"]["session"]["session_id"]
        submitted = await _call(
            reader,
            writer,
            "story.advice.submit.v2",
            _submit_body(session_id, "input_turn_1"),
            "req-submit-v2",
            idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        assert submitted["payload"]["receipt"]["status"] == "committed"
        assert "delivery" not in submitted["payload"]
        await asyncio.wait_for(entered.wait(), timeout=5)

        assert _narrative_count(root) == 0
        jobs_by_kind = {row["kind"]: row for row in _jobs(root)}
        job = jobs_by_kind["narrative_publish"]
        assert job["state"] == "running"
        assert len(captured_sources) == 1
        assert {
            "job_id": captured_sources[0].job_id,
            "turn_id": captured_sources[0].turn_id,
            "session_id": captured_sources[0].session_id,
            "kind": captured_sources[0].kind.value,
            "recipe_revision": captured_sources[0].recipe_revision,
            "source_story_revision": captured_sources[0].source_story_revision,
            "source_world_revision": captured_sources[0].source_world_revision,
            "input_digest": captured_sources[0].input_digest,
        } == {
            "job_id": job["job_id"],
            "turn_id": job["turn_id"],
            "session_id": job["session_id"],
            "kind": job["kind"],
            "recipe_revision": job["recipe_revision"],
            "source_story_revision": job["source_story_revision"],
            "source_world_revision": job["source_world_revision"],
            "input_digest": job["input_digest"],
        }
        assert captured_sources[0].kind is PostCommitKind.NARRATIVE_PUBLISH
        assert not settlement_called.is_set()
        revision_while_blocked = _world_revision(root)

        await _close(server, reader, writer)
        server = reader = writer = None
        close_task = asyncio.create_task(runtime.close())
        await stop_started.wait()
        assert runtime._post_commit_worker.is_stopping
        assert not worker_stopped.is_set()
        assert not database_close_started.is_set()
        assert await runtime._database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        )
        release.set()
        await close_task
        runtime_closed = True
        assert acknowledged.is_set()
        assert worker_stopped.is_set()
        assert database_close_started.is_set()
        assert not runtime._post_commit_worker.is_running
        assert _world_revision(root) == revision_while_blocked
        assert _narrative_count(root) == 1
        completed_jobs = {row["kind"]: row for row in _jobs(root)}
        assert completed_jobs["narrative_publish"]["state"] == "succeeded"
        assert completed_jobs["audio_prepare"]["state"] == "blocked"
        assert not settlement_called.is_set()
    finally:
        release.set()
        if server is not None:
            await _close(server, reader, writer)
        if not runtime_closed:
            await runtime.close()


@pytest.mark.asyncio
async def test_durable_worker_recovers_artifact_written_before_ack_after_restart(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
):
    from infrastructure.post_commit_job_repository import SQLitePostCommitJobRepository
    from infrastructure.scenarios.post_commit_handlers import (
        ScenarioNarrativePublishHandler,
    )

    first_interrupted = asyncio.Event()
    recovered = asyncio.Event()
    acknowledged = asyncio.Event()
    sources = []
    original_execute = ScenarioNarrativePublishHandler.execute
    original_complete = SQLitePostCommitJobRepository.complete

    async def interrupt_after_artifact(self, source):
        sources.append(source)
        result = await original_execute(self, source)
        if len(sources) == 1:
            first_interrupted.set()
            raise asyncio.CancelledError
        recovered.set()
        return result

    async def track_complete(self, *args, **kwargs):
        result = await original_complete(self, *args, **kwargs)
        acknowledged.set()
        return result

    monkeypatch.setattr(
        ScenarioNarrativePublishHandler,
        "execute",
        interrupt_after_artifact,
    )
    monkeypatch.setattr(SQLitePostCommitJobRepository, "complete", track_complete)

    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact, durable_post_commit=True)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        await _handshake(reader, writer)
        opened = await _call(
            reader,
            writer,
            "story.session.open",
            _open_body("open_request_1", 0),
            "req-open",
            idempotency_key="open_request_1",
        )
        session_id = opened["payload"]["session"]["session_id"]
        submitted = await _call(
            reader,
            writer,
            "story.advice.submit.v2",
            _submit_body(session_id, "input_turn_1"),
            "req-submit-v2",
            idempotency_key="input_turn_1",
        )
        assert submitted["status"] == "ok"
        await asyncio.wait_for(first_interrupted.wait(), timeout=5)
        await _close(server, reader, writer)
        server = reader = writer = None
        await runtime.close()
    finally:
        if server is not None:
            await _close(server, reader, writer)
        if runtime._database._close_task is None:
            await runtime.close()

    jobs_after_crash = _jobs(root)
    narrative_after_crash = next(
        row for row in jobs_after_crash if row["kind"] == "narrative_publish"
    )
    assert narrative_after_crash["state"] == "running"
    assert _narrative_count(root) == 1
    revision_after_commit = _world_revision(root)

    restarted = await _open_runtime(root, content_artifact, durable_post_commit=True)
    try:
        await asyncio.wait_for(recovered.wait(), timeout=5)
        await asyncio.wait_for(acknowledged.wait(), timeout=5)
        assert len(sources) == 2
        assert sources[0] == sources[1]
        assert _narrative_count(root) == 1
        recovered_job = next(
            row for row in _jobs(root) if row["kind"] == "narrative_publish"
        )
        assert recovered_job["state"] == "succeeded"
        assert _world_revision(root) == revision_after_commit
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_durable_episode_handler_is_the_only_revision_advancing_post_commit_work(
    tmp_path: Path,
    content_artifact: Path,
    socket_path: Path,
    monkeypatch,
):
    from application.post_commit_expression import PostCommitExpressionService
    from application.post_commit_work import (
        PostCommitKind,
        PostCommitResultState,
        PostCommitWorkSource,
    )
    from infrastructure.post_commit_job_repository import SQLitePostCommitJobRepository
    from infrastructure.scenarios.post_commit_handlers import (
        ScenarioEpisodeFinalizeHandler,
    )

    episode_entered = asyncio.Event()
    release_episode = asyncio.Event()
    episode_acknowledged = asyncio.Event()
    episode_sources = []
    expression_publications = {}
    original_execute = ScenarioEpisodeFinalizeHandler.execute
    original_complete = SQLitePostCommitJobRepository.complete
    original_publish = PostCommitExpressionService.publish

    async def hold_episode(self, source):
        episode_sources.append(source)
        episode_entered.set()
        await release_episode.wait()
        return await original_execute(self, source)

    async def track_complete(self, job_id, *args, **kwargs):
        result = await original_complete(self, job_id, *args, **kwargs)
        if ":episode_finalize:" in job_id:
            episode_acknowledged.set()
        return result

    async def track_expression_publish(self, *, turn_number, commit):
        expression_publications[commit.turn_id] = (
            expression_publications.get(commit.turn_id, 0) + 1
        )
        return await original_publish(
            self,
            turn_number=turn_number,
            commit=commit,
        )

    monkeypatch.setattr(ScenarioEpisodeFinalizeHandler, "execute", hold_episode)
    monkeypatch.setattr(SQLitePostCommitJobRepository, "complete", track_complete)
    monkeypatch.setattr(
        PostCommitExpressionService,
        "publish",
        track_expression_publish,
    )

    root = tmp_path / "app-support"
    runtime = await _open_runtime(root, content_artifact, durable_post_commit=True)
    server = await _start_server(socket_path, runtime)
    reader = writer = None
    try:
        catalog = load_five_turn_catalog(content_artifact, _bundle_payload()["seed"])
        reader, writer = await asyncio.open_unix_connection(socket_path)
        hello = await _handshake(reader, writer)
        assert set(hello["payload"]["capabilities"]) == {
            "system.health",
            "system.shutdown",
            *DURABLE_STORY_CAPABILITIES,
        }
        opened = await _call(
            reader,
            writer,
            "story.session.open",
            _open_body("open_durable_episode", 0),
            "req-open",
            idempotency_key="open_durable_episode",
        )
        session_id = opened["payload"]["session"]["session_id"]
        for turn_number in range(1, 6):
            advice = catalog.advice_templates[turn_number]
            body = _submit_body(
                session_id,
                f"durable_input_{turn_number:02d}",
                advice.raw_input,
            )
            body["expected_story_revision"] = turn_number - 1
            body["expected_store_revision"] = turn_number
            submitted = await _call(
                reader,
                writer,
                "story.advice.submit.v2",
                body,
                f"req-turn-{turn_number:02d}",
                idempotency_key=f"durable_input_{turn_number:02d}",
            )
            assert submitted["status"] == "ok"
            assert submitted["payload"]["receipt"]["committed_story_revision"] == turn_number

        await asyncio.wait_for(episode_entered.wait(), timeout=5)
        assert _world_revision(root) == 6
        assert _episode_count(root) == 0
        rows_before_finalize = _jobs(root)
        assert sum(row["kind"] == "narrative_publish" and row["state"] == "succeeded"
                   for row in rows_before_finalize) == 5
        assert sum(row["kind"] == "audio_prepare" and row["state"] == "blocked"
                   for row in rows_before_finalize) == 5
        assert next(row for row in rows_before_finalize
                    if row["kind"] == "episode_finalize")["state"] == "running"

        release_episode.set()
        await asyncio.wait_for(episode_acknowledged.wait(), timeout=5)
        assert _episode_count(root) == 1
        assert _world_revision(root) == 7

        source = episode_sources[0]
        assert isinstance(source, PostCommitWorkSource)
        assert source.kind is PostCommitKind.EPISODE_FINALIZE
        assert expression_publications[source.turn_id] == 1
        handler = runtime._post_commit_worker._handlers[
            PostCommitKind.EPISODE_FINALIZE.value
        ]
        replay = await handler.execute(source)
        assert replay.state is PostCommitResultState.SUCCEEDED
        assert _episode_count(root) == 1
        assert _world_revision(root) == 7
    finally:
        release_episode.set()
        if server is not None:
            await _close(server, reader, writer)
        await runtime.close()


def _jobs(root: Path) -> list[dict]:
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        connection.row_factory = stdlib_sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                "SELECT job_id,turn_id,session_id,kind,recipe_revision,"
                "source_story_revision,source_world_revision,input_digest,"
                "state,last_error_code "
                "FROM post_commit_jobs ORDER BY kind"
            )
        ]


def _narrative_count(root: Path) -> int:
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        return connection.execute("SELECT count(*) FROM narrative_blocks").fetchone()[0]


def _world_revision(root: Path) -> int:
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        return connection.execute(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ).fetchone()[0]


def _episode_count(root: Path) -> int:
    with stdlib_sqlite3.connect(_world_path(root)) as connection:
        return connection.execute("SELECT count(*) FROM episodes").fetchone()[0]
