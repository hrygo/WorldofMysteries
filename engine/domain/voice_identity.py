"""Pure Domain value objects for stable voice identity and binding.

W-V04 deliberately separates presentation identity revisions from world facts.
Provider catalog/snapshot revisions are not voice identities; only an explicit
content-addressed voice revision may be used as a conditional synthesis pin.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re


_IDENTIFIER_LIMIT = 256
_MODEL_REVISION = re.compile(r"^[0-9a-f]{40}$")


class VoiceIdentityError(ValueError):
    """Voice identity or binding input violates a Domain invariant."""


class VoiceBindingConflict(VoiceIdentityError):
    """A caller attempted to evolve a stale binding revision."""


class VoiceIdentityAssurance(str, Enum):
    LEGACY = "legacy"
    CONTENT_ADDRESSED = "content_addressed"


class VoiceBindingStatus(str, Enum):
    RESERVED = "reserved"
    ACTIVE = "active"
    REVOKED = "revoked"


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _IDENTIFIER_LIMIT:
        raise VoiceIdentityError(f"{field} must be a bounded nonempty identifier")
    if "\x00" in value:
        raise VoiceIdentityError(f"{field} contains an invalid character")
    return value


@dataclass(frozen=True, slots=True)
class VoicePersonaRevision:
    """Immutable game-owned presentation persona revision."""

    logical_voice_id: str
    revision: str

    def __post_init__(self) -> None:
        _identifier(self.logical_voice_id, "logical_voice_id")
        _identifier(self.revision, "persona_revision")


@dataclass(frozen=True, slots=True)
class ProviderVoiceRevision:
    """Safe provider routing identity captured from capability discovery.

    model_catalog_revision is retained as a separate execution constraint.
    It must never be promoted into voice_revision or identity assurance.
    """

    provider_instance: str
    voice_id: str
    assurance: VoiceIdentityAssurance
    voice_revision: str | None = None
    model_catalog_revision: str | None = None
    revoked: bool = False

    def __post_init__(self) -> None:
        _identifier(self.provider_instance, "provider_instance")
        _identifier(self.voice_id, "voice_id")
        if not isinstance(self.assurance, VoiceIdentityAssurance):
            raise VoiceIdentityError("voice assurance is invalid")

        if self.assurance is VoiceIdentityAssurance.LEGACY:
            if self.voice_revision is not None:
                raise VoiceIdentityError(
                    "legacy assurance cannot carry a supposedly immutable voice revision"
                )
        else:
            if self.voice_revision is None:
                raise VoiceIdentityError(
                    "content-addressed assurance requires a voice revision"
                )
            _identifier(self.voice_revision, "voice_revision")

        if self.model_catalog_revision is not None:
            if _MODEL_REVISION.fullmatch(self.model_catalog_revision) is None:
                raise VoiceIdentityError(
                    "model catalog revision must be a lowercase 40-character hex revision"
                )

    @property
    def conditional_pin(self) -> str | None:
        """Revision suitable for provider conditional synthesis, if proven."""

        if self.assurance is VoiceIdentityAssurance.CONTENT_ADDRESSED and not self.revoked:
            return self.voice_revision
        return None

    @property
    def permits_new_render(self) -> bool:
        return not self.revoked


@dataclass(frozen=True, slots=True)
class VoiceBindingScope:
    """Stable presentation scope; hidden/canonical identity is intentionally absent."""

    owner_id: str
    world_id: str
    worldline_id: str
    presentation_identity: str
    phase: str
    locale: str

    def __post_init__(self) -> None:
        for field, value in (
            ("owner_id", self.owner_id),
            ("world_id", self.world_id),
            ("worldline_id", self.worldline_id),
            ("presentation_identity", self.presentation_identity),
            ("phase", self.phase),
            ("locale", self.locale),
        ):
            _identifier(value, field)


@dataclass(frozen=True, slots=True)
class VoiceBinding:
    """One durable presentation binding revision.

    binding_revision is presentation-domain CAS state. reserved_at_world_revision
    records the world snapshot that authorized the reservation, but it is not the
    binding revision and advancing the binding does not advance world truth.
    """

    binding_id: str
    scope: VoiceBindingScope
    persona: VoicePersonaRevision
    provider: ProviderVoiceRevision
    binding_revision: int
    status: VoiceBindingStatus
    reserved_at_world_revision: int

    def __post_init__(self) -> None:
        _identifier(self.binding_id, "binding_id")
        if type(self.binding_revision) is not int or self.binding_revision < 1:
            raise VoiceIdentityError("binding revision must be a positive integer")
        if type(self.reserved_at_world_revision) is not int or self.reserved_at_world_revision < 0:
            raise VoiceIdentityError("reserved world revision must be a nonnegative integer")
        if not isinstance(self.status, VoiceBindingStatus):
            raise VoiceIdentityError("binding status is invalid")

    @classmethod
    def reserve(
        cls,
        *,
        binding_id: str,
        scope: VoiceBindingScope,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
        world_revision: int,
    ) -> "VoiceBinding":
        if provider.revoked:
            raise VoiceIdentityError("a revoked provider voice cannot be newly reserved")
        return cls(
            binding_id=binding_id,
            scope=scope,
            persona=persona,
            provider=provider,
            binding_revision=1,
            status=VoiceBindingStatus.RESERVED,
            reserved_at_world_revision=world_revision,
        )

    def activate(self, *, expected_binding_revision: int) -> "VoiceBinding":
        self._require_revision(expected_binding_revision)
        if self.status is VoiceBindingStatus.REVOKED:
            raise VoiceIdentityError("a revoked binding cannot be activated")
        if self.provider.revoked:
            raise VoiceIdentityError("a revoked provider voice cannot be activated")
        if self.status is VoiceBindingStatus.ACTIVE:
            return self
        return replace(
            self,
            binding_revision=self.binding_revision + 1,
            status=VoiceBindingStatus.ACTIVE,
        )

    def rebind(
        self,
        *,
        expected_binding_revision: int,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
    ) -> "VoiceBinding":
        self._require_revision(expected_binding_revision)
        if self.status is VoiceBindingStatus.REVOKED:
            raise VoiceIdentityError("a revoked binding cannot be rebound")
        if provider.revoked:
            raise VoiceIdentityError("a revoked provider voice cannot be bound")
        return replace(
            self,
            persona=persona,
            provider=provider,
            binding_revision=self.binding_revision + 1,
            status=VoiceBindingStatus.RESERVED,
        )

    def revoke(self, *, expected_binding_revision: int) -> "VoiceBinding":
        self._require_revision(expected_binding_revision)
        if self.status is VoiceBindingStatus.REVOKED:
            return self
        return replace(
            self,
            binding_revision=self.binding_revision + 1,
            status=VoiceBindingStatus.REVOKED,
        )

    @property
    def permits_new_render(self) -> bool:
        return (
            self.status is VoiceBindingStatus.ACTIVE
            and self.provider.permits_new_render
        )

    def _require_revision(self, expected: int) -> None:
        if type(expected) is not int or expected != self.binding_revision:
            raise VoiceBindingConflict("expected binding revision does not match")
