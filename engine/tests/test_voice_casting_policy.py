"""W-V05 authorization-first casting policy tests."""
from __future__ import annotations

import pytest

from application.voice_casting_policy import (
    CastingPolicyRequest,
    VoiceCandidate,
    VoiceCastingPolicy,
    VoiceCastingPolicyError,
    audible_voice_key,
    voice_revision_key,
)
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingScope,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)


def _provider(
    code: str,
    *,
    assurance: VoiceIdentityAssurance = VoiceIdentityAssurance.CONTENT_ADDRESSED,
    revoked: bool = False,
) -> ProviderVoiceRevision:
    return ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id=f"voice-{code}",
        assurance=assurance,
        voice_revision=None if assurance is VoiceIdentityAssurance.LEGACY else f"vr-{code}-" + code * 40,
        model_catalog_revision=code * 40,
        revoked=revoked,
    )


def _candidate(
    code: str,
    *,
    traits: frozenset[str] = frozenset({"calm"}),
    locales: frozenset[str] = frozenset({"zh-CN"}),
    usages: frozenset[str] = frozenset({"dialogue"}),
    available: bool = True,
    production_ready: bool = True,
    rights_granted: bool = True,
    quality_approved: bool = True,
    assurance: VoiceIdentityAssurance = VoiceIdentityAssurance.CONTENT_ADDRESSED,
    revoked: bool = False,
    explicit_legacy_approval: bool = False,
) -> VoiceCandidate:
    return VoiceCandidate(
        provider=_provider(code, assurance=assurance, revoked=revoked),
        locales=locales,
        allowed_usages=usages,
        public_traits=traits,
        available=available,
        production_ready=production_ready,
        rights_granted=rights_granted,
        quality_approved=quality_approved,
        explicit_legacy_approval=explicit_legacy_approval,
    )


def _scope(
    *,
    presentation_identity: str = "masked-npc",
    worldline_id: str = "line-1",
    locale: str = "zh-CN",
) -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="world-1",
        worldline_id=worldline_id,
        presentation_identity=presentation_identity,
        phase="default",
        locale=locale,
    )


def _request(
    candidates: tuple[VoiceCandidate, ...],
    *,
    authorized: frozenset[tuple[str, str, str | None]] | None = None,
    occupied: frozenset[tuple[str, str]] = frozenset(),
    traits: frozenset[str] = frozenset({"calm"}),
    scope: VoiceBindingScope | None = None,
) -> CastingPolicyRequest:
    return CastingPolicyRequest(
        scope=scope or _scope(),
        usage="dialogue",
        authorized_voice_revisions=(
            authorized
            if authorized is not None
            else frozenset(item.revision_key for item in candidates)
        ),
        occupied_audible_voices=occupied,
        desired_public_traits=traits,
    )


def _active_binding(
    provider: ProviderVoiceRevision,
    *,
    scope: VoiceBindingScope | None = None,
) -> VoiceBinding:
    return VoiceBinding.reserve(
        binding_id="binding-existing",
        scope=scope or _scope(),
        persona=VoicePersonaRevision("voice-masked", "persona-r1"),
        provider=provider,
        world_revision=8,
    ).activate(expected_binding_revision=1)


def test_hard_filters_run_before_public_trait_ranking():
    candidates = (
        _candidate("a", locales=frozenset({"en-US"}), traits=frozenset({"calm", "warm"})),
        _candidate("b", rights_granted=False, traits=frozenset({"calm", "warm"})),
        _candidate("c", available=False, traits=frozenset({"calm", "warm"})),
        _candidate("d", production_ready=False, traits=frozenset({"calm", "warm"})),
        _candidate("e", quality_approved=False, traits=frozenset({"calm", "warm"})),
        _candidate("f", revoked=True, traits=frozenset({"calm", "warm"})),
        _candidate("1", traits=frozenset({"calm"})),
    )

    decision = VoiceCastingPolicy().choose(_request(candidates), candidates)

    assert decision.provider.voice_id == "voice-1"
    assert decision.matched_public_traits == 1


