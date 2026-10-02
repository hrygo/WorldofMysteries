from dataclasses import replace
import re

import pytest

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceEvidenceReference,
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


def _evidence(**overrides):
    values = {
        "evidence_id": "ev_klein_1",
        "evidence_digest": "d" * 64,
        "model_artifact_revision": "qwen3-tts-2026-09-29",
    }
    values.update(overrides)
    return VoiceEvidenceReference(**values)


def _reviewed(**overrides):
    """A reservation that already carries the review standing behind it."""
    values = {
        "binding_id": "binding-1",
        "scope": _scope(),
        "persona": _persona(),
        "provider": _provider(),
        "world_revision": 5,
    }
    values.update(overrides)
    return replace(VoiceBinding.reserve(**values), evidence=_evidence())


@pytest.mark.parametrize(
    "digest",
    ["D" * 64, "d" * 63, "d" * 65, "not-a-digest", "", 12345],
)
def test_evidence_reference_requires_a_real_sha256_digest(digest):
    """The digest is what makes the reference checkable. An identifier alone
    can be reused against a rewritten record; a content digest cannot."""
    with pytest.raises(VoiceIdentityError, match="evidence digest"):
        _evidence(evidence_digest=digest)


@pytest.mark.parametrize("field", ["evidence_id", "model_artifact_revision"])
def test_evidence_reference_requires_bounded_identifiers(field):
    with pytest.raises(VoiceIdentityError, match=field):
        _evidence(**{field: "  "})


def test_a_reserved_binding_may_exist_before_it_is_reviewed():
    """Reserving a voice is a claim; activating it is a decision. This task
    only introduces the reference, so a reservation without one is still
    legal — refusing it is the next step, not this one."""
    binding = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=7,
    )
    assert binding.evidence is None


def test_a_binding_carries_the_review_that_stands_behind_it():
    binding = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=7,
    )
    reviewed = replace(binding, evidence=_evidence())
    assert reviewed.evidence is not None
    assert reviewed.evidence.evidence_id == "ev_klein_1"
    # The artifact a human heard is not the catalogue entry describing it.
    assert reviewed.evidence.model_artifact_revision != reviewed.provider.model_catalog_revision
    assert binding.evidence is None


def test_a_binding_rejects_a_malformed_evidence_reference():
    binding = VoiceBinding.reserve(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=7,
    )
    with pytest.raises(VoiceIdentityError, match="evidence reference"):
        replace(binding, evidence="ev_klein_1")


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

    # A reservation is a claim, not a decision. Without a human review behind
    # it, the binding must not be promotable into something a player hears.
    with pytest.raises(VoiceIdentityError, match="without approved evidence"):
        binding.activate(expected_binding_revision=1)

    active = replace(binding, evidence=_evidence()).activate(
        expected_binding_revision=1
    )
    assert active.status is VoiceBindingStatus.ACTIVE
    assert active.binding_revision == 2
    assert active.reserved_at_world_revision == 42
    assert active.permits_new_render
    assert active.provider.conditional_pin == "vr_" + "a" * 40


def test_stale_binding_revision_cannot_change_casting():
    binding = _reviewed(world_revision=5).activate(expected_binding_revision=1)

    with pytest.raises(VoiceBindingConflict):
        binding.rebind(
            expected_binding_revision=1,
            persona=_persona("persona-r2"),
            provider=_provider(revision="vr_" + "d" * 40),
        )

    assert binding.binding_revision == 2
    assert binding.persona.revision == "persona-r1"


def test_rebind_creates_new_presentation_revision_without_mutating_world_revision():
    active = _reviewed(world_revision=99).activate(expected_binding_revision=1)

    rebound = active.rebind(
        expected_binding_revision=2,
        persona=_persona("persona-r2"),
        provider=_provider(revision="vr_" + "d" * 40),
    )

    assert rebound.binding_revision == 3
    assert rebound.reserved_at_world_revision == 99
    assert rebound.status is VoiceBindingStatus.RESERVED
    assert not rebound.permits_new_render


def test_rebinding_drops_the_review_that_belonged_to_the_old_voice():
    """Trust is not transferable. A human approved one specific voice; letting
    a replacement inherit that approval would put an unheard voice behind a
    signature they never gave."""
    active = _reviewed(world_revision=99).activate(expected_binding_revision=1)
    assert active.evidence is not None

    rebound = active.rebind(
        expected_binding_revision=2,
        persona=_persona("persona-r2"),
        provider=_provider(revision="vr_" + "d" * 40),
    )
    assert rebound.evidence is None


def test_rebinding_can_carry_the_review_of_the_replacement_voice():
    active = _reviewed(world_revision=99).activate(expected_binding_revision=1)
    replacement_review = _evidence(evidence_id="ev_klein_2")

    rebound = active.rebind(
        expected_binding_revision=2,
        persona=_persona("persona-r2"),
        provider=_provider(revision="vr_" + "d" * 40),
        evidence=replacement_review,
    )
    assert rebound.evidence == replacement_review


def test_rebinding_refuses_a_malformed_review_reference():
    active = _reviewed(world_revision=99).activate(expected_binding_revision=1)
    with pytest.raises(VoiceIdentityError, match="evidence reference"):
        active.rebind(
            expected_binding_revision=2,
            persona=_persona("persona-r2"),
            provider=_provider(revision="vr_" + "d" * 40),
            evidence="ev_klein_2",
        )


def test_revocation_blocks_new_render_but_preserves_historical_identity():
    active = _reviewed(world_revision=7).activate(expected_binding_revision=1)

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


def test_a_scope_and_its_binding_row_key_are_the_same_fact():
    """``voice_bindings`` is UNIQUE on the scope, so the row key must be too.

    The renderer resolves a voice by scope. A row key that was not a function
    of the scope would let one character's voice be committed under another
    character's key, and the lookup that matters would never find it.
    """
    scope = _scope()

    assert scope.binding_identity == _scope().binding_identity
    assert scope.binding_identity.startswith("vb-")


@pytest.mark.parametrize(
    "field",
    [
        "owner_id",
        "world_id",
        "worldline_id",
        "presentation_identity",
        "phase",
        "locale",
    ],
)
def test_no_field_of_the_scope_can_be_changed_without_moving_the_binding(field):
    assert _scope().binding_identity != _scope(**{field: "other"}).binding_identity


def test_a_worldline_fork_gets_its_own_binding():
    """D9: a fork is explicit and isolated, and it inherits no binding by accident.

    The worldline is part of the key precisely so a fork cannot resolve to
    the voice its parent worldline happens to be using.
    """
    assert (
        _scope(worldline_id="line-1").binding_identity
        != _scope(worldline_id="line-2").binding_identity
    )


def test_a_separator_inside_a_field_cannot_forge_another_scope():
    """Length-prefixing is what makes the encoding injective.

    Joining on a bare ``|`` would let a scope whose identity contains one
    hash to the same row as a scope that splits differently across the fields
    — and two scopes sharing a binding row is the whole failure being
    prevented.
    """
    left = _scope(presentation_identity="a|zh-CN", locale="en-US")
    right = _scope(presentation_identity="a", locale="zh-CN|en-US")

    assert left != right
    assert left.binding_identity != right.binding_identity


def test_the_binding_key_is_an_opaque_fixed_width_digest():
    """A readable key would leak the presentation identity into a log line.

    The row key travels in error messages and diagnostics, and the scope names
    a character. Pinning the shape keeps that name out of all of them.
    """
    key = _scope().binding_identity

    assert re.fullmatch(r"vb-[0-9a-f]{16}", key)
