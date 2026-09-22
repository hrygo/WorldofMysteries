"""Atomic read-only capability discovery for SpeechRail 3.x.

SpeechRail's namespaced effective capability endpoint is the routing source of
truth. The client never rebuilds an atomic view by joining health, model and
voice reads from different instants. Discovery remains side-effect free and
does not imply a model residency or inference lease.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import AudioProviderConfig


ProbeStatus = Literal[
    "ready",
    "not_ready",
    "degraded",
    "unreachable",
    "invalid_config",
    "not_applicable",
]
ProbeAssurance = Literal["effective_capabilities_v1", "unknown", "not_applicable"]


@dataclass(frozen=True)
class ProbeHttpResponse:
    """One bounded JSON response used by the discovery adapter."""

    status_code: int
    payload: object
    etag: str | None = None


@dataclass(frozen=True)
class VoiceCapabilityObservation:
    """Safe subset of one SpeechRail namespaced voice entry."""

    voice_id: str
    available: bool | None = None
    variant: str | None = None
    voice_revision: str | None = None
    voice_identity_assurance: str | None = None
    production_ready: bool | None = None
    supports_speaker: bool | None = None
    supports_instruction: bool | None = None
    supports_clone: bool | None = None


@dataclass(frozen=True)
class AudioCapabilityObservation:
    """One verified effective capability generation.

    Readiness and runtime revision stay unknown unless the snapshot explicitly
    provides equivalent evidence. A discovery snapshot is not an inference
    lease and available is not worker residency or quality proof.
    """

    provider_name: str
    status: ProbeStatus
    assurance: ProbeAssurance
    ready: bool | None = None
    service_version: str | None = None
    profile: str | None = None
    asr_ready: bool | None = None
    tts_ready: bool | None = None
    model_ids: tuple[str, ...] = ()
    voices: tuple[VoiceCapabilityObservation, ...] = ()
    errors: tuple[str, ...] = ()
    service_instance_epoch: str | None = None
    catalog_revision: str | None = None
    snapshot_id: str | None = None
    etag: str | None = None


JsonFetcher = Callable[[str, float, Mapping[str, str]], Awaitable[ProbeHttpResponse]]
_MAX_DISCOVERY_BYTES = 1024 * 1024
_SCHEMA_VERSION = "effective_capabilities_v1"


class _NoRedirect(HTTPRedirectHandler):
    """Reject redirects so discovery cannot silently cross trust boundaries."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


class CapabilityTransportError(RuntimeError):
    """A discovery request could not produce a bounded HTTP response."""


def _decode_json(payload: bytes) -> object:
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapabilityTransportError("invalid_json") from exc


def _sync_get_json(
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str],
) -> ProbeHttpResponse:
    opener = build_opener(_NoRedirect)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "WorldOfMysteries-VoiceProbe/2",
            **dict(headers),
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            payload = response.read(_MAX_DISCOVERY_BYTES + 1)
            if len(payload) > _MAX_DISCOVERY_BYTES:
                raise CapabilityTransportError("response_too_large")
            return ProbeHttpResponse(
                status_code=int(response.status),
                payload=_decode_json(payload),
                etag=response.headers.get("ETag"),
            )
    except HTTPError as exc:
        payload = exc.read(_MAX_DISCOVERY_BYTES + 1)
        if len(payload) > _MAX_DISCOVERY_BYTES:
            raise CapabilityTransportError("response_too_large") from exc
        parsed: object = {}
        if exc.code != 304:
            try:
                parsed = _decode_json(payload)
            except CapabilityTransportError:
                parsed = {}
        return ProbeHttpResponse(
            status_code=int(exc.code),
            payload=parsed,
            etag=exc.headers.get("ETag"),
        )
    except (URLError, TimeoutError, OSError) as exc:
        raise CapabilityTransportError("transport_error") from exc


async def _default_fetch_json(
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str],
) -> ProbeHttpResponse:
    return await asyncio.to_thread(_sync_get_json, url, timeout_seconds, headers)


def _speechrail_capabilities_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("invalid SpeechRail base URL")
    path = parts.path.rstrip("/")
    if not path.endswith("/v1"):
        raise ValueError("SpeechRail base URL must end with /v1")
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        f"{path}/speechrail/capabilities",
        "",
        "",
    ))


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parameter_supported(entry: Mapping[str, object], name: str) -> bool | None:
    operations = entry.get("operations")
    if not isinstance(operations, Mapping):
        return None
    speech = operations.get("http_speech")
    if not isinstance(speech, Mapping):
        return None
    parameters = speech.get("parameters")
    if not isinstance(parameters, Mapping):
        return None
    parameter = parameters.get(name)
    if not isinstance(parameter, Mapping):
        return None
    status = parameter.get("status")
    if status == "supported":
        return True
    if status == "unsupported":
        return False
    return None


