"""W-V05 authorization-first casting policy tests."""
from __future__ import annotations

import pytest

from application.voice_casting_policy import (
    CastingPolicyRequest,
    VoiceCandidate,
    VoiceCastingPolicy,
    VoiceCastingPolicyError,
    SceneCastingPlanner,
    SceneCastingRole,
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


def test_scene_casting_jointly_avoids_greedy_dead_end():
    voice_a = _candidate("a", traits=frozenset({"calm", "warm"}))
    voice_b = _candidate("b", traits=frozenset({"calm"}))
    role_a = SceneCastingRole(
        role_id="role-a",
        request=_request(
            (voice_a, voice_b),
            traits=frozenset({"calm", "warm"}),
            scope=_scope(presentation_identity="role-a"),
        ),
        candidates=(voice_a, voice_b),
    )
    role_b = SceneCastingRole(
        role_id="role-b",
        request=_request(
            (voice_a,),
            traits=frozenset({"calm", "warm"}),
            scope=_scope(presentation_identity="role-b"),
        ),
        candidates=(voice_a,),
    )

    decisions = SceneCastingPlanner().plan((role_a, role_b))

    by_role = {item.role_id: item.decision for item in decisions}
    assert by_role["role-a"].provider == voice_b.provider
    assert by_role["role-b"].provider == voice_a.provider
    assert sum(item.decision.matched_public_traits for item in decisions) == 3


def test_scene_casting_is_independent_of_role_and_candidate_order():
    voice_a = _candidate("a")
    voice_b = _candidate("b")
    first_roles = (
        SceneCastingRole(
            "role-b",
            _request(
                (voice_b, voice_a),
                scope=_scope(presentation_identity="role-b"),
            ),
            (voice_b, voice_a),
        ),
        SceneCastingRole(
            "role-a",
            _request(
                (voice_a, voice_b),
                scope=_scope(presentation_identity="role-a"),
            ),
            (voice_a, voice_b),
        ),
    )
    second_roles = (
        SceneCastingRole(
            "role-a",
            _request(
                (voice_b, voice_a),
                scope=_scope(presentation_identity="role-a"),
            ),
            (voice_b, voice_a),
        ),
        SceneCastingRole(
            "role-b",
            _request(
                (voice_a, voice_b),
                scope=_scope(presentation_identity="role-b"),
            ),
            (voice_a, voice_b),
        ),
    )

    assert SceneCastingPlanner().plan(first_roles) == SceneCastingPlanner().plan(
        second_roles
    )


def test_scene_casting_existing_binding_is_hard_lock_and_blocks_reuse():
    locked_scope = _scope(presentation_identity="role-a")
    locked = _active_binding(_provider("a"), scope=locked_scope)
    voice_a = _candidate("a")
    voice_b = _candidate("b")
    role_a = SceneCastingRole(
        "role-a",
        _request(
            (),
            authorized=frozenset({voice_revision_key(locked.provider)}),
            scope=locked_scope,
        ),
        (),
        existing_binding=locked,
    )
    role_b = SceneCastingRole(
        "role-b",
        _request(
            (voice_a, voice_b),
            scope=_scope(presentation_identity="role-b"),
        ),
        (voice_a, voice_b),
    )

    decisions = SceneCastingPlanner().plan((role_b, role_a))
    by_role = {item.role_id: item.decision for item in decisions}

    assert by_role["role-a"].source == "existing_binding"
    assert by_role["role-a"].provider == locked.provider
    assert by_role["role-b"].provider == voice_b.provider


def test_scene_casting_keeps_authorization_hard_filter_for_every_role():
    familiar = _candidate("a", traits=frozenset({"calm", "familiar"}))
    safe = _candidate("b", traits=frozenset({"calm"}))
    role = SceneCastingRole(
        "masked-role",
        _request(
            (familiar, safe),
            authorized=frozenset({safe.revision_key}),
            traits=frozenset({"calm", "familiar"}),
            scope=_scope(presentation_identity="masked-role"),
        ),
        (familiar, safe),
    )

    decision = SceneCastingPlanner().plan((role,))[0].decision
    assert decision.provider == safe.provider


def test_scene_casting_rejects_cross_worldline_or_duplicate_roles():
    voice = _candidate("a")
    role_a = SceneCastingRole(
        "role-a",
        _request((voice,), scope=_scope(presentation_identity="role-a")),
        (voice,),
    )
    role_other_line = SceneCastingRole(
        "role-b",
        _request(
            (voice,),
            scope=_scope(
                presentation_identity="role-b",
                worldline_id="line-2",
            ),
        ),
        (voice,),
    )
    planner = SceneCastingPlanner()

    with pytest.raises(VoiceCastingPolicyError, match="scene_scope_mismatch"):
        planner.plan((role_a, role_other_line))

    with pytest.raises(VoiceCastingPolicyError, match="duplicate_scene_role"):
        planner.plan((role_a, role_a))


def test_scene_casting_search_space_is_explicitly_bounded():
    candidates = tuple(_candidate(chr(97 + index)) for index in range(13))
    oversized_pool = SceneCastingRole(
        "role-a",
        _request(
            candidates,
            scope=_scope(presentation_identity="role-a"),
        ),
        candidates,
    )
    planner = SceneCastingPlanner()

    with pytest.raises(
        VoiceCastingPolicyError, match="scene_candidate_limit_exceeded"
    ):
        planner.plan((oversized_pool,))

    small_candidate = (_candidate("z"),)
    too_many_unbound = tuple(
        SceneCastingRole(
            f"role-{index}",
            _request(
                small_candidate,
                scope=_scope(presentation_identity=f"role-{index}"),
            ),
            small_candidate,
        )
        for index in range(SceneCastingPlanner.MAX_UNBOUND_ROLES + 1)
    )
    with pytest.raises(
        VoiceCastingPolicyError, match="scene_unbound_role_limit_exceeded"
    ):
        planner.plan(too_many_unbound)
