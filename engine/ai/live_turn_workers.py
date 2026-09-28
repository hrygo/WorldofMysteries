"""Live model workers for the interpretation, proposal and narrative stages.

Deterministic fixture workers provide content authored at build time.  This
module provides the three model-controlled stages a real session needs, each
one strictly bounded:

``LiveAdviceInterpreter``
    durable ``PlayerAdvice`` semantics for whatever the player actually said,
    including a SpeechRail transcript.

``LiveActionIntentProposer``
    the protagonist's bounded action proposal.  Turn identity, actor identity and
    evidence references are still bound by ``AdviceActionIntentService``; this
    worker only supplies semantics.

``LiveNarrativeCompiler``
    the post-COMMIT expression stage.  It runs *after* the durable commit and
    therefore cannot influence Domain state (invariant 9).

Every worker validates the model reply against the existing Application
candidate types before returning.  A malformed, oversized, unreachable or
non-JSON reply raises; nothing degrades to canned text.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from application.advice_action import (
    ActionIntentCandidate,
    AdviceActionError,
    ActionIntentScope,
)
from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.narrative_publication import (
    NarrativeCandidate,
    NarrativeCompilerPort,
    NarrativePublicationError,
)
from application.scenario_policy import ActionSignature
from application.story_initialization import StorySessionBootstrap
from contracts import AdherenceType, InputMode, PlayerAdvice
from contracts.models import IntentAction

from .openai_compatible import (
    ModelEndpointConfig,
    ModelTransportError,
    OpenAICompatibleChatTransport,
    chat_wire,
)

_REPAIR_HINT = (
    "Return one valid JSON object matching the requested keys. "
    "No markdown, no code fence, no commentary."
)
_DEFAULT_TIMEOUT_SECONDS = 45.0
_MAX_ACTIONS = 8
_MAX_SECONDARY_INTENTS = 8
_MAX_NARRATIVE_CHARS = 1200


class LiveWorkerError(RuntimeError):
    """A live model worker could not produce a schema-valid candidate."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    body = lines[1:-1]
    if body and body[0].strip().lower().startswith("json"):
        body = body[1:]
    return "\n".join(body).strip()


def _object_from_reply(text: str) -> dict[str, Any]:
    candidate = _strip_fence(text)
    if not candidate:
        raise LiveWorkerError("model_reply_not_json")
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        raise LiveWorkerError("model_reply_not_json")
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        raise LiveWorkerError("model_reply_not_json") from None
    if not isinstance(parsed, dict):
        raise LiveWorkerError("model_reply_not_json")
    return parsed