def _parse_model_ids(payload: Mapping[str, object]) -> tuple[str, ...] | None:
    models = payload.get("models")
    if not isinstance(models, Mapping):
        return None
    ids: set[str] = set()
    for key, raw in models.items():
        if not isinstance(key, str) or not key or not isinstance(raw, Mapping):
            return None
        source = raw.get("source_model")
        ids.add(source if isinstance(source, str) and source else key)
    return tuple(sorted(ids))


def _parse_voices(payload: Mapping[str, object]) -> tuple[VoiceCapabilityObservation, ...] | None:
    raw_voices = payload.get("voices")
    if not isinstance(raw_voices, list):
        return None
    voices: list[VoiceCapabilityObservation] = []
    for entry in raw_voices:
        if not isinstance(entry, Mapping):
            return None
        voice_id = entry.get("id")
        if not isinstance(voice_id, str) or not voice_id:
            return None
        mode = entry.get("mode")
        voices.append(
            VoiceCapabilityObservation(
                voice_id=voice_id,
                available=_bool_or_none(entry.get("available")),
                variant=_str_or_none(entry.get("variant")),
                voice_revision=_str_or_none(entry.get("voice_revision")),
                voice_identity_assurance=_str_or_none(entry.get("voice_identity_assurance")),
                production_ready=_bool_or_none(entry.get("production_ready")),
                supports_instruction=_parameter_supported(entry, "instructions"),
                supports_speaker=None,
                supports_clone=(True if mode == "clone" else None),
            )
        )
    return tuple(sorted(voices, key=lambda item: item.voice_id))


def _invalid_snapshot(config: AudioProviderConfig, code: str) -> AudioCapabilityObservation:
    return AudioCapabilityObservation(
        provider_name=config.provider_name,
        status="degraded",
        assurance="unknown",
        errors=(code,),
    )


def _parse_snapshot(
    config: AudioProviderConfig,
    response: ProbeHttpResponse,
) -> AudioCapabilityObservation:
    payload = response.payload
    if not isinstance(payload, Mapping):
        return _invalid_snapshot(config, "capabilities_invalid")
    if payload.get("schema_version") != _SCHEMA_VERSION:
        return _invalid_snapshot(config, "capabilities_schema_unsupported")
    epoch = _str_or_none(payload.get("service_instance_epoch"))
    catalog_revision = _str_or_none(payload.get("catalog_revision"))
    snapshot_id = _str_or_none(payload.get("snapshot_id"))
    models = _parse_model_ids(payload)
    voices = _parse_voices(payload)
    if (
        epoch is None
        or catalog_revision is None
        or snapshot_id is None
        or models is None
        or voices is None
        or not isinstance(payload.get("operations"), Mapping)
        or not isinstance(payload.get("guarantees"), Mapping)
    ):
        return _invalid_snapshot(config, "capabilities_invalid")
    return AudioCapabilityObservation(
        provider_name=config.provider_name,
        status="ready",
        assurance=_SCHEMA_VERSION,
        profile=_str_or_none(payload.get("profile")),
        model_ids=models,
        voices=voices,
        service_instance_epoch=epoch,
        catalog_revision=catalog_revision,
        snapshot_id=snapshot_id,
        etag=response.etag,
    )


async def probe_audio_capabilities(
    config: AudioProviderConfig,
    *,
    fetch_json: JsonFetcher | None = None,
    cached: AudioCapabilityObservation | None = None,
) -> AudioCapabilityObservation:
    """Read one SpeechRail effective capability generation without side effects."""

    if config.provider_name.casefold() != "speechrail":
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="not_applicable",
            assurance="not_applicable",
        )
    try:
        url = _speechrail_capabilities_url(config.base_url)
    except ValueError:
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="invalid_config",
            assurance="unknown",
            errors=("base_url_invalid",),
        )
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    if cached is not None and cached.assurance == _SCHEMA_VERSION and cached.etag:
        headers["If-None-Match"] = cached.etag
    fetch = fetch_json or _default_fetch_json
    try:
        response = await fetch(url, config.timeout_seconds, headers)
    except BaseException:
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="unreachable",
            assurance="unknown",
            errors=("capabilities_transport_error",),
        )
    if response.status_code == 304:
        if cached is not None and cached.assurance == _SCHEMA_VERSION and cached.etag:
            return cached
        return _invalid_snapshot(config, "capabilities_304_without_cache")
    if response.status_code == 503:
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="not_ready",
            assurance="unknown",
            errors=("capabilities_http_503",),
        )
    if response.status_code != 200:
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="degraded",
            assurance="unknown",
            errors=(f"capabilities_http_{response.status_code}",),
        )
    return _parse_snapshot(config, response)
