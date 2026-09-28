"""Application-owned identities for immutable authorized context snapshots."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal, Protocol

from .context_plan import PromptPlan, canonical_json, digest

TurnContextStage = Literal["interpretation", "action", "narrative"]
_STAGES = frozenset({"interpretation", "action", "narrative"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_SOURCES = 8192
_MAX_MANIFEST_BYTES = 1_048_576


class TurnContextBindingError(RuntimeError):
    """A context binding cannot be created or safely reused."""

    def __init__(self, code: str) -> None:
        if code not in {
            "context_stale",
            "legacy_context_unbound",
            "revision_conflict",
            "turn_identity_conflict",
        }:
            code = "revision_conflict"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TurnContextBindingIdentity:
    """Trusted turn identity supplied by the orchestration boundary."""

    turn_id: str
    stage: TurnContextStage
    input_turn_id: str
    content_digest: str
    source_store_revision: int | None = None
    source_story_revision: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("turn_id", self.turn_id),
            ("input_turn_id", self.input_turn_id),
            ("content_digest", self.content_digest),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 256
                or "\x00" in value
            ):
                raise ValueError(f"invalid_{name}")
        if not isinstance(self.stage, str) or self.stage not in _STAGES:
            raise ValueError("invalid_turn_context_stage")
        for revision in (
            self.source_store_revision,
            self.source_story_revision,
        ):
            if revision is not None and (
                type(revision) is not int or not 0 <= revision < 2**63
            ):
                raise ValueError("invalid_turn_context_revision")


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedContextSource:
    """Authorized source identity only; evidence bodies are never retained."""

    source_id: str
    source_revision: int
    fingerprint: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id.strip()
            or len(self.source_id) > 256
            or "\x00" in self.source_id
            or type(self.source_revision) is not int
            or not 0 <= self.source_revision < 2**63
            or not isinstance(self.fingerprint, str)
            or _SHA256.fullmatch(self.fingerprint) is None
        ):
            raise ValueError("invalid_turn_context_source")


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizedTurnContextBinding:
    """Server-derived context identity suitable for application and storage ports."""

    turn_id: str
    stage: TurnContextStage
    input_turn_id: str
    source_store_revision: int
    source_story_revision: int
    policy_revision: str
    content_digest: str
    lineage_digest: str
    manifest: tuple[AuthorizedContextSource, ...] = field(repr=False)
    context_revision: str = field(init=False)
    manifest_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("turn_id", self.turn_id),
            ("input_turn_id", self.input_turn_id),
            ("policy_revision", self.policy_revision),
            ("content_digest", self.content_digest),
            ("lineage_digest", self.lineage_digest),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 256
                or "\x00" in value
            ):
                raise ValueError(f"invalid_{name}")
        if not isinstance(self.stage, str) or self.stage not in _STAGES:
            raise ValueError("invalid_turn_context_stage")
        for revision in (
            self.source_store_revision,
            self.source_story_revision,
        ):
            if type(revision) is not int or not 0 <= revision < 2**63:
                raise ValueError("invalid_turn_context_revision")

        sources = tuple(self.manifest)
        if (
            len(sources) > _MAX_SOURCES
            or any(not isinstance(source, AuthorizedContextSource) for source in sources)
            or len({source.source_id for source in sources}) != len(sources)
        ):
            raise ValueError("invalid_turn_context_manifest")

        manifest_json = canonical_json(
            [
                {
                    "source_id": source.source_id,
                    "source_revision": source.source_revision,
                    "fingerprint": source.fingerprint,
                }
                for source in sources
            ]
        )
        if len(manifest_json.encode("utf-8")) > _MAX_MANIFEST_BYTES:
            raise ValueError("turn_context_manifest_too_large")
        manifest_digest = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
        context_revision = digest(
            {
                "turn_id": self.turn_id,
                "stage": self.stage,
                "input_turn_id": self.input_turn_id,
                "source_store_revision": self.source_store_revision,
                "source_story_revision": self.source_story_revision,
                "policy_revision": self.policy_revision,
                "content_digest": self.content_digest,
                "lineage_digest": self.lineage_digest,
                "manifest_digest": manifest_digest,
            }
        )
        object.__setattr__(self, "manifest", sources)
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "context_revision", context_revision)

    @classmethod
    def from_plan(
        cls,
        plan: PromptPlan,
        *,
        stage: TurnContextStage,
        turn_id: str,
        input_turn_id: str,
        content_digest: str,
    ) -> AuthorizedTurnContextBinding:
        context = plan.context
        return cls(
            turn_id=turn_id,
            stage=stage,
            input_turn_id=input_turn_id,
            source_store_revision=context.world_revision,
            source_story_revision=context.story_revision,
            policy_revision=context.scope.policy_revision,
            content_digest=content_digest,
            lineage_digest=context.scope.lineage_digest,
            manifest=tuple(
                AuthorizedContextSource(
                    source_id=evidence.source_id,
                    source_revision=evidence.source_revision,
                    fingerprint=evidence.fingerprint,
                )
                for evidence in plan.ordered_evidence
            ),
        )

    @property
    def authorized_source_ids(self) -> frozenset[str]:
        return frozenset(source.source_id for source in self.manifest)

    def same_snapshot(self, other: object) -> bool:
        return (
            isinstance(other, AuthorizedTurnContextBinding)
            and self.source_store_revision == other.source_store_revision
            and self.source_story_revision == other.source_story_revision
            and self.policy_revision == other.policy_revision
            and self.content_digest == other.content_digest
            and self.lineage_digest == other.lineage_digest
        )


class TurnContextBindingPort(Protocol):
    async def save(
        self, binding: AuthorizedTurnContextBinding
    ) -> AuthorizedTurnContextBinding: ...

    async def load(
        self,
        *,
        turn_id: str,
        stage: TurnContextStage,
    ) -> AuthorizedTurnContextBinding | None: ...


__all__ = [
    "AuthorizedContextSource",
    "AuthorizedTurnContextBinding",
    "TurnContextBindingError",
    "TurnContextBindingIdentity",
    "TurnContextBindingPort",
    "TurnContextStage",
]
