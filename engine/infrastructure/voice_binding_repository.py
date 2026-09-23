"""SQLite persistence for stable W-V04 VoiceBinding presentation state."""
from __future__ import annotations

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingConflict,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)

from .database_manager import DatabaseManager, PresentationTransaction, StorageError


def _from_row(row: dict) -> VoiceBinding:
    return VoiceBinding(
        binding_id=row["binding_id"],
        scope=VoiceBindingScope(
            owner_id=row["owner_id"],
            world_id=row["world_id"],
            worldline_id=row["worldline_id"],
            presentation_identity=row["presentation_identity"],
            phase=row["phase"],
            locale=row["locale"],
        ),
        persona=VoicePersonaRevision(
            logical_voice_id=row["logical_voice_id"],
            revision=row["persona_revision"],
        ),
        provider=ProviderVoiceRevision(
            provider_instance=row["provider_instance"],
            voice_id=row["provider_voice_id"],
            assurance=VoiceIdentityAssurance(row["assurance"]),
            voice_revision=row["voice_revision"],
            model_catalog_revision=row["model_catalog_revision"],
            revoked=bool(row["provider_revoked"]),
        ),
        binding_revision=row["binding_revision"],
        status=VoiceBindingStatus(row["status"]),
        reserved_at_world_revision=row["reserved_at_world_revision"],
    )


def _values(binding: VoiceBinding) -> tuple:
    return (
        binding.binding_id,
        binding.scope.owner_id,
        binding.scope.world_id,
        binding.scope.worldline_id,
        binding.scope.presentation_identity,
        binding.scope.phase,
        binding.scope.locale,
        binding.persona.logical_voice_id,
        binding.persona.revision,
        binding.provider.provider_instance,
        binding.provider.voice_id,
        binding.provider.assurance.value,
        binding.provider.voice_revision,
        binding.provider.model_catalog_revision,
        int(binding.provider.revoked),
        binding.binding_revision,
        binding.status.value,
        binding.reserved_at_world_revision,
    )


class SQLiteVoiceBindingRepository:
    """Single-writer CAS repository for presentation identity bindings."""

    def __init__(self, database: DatabaseManager):
        self.database = database

    async def load(self, binding_id: str) -> VoiceBinding:
        rows = await self.database.read_world(
            "SELECT * FROM voice_bindings WHERE binding_id=?", (binding_id,)
        )
        if len(rows) != 1:
            raise StorageError("VoiceBinding not found")
        return _from_row(rows[0])

    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None:
        rows = await self.database.read_world(
            "SELECT * FROM voice_bindings WHERE owner_id=? AND world_id=? AND worldline_id=? "
            "AND presentation_identity=? AND phase=? AND locale=?",
            (
                scope.owner_id,
                scope.world_id,
                scope.worldline_id,
                scope.presentation_identity,
                scope.phase,
                scope.locale,
            ),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("VoiceBinding scope uniqueness is corrupted")
        return _from_row(rows[0])

    async def reserve(self, candidate: VoiceBinding) -> VoiceBinding:
        if candidate.status is not VoiceBindingStatus.RESERVED or candidate.binding_revision != 1:
            raise StorageError("VoiceBinding reservation must begin at revision 1")

        def apply(tx: PresentationTransaction):
            existing = tx.execute(
                "SELECT * FROM voice_bindings WHERE owner_id=? AND world_id=? AND worldline_id=? "
                "AND presentation_identity=? AND phase=? AND locale=?",
                (
                    candidate.scope.owner_id,
                    candidate.scope.world_id,
                    candidate.scope.worldline_id,
                    candidate.scope.presentation_identity,
                    candidate.scope.phase,
                    candidate.scope.locale,
                ),
            )
            if existing:
                return _from_row(existing[0])
            tx.execute(
                "INSERT INTO voice_bindings("
                "binding_id,owner_id,world_id,worldline_id,presentation_identity,phase,locale,"
                "logical_voice_id,persona_revision,provider_instance,provider_voice_id,assurance,"
                "voice_revision,model_catalog_revision,provider_revoked,binding_revision,status,"
                "reserved_at_world_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _values(candidate),
            )
            return candidate

        return await self.database.presentation_write(apply)

    async def activate(self, binding_id: str, *, expected_binding_revision: int) -> VoiceBinding:
        return await self._evolve(
            binding_id,
            expected_binding_revision,
            lambda current: current.activate(
                expected_binding_revision=expected_binding_revision
            ),
        )

    async def revoke(self, binding_id: str, *, expected_binding_revision: int) -> VoiceBinding:
        return await self._evolve(
            binding_id,
            expected_binding_revision,
            lambda current: current.revoke(
                expected_binding_revision=expected_binding_revision
            ),
        )

    async def rebind(
        self,
        binding_id: str,
        *,
        expected_binding_revision: int,
        persona: VoicePersonaRevision,
        provider: ProviderVoiceRevision,
    ) -> VoiceBinding:
        return await self._evolve(
            binding_id,
            expected_binding_revision,
            lambda current: current.rebind(
                expected_binding_revision=expected_binding_revision,
                persona=persona,
                provider=provider,
            ),
        )

    async def _evolve(self, binding_id: str, expected_revision: int, evolve) -> VoiceBinding:
        def apply(tx: PresentationTransaction):
            rows = tx.execute("SELECT * FROM voice_bindings WHERE binding_id=?", (binding_id,))
            if len(rows) != 1:
                raise StorageError("VoiceBinding not found")
            current = _from_row(rows[0])
            if current.binding_revision != expected_revision:
                raise VoiceBindingConflict("expected binding revision does not match")
            updated = evolve(current)
            tx.execute(
                "UPDATE voice_bindings SET logical_voice_id=?,persona_revision=?,"
                "provider_instance=?,provider_voice_id=?,assurance=?,voice_revision=?,"
                "model_catalog_revision=?,provider_revoked=?,binding_revision=?,status=? "
                "WHERE binding_id=? AND binding_revision=?",
                (
                    updated.persona.logical_voice_id,
                    updated.persona.revision,
                    updated.provider.provider_instance,
                    updated.provider.voice_id,
                    updated.provider.assurance.value,
                    updated.provider.voice_revision,
                    updated.provider.model_catalog_revision,
                    int(updated.provider.revoked),
                    updated.binding_revision,
                    updated.status.value,
                    binding_id,
                    expected_revision,
                ),
            )
            return updated

        return await self.database.presentation_write(apply)
