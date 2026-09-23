"""Authorization-first W-V05 voice casting policy.

This module receives only presentation-safe candidate metadata and an explicit
authorization grant set. It never reads Domain/DB state, provider APIs, hidden
identity, or canonical facts. Existing durable bindings are hard locks unless
their revision is no longer authorized or renderable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
)


VoiceRevisionKey = tuple[str, str, str | None]
AudibleVoiceKey = tuple[str, str]


class VoiceCastingPolicyError(RuntimeError):
    """A casting decision cannot be made without crossing a safety boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise VoiceCastingPolicyError(f"invalid_{field}")
    return value.strip()


def _normalized(values: frozenset[str], field: str) -> frozenset[str]:
    try:
        normalized = frozenset(_text(value, field).casefold() for value in values)
    except TypeError:
        raise VoiceCastingPolicyError(f"invalid_{field}") from None
    if not normalized:
        raise VoiceCastingPolicyError(f"missing_{field}")
    return normalized


def voice_revision_key(provider: ProviderVoiceRevision) -> VoiceRevisionKey:
    return (provider.provider_instance, provider.voice_id, provider.voice_revision)


def audible_voice_key(provider: ProviderVoiceRevision) -> AudibleVoiceKey:
    # Different immutable revisions of the same provider voice can still reveal
    # the same audible identity, so co-scene distinctness ignores revision here.
    return (provider.provider_instance, provider.voice_id)


@dataclass(frozen=True, slots=True)
class VoiceCandidate:
    """One sanitized candidate visible to the casting policy."""

    provider: ProviderVoiceRevision
    locales: frozenset[str]
    allowed_usages: frozenset[str]
    public_traits: frozenset[str]
    available: bool
    production_ready: bool
    rights_granted: bool
    quality_approved: bool
    explicit_legacy_approval: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "locales", _normalized(self.locales, "locale"))
        object.__setattr__(
            self, "allowed_usages", _normalized(self.allowed_usages, "usage")
        )
        traits = frozenset(
            _text(value, "public_trait").casefold() for value in self.public_traits
        )
        object.__setattr__(self, "public_traits", traits)
        for field in (
            "available",
            "production_ready",
            "rights_granted",
            "quality_approved",
            "explicit_legacy_approval",
        ):
            if type(getattr(self, field)) is not bool:
                raise VoiceCastingPolicyError(f"invalid_{field}")

    @property
    def revision_key(self) -> VoiceRevisionKey:
        return voice_revision_key(self.provider)

    @property
    def audible_key(self) -> AudibleVoiceKey:
        return audible_voice_key(self.provider)


@dataclass(frozen=True, slots=True)
class CastingPolicyRequest:
    """Fresh authorization and public presentation inputs for one casting choice."""

    locale: str
    usage: str
    authorized_voice_revisions: frozenset[VoiceRevisionKey]
    occupied_audible_voices: frozenset[AudibleVoiceKey]
    desired_public_traits: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "locale", _text(self.locale, "locale").casefold())
        object.__setattr__(self, "usage", _text(self.usage, "usage").casefold())
        object.__setattr__(
            self,
            "desired_public_traits",
            frozenset(
                _text(value, "public_trait").casefold()
                for value in self.desired_public_traits
            ),
        )
        object.__setattr__(
            self, "authorized_voice_revisions", frozenset(self.authorized_voice_revisions)
        )
        object.__setattr__(
            self, "occupied_audible_voices", frozenset(self.occupied_audible_voices)
        )
        for key in self.authorized_voice_revisions:
            if (
                type(key) is not tuple
                or len(key) != 3
                or any(type(value) is not str or not value for value in key[:2])
                or (key[2] is not None and (type(key[2]) is not str or not key[2]))
            ):
                raise VoiceCastingPolicyError("invalid_authorized_voice_revision")
        for key in self.occupied_audible_voices:
            if (
                type(key) is not tuple
                or len(key) != 2
                or any(type(value) is not str or not value for value in key)
            ):
                raise VoiceCastingPolicyError("invalid_occupied_audible_voice")


@dataclass(frozen=True, slots=True)
class CastingDecision:
    provider: ProviderVoiceRevision
    source: Literal["existing_binding", "candidate"]
    matched_public_traits: int


class VoiceCastingPolicy:
    """Hard-filter before ranking; never recast an authorized durable binding."""

    def choose(
        self,
        request: CastingPolicyRequest,
        candidates: tuple[VoiceCandidate, ...],
        *,
        existing_binding: VoiceBinding | None = None,
    ) -> CastingDecision:
        if existing_binding is not None:
            if (
                existing_binding.status is not VoiceBindingStatus.ACTIVE
                or not existing_binding.permits_new_render
            ):
                raise VoiceCastingPolicyError("existing_voice_not_renderable")
            if (
                voice_revision_key(existing_binding.provider)
                not in request.authorized_voice_revisions
            ):
                raise VoiceCastingPolicyError("existing_voice_not_authorized")
            return CastingDecision(
                provider=existing_binding.provider,
                source="existing_binding",
                matched_public_traits=0,
            )

        seen: set[VoiceRevisionKey] = set()
        eligible: list[tuple[VoiceCandidate, int]] = []
        for candidate in candidates:
            key = candidate.revision_key
            if key in seen:
                raise VoiceCastingPolicyError("duplicate_voice_candidate")
            seen.add(key)

            if key not in request.authorized_voice_revisions:
                continue
            if candidate.provider.revoked:
                continue
            if not (
                candidate.available
                and candidate.production_ready
                and candidate.rights_granted
                and candidate.quality_approved
            ):
                continue
            if request.locale not in candidate.locales:
                continue
            if request.usage not in candidate.allowed_usages:
                continue
            if candidate.audible_key in request.occupied_audible_voices:
                continue
            if (
                candidate.provider.assurance is VoiceIdentityAssurance.LEGACY
                and not candidate.explicit_legacy_approval
            ):
                continue

            matched = len(
                request.desired_public_traits.intersection(candidate.public_traits)
            )
            eligible.append((candidate, matched))

        if not eligible:
            raise VoiceCastingPolicyError("no_authorized_voice_candidate")

        candidate, matched = min(
            eligible,
            key=lambda item: (
                -item[1],
                item[0].provider.provider_instance,
                item[0].provider.voice_id,
                item[0].provider.voice_revision or "",
            ),
        )
        return CastingDecision(
            provider=candidate.provider,
            source="candidate",
            matched_public_traits=matched,
        )
