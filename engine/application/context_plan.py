"""Internal, immutable context IR. Not an IPC DTO or an authorization service.

Domain-owned authorization must grant the *complete* evidence fingerprint, including
its provenance and placement. A caller constructing a grant set is a trusted part
of the application, never a model, plugin, or an untrusted IPC request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
import hashlib
import json
from typing import Any


class ContextError(ValueError):
    """A safe error code; do not attach rejected source text to this exception."""


def canonical_json(value: Any) -> str:
    """Preserve strings and array order; reject non-JSON keys and nonfinite values."""
    def validate(item: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ContextError("json_depth_exceeded")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ContextError("non_string_json_key")
            for child in item.values():
                validate(child, depth + 1)
        elif type(item) in (list, tuple):
            for child in item:
                validate(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ContextError("unsupported_json_value")
    try:
        validate(value)
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ContextError("invalid_json") from None


def parse_json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ContextError("duplicate_json_key")
            result[key] = value
        return result
    try:
        result = json.loads(text, object_pairs_hook=pairs)
        canonical_json(result)
        return result
    except (ValueError, TypeError, RecursionError):
        raise ContextError("invalid_json") from None


def digest(value: Any) -> str:
    """Internal content identity, not a signature or a safe-to-publish secret hash."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ContextError("invalid_identifier")


def natural(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ContextError("invalid_revision")


class Layer(IntEnum):
    STATIC = 0
    CORE = 1
    CHECKPOINT = 2
    HISTORY = 3
    STATE = 4
    RECALL = 5


@dataclass(frozen=True, repr=False)
class ContextScope:
    owner_id: str
    world_id: str
    worldline_id: str
    consumer: str
    subject_id: str
    session_id: str
    policy_revision: str
    lineage_digest: str

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            identifier(value)


@dataclass(frozen=True, repr=False)
class Evidence:
    source_id: str
    source_revision: int
    kind: str
    layer: Layer
    content_json: str = field(repr=False)
    world_id: str | None = None
    worldline_id: str | None = None
    subject_id: str | None = None
    available_at_tick: int = 0
    committed_revision: int | None = None
    sequence: int | None = None

    def __post_init__(self) -> None:
        identifier(self.source_id)
        identifier(self.kind)
        natural(self.source_revision)
        natural(self.available_at_tick)
        if not isinstance(self.layer, Layer):
            raise ContextError("invalid_layer")
        for value in (self.world_id, self.worldline_id, self.subject_id):
            if value is not None:
                identifier(value)
        for value in (self.committed_revision, self.sequence):
            if value is not None:
                natural(value)
        if (self.world_id is None) != (self.worldline_id is None):
            raise ContextError("incomplete_source_scope")
        if self.worldline_id is not None and self.committed_revision is None:
            raise ContextError("uncommitted_world_evidence")
        if self.layer == Layer.HISTORY and (
            self.sequence is None or self.committed_revision is None or self.worldline_id is None
        ):
            raise ContextError("uncommitted_history")
        if self.layer != Layer.HISTORY and self.sequence is not None:
            raise ContextError("sequence_outside_history")
        object.__setattr__(self, "content_json", canonical_json(parse_json(self.content_json)))

    @property
    def fingerprint(self) -> str:
        data = asdict(self)
        data["layer"] = int(self.layer)
        return digest(data)

    def model_value(self) -> dict[str, Any]:
        # Do not send the authorization manifest, excluded counts or debug metadata.
        return {"source_id": self.source_id, "source_revision": self.source_revision,
                "kind": self.kind, "content": parse_json(self.content_json)}


@dataclass(frozen=True, repr=False)
class AuthorizationView:
    """Fresh Domain-issued eligible set; no candidate can authorize itself.

    Ancestor limits are inclusive commit revisions at each fork boundary. The
    issuer must resolve knowledge, disclosure, time and source provenance before
    constructing this view. This library does not query Domain databases.
    """
    scope: ContextScope
    world_revision: int
    story_revision: int
    world_tick: int
    grants: frozenset[str]
    ancestor_limits: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        for value in (self.world_revision, self.story_revision, self.world_tick):
            natural(value)
        object.__setattr__(self, "grants", frozenset(self.grants))
        limits = tuple((line, revision) for line, revision in self.ancestor_limits)
        if len({line for line, _ in limits}) != len(limits):
            raise ContextError("duplicate_ancestor")
        for line, revision in limits:
            identifier(line)
            natural(revision)
            if line == self.scope.worldline_id:
                raise ContextError("self_ancestor")
        object.__setattr__(self, "ancestor_limits", limits)


@dataclass(frozen=True, repr=False)
class WorkerProfile:
    """Application-owned prompt registry entry, never supplied by the LLM."""
    consumer: str
    prompt_revision: str
    instructions: str = field(repr=False)
    schema_json: str = field(repr=False)
    tools_json: str = field(default="[]", repr=False)

    def __post_init__(self) -> None:
        identifier(self.consumer)
        identifier(self.prompt_revision)
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ContextError("missing_instructions")
        schema, tools = parse_json(self.schema_json), parse_json(self.tools_json)
        if not isinstance(schema, dict) or not isinstance(tools, list):
            raise ContextError("invalid_profile_contract")
        object.__setattr__(self, "schema_json", canonical_json(schema))
        object.__setattr__(self, "tools_json", canonical_json(tools))


@dataclass(frozen=True, repr=False)
class ContextInput:
    scope: ContextScope
    world_revision: int
    story_revision: int
    epoch_id: str
    evidence: tuple[Evidence, ...]
    task_json: str = field(repr=False)
    request_id: str = field(repr=False)

    def __post_init__(self) -> None:
        identifier(self.epoch_id)
        identifier(self.request_id)
        natural(self.world_revision)
        natural(self.story_revision)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "task_json", canonical_json(parse_json(self.task_json)))


@dataclass(frozen=True, repr=False)
class PromptPlan:
    profile: WorkerProfile
    context: ContextInput
    ordered_evidence: tuple[Evidence, ...]
    compiler_revision: str = "cache-aware-v1"

    @property
    def stable_evidence(self) -> tuple[Evidence, ...]:
        return tuple(e for e in self.ordered_evidence if e.layer < Layer.STATE)

    @property
    def dynamic_evidence(self) -> tuple[Evidence, ...]:
        return tuple(e for e in self.ordered_evidence if e.layer >= Layer.STATE)
