"""Atomic read-only capability discovery for SpeechRail.

SpeechRail's namespaced effective capability endpoint is the routing source of
truth. The client never rebuilds an atomic view by joining health, model and
voice reads from different instants. Discovery remains side-effect free and
does not imply a model residency or inference lease.

Two separations are load bearing and must not be collapsed:

* ``operations.http_speech`` and ``operations.realtime_speech`` are different
  capability entries. A voice can support an HTTP parameter while having no
  incremental Realtime path, so the two are observed independently.
* ``available`` is catalogue availability, not worker residency, not quality
  evidence and not a conditional-synthesis pin. ``status == "ready"`` only
  means the discovery document parsed as one atomic generation; ``ready``,
  ``asr_ready`` and ``tts_ready`` stay ``None`` without explicit evidence.
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
    availability_reason: str | None = None
    variant: str | None = None
    voice_revision: str | None = None
    voice_identity_assurance: str | None = None
    revoked: bool = False
    production_ready: bool | None = None
    production_ready_reason: str | None = None
    quality_status: str | None = None
    supports_speaker: bool | None = None
    supports_instruction: bool | None = None
    supports_clone: bool | None = None
    # HTTP synthesis parameters and the Realtime incremental path are separate
    # provider claims; a parameter that works over HTTP proves nothing about
    # ``speechrail.tts.start``.
    realtime_speech: bool | None = None
    model_source: str | None = None
    model_artifact: str | None = None
    model_variant: str | None = None
    model_assurance: str | None = None
    model_runtime_revision: str | None = None
    model_catalog_revision: str | None = None

    @property
    def conditional_pin(self) -> str | None:
        """Revision suitable for a provider conditional synthesis request."""
        if self.voice_identity_assurance == "content_addressed" and not self.revoked:
            return self.voice_revision
        return None


@dataclass(frozen=True)
class RealtimeResponsibilityObservation:
    """The provider's published Realtime responsibility split.

    SpeechRail is a stateless Speech Plane: the caller owns orchestration,
    conversation state, playback and barge-in. Asserting this in discovery
    keeps the Engine from assuming a server-side assistant.
    """

    orchestration: str | None = None
    server_llm: bool | None = None
    conversation_state: bool | None = None
    websocket_path: str | None = None
    mcp_realtime: bool | None = None

    @property
    def caller_orchestrated(self) -> bool | None:
        """True only when the provider explicitly states caller orchestration."""
        if self.orchestration != "caller":
            return None
        if self.server_llm is False and self.conversation_state is False:
            return True
        return None


@dataclass(frozen=True)
class AudioCapabilityObservation:
    """One verified effective capability generation.

    Readiness and runtime revision stay unknown unless the snapshot explicitly
    provides equivalent evidence. A discovery snapshot is not an inference
    lease and available is not worker residency or quality proof.

    ``status == "ready"`` means exactly one thing: the document parsed as a
    single atomic generation of the declared schema. It is not a statement that
    a model is resident, that a voice can be rendered, or that the user may
    start recording. Product surfaces must keep using ``ready``/``asr_ready``/
    ``tts_ready``, which stay ``None`` without explicit evidence.
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
    realtime: RealtimeResponsibilityObservation | None = None
    guarantees: Mapping[str, object] | None = None


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
    return _parameter_supported_in(entry, "http_speech", name)


def _parameter_supported_in(
    entry: Mapping[str, object], operation: str, name: str
) -> bool | None:
    """Read one parameter status from a named provider operation entry."""
    operations = entry.get("operations")
    if not isinstance(operations, Mapping):
        return None
    speech = operations.get(operation)
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


def _operation_declared(entry: Mapping[str, object], operation: str) -> bool | None:
    """Whether the provider publishes this operation for the entry at all."""
    operations = entry.get("operations")
    if not isinstance(operations, Mapping):
        return None
    return operation in operations


def _parse_model_identity(value: object) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        return {
            "source": None,
            "artifact": None,
            "variant": None,
            "assurance": None,
            "runtime_revision": None,
            "catalog_revision": None,
        }
    return {
        "source": _str_or_none(value.get("source_model")),
        "artifact": _str_or_none(value.get("artifact")),
        "variant": _str_or_none(value.get("variant")),
        "assurance": _str_or_none(value.get("assurance")),
        "runtime_revision": _str_or_none(value.get("runtime_revision")),
        "catalog_revision": _str_or_none(value.get("catalog_revision")),
    }


def _parse_quality_status(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    return _str_or_none(value.get("status"))


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
        identity = _parse_model_identity(entry.get("model"))
        voices.append(
            VoiceCapabilityObservation(
                voice_id=voice_id,
                available=_bool_or_none(entry.get("available")),
                availability_reason=_str_or_none(entry.get("availability_reason")),
                variant=_str_or_none(entry.get("variant")),
                voice_revision=_str_or_none(entry.get("voice_revision")),
                voice_identity_assurance=_str_or_none(entry.get("voice_identity_assurance")),
                production_ready=_bool_or_none(entry.get("production_ready")),
                production_ready_reason=_str_or_none(
                    entry.get("production_ready_reason")
                ),
                quality_status=_parse_quality_status(entry.get("quality_summary")),
                supports_instruction=_parameter_supported(entry, "instructions"),
                supports_speaker=None,
                supports_clone=(True if mode == "clone" else None),
                realtime_speech=_operation_declared(entry, "realtime_speech"),
                model_source=identity["source"],
                model_artifact=identity["artifact"],
                model_variant=identity["variant"],
                model_assurance=identity["assurance"],
                model_runtime_revision=identity["runtime_revision"],
                model_catalog_revision=identity["catalog_revision"],
            )
        )
    return tuple(sorted(voices, key=lambda item: item.voice_id))


def _parse_realtime(payload: Mapping[str, object]) -> RealtimeResponsibilityObservation | None:
    value = payload.get("realtime")
    if not isinstance(value, Mapping):
        return None
    return RealtimeResponsibilityObservation(
        orchestration=_str_or_none(value.get("orchestration")),
        server_llm=_bool_or_none(value.get("server_llm")),
        conversation_state=_bool_or_none(value.get("conversation_state")),
        websocket_path=_str_or_none(value.get("websocket_path")),
        mcp_realtime=_bool_or_none(value.get("mcp_realtime")),
    )


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
        realtime=_parse_realtime(payload),
        guarantees=dict(payload["guarantees"]),
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
    except asyncio.CancelledError:
        # Cancellation is not an observation. Swallowing it here would let a
        # cancelled probe answer a live voice request with "unreachable".
        raise
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
