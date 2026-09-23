from dataclasses import replace

import pytest

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
    VoiceIdentityError,
    VoicePersonaRevision,
)


def _scope(**overrides):
    values = {
        "owner_id": "player",
        "world_id": "world-1",
        "worldline_id": "line-1",
        "presentation_identity": "character-visible-identity",
        "phase": "default",
        "locale": "zh-CN",
    }
    values.update(overrides)
    return VoiceBindingScope(**values)


def _persona(revision="persona-r1"):
    return VoicePersonaRevision("voice-klein", revision)


def _provider(*, revision="vr_" + "a" * 40, revoked=False):
    return ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
        voice_revision=revision,
        model_catalog_revision="b" * 40,
        revoked=revoked,
    )


def test_content_addressed_identity_requires_real_voice_revision():
    with pytest.raises(VoiceIdentityError, match="requires a voice revision"):
        ProviderVoiceRevision(
            provider_instance="speechrail-local",
            voice_id="serena",
            assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
        )


def test_legacy_identity_cannot_promote_catalog_revision_to_voice_revision():
    legacy = ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id="serena",
        assurance=VoiceIdentityAssurance.LEGACY,
        model_catalog_revision="c" * 40,
    )
    assert legacy.voice_revision is None
    assert legacy.conditional_pin is None

    with pytest.raises(VoiceIdentityError, match="legacy assurance"):
        replace(legacy, voice_revision="c" * 40)


def test_reservation_is_persistable_before_first_output_but_not_renderable_yet():
    binding = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=42,
    )

    assert binding.status is VoiceBindingStatus.RESERVED
    assert binding.binding_revision == 1
    assert binding.reserved_at_world_revision == 42
    assert not binding.permits_new_render

    active = binding.activate(expected_binding_revision=1)
    assert active.status is VoiceBindingStatus.ACTIVE
    assert active.binding_revision == 2
    assert active.reserved_at_world_revision == 42
    assert active.permits_new_render
    assert active.provider.conditional_pin == "vr_" + "a" * 40


def test_stale_binding_revision_cannot_change_casting():
    binding = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=5,
    ).activate(expected_binding_revision=1)

    with pytest.raises(VoiceBindingConflict):
        binding.rebind(
            expected_binding_revision=1,
            persona=_persona("persona-r2"),
            provider=_provider(revision="vr_" + "d" * 40),
        )

    assert binding.binding_revision == 2
    assert binding.persona.revision == "persona-r1"


def test_rebind_creates_new_presentation_revision_without_mutating_world_revision():
    active = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=99,
    ).activate(expected_binding_revision=1)

    rebound = active.rebind(
        expected_binding_revision=2,
        persona=_persona("persona-r2"),
        provider=_provider(revision="vr_" + "d" * 40),
    )

    assert rebound.binding_revision == 3
    assert rebound.reserved_at_world_revision == 99
    assert rebound.status is VoiceBindingStatus.RESERVED
    assert not rebound.permits_new_render


def test_revocation_blocks_new_render_but_preserves_historical_identity():
    active = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=7,
    ).activate(expected_binding_revision=1)

    revoked = active.revoke(expected_binding_revision=2)
    assert revoked.status is VoiceBindingStatus.REVOKED
    assert revoked.binding_revision == 3
    assert not revoked.permits_new_render
    assert revoked.provider.voice_id == active.provider.voice_id
    assert revoked.provider.voice_revision == active.provider.voice_revision

    with pytest.raises(VoiceIdentityError, match="cannot be rebound"):
        revoked.rebind(
            expected_binding_revision=3,
            persona=_persona("persona-r2"),
            provider=_provider(revision="vr_" + "e" * 40),
        )


def test_revoked_provider_voice_cannot_be_reserved_or_activated():
    with pytest.raises(VoiceIdentityError, match="revoked provider"):
        VoiceBinding.reserve(
            binding_id="binding-1",
            scope=_scope(),
            persona=_persona(),
            provider=_provider(revoked=True),
            world_revision=1,
        )

    reserved = VoiceBinding.reserve(
        binding_id="binding-2",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=1,
    )
    invalidated = replace(reserved, provider=replace(reserved.provider, revoked=True))
    with pytest.raises(VoiceIdentityError, match="revoked provider"):
        invalidated.activate(expected_binding_revision=1)
