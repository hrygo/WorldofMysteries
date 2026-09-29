"""Durable provenance bindings for authorized turn-context stages.

Only source identities, revisions, and fingerprints are persisted. Evidence
bodies, rendered prompts, credentials, and provider responses stay in memory.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from .database_manager import DatabaseManager, TurnCommandTransaction
from .database_schema import StorageError

_STAGES = frozenset({"interpretation", "action", "narrative"})
_MANIFEST_FIELDS = frozenset({"source_id", "source_revision", "fingerprint"})
_MAX_IDENTIFIER_LENGTH = 256
_MAX_MANIFEST_SOURCES = 8192
_MAX_MANIFEST_BYTES = 1_048_576
_MAX_SQLITE_INTEGER = 2**63 - 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TurnContextStorageConflict(StorageError):
    """A frozen context binding cannot be replaced or safely recovered."""

    def __init__(self, code: str) -> None:
        if code not in {
            "context_stale",
            "legacy_context_unbound",
            "revision_conflict",
            "turn_identity_conflict",
        }:
            code = "revision_conflict"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True, repr=False)
class TurnContextSource:
    """One authorized source identity; never its evidence body."""

    source_id: str
    source_revision: int
    fingerprint: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or not self.source_id.strip()
            or len(self.source_id) > _MAX_IDENTIFIER_LENGTH
            or "\x00" in self.source_id
            or type(self.source_revision) is not int
            or not 0 <= self.source_revision <= _MAX_SQLITE_INTEGER
            or not isinstance(self.fingerprint, str)
            or not _SHA256.fullmatch(self.fingerprint)
        ):
            raise StorageError("Invalid turn context manifest")


@dataclass(frozen=True, slots=True, repr=False)
class TurnContextBinding:
    """Server-derived immutable identity for one authorized context stage."""

    turn_id: str
    stage: Literal["interpretation", "action", "narrative"]
    input_turn_id: str
    source_store_revision: int
    source_story_revision: int
    policy_revision: str
    content_digest: str
    lineage_digest: str
    manifest: tuple[TurnContextSource, ...] = field(repr=False)
    context_revision: str = field(init=False)
    manifest_json: str = field(init=False, repr=False)
    manifest_digest: str = field(init=False)

    @classmethod
    def from_manifest(
        cls,
        *,
        turn_id: str,
        stage: str,
        input_turn_id: str,
        source_store_revision: int,
        source_story_revision: int,
        policy_revision: str,
        content_digest: str,
        lineage_digest: str,
        manifest: Sequence[TurnContextSource | Mapping[str, object]],
    ) -> TurnContextBinding:
        """Build revision identifiers from the server-owned canonical manifest."""
        if isinstance(manifest, (str, bytes)) or not isinstance(manifest, Sequence):
            raise StorageError("Invalid turn context manifest")
        sources: list[TurnContextSource] = []
        for source in manifest:
            if isinstance(source, TurnContextSource):
                sources.append(source)
                continue
            if not isinstance(source, Mapping) or set(source) != _MANIFEST_FIELDS:
                raise StorageError("Invalid turn context manifest")
            try:
                sources.append(
                    TurnContextSource(
                        source_id=source["source_id"],  # type: ignore[arg-type]
                        source_revision=source["source_revision"],  # type: ignore[arg-type]
                        fingerprint=source["fingerprint"],  # type: ignore[arg-type]
                    )
                )
            except (KeyError, TypeError):
                raise StorageError("Invalid turn context manifest") from None
        return cls(
            turn_id=turn_id,
            stage=stage,  # type: ignore[arg-type]
            input_turn_id=input_turn_id,
            source_store_revision=source_store_revision,
            source_story_revision=source_story_revision,
            policy_revision=policy_revision,
            content_digest=content_digest,
            lineage_digest=lineage_digest,
            manifest=tuple(sources),
        )

    def __post_init__(self) -> None:
        for identifier in (self.turn_id, self.input_turn_id):
            _require_identifier(identifier)
        if not isinstance(self.stage, str) or self.stage not in _STAGES:
            raise StorageError("Invalid turn context stage")
        for revision in (self.source_store_revision, self.source_story_revision):
            if type(revision) is not int or not 0 <= revision <= _MAX_SQLITE_INTEGER:
                raise StorageError("Invalid turn context revision")
        for value in (
            self.policy_revision,
            self.content_digest,
            self.lineage_digest,
        ):
            _require_identifier(value)

        try:
            sources = tuple(self.manifest)
        except TypeError:
            raise StorageError("Invalid turn context manifest") from None
        if len(sources) > _MAX_MANIFEST_SOURCES or any(
            not isinstance(source, TurnContextSource) for source in sources
        ):
            raise StorageError("Invalid turn context manifest")
        source_ids = [source.source_id for source in sources]
        if len(set(source_ids)) != len(source_ids):
            raise StorageError("Invalid turn context manifest")

        manifest_value = [
            {
                "source_id": source.source_id,
                "source_revision": source.source_revision,
                "fingerprint": source.fingerprint,
            }
            for source in sources
        ]
        manifest_json = _canonical_json(manifest_value)
        if len(manifest_json.encode("utf-8")) > _MAX_MANIFEST_BYTES:
            raise StorageError("Turn context manifest is too large")
        manifest_digest = _sha256(manifest_json)
        context_revision = _sha256(
            _canonical_json(
                {
                    "turn_id": self.turn_id,
                    "stage": self.stage,
                    "input_turn_id": self.input_turn_id,
                    "source_store_revision": self.source_store_revision,
                    "source_story_revision": self.source_story_revision,
                    "policy_revision": self.policy_revision,
                    "content_digest": self.content_digest,
                    "lineage_digest": self.lineage_digest,
                    "manifest_digest": manifest_digest,
                }
            )
        )
        object.__setattr__(self, "manifest", sources)
        object.__setattr__(self, "manifest_json", manifest_json)
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "context_revision", context_revision)


class SQLiteTurnContextRepository:
    """Store immutable context bindings through the turn-command writer only."""

    def __init__(self, database: DatabaseManager) -> None:
        if not isinstance(database, DatabaseManager):
            raise StorageError("Turn context repository requires the world database")
        self._database = database

    async def save(self, binding: TurnContextBinding) -> TurnContextBinding:
        if not isinstance(binding, TurnContextBinding):
            raise StorageError("Turn context binding is required")
        stored = await self._database.turn_command_write(
            lambda tx: self.save_in_transaction(tx, binding)
        )
        if not isinstance(stored, TurnContextBinding):
            raise StorageError("Turn context binding was not durably stored")
        return stored

    def save_in_transaction(
        self,
        tx: TurnCommandTransaction,
        binding: TurnContextBinding,
    ) -> TurnContextBinding:
        """Save as part of an existing explanation command transaction."""
        if not isinstance(tx, TurnCommandTransaction):
            raise StorageError("Turn context binding requires the turn-command writer")
        if not isinstance(binding, TurnContextBinding):
            raise StorageError("Turn context binding is required")

        self._require_transaction(tx)
        inputs = tx.execute(
            "SELECT turn_id FROM turn_intake_commands WHERE input_turn_id=?",
            (binding.input_turn_id,),
        )
        advice = tx.execute(
            "SELECT input_turn_id FROM turn_advice_interpretations WHERE turn_id=?",
            (binding.turn_id,),
        )
        if (
            len(inputs) != 1
            or inputs[0]["turn_id"] != binding.turn_id
            or len(advice) != 1
            or advice[0]["input_turn_id"] != binding.input_turn_id
        ):
            raise TurnContextStorageConflict("turn_identity_conflict")

        prior_rows = tx.execute(
            "SELECT * FROM turn_context_bindings WHERE turn_id=? AND stage=? "
            "ORDER BY context_revision",
            (binding.turn_id, binding.stage),
        )
        if prior_rows:
            if len(prior_rows) != 1:
                raise TurnContextStorageConflict("revision_conflict")
            prior = self._from_row(prior_rows[0])
            if prior != binding:
                raise TurnContextStorageConflict("context_stale")
            return prior

        tx.execute(
            "INSERT INTO turn_context_bindings("
            "turn_id,stage,context_revision,input_turn_id,"
            "source_store_revision,source_story_revision,policy_revision,"
            "content_digest,lineage_digest,manifest_json,manifest_digest"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            self._values(binding),
        )
        rows = tx.execute(
            "SELECT * FROM turn_context_bindings "
            "WHERE turn_id=? AND stage=? AND context_revision=?",
            (binding.turn_id, binding.stage, binding.context_revision),
        )
        if len(rows) != 1:
            raise StorageError("Turn context binding was not durably inserted")
        stored = self._from_row(rows[0])
        if stored != binding:
            raise StorageError("Stored turn context binding does not match")
        return stored

    def load_in_transaction(
        self,
        tx: TurnCommandTransaction,
        *,
        turn_id: str,
        stage: str,
    ) -> TurnContextBinding | None:
        """Load one frozen binding without leaving its owning write transaction."""
        self._require_transaction(tx)
        _require_identifier(turn_id)
        if not isinstance(stage, str) or stage not in _STAGES:
            raise StorageError("Invalid turn context stage")
        rows = tx.execute(
            "SELECT * FROM turn_context_bindings WHERE turn_id=? AND stage=? "
            "ORDER BY context_revision",
            (turn_id, stage),
        )
        if len(rows) > 1:
            raise TurnContextStorageConflict("revision_conflict")
        return self._from_row(rows[0]) if rows else None

    async def load(
        self,
        *,
        turn_id: str,
        stage: str,
        context_revision: str | None = None,
    ) -> TurnContextBinding | None:
        _require_identifier(turn_id)
        if stage not in _STAGES:
            raise StorageError("Invalid turn context stage")
        if context_revision is not None and not _SHA256.fullmatch(context_revision):
            raise StorageError("Invalid turn context revision")
        if context_revision is None:
            rows = await self._database.read_world(
                "SELECT * FROM turn_context_bindings WHERE turn_id=? AND stage=? "
                "ORDER BY context_revision",
                (turn_id, stage),
            )
            if len(rows) > 1:
                raise TurnContextStorageConflict("revision_conflict")
        else:
            rows = await self._database.read_world(
                "SELECT * FROM turn_context_bindings "
                "WHERE turn_id=? AND stage=? AND context_revision=?",
                (turn_id, stage, context_revision),
            )
        if not rows:
            return None
        return self._from_row(rows[0])

    @staticmethod
    def _values(binding: TurnContextBinding) -> tuple[object, ...]:
        return (
            binding.turn_id,
            binding.stage,
            binding.context_revision,
            binding.input_turn_id,
            binding.source_store_revision,
            binding.source_story_revision,
            binding.policy_revision,
            binding.content_digest,
            binding.lineage_digest,
            binding.manifest_json,
            binding.manifest_digest,
        )

    @staticmethod
    def _require_transaction(tx: object) -> None:
        if not isinstance(tx, TurnCommandTransaction):
            raise StorageError("Turn context binding requires the turn-command writer")

    @classmethod
    def _from_row(cls, row: Mapping[str, object]) -> TurnContextBinding:
        raw_manifest = row.get("manifest_json")
        try:
            parsed = (
                json.loads(raw_manifest, object_pairs_hook=_unique_object)
                if isinstance(raw_manifest, str)
                else None
            )
            if not isinstance(parsed, list):
                raise TypeError
            binding = TurnContextBinding.from_manifest(
                turn_id=row["turn_id"],  # type: ignore[arg-type]
                stage=row["stage"],  # type: ignore[arg-type]
                input_turn_id=row["input_turn_id"],  # type: ignore[arg-type]
                source_store_revision=row["source_store_revision"],  # type: ignore[arg-type]
                source_story_revision=row["source_story_revision"],  # type: ignore[arg-type]
                policy_revision=row["policy_revision"],  # type: ignore[arg-type]
                content_digest=row["content_digest"],  # type: ignore[arg-type]
                lineage_digest=row["lineage_digest"],  # type: ignore[arg-type]
                manifest=parsed,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            RecursionError,
            StorageError,
        ):
            raise StorageError("Stored turn context binding is invalid") from None
        if (
            row.get("manifest_json") != binding.manifest_json
            or row.get("manifest_digest") != binding.manifest_digest
            or row.get("context_revision") != binding.context_revision
        ):
            raise StorageError("Stored turn context binding digest mismatch")
        return binding


def _require_identifier(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _MAX_IDENTIFIER_LENGTH
        or "\x00" in value
    ):
        raise StorageError("Invalid turn context identifier")


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise StorageError("Turn context manifest is not canonical JSON") from None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = child
    return value


__all__ = [
    "SQLiteTurnContextRepository",
    "TurnContextBinding",
    "TurnContextSource",
    "TurnContextStorageConflict",
]
