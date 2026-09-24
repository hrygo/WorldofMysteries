"""W-V07 durable dry-voice AudioTake store.

Publication ordering is intentionally file-first:
partial write -> file fsync -> atomic final link -> directory fsync -> DB complete row.
A crash can therefore leave an orphan final file, but never a database row pointing
at a partial/missing asset.

RenderManifest authenticity requires a caller-supplied HMAC key. No source-code,
database or environment fallback is provided here.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable, Mapping

from .database_manager import DatabaseManager, PresentationTransaction
from .database_schema import StorageError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MODEL_REVISION = re.compile(r"^[0-9a-f]{40}$")
_ID_LIMIT = 256
_MANIFEST_LIMIT = 64 * 1024


def _text(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _ID_LIMIT
        or "\x00" in value
    ):
        raise StorageError(f"Invalid {field}")
    return value


def _sha(value: str, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise StorageError(f"Invalid {field}")
    return value


def _model_revision(value: str) -> str:
    if not isinstance(value, str) or _MODEL_REVISION.fullmatch(value) is None:
        raise StorageError("Invalid model revision")
    return value


def _canonical_json(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise StorageError("Render metadata must be bounded finite JSON") from None
    if len(encoded.encode("utf-8")) > _MANIFEST_LIMIT:
        raise StorageError("Render metadata exceeds limit")
    return encoded


def fingerprint_backend_fields(fields: Mapping[str, object]) -> str:
    if not isinstance(fields, Mapping):
        raise StorageError("Backend fields must be a mapping")
    return hashlib.sha256(_canonical_json(dict(fields)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DryRenderRecipe:
    provider_instance: str
    model_id: str
    model_revision: str
    voice_id: str
    voice_revision: str
    spoken_text_sha256: str
    pronunciation_revision: str
    backend_fingerprint: str
    codec: str = "pcm_s16le"
    sample_rate: int = 24_000
    channels: int = 1

    def __post_init__(self) -> None:
        for value, field in (
            (self.provider_instance, "provider instance"),
            (self.model_id, "model id"),
            (self.voice_id, "voice id"),
            (self.voice_revision, "voice revision"),
            (self.pronunciation_revision, "pronunciation revision"),
        ):
            _text(value, field)
        _model_revision(self.model_revision)
        _sha(self.spoken_text_sha256, "spoken text hash")
        _sha(self.backend_fingerprint, "backend fingerprint")
        if self.codec != "pcm_s16le":
            raise StorageError("Unsupported dry take codec")
        if self.sample_rate != 24_000 or self.channels != 1:
            raise StorageError("Unsupported dry take audio format")

    @classmethod
    def build(
        cls,
        *,
        provider_instance: str,
        model_id: str,
        model_revision: str,
        voice_id: str,
        voice_revision: str,
        spoken_text: str,
        pronunciation_revision: str,
        backend_fields: Mapping[str, object],
    ) -> "DryRenderRecipe":
        _text(spoken_text, "spoken text")
        return cls(
            provider_instance=provider_instance,
            model_id=model_id,
            model_revision=model_revision,
            voice_id=voice_id,
            voice_revision=voice_revision,
            spoken_text_sha256=hashlib.sha256(spoken_text.encode("utf-8")).hexdigest(),
            pronunciation_revision=pronunciation_revision,
            backend_fingerprint=fingerprint_backend_fields(backend_fields),
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "kind": "dry_voice",
            "provider_instance": self.provider_instance,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "voice_id": self.voice_id,
            "voice_revision": self.voice_revision,
            "spoken_text_sha256": self.spoken_text_sha256,
            "pronunciation_revision": self.pronunciation_revision,
            "backend_fingerprint": self.backend_fingerprint,
            "format": {
                "codec": self.codec,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
            },
        }

    @property
    def render_key(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload()).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RenderOutcome:
    provider_instance: str
    model_id: str
    model_revision: str
    voice_id: str
    voice_revision: str
    receipt_id: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.provider_instance, "resolved provider instance"),
            (self.model_id, "resolved model id"),
            (self.voice_id, "resolved voice id"),
            (self.voice_revision, "resolved voice revision"),
            (self.receipt_id, "render receipt id"),
        ):
            _text(value, field)
        _model_revision(self.model_revision)


@dataclass(frozen=True, slots=True)
class PublishedAudioTake:
    take_id: str
    render_key: str
    relative_path: str
    file_sha256: str
    manifest: dict[str, object]
    manifest_hmac: str
    replayed: bool


class RenderManifestSigner:
    def __init__(self, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) < 32:
            raise StorageError("RenderManifest HMAC key must contain at least 32 bytes")
        self._key = bytes(key)

    def sign_json(self, manifest_json: str) -> str:
        return hmac.new(
            self._key,
            manifest_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_json(self, manifest_json: str, signature: str) -> None:
        if not isinstance(signature, str) or _SHA256.fullmatch(signature) is None:
            raise StorageError("Invalid RenderManifest HMAC")
        expected = self.sign_json(manifest_json)
        if not hmac.compare_digest(expected, signature):
            raise StorageError("RenderManifest authentication failed")


class SQLiteAudioTakeStore:
    def __init__(
        self,
        database: DatabaseManager,
        assets_root: Path,
        *,
        manifest_hmac_key: bytes,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._database = database
        self._root = Path(assets_root)
        self._signer = RenderManifestSigner(manifest_hmac_key)
        self._fault_hook = fault_hook

    async def publish_pcm(
        self,
        recipe: DryRenderRecipe,
        outcome: RenderOutcome,
        pcm16: bytes,
    ) -> PublishedAudioTake:
        if not isinstance(recipe, DryRenderRecipe) or not isinstance(outcome, RenderOutcome):
            raise StorageError("Invalid dry render publication")
        self._require_outcome(recipe, outcome)
        if not isinstance(pcm16, (bytes, bytearray)):
            raise StorageError("PCM take must be bytes")
        frozen = bytes(pcm16)
        if not frozen or len(frozen) % 2:
            raise StorageError("PCM take must contain complete signed-16 frames")

        file_sha = hashlib.sha256(frozen).hexdigest()
        sample_count = len(frozen) // 2
        duration_ms = (sample_count * 1000 + recipe.sample_rate - 1) // recipe.sample_rate
        render_key = recipe.render_key
        take_id = "take_" + hashlib.sha256(
            f"{render_key}:{file_sha}".encode("ascii")
        ).hexdigest()[:32]

        manifest = {
            "schema_version": "1.0",
            "take_id": take_id,
            "render_key": render_key,
            "recipe": recipe.payload(),
            "resolved": {
                "provider_instance": outcome.provider_instance,
                "model_id": outcome.model_id,
                "model_revision": outcome.model_revision,
                "voice_id": outcome.voice_id,
                "voice_revision": outcome.voice_revision,
                "receipt_id": outcome.receipt_id,
            },
            "audio": {
                "codec": recipe.codec,
                "sample_rate": recipe.sample_rate,
                "channels": recipe.channels,
                "sample_count": sample_count,
                "byte_count": len(frozen),
                "duration_ms": duration_ms,
                "sha256": file_sha,
            },
        }
        manifest_json = _canonical_json(manifest)
        manifest_hmac = self._signer.sign_json(manifest_json)

        relative_path = await asyncio.to_thread(self._publish_file, frozen, file_sha)
        self._hit("after_asset_publish")

        def apply(tx: PresentationTransaction):
            rows = tx.execute(
                "SELECT * FROM audio_takes WHERE render_key=?",
                (render_key,),
            )
            if rows:
                row = rows[0]
                if (
                    row["file_sha256"] == file_sha
                    and row["manifest_json"] == manifest_json
                    and row["manifest_hmac"] == manifest_hmac
                    and row["relative_path"] == relative_path
                ):
                    return True
                raise StorageError("Render key is already bound to a different AudioTake")
            tx.execute(
                "INSERT INTO audio_takes("
                "take_id,render_key,relative_path,file_sha256,codec,sample_rate,channels,"
                "sample_count,byte_count,duration_ms,manifest_json,manifest_hmac,status"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    take_id,
                    render_key,
                    relative_path,
                    file_sha,
                    recipe.codec,
                    recipe.sample_rate,
                    recipe.channels,
                    sample_count,
                    len(frozen),
                    duration_ms,
                    manifest_json,
                    manifest_hmac,
                    "complete",
                ),
            )
            return False

        replayed = bool(await self._database.presentation_write(apply))
        self._hit("after_database_commit")
        return PublishedAudioTake(
            take_id=take_id,
            render_key=render_key,
            relative_path=relative_path,
            file_sha256=file_sha,
            manifest=manifest,
            manifest_hmac=manifest_hmac,
            replayed=replayed,
        )

    async def load(self, render_key: str) -> PublishedAudioTake | None:
        _sha(render_key, "render key")
        rows = await self._database.read_world(
            "SELECT * FROM audio_takes WHERE render_key=?",
            (render_key,),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("Render key resolves ambiguously")
        row = rows[0]
        if row["status"] != "complete":
            raise StorageError("AudioTake is not complete")
        manifest_json = row["manifest_json"]
        self._signer.verify_json(manifest_json, row["manifest_hmac"])
        try:
            manifest = json.loads(manifest_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise StorageError("Stored RenderManifest is invalid") from None
        if _canonical_json(manifest) != manifest_json:
            raise StorageError("Stored RenderManifest is not canonical")
        if manifest.get("render_key") != render_key:
            raise StorageError("Stored RenderManifest render key mismatch")
        await asyncio.to_thread(
            self._verify_file,
            row["relative_path"],
            row["file_sha256"],
            row["byte_count"],
        )
        return PublishedAudioTake(
            take_id=row["take_id"],
            render_key=render_key,
            relative_path=row["relative_path"],
            file_sha256=row["file_sha256"],
            manifest=manifest,
            manifest_hmac=row["manifest_hmac"],
            replayed=True,
        )

    async def orphan_relative_paths(self) -> tuple[str, ...]:
        referenced = {
            row["relative_path"]
            for row in await self._database.read_world(
                "SELECT relative_path FROM audio_takes WHERE status='complete'"
            )
        }
        return await asyncio.to_thread(self._orphan_paths, referenced)

    def _publish_file(self, pcm16: bytes, file_sha: str) -> str:
        root = self._secure_directory(self._root)
        partial_dir = self._secure_directory(root / ".partial")
        takes_dir = self._secure_directory(root / "Takes")
        relative = f"Takes/{file_sha}.pcm"
        final_path = root / relative

        fd, temporary_name = tempfile.mkstemp(
            prefix=".take-",
            suffix=".partial",
            dir=partial_dir,
        )
        temporary = Path(temporary_name)
        os.fchmod(fd, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as stream:
                stream.write(pcm16)
                stream.flush()
                os.fsync(stream.fileno())
            self._hit("after_partial_fsync")

            try:
                os.link(temporary, final_path, follow_symlinks=False)
            except FileExistsError:
                self._verify_file(relative, file_sha, len(pcm16))
            else:
                self._fsync_directory(takes_dir)
            temporary.unlink(missing_ok=True)
            self._fsync_directory(partial_dir)
            self._verify_file(relative, file_sha, len(pcm16))
            return relative
        finally:
            temporary.unlink(missing_ok=True)

    def _verify_file(self, relative_path: str, expected_sha: str, expected_bytes: int) -> None:
        if (
            not isinstance(relative_path, str)
            or not relative_path.startswith("Takes/")
            or "/" in relative_path[len("Takes/"):]
            or ".." in relative_path
        ):
            raise StorageError("Invalid AudioTake relative path")
        path = self._root / relative_path
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError:
            raise StorageError("AudioTake file is unavailable") from None
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size != expected_bytes
            ):
                raise StorageError("AudioTake file metadata is invalid")
            with os.fdopen(os.dup(fd), "rb", closefd=True) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != expected_sha:
                raise StorageError("AudioTake file digest mismatch")
        finally:
            os.close(fd)

    def _orphan_paths(self, referenced: set[str]) -> tuple[str, ...]:
        root = self._secure_directory(self._root)
        takes = self._secure_directory(root / "Takes")
        found: list[str] = []
        for entry in takes.iterdir():
            if entry.is_symlink() or not entry.name.endswith(".pcm"):
                continue
            relative = f"Takes/{entry.name}"
            if relative not in referenced:
                self._verify_file(relative, entry.stem, entry.stat().st_size)
                found.append(relative)
        return tuple(sorted(found))

    @staticmethod
    def _secure_directory(path: Path) -> Path:
        try:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            info = path.lstat()
        except OSError:
            raise StorageError("Audio asset directory is unavailable") from None
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise StorageError("Audio asset directory must be private")
        return path

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _require_outcome(recipe: DryRenderRecipe, outcome: RenderOutcome) -> None:
        if (
            outcome.provider_instance != recipe.provider_instance
            or outcome.model_id != recipe.model_id
            or outcome.model_revision != recipe.model_revision
            or outcome.voice_id != recipe.voice_id
            or outcome.voice_revision != recipe.voice_revision
        ):
            raise StorageError("Resolved render identity does not match RenderKey")

    def _hit(self, stage: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(stage)
