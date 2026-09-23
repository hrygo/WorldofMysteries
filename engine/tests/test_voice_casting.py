"""Application-level W-V04 casting durability barrier tests."""
from __future__ import annotations

import asyncio

import pytest

from application.voice_casting import VoiceCastingError, VoiceCastingService
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)


def _scope() -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="world-1",
        worldline_id="line-1",
        presentation_identity="klein-visible",
        phase="default",
        locale="zh-CN",
    )


def _persona(revision: str = "persona-r1") -> VoicePersonaRevision:
    return VoicePersonaRevision("voice-klein", revision)


def _provider(char: str = "a", *, revoked: bool = False) -> ProviderVoiceRevision:
    return ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id=f"klein-{char}",
        assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
        voice_revision="voice-" + char * 40,
        model_catalog_revision=char * 40,
        revoked=revoked,
    )


def _reserved(
    binding_id: str = "binding-winner",
    *,
    persona: VoicePersonaRevision | None = None,
    provider: ProviderVoiceRevision | None = None,
) -> VoiceBinding:
    return VoiceBinding.reserve(
        binding_id=binding_id,
        scope=_scope(),
        persona=persona or _persona(),
        provider=provider or _provider(),
        world_revision=9,
    )


class MemoryPort:
    def __init__(self, existing: VoiceBinding | None = None):
        self.current = existing
        self.reserve_candidates: list[VoiceBinding] = []
        self.activate_calls = 0

    async def load_scope(self, scope):
        return self.current if self.current is not None and self.current.scope == scope else None

    async def reserve(self, candidate):
        self.reserve_candidates.append(candidate)
        if self.current is None:
            self.current = candidate
        return self.current

    async def activate(self, binding_id, *, expected_binding_revision):
        self.activate_calls += 1
        if self.current is None or self.current.binding_id != binding_id:
            raise VoiceBindingConflict("missing winner")
        self.current = self.current.activate(
            expected_binding_revision=expected_binding_revision
        )
        return self.current

    async def rebind(
        self,
        binding_id,
        *,
        expected_binding_revision,
        persona,
        provider,
    ):
        if self.current is None or self.current.binding_id != binding_id:
            raise VoiceBindingConflict("missing winner")
        self.current = self.current.rebind(
            expected_binding_revision=expected_binding_revision,
            persona=persona,
            provider=provider,
        )
        return self.current

    async def revoke(self, binding_id, *, expected_binding_revision):
        if self.current is None or self.current.binding_id != binding_id:
            raise VoiceBindingConflict("missing winner")
        self.current = self.current.revoke(
            expected_binding_revision=expected_binding_revision
        )
        return self.current


class ActivationRacePort(MemoryPort):
    async def activate(self, binding_id, *, expected_binding_revision):
        # Simulate another process winning the CAS after this caller observed RESERVED.
        if self.current is None:
            raise AssertionError("reservation must happen before activation")
        self.current = self.current.activate(
            expected_binding_revision=expected_binding_revision
        )
        raise VoiceBindingConflict("concurrent activation won")


async def test_first_render_persists_reservation_before_activation():
    port = MemoryPort()
    service = VoiceCastingService(port)

    active = await service.prepare_render(
        binding_id="binding-1",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=9,
    )

    assert [item.status for item in port.reserve_candidates] == [VoiceBindingStatus.RESERVED]
    assert active.status is VoiceBindingStatus.ACTIVE
    assert active.binding_revision == 2
    assert active.reserved_at_world_revision == 9
    assert active.provider.conditional_pin == "voice-" + "a" * 40


async def test_existing_binding_wins_over_new_candidate_and_is_not_recast():
    existing = _reserved("binding-old", provider=_provider("a")).activate(
        expected_binding_revision=1
    )
    port = MemoryPort(existing)
    service = VoiceCastingService(port)

    active = await service.prepare_render(
        binding_id="binding-new",
        scope=_scope(),
        persona=_persona("persona-r2"),
        provider=_provider("b"),
        world_revision=99,
    )

    assert active == existing
    assert port.current == existing
    assert port.activate_calls == 0
    assert port.reserve_candidates[0].binding_id == "binding-new"


async def test_stale_activation_race_recovers_same_persisted_winner():
    port = ActivationRacePort()
    service = VoiceCastingService(port)

    active = await service.prepare_render(
        binding_id="binding-winner",
        scope=_scope(),
        persona=_persona(),
        provider=_provider(),
        world_revision=9,
    )

    assert active.binding_id == "binding-winner"
    assert active.status is VoiceBindingStatus.ACTIVE
    assert active.binding_revision == 2


async def test_revoked_existing_binding_blocks_new_render_even_with_new_candidate():
    revoked = _reserved().activate(expected_binding_revision=1).revoke(
        expected_binding_revision=2
    )
    port = MemoryPort(revoked)

    with pytest.raises(VoiceCastingError, match="revoked"):
        await VoiceCastingService(port).prepare_render(
            binding_id="replacement-without-command",
            scope=_scope(),
            persona=_persona("persona-r9"),
            provider=_provider("b"),
            world_revision=10,
        )

    assert port.current == revoked


async def test_explicit_replace_is_only_path_that_changes_active_voice():
    current = _reserved().activate(expected_binding_revision=1)
    port = MemoryPort(current)
    service = VoiceCastingService(port)

    updated = await service.replace_for_future_render(
        binding_id=current.binding_id,
        expected_binding_revision=current.binding_revision,
        persona=_persona("persona-r2"),
        provider=_provider("d"),
    )

    assert updated.status is VoiceBindingStatus.ACTIVE
    assert updated.binding_revision == 4
    assert updated.persona.revision == "persona-r2"
    assert updated.provider.voice_id == "klein-d"


async def test_revoke_command_persists_terminal_binding():
    current = _reserved().activate(expected_binding_revision=1)
    service = VoiceCastingService(MemoryPort(current))

    revoked = await service.revoke(
        current.binding_id, expected_binding_revision=current.binding_revision
    )

    assert revoked.status is VoiceBindingStatus.REVOKED
    assert not revoked.permits_new_render
