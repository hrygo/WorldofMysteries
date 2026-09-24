"""Authorization-first W-V05 voice casting policy.

This module receives only presentation-safe candidate metadata and an explicit
authorization grant set. It never reads Domain/DB state, provider APIs, hidden
identity, or canonical facts. Existing durable bindings are hard locks unless
their revision is no longer authorized or renderable.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingStatus,
    VoiceBindingScope,
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

    scope: VoiceBindingScope
    usage: str
    authorized_voice_revisions: frozenset[VoiceRevisionKey]
    occupied_audible_voices: frozenset[AudibleVoiceKey]
    desired_public_traits: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, VoiceBindingScope):
            raise VoiceCastingPolicyError("invalid_voice_binding_scope")
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
            if existing_binding.scope != request.scope:
                raise VoiceCastingPolicyError("existing_voice_scope_mismatch")
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

        ranked = self.rank_candidates(request, candidates)
        if not ranked:
            raise VoiceCastingPolicyError("no_authorized_voice_candidate")
        candidate, matched = ranked[0]
        return CastingDecision(
            provider=candidate.provider,
            source="candidate",
            matched_public_traits=matched,
        )

    def rank_candidates(
        self,
        request: CastingPolicyRequest,
        candidates: tuple[VoiceCandidate, ...],
    ) -> tuple[tuple[VoiceCandidate, int], ...]:
        """Return the complete hard-filtered ranking for joint scene planning."""
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
            if request.scope.locale.casefold() not in candidate.locales:
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

        return tuple(
            sorted(
                eligible,
                key=lambda item: (
                    -item[1],
                    item[0].provider.provider_instance,
                    item[0].provider.voice_id,
                    item[0].provider.voice_revision or "",
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class SceneCastingRole:
    role_id: str
    request: CastingPolicyRequest
    candidates: tuple[VoiceCandidate, ...]
    existing_binding: VoiceBinding | None = None

    def __post_init__(self) -> None:
        _text(self.role_id, "scene_role_id")
        if not isinstance(self.request, CastingPolicyRequest):
            raise VoiceCastingPolicyError("invalid_scene_casting_request")
        if self.existing_binding is not None and not isinstance(
            self.existing_binding, VoiceBinding
        ):
            raise VoiceCastingPolicyError("invalid_scene_existing_binding")


@dataclass(frozen=True, slots=True)
class SceneCastingDecision:
    role_id: str
    decision: CastingDecision


class SceneCastingPlanner:
    """Jointly assign distinct voices for a small co-scene role set.

    Existing bindings remain hard locks. Unbound roles are solved together rather
    than greedily, maximizing total public-trait fit with a deterministic identity
    tie-break. This planner intentionally stays small and exact.
    """

    MAX_SCENE_ROLES = 12
    MAX_UNBOUND_ROLES = 5
    MAX_CANDIDATES_PER_ROLE = 12

    def __init__(self, policy: VoiceCastingPolicy | None = None) -> None:
        self._policy = policy or VoiceCastingPolicy()

    def plan(
        self, roles: tuple[SceneCastingRole, ...]
    ) -> tuple[SceneCastingDecision, ...]:
        if not roles or len(roles) > self.MAX_SCENE_ROLES:
            raise VoiceCastingPolicyError("invalid_scene_role_count")
        if any(
            len(role.candidates) > self.MAX_CANDIDATES_PER_ROLE for role in roles
        ):
            raise VoiceCastingPolicyError("scene_candidate_limit_exceeded")

        ordered = tuple(sorted(roles, key=lambda item: item.role_id))
        if len({role.role_id for role in ordered}) != len(ordered):
            raise VoiceCastingPolicyError("duplicate_scene_role")

        reference = ordered[0].request.scope
        for role in ordered[1:]:
            scope = role.request.scope
            if (
                scope.owner_id != reference.owner_id
                or scope.world_id != reference.world_id
                or scope.worldline_id != reference.worldline_id
                or scope.locale.casefold() != reference.locale.casefold()
            ):
                raise VoiceCastingPolicyError("scene_scope_mismatch")

        externally_occupied: set[AudibleVoiceKey] = set()
        for role in ordered:
            externally_occupied.update(role.request.occupied_audible_voices)

        locked: list[SceneCastingDecision] = []
        locked_audible: set[AudibleVoiceKey] = set()
        unbound: list[SceneCastingRole] = []
        for role in ordered:
            if role.existing_binding is None:
                unbound.append(role)
                continue
            decision = self._policy.choose(
                role.request, (), existing_binding=role.existing_binding
            )
            locked.append(SceneCastingDecision(role.role_id, decision))
            locked_audible.add(audible_voice_key(decision.provider))

        if len(unbound) > self.MAX_UNBOUND_ROLES:
            raise VoiceCastingPolicyError("scene_unbound_role_limit_exceeded")

        base_occupied = frozenset(externally_occupied | locked_audible)
        memo: dict[
            tuple[int, frozenset[AudibleVoiceKey]],
            tuple[int, tuple[SceneCastingDecision, ...]] | None,
        ] = {}

        def tie_key(items: tuple[SceneCastingDecision, ...]) -> tuple:
            return tuple(
                (
                    item.role_id,
                    item.decision.provider.provider_instance,
                    item.decision.provider.voice_id,
                    item.decision.provider.voice_revision or "",
                )
                for item in items
            )

        def solve(
            index: int, used: frozenset[AudibleVoiceKey]
        ) -> tuple[int, tuple[SceneCastingDecision, ...]] | None:
            key = (index, used)
            if key in memo:
                return memo[key]
            if index == len(unbound):
                result = (0, ())
                memo[key] = result
                return result

            role = unbound[index]
            request = replace(
                role.request,
                occupied_audible_voices=frozenset(base_occupied | used),
            )
            ranked = self._policy.rank_candidates(request, role.candidates)
            best: tuple[int, tuple[SceneCastingDecision, ...]] | None = None
            for candidate, matched in ranked:
                audible = candidate.audible_key
                tail = solve(index + 1, used | frozenset({audible}))
                if tail is None:
                    continue
                decision = SceneCastingDecision(
                    role_id=role.role_id,
                    decision=CastingDecision(
                        provider=candidate.provider,
                        source="candidate",
                        matched_public_traits=matched,
                    ),
                )
                candidate_result = (matched + tail[0], (decision,) + tail[1])
                if (
                    best is None
                    or candidate_result[0] > best[0]
                    or (
                        candidate_result[0] == best[0]
                        and tie_key(candidate_result[1]) < tie_key(best[1])
                    )
                ):
                    best = candidate_result

            memo[key] = best
            return best

        solved = solve(0, frozenset())
        if solved is None:
            raise VoiceCastingPolicyError("no_distinct_scene_cast")

        combined = tuple(locked) + solved[1]
        return tuple(sorted(combined, key=lambda item: item.role_id))
