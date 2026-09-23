"""Application commands for stable W-V04 voice binding before render.

This layer does not choose a voice. W-V05 supplies an already-authorized candidate;
this service makes the choice durable before any synthesis can start and recovers
the same winner across races/restarts.
"""
from __future__ import annotations

from typing import Protocol

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoicePersonaRevision,
)


class VoiceCastingError(RuntimeError):
    """Application voice-binding command cannot safely authorize a new render."""


class VoiceBindingPort(Protocol):
    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None: ...

    async def reserve(self, candidate: VoiceBinding) -> VoiceBinding: ...

    async def activate(
        self, binding_id: str, *, expected_binding_revision: int
    ) -> VoiceBinding: ...

    async def rebind(
        self,
        binding_id: str,
        *,
        expected_binding_revision: int,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
    ) -> VoiceBinding: ...

    async def revoke(
        self, binding_id: str, *, expected_binding_revision: int
    ) -> VoiceBinding: ...


class VoiceCastingService:
    """Durability barrier between candidate selection and synthesis.

    A candidate is first persisted as RESERVED. Only that persisted winner may then
    become ACTIVE and authorize a new render. A stale activation race is recovered
    by re-reading the same scope rather than selecting a second voice.
    """

    def __init__(self, port: VoiceBindingPort):
        self._port = port

    async def prepare_render(
        self,
        *,
        binding_id: str,
        scope: VoiceBindingScope,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
        world_revision: int,
    ) -> VoiceBinding:
        candidate = VoiceBinding.reserve(
            binding_id=binding_id,
            scope=scope,
            persona=persona,
            provider=provider,
            world_revision=world_revision,
        )
        persisted = await self._port.reserve(candidate)
        self._require_scope(persisted, scope)

        if persisted.status is VoiceBindingStatus.REVOKED:
            raise VoiceCastingError("revoked voice binding cannot authorize a new render")
        if persisted.status is VoiceBindingStatus.ACTIVE:
            return self._require_renderable(persisted)
        if persisted.status is not VoiceBindingStatus.RESERVED:
            raise VoiceCastingError("voice binding has an unsupported lifecycle state")

        try:
            active = await self._port.activate(
                persisted.binding_id,
                expected_binding_revision=persisted.binding_revision,
            )
        except VoiceBindingConflict:
            # Another concurrent caller may have activated the exact persisted winner.
            # Recover authoritative state; never fall back to the caller's candidate.
            recovered = await self._port.load_scope(scope)
            if recovered is None or recovered.binding_id != persisted.binding_id:
                raise VoiceCastingError(
                    "voice binding activation race did not preserve the reserved winner"
                ) from None
            active = recovered

        self._require_scope(active, scope)
        if active.status is not VoiceBindingStatus.ACTIVE:
            raise VoiceCastingError("voice binding is not active after reservation barrier")
        return self._require_renderable(active)

    async def replace_for_future_render(
        self,
        *,
        binding_id: str,
        expected_binding_revision: int,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
    ) -> VoiceBinding:
        """Explicitly change voice identity; replacement never happens implicitly."""
        reserved = await self._port.rebind(
            binding_id,
            expected_binding_revision=expected_binding_revision,
            persona=persona,
            provider=provider,
        )
        if reserved.status is not VoiceBindingStatus.RESERVED:
            raise VoiceCastingError("voice replacement did not enter reserved state")
        try:
            active = await self._port.activate(
                binding_id,
                expected_binding_revision=reserved.binding_revision,
            )
        except VoiceBindingConflict as exc:
            raise VoiceCastingError("voice replacement lost its CAS activation") from exc
        return self._require_renderable(active)

    async def revoke(
        self, binding_id: str, *, expected_binding_revision: int
    ) -> VoiceBinding:
        revoked = await self._port.revoke(
            binding_id, expected_binding_revision=expected_binding_revision
        )
        if revoked.status is not VoiceBindingStatus.REVOKED:
            raise VoiceCastingError("voice binding revocation did not persist")
        return revoked

    @staticmethod
    def _require_scope(binding: VoiceBinding, scope: VoiceBindingScope) -> None:
        if binding.scope != scope:
            raise VoiceCastingError("voice binding repository returned another scope")

    @staticmethod
    def _require_renderable(binding: VoiceBinding) -> VoiceBinding:
        if not binding.permits_new_render:
            raise VoiceCastingError("voice binding does not permit a new render")
        return binding