def _bounded_text(value: object, limit: int, *, field: str, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise LiveWorkerError(f"invalid_{field}")
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise LiveWorkerError(f"invalid_{field}")
    return value.strip()


def _bounded_number(value: object, *, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveWorkerError(f"invalid_{field}")
    number = float(value)
    if not minimum <= number <= maximum or number != number:
        raise LiveWorkerError(f"invalid_{field}")
    return number


def _string_tuple(
    value: object, *, field: str, minimum: int, maximum: int, limit: int
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise LiveWorkerError(f"invalid_{field}")
    if not minimum <= len(value) <= maximum:
        raise LiveWorkerError(f"invalid_{field}")
    items: list[str] = []
    for item in value:
        text = _bounded_text(item, limit, field=field)
        assert text is not None
        items.append(text)
    if len(set(items)) != len(items):
        raise LiveWorkerError(f"invalid_{field}")
    return tuple(items)


@dataclass(frozen=True, slots=True)
class _SceneBrief:
    """The only world context a turn worker is allowed to see.

    Invariant 6 (zero knowledge leak) and invariant 7 (semantic authorization
    first) mean a worker may not read Domain state directly.  This brief is the
    already-authorized projection the Content Compiler produced for the frozen
    scenario, and it carries no secret, no unseen fact and no other session.
    """

    scenario_id: str
    world_name: str
    location_name: str
    protagonist_name: str
    protagonist_role: str
    title: str

    @classmethod
    def from_bootstrap(cls, bootstrap: StorySessionBootstrap) -> _SceneBrief:
        character = bootstrap.character if isinstance(bootstrap.character, Mapping) else {}
        identity = character.get("identity") if isinstance(character, Mapping) else {}
        core = character.get("core") if isinstance(character, Mapping) else {}
        world = bootstrap.world if isinstance(bootstrap.world, Mapping) else {}
        presentation = bootstrap.presentation
        return cls(
            scenario_id=bootstrap.scenario_id,
            world_name=str(world.get("name") or bootstrap.scenario_id),
            location_name=presentation.scene_display_name,
            protagonist_name=str(
                (identity or {}).get("display_name")
                or bootstrap.initial_session.protagonist_id
            ),
            protagonist_role=str((core or {}).get("role") or "未知身份"),
            title=presentation.scenario_title,
        )

    def prompt(self) -> str:
        return (
            f"场景：{self.world_name}，地点：{self.location_name}\n"
            f"视角人物：{self.protagonist_name}（{self.protagonist_role}）\n"
            f"篇章：{self.title}"
        )


class _StructuredWorker:
    """Shared one-call JSON worker with a single bounded repair attempt."""

    def __init__(
        self,
        transport: OpenAICompatibleChatTransport,
        *,
        output_tokens: int,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        revision: str,
    ) -> None:
        if not isinstance(transport, OpenAICompatibleChatTransport):
            raise LiveWorkerError("invalid_model_endpoint")
        self._transport = transport
        self._target = transport.config.provider_profile()
        self._output_tokens = output_tokens
        self._timeout = timeout_seconds
        self._revision = revision

    @property
    def revision(self) -> str:
        return self._revision

    async def _ask(self, system: str, user: str) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(2):
            wire = chat_wire(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                target=self._target,
                output_tokens=self._output_tokens,
                json_mode=True,
                repair_hint=_REPAIR_HINT if attempt else None,
            )
            try:
                async with asyncio.timeout(self._timeout):
                    reply = await self._transport.send(wire)
            except (TimeoutError, asyncio.TimeoutError):
                last = LiveWorkerError("model_stage_timeout")
            except ModelTransportError as exc:
                last = LiveWorkerError(exc.code)
            except asyncio.CancelledError:
                raise
            except Exception:
                last = LiveWorkerError("model_stage_failed")
            else:
                try:
                    return _object_from_reply(reply.text)
                except LiveWorkerError as exc:
                    last = exc
        raise last or LiveWorkerError("model_stage_failed")


class LiveAdviceInterpreter(_StructuredWorker):
    """Interpret arbitrary player input, including a voice transcript."""

    def __init__(self, transport: OpenAICompatibleChatTransport, brief: _SceneBrief) -> None:
        super().__init__(transport, output_tokens=512, revision="wom-live-interpreter-v1")
        self._brief = brief

    async def interpret(self, value: FrozenTurnInput) -> AdviceInterpretationCandidate:
        if not isinstance(value, FrozenTurnInput):
            raise AdviceInterpretationError("invalid_interpretation_candidate")
        if value.input_mode not in (InputMode.TEXT, InputMode.VOICE):
            raise AdviceInterpretationError("deterministic_input_unsupported")

        spoken = "（玩家使用语音输入，内容来自实时语音识别）" if value.input_mode is InputMode.VOICE else "（玩家使用文本输入）"
        payload = await self._ask(
            "你是《诡秘世界》玩家意图解析器。只输出一个 JSON 对象，"
            "键为 primary_intent(string)、secondary_intents(string[]，可为空)、"
            "proposed_actions(string[]，1 到 8 条，每条是不超过 24 字的行动短语)、"
            "risk_preference(string 或 null)、confidence(number，0 到 1)。"
            "你只解释玩家想做什么，不得虚构世界事实，也不得给出数值结算结果。",
            f"{self._brief.prompt()}\n{spoken}\n"
            f"玩家原话：{value.raw_input}",
        )
        try:
            primary = _bounded_text(payload.get("primary_intent"), 128, field="primary_intent")
            secondary = _string_tuple(
                payload.get("secondary_intents") or [],
                field="secondary_intents",
                minimum=0,
                maximum=_MAX_SECONDARY_INTENTS,
                limit=128,
            )
            actions = _string_tuple(
                payload.get("proposed_actions"),
                field="proposed_actions",
                minimum=1,
                maximum=32,
                limit=64,
            )
            risk = _bounded_text(
                payload.get("risk_preference"), 128, field="risk_preference", required=False
            )
            confidence = _bounded_number(
                payload.get("confidence"), field="confidence", minimum=0.0, maximum=1.0
            )
        except LiveWorkerError as exc:
            raise AdviceInterpretationError("model_proposal_invalid") from exc
        assert primary is not None
        return AdviceInterpretationCandidate(
            interpreter_revision=self._revision,
            primary_intent=primary,
            secondary_intents=secondary,
            proposed_actions=actions,
            risk_preference=risk,
            confidence=confidence,
        )


class LiveActionIntentProposer(_StructuredWorker):
    """Propose the protagonist's bounded action intent for one committed input."""

    def __init__(
        self,
        transport: OpenAICompatibleChatTransport,
        brief: _SceneBrief,
        allowed_signatures: tuple[tuple[str, tuple[str, ...]], ...],
    ) -> None:
        super().__init__(transport, output_tokens=768, revision="wom-live-proposer-v1")
        self._brief = brief
        if not allowed_signatures:
            raise LiveWorkerError("empty_resolution_policy")
        self._allowed = allowed_signatures

    async def propose(
        self,
        *,
        frozen: FrozenTurnInput,
        advice: PlayerAdvice,
        scope: ActionIntentScope,
    ) -> ActionIntentCandidate:
        if not isinstance(advice, PlayerAdvice) or not isinstance(scope, ActionIntentScope):
            raise AdviceActionError("invalid_player_advice")

        # The deterministic resolver only accepts signatures that a validated
        # resolution rule covers. Offering the model anything else would let it
        # author semantics the Domain is unable to commit, so the validated set
        # is stated explicitly and re-checked on the way back.
        allowed = "；".join(
            f"intent 固定为 {intent}，且 actions 数组必须恰好是 {list(types)}"
            f"（长度 {len(types)}，每个 type 各出现一次，不得增删）"
            for intent, types in self._allowed
        )
        payload = await self._ask(
            "你是《诡秘世界》角色行动提案器。只输出一个 JSON 对象，键为 "
            "intent(string)、adherence(string，只能是 full 或 partial)、"
            "actions(数组，1 到 8 项，每项键 type(string)、purpose(string 或 null)、"
            "target_ids(string[] 或 null)、parameters(object 或 null))、"
            "reason_summary(string 或 null)、speech_intent(string 或 null)。"
            "角色有自己的动机：玩家只是建议，角色可以只部分配合。"
            "不得虚构玩家未获得的线索，也不得写入任何世界数值。"
            f"intent 与 actions 的 type 组合只能从以下已验证方案中二选一或照抄：{allowed}。"
            "你负责的是语义（purpose、reason_summary、speech_intent），"
            "intent 与动作类型必须原样使用上述已验证取值。",
            f"{self._brief.prompt()}\n"
            f"玩家行动：{advice.raw_input}\n"
            f"已解析意图：{advice.primary_intent}\n"
            f"玩家建议的行动：{'、'.join(advice.proposed_actions)}",
        )
        try:
            intent = _bounded_text(payload.get("intent"), 128, field="intent")
            adherence_raw = _bounded_text(
                payload.get("adherence"), 32, field="adherence"
            )
            assert adherence_raw is not None
            try:
                adherence = AdherenceType(adherence_raw)
            except ValueError:
                raise LiveWorkerError("invalid_adherence") from None
            actions = self._actions(payload.get("actions"))
            reason = _bounded_text(
                payload.get("reason_summary"), 2048, field="reason_summary", required=False
            )
            speech = _bounded_text(
                payload.get("speech_intent"), 1024, field="speech_intent", required=False
            )
        except LiveWorkerError as exc:
            raise AdviceActionError("model_proposal_invalid") from exc
        except (TypeError, ValueError) as exc:
            raise AdviceActionError("model_proposal_invalid") from exc
        assert intent is not None
        signature = intent, tuple(sorted(action.type for action in actions))
        if signature not in self._allowed:
            # A proposal the validated policy cannot resolve is a capability
            # outage for this turn, not a malformed request: the pre-COMMIT
            # input receipt stays durable and a retry replays the same turn id.
            raise AdviceActionError("unresolvable_action_intent")
        return ActionIntentCandidate(
            proposer_revision=self._revision,
            intent=intent,
            adherence=adherence,
            actions=actions,
            reason_summary=reason,
            speech_intent=speech,
        )

    @staticmethod
    def _actions(value: object) -> tuple[IntentAction, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise LiveWorkerError("invalid_actions")
        if not 1 <= len(value) <= _MAX_ACTIONS:
            raise LiveWorkerError("invalid_actions")
        actions: list[IntentAction] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise LiveWorkerError("invalid_actions")
            targets = item.get("target_ids")
            if targets is not None:
                targets = list(
                    _string_tuple(
                        targets,
                        field="action_targets",
                        minimum=0,
                        maximum=16,
                        limit=256,
                    )
                )
            parameters = item.get("parameters")
            if parameters is not None and not isinstance(parameters, Mapping):
                raise LiveWorkerError("invalid_action_parameters")
            try:
                # `target_ids` / `parameters` may be omitted but must never be
                # explicit nulls; a model that emits `"parameters": null` is
                # describing an absent value, so drop the key instead of
                # forwarding a null the contract rejects.
                candidate: dict[str, Any] = {
                    "type": _bounded_text(item.get("type"), 128, field="action_type"),
                    "purpose": _bounded_text(
                        item.get("purpose"), 512, field="action_purpose", required=False
                    ),
                }
                if targets is not None:
                    candidate["target_ids"] = targets
                if parameters is not None:
                    candidate["parameters"] = dict(parameters)
                actions.append(
                    IntentAction.model_validate(candidate)
                )
            except LiveWorkerError:
                raise
            except (TypeError, ValueError):
                raise LiveWorkerError("invalid_actions") from None
        return tuple(actions)


class LiveNarrativeCompiler(_StructuredWorker):
    """Post-COMMIT expression stage: narrate what the Domain already decided.

    This worker runs strictly after ``COMMIT`` and only reads already-committed
    facts.  It cannot propose a state change: the deterministic resolver and the
    validators own every effect (invariant 9).
    """

    def __init__(self, transport: OpenAICompatibleChatTransport, brief: _SceneBrief) -> None:
        super().__init__(transport, output_tokens=900, revision="wom-live-narrative-v1")
        self._brief = brief

    async def compile(self, *, committed: str) -> NarrativeCandidate:
        """Render committed facts without assigning a speaker identity."""
        if not isinstance(committed, str) or not committed.strip():
            raise LiveWorkerError("invalid_narrative_source")
        payload = await self._ask(
            "你是《诡秘世界》叙事编译器。只输出一个 JSON 对象，键为 "
            "narration(string) 与 speech(string)。两者都是已经发生事实的口语化转述："
            "不得引入新线索、不得改变结果、不得替玩家说话。"
            "speech 是角色实际说出口的那句话，narration 是对场景与反应的客观描写。"
            f"总长度不超过 {_MAX_NARRATIVE_CHARS} 个字。",
            f"{self._brief.prompt()}\n已提交的事实：{committed.strip()}",
        )
        if "narration" not in payload or set(payload) - {"narration", "speech"}:
            raise LiveWorkerError("narrative_model_invalid")
        try:
            narration = _bounded_text(
                payload.get("narration"), _MAX_NARRATIVE_CHARS, field="narration"
            )
            raw_speech = payload.get("speech")
            if raw_speech is None:
                speech = ""
            elif (
                not isinstance(raw_speech, str)
                or "\x00" in raw_speech
                or len(raw_speech) > _MAX_NARRATIVE_CHARS
            ):
                raise LiveWorkerError("invalid_speech")
            else:
                # Empty dialogue is a valid narration-only result. The durable
                # block will contain no character segment, so no audio can be
                # sealed from it.
                speech = raw_speech.strip()
            assert narration is not None
            return NarrativeCandidate(narration=narration, speech=speech)
        except LiveWorkerError as exc:
            raise LiveWorkerError("narrative_model_invalid") from exc
        except NarrativePublicationError as exc:
            raise LiveWorkerError("narrative_model_invalid") from exc


class LiveFirstTurnFactory:
    """Create live model workers for a scenario-selected turn.

    The application supplies allowed action signatures from the trusted
    scenario policy. This factory creates workers only; it owns no turn limit,
    fixed input, resolver policy, or Domain validation context.
    """

    def __init__(
        self,
        transport: OpenAICompatibleChatTransport,
    ) -> None:
        if not isinstance(transport, OpenAICompatibleChatTransport):
            raise LiveWorkerError("invalid_model_endpoint")
        self._transport = transport

    @classmethod
    def from_config(cls, config: ModelEndpointConfig) -> "LiveFirstTurnFactory":
        return cls(OpenAICompatibleChatTransport(config))

    @property
    def supports_live_input(self) -> bool:
        return True

    def _brief(self, bootstrap: StorySessionBootstrap) -> _SceneBrief:
        return _SceneBrief.from_bootstrap(bootstrap)

    def interpreter_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ) -> LiveAdviceInterpreter:
        if turn_number < 1:
            raise LiveWorkerError("invalid_turn_number")
        return LiveAdviceInterpreter(self._transport, self._brief(bootstrap))

    def proposer_for(
        self,
        bootstrap: StorySessionBootstrap,
        turn_number: int,
        allowed_signatures: tuple[ActionSignature, ...],
    ) -> LiveActionIntentProposer:
        if turn_number < 1:
            raise LiveWorkerError("invalid_turn_number")
        return LiveActionIntentProposer(
            self._transport,
            self._brief(bootstrap),
            allowed_signatures,
        )

    def narrative_compiler(
        self, bootstrap: StorySessionBootstrap
    ) -> NarrativeCompilerPort:
        return LiveNarrativeCompiler(self._transport, self._brief(bootstrap))

    async def aclose(self) -> None:
        await self._transport.aclose()


__all__ = [
    "LiveActionIntentProposer",
    "LiveAdviceInterpreter",
    "LiveFirstTurnFactory",
    "LiveNarrativeCompiler",
    "LiveWorkerError",
]