def test_masked_familiar_voice_cannot_win_without_explicit_authorization():
    familiar = _candidate("a", traits=frozenset({"calm", "warm", "familiar"}))
    public_alternative = _candidate("b", traits=frozenset({"calm"}))
    request = _request(
        (familiar, public_alternative),
        authorized=frozenset({public_alternative.revision_key}),
        traits=frozenset({"calm", "warm", "familiar"}),
    )

    decision = VoiceCastingPolicy().choose(
        request, (familiar, public_alternative)
    )

    assert decision.provider == public_alternative.provider


def test_existing_authorized_binding_is_a_hard_lock():
    existing = _active_binding(_provider("a"))
    better_new_candidate = _candidate(
        "b", traits=frozenset({"calm", "warm", "bright"})
    )
    request = _request(
        (better_new_candidate,),
        authorized=frozenset(
            {
                voice_revision_key(existing.provider),
                better_new_candidate.revision_key,
            }
        ),
        traits=frozenset({"calm", "warm", "bright"}),
    )

    decision = VoiceCastingPolicy().choose(
        request, (better_new_candidate,), existing_binding=existing
    )

    assert decision.source == "existing_binding"
    assert decision.provider == existing.provider


def test_existing_binding_fails_closed_when_its_revision_is_not_authorized():
    existing = _active_binding(_provider("a"))
    candidate = _candidate("b")
    request = _request(
        (candidate,), authorized=frozenset({candidate.revision_key})
    )

    with pytest.raises(
        VoiceCastingPolicyError, match="existing_voice_not_authorized"
    ):
        VoiceCastingPolicy().choose(
            request, (candidate,), existing_binding=existing
        )


def test_candidate_order_does_not_change_deterministic_tie_break():
    a = _candidate("a", traits=frozenset({"calm"}))
    b = _candidate("b", traits=frozenset({"calm"}))
    request = _request((a, b))

    first = VoiceCastingPolicy().choose(request, (b, a))
    second = VoiceCastingPolicy().choose(request, (a, b))

    assert first.provider == second.provider == a.provider


def test_occupied_audible_identity_is_not_reused_in_same_scene():
    a = _candidate("a", traits=frozenset({"calm", "warm"}))
    b = _candidate("b", traits=frozenset({"calm"}))
    request = _request(
        (a, b), occupied=frozenset({audible_voice_key(a.provider)})
    )

    decision = VoiceCastingPolicy().choose(request, (a, b))

    assert decision.provider == b.provider


def test_legacy_candidate_requires_explicit_freeze_approval():
    legacy = _candidate(
        "a",
        assurance=VoiceIdentityAssurance.LEGACY,
        explicit_legacy_approval=False,
    )
    request = _request((legacy,))

    with pytest.raises(
        VoiceCastingPolicyError, match="no_authorized_voice_candidate"
    ):
        VoiceCastingPolicy().choose(request, (legacy,))

    approved = _candidate(
        "a",
        assurance=VoiceIdentityAssurance.LEGACY,
        explicit_legacy_approval=True,
    )
    decision = VoiceCastingPolicy().choose(_request((approved,)), (approved,))
    assert decision.provider == approved.provider


def test_duplicate_revision_candidate_metadata_is_rejected():
    first = _candidate("a", traits=frozenset({"calm"}))
    duplicate = _candidate("a", traits=frozenset({"bright"}))
    request = _request((first,))

    with pytest.raises(VoiceCastingPolicyError, match="duplicate_voice_candidate"):
        VoiceCastingPolicy().choose(request, (first, duplicate))


def test_existing_binding_must_match_current_public_presentation_scope():
    existing = _active_binding(
        _provider("a"),
        scope=_scope(presentation_identity="other-visible-character"),
    )
    candidate = _candidate("b")
    request = _request(
        (candidate,),
        authorized=frozenset(
            {voice_revision_key(existing.provider), candidate.revision_key}
        ),
        scope=_scope(presentation_identity="masked-npc"),
    )

    with pytest.raises(
        VoiceCastingPolicyError, match="existing_voice_scope_mismatch"
    ):
        VoiceCastingPolicy().choose(
            request, (candidate,), existing_binding=existing
        )
