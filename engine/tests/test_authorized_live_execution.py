import asyncio
import json

import pytest

from ai.authorized_live_execution import AuthorizedExecutionBudget, AuthorizedLiveExecution
from ai.openai_compatible import ModelEndpointConfig, OpenAICompatibleChatTransport
from ai.prompt_renderer import PromptRenderer
from application.context_plan import AuthorizationView, ContextError, Evidence, Layer, WorkerProfile
from application.gameplay_context import (
    ContextFacet,
    ContextSnapshot,
    EligibilityTicket,
    GameplayCall,
    GameplayContextCoordinator,
    GameplayMode,
)
from application.turn_context_binding import (
    AuthorizedContextSource,
    AuthorizedTurnContextBinding,
    TurnContextBindingIdentity,
)

SCHEMA = (
    '{"type":"object","properties":{"action":{"type":"string"}},'
    '"required":["action"],"additionalProperties":false}'
)


class LocalChatEndpoint:
    """Capture bytes received by a local HTTP endpoint used by the OpenAI SDK."""

    def __init__(self, replies, *, after_request=None):
        self.replies = list(replies)
        self.after_request = after_request
        self.bodies = []
        self.server = None
        self.base_url = ""

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        address = self.server.sockets[0].getsockname()
        self.base_url = f"http://127.0.0.1:{address[1]}/v1"
        return self

    async def __aexit__(self, *_exc_info):
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            header_values = {}
            for line in headers.split(b"\r\n")[1:]:
                if b":" in line:
                    name, value = line.split(b":", 1)
                    header_values[name.lower()] = value.strip()
            body_size = int(header_values[b"content-length"])
            request_body = json.loads(await reader.readexactly(body_size))
            self.bodies.append(request_body)

            index = len(self.bodies) - 1
            if self.after_request is not None:
                self.after_request(index)
            content = self.replies.pop(0)
            response_body = json.dumps({
                "id": "chatcmpl-local-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            }).encode("utf-8")
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(response_body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
                + response_body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()


class SnapshotPort:
    def __init__(self):
        self.calls = 0
        self.value = ContextSnapshot(
            10,
            3,
            20,
            "policy-v1",
            "lineage-v1",
            (),
            (
                ("content_pack", "pack-v1"),
                ("character_core", "core-v1"),
                ("story_seed", "seed-v1"),
                ("checkpoint", "checkpoint-v1"),
                ("narrative_dna", "dna-v1"),
                ("voice_persona", "voice-v1"),
                ("episode", "episode-v1"),
                ("world_checkpoint", "world-v1"),
                ("spoiler_profile", "spoiler-v1"),
                ("era", "era-v1"),
                ("sequence_profile", "sequence-v1"),
                ("scene", "scene-v1"),
                ("episode_seed", "episode-seed-v1"),
            ),
        )

    async def resolve(self, _call, _recipe):
        self.calls += 1
        return self.value


class AuthorizationPort:
    def __init__(self):
        self.drop_sources = set()
        self.revision_delta = 0
        self.eligibility_calls = 0
        self.authorization_calls = 0

    async def eligibility(self, scope, _snapshot, _recipe):
        self.eligibility_calls += 1
        return EligibilityTicket(scope, "domain-issued-test-ticket")

    async def authorize(self, request, _recipe):
        self.authorization_calls += 1
        grants = frozenset(
            item.fingerprint
            for item in request.evidence
            if item.source_id not in self.drop_sources
        )
        return AuthorizationView(
            request.scope,
            request.world_revision + self.revision_delta,
            request.story_revision,
            20,
            grants,
        )


class FacetPort:
    def __init__(self, evidence=()):
        self.evidence = tuple(evidence)
        self.snapshots = []

    async def load(self, _call, snapshot, _recipe, _eligibility):
        self.snapshots.append(snapshot)
        return self.evidence


class ProfilePort:
    def profile(self, _mode, consumer):
        return WorkerProfile(consumer, "test-profile-v1", "Return a typed proposal.", SCHEMA)


def _evidence(source, kind, layer, content, *, subject=None, state=False):
    return Evidence(
        source,
        1,
        kind,
        layer,
        json.dumps(content, ensure_ascii=False),
        world_id="world" if state else None,
        worldline_id="line" if state else None,
        subject_id=subject,
        available_at_tick=20 if state else 0,
        committed_revision=10 if state else None,
    )


def build_coordinator(mode, authorization=None):
    authorization = authorization or AuthorizationPort()
    snapshot = SnapshotPort()
    ports = {
        ContextFacet.LORE: FacetPort(),
        ContextFacet.WORLD: FacetPort(),
        ContextFacet.CHARACTER: FacetPort(),
        ContextFacet.STORY: FacetPort(),
        ContextFacet.MEMORY: FacetPort(),
    }

    if mode is GameplayMode.CHARACTER_REASONING:
        ports[ContextFacet.LORE] = FacetPort((
            _evidence("known-canon", "canon_known", Layer.STATIC, {"fact": "A fact this character knows"}),
        ))
        ports[ContextFacet.WORLD] = FacetPort((
            _evidence("current-state", "observation", Layer.STATE, {"place": "station"}, state=True),
        ))
        ports[ContextFacet.CHARACTER] = FacetPort((
            _evidence("character-core", "character_core", Layer.CORE, {"identity": "investigator"}, subject="hero"),
        ))
        ports[ContextFacet.STORY] = FacetPort((
            _evidence("checkpoint", "checkpoint", Layer.CHECKPOINT, {"summary": "The scene is active"}, state=True),
        ))
        ports[ContextFacet.MEMORY] = FacetPort((
            _evidence("known-memory", "memory", Layer.RECALL, {"memory": "The hero saw a note"}, subject="hero"),
            _evidence(
                "unknown-role-memory",
                "memory",
                Layer.RECALL,
                {"private_marker": "UNKNOWN_ROLE_PRIVATE_MEMORY"},
                subject="rival",
            ),
        ))
        authorization.drop_sources.add("unknown-role-memory")
    elif mode is GameplayMode.NARRATIVE_COMPILATION:
        ports[ContextFacet.CHARACTER] = FacetPort((
            _evidence("voice-style", "voice_persona", Layer.CORE, {"style": "measured"}, subject="hero"),
        ))
        ports[ContextFacet.STORY] = FacetPort((
            _evidence(
                "disclosed-commit",
                "disclosed_fact",
                Layer.STATE,
                {"result": "The sealed door remained closed"},
                state=True,
            ),
        ))
    else:
        raise AssertionError(f"unsupported test fixture mode: {mode}")

    coordinator = GameplayContextCoordinator(
        snapshot=snapshot,
        authorization=authorization,
        profiles=ProfilePort(),
        **{facet.value: port for facet, port in ports.items()},
    )
    return coordinator, snapshot, authorization, ports


def make_call(mode, task_json):
    return GameplayCall(
        mode,
        "owner",
        "world",
        "line",
        "hero",
        "session",
        task_json,
        "request-1",
    )


def make_executor(coordinator, endpoint):
    transport = OpenAICompatibleChatTransport(ModelEndpointConfig(
        endpoint.base_url,
        "local-test-key",
        "test-model",
        timeout_seconds=2,
    ))
    executor = AuthorizedLiveExecution(
        coordinator=coordinator,
        renderer=PromptRenderer(b"r" * 32),
        transport=transport,
        validate_proposal=lambda _proposal, _request: True,
    )
    return executor, transport


def request_text(body):
    return "\n".join(
        part["text"]
        for message in body["messages"]
        for part in (
            message["content"]
            if isinstance(message["content"], list)
            else [{"text": message["content"]}]
        )
    )


@pytest.mark.asyncio
async def test_request_body_contains_only_domain_authorized_character_evidence():
    coordinator, _snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING
    )
    async with LocalChatEndpoint(['{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            result = await executor.execute(
                make_call(
                    GameplayMode.CHARACTER_REASONING,
                    '{"advice":"PLAYER-INTENT-IS-UNTRUSTED"}',
                ),
                AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
            )
        finally:
            await transport.aclose()

    assert result.proposal() == {"action": "wait"}
    assert len(endpoint.bodies) == 1
    body_text = request_text(endpoint.bodies[0])
    assert "A fact this character knows" in body_text
    assert "PLAYER-INTENT-IS-UNTRUSTED" in body_text
    assert "UNKNOWN_ROLE_PRIVATE_MEMORY" not in body_text
    assert "unknown-role-memory" not in body_text


@pytest.mark.asyncio
async def test_result_binding_records_only_finally_authorized_source_identities():
    coordinator, _snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING
    )
    async with LocalChatEndpoint(['{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            result = await executor.execute(
                make_call(GameplayMode.CHARACTER_REASONING, '{"advice":"observe"}'),
                AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
                binding_identity=TurnContextBindingIdentity(
                    turn_id="turn-1",
                    stage="action",
                    input_turn_id="input-1",
                    content_digest="a" * 64,
                    source_store_revision=10,
                    source_story_revision=3,
                ),
            )
        finally:
            await transport.aclose()

    binding = result.context_binding
    assert binding is not None
    assert binding.stage == "action"
    assert binding.context_revision
    assert binding.manifest_digest
    assert binding.authorized_source_ids == {
        "known-canon",
        "current-state",
        "character-core",
        "checkpoint",
        "known-memory",
    }
    assert all(isinstance(source, AuthorizedContextSource) for source in binding.manifest)


@pytest.mark.asyncio
async def test_expected_context_binding_rejects_a_stale_revision_before_send():
    coordinator, _snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING
    )
    expected = AuthorizedTurnContextBinding(
        turn_id="turn-1",
        stage="interpretation",
        input_turn_id="input-1",
        source_store_revision=9,
        source_story_revision=3,
        policy_revision="policy-v1",
        content_digest="a" * 64,
        lineage_digest="lineage-v1",
        manifest=(),
    )
    async with LocalChatEndpoint(['{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            with pytest.raises(ContextError, match="context_stale"):
                await executor.execute(
                    make_call(
                        GameplayMode.CHARACTER_REASONING,
                        '{"advice":"observe"}',
                    ),
                    AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
                    binding_identity=TurnContextBindingIdentity(
                        turn_id="turn-1",
                        stage="action",
                        input_turn_id="input-1",
                        content_digest="a" * 64,
                    ),
                    expected_binding=expected,
                )
        finally:
            await transport.aclose()

    assert endpoint.bodies == []


@pytest.mark.asyncio
async def test_schema_repair_reuses_the_same_prepared_snapshot_and_prompt():
    coordinator, snapshot, _authorization, ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING
    )
    async with LocalChatEndpoint(['{"wrong":true}', '{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            result = await executor.execute(
                make_call(GameplayMode.CHARACTER_REASONING, '{"advice":"observe"}'),
                AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
            )
        finally:
            await transport.aclose()

    assert result.proposal() == {"action": "wait"}
    assert result.attempts == 2
    assert len(endpoint.bodies) == 2
    first_messages = endpoint.bodies[0]["messages"]
    repair_messages = endpoint.bodies[1]["messages"]
    assert repair_messages[:-1] == first_messages
    assert repair_messages[-1]["role"] == "user"
    assert "valid JSON object matching the output schema" in request_text({
        "messages": [repair_messages[-1]]
    })
    assert snapshot.calls == 1
    loaded_snapshots = [
        observed
        for port in ports.values()
        for observed in port.snapshots
    ]
    assert loaded_snapshots
    assert all(observed is snapshot.value for observed in loaded_snapshots)


@pytest.mark.asyncio
async def test_revoked_evidence_after_model_await_rejects_candidate_without_repair():
    authorization = AuthorizationPort()
    coordinator, snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING,
        authorization,
    )

    def revoke_current_state(_index):
        authorization.drop_sources.add("current-state")

    async with LocalChatEndpoint(
        ['{"action":"wait"}'],
        after_request=revoke_current_state,
    ) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            with pytest.raises(ContextError, match="evidence_not_authorized"):
                await executor.execute(
                    make_call(GameplayMode.CHARACTER_REASONING, '{"advice":"observe"}'),
                    AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
                )
        finally:
            await transport.aclose()

    assert len(endpoint.bodies) == 1
    assert snapshot.calls == 1


@pytest.mark.asyncio
async def test_revision_change_after_model_await_rejects_candidate_without_repair():
    authorization = AuthorizationPort()
    coordinator, snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING,
        authorization,
    )

    def advance_revision(_index):
        authorization.revision_delta = 1

    async with LocalChatEndpoint(
        ['{"action":"wait"}'],
        after_request=advance_revision,
    ) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            with pytest.raises(ContextError, match="stale_snapshot"):
                await executor.execute(
                    make_call(GameplayMode.CHARACTER_REASONING, '{"advice":"observe"}'),
                    AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
                )
        finally:
            await transport.aclose()

    assert len(endpoint.bodies) == 1
    assert snapshot.calls == 1


@pytest.mark.asyncio
async def test_narrative_request_omits_untrusted_player_task_text():
    coordinator, _snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.NARRATIVE_COMPILATION
    )
    async with LocalChatEndpoint(['{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            await executor.execute(
                make_call(
                    GameplayMode.NARRATIVE_COMPILATION,
                    '{"raw_input":"UNTRUSTED_PLAYER_QUOTE",'
                    '"disclosed_facts":"clue_with_no_display_name"}',
                ),
                AuthorizedExecutionBudget(output_tokens=32, timeout_seconds=5),
            )
        finally:
            await transport.aclose()

    assert len(endpoint.bodies) == 1
    body_text = request_text(endpoint.bodies[0])
    assert "The sealed door remained closed" in body_text
    assert "UNTRUSTED_PLAYER_QUOTE" not in body_text
    assert "clue_with_no_display_name" not in body_text


@pytest.mark.asyncio
async def test_request_byte_limit_rejects_before_network_send():
    coordinator, _snapshot, _authorization, _ports = build_coordinator(
        GameplayMode.CHARACTER_REASONING
    )
    async with LocalChatEndpoint(['{"action":"wait"}']) as endpoint:
        executor, transport = make_executor(coordinator, endpoint)
        try:
            with pytest.raises(ContextError, match="model_request_too_large"):
                await executor.execute(
                    make_call(
                        GameplayMode.CHARACTER_REASONING,
                        json.dumps({"advice": "x" * 1_000}, separators=(",", ":")),
                    ),
                    AuthorizedExecutionBudget(
                        output_tokens=32,
                        timeout_seconds=5,
                        max_request_bytes=512,
                    ),
                )
        finally:
            await transport.aclose()

    assert endpoint.bodies == []
