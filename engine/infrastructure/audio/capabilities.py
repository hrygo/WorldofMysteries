"""Conservative read-only capability discovery for the managed SpeechRail service.

The probe deliberately consumes only stable, routing-relevant fields from the
current SpeechRail read APIs. It never performs synthesis as a capability test,
never downloads models, and never upgrades missing metadata into a guarantee.
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
ProbeAssurance = Literal["legacy_observed", "not_applicable"]


@dataclass(frozen=True)
class ProbeHttpResponse:
    """One bounded JSON response used by the discovery adapter."""

    status_code: int
    payload: object


@dataclass(frozen=True)
class VoiceCapabilityObservation:
    """Safe subset of one discovered SpeechRail voice entry."""

    voice_id: str
    available: bool | None = None
    variant: str | None = None
    supports_speaker: bool | None = None
    supports_instruction: bool | None = None
    supports_clone: bool | None = None


@dataclass(frozen=True)
class AudioCapabilityObservation:
    """Point-in-time legacy discovery result.

    The current SpeechRail endpoints are independent reads, so this result is
    intentionally marked legacy_observed rather than pretending that models
    and voices belong to one atomic catalog snapshot.
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


JsonFetcher = Callable[[str, float], Awaitable[ProbeHttpResponse]]
_MAX_DISCOVERY_BYTES = 1024 * 1024


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


def _sync_get_json(url: str, timeout_seconds: float) -> ProbeHttpResponse:
    opener = build_opener(_NoRedirect)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "WorldOfMysteries-VoiceProbe/1",
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
            )
    except HTTPError as exc:
        payload = exc.read(_MAX_DISCOVERY_BYTES + 1)
        if len(payload) > _MAX_DISCOVERY_BYTES:
            raise CapabilityTransportError("response_too_large") from exc
        parsed: object
        try:
            parsed = _decode_json(payload)
        except CapabilityTransportError:
            parsed = {}
        return ProbeHttpResponse(status_code=int(exc.code), payload=parsed)
    except (URLError, TimeoutError, OSError) as exc:
        raise CapabilityTransportError("transport_error") from exc


async def _default_fetch_json(url: str, timeout_seconds: float) -> ProbeHttpResponse:
    return await asyncio.to_thread(_sync_get_json, url, timeout_seconds)


def _speechrail_urls(base_url: str) -> dict[str, str]:
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
    root_path = path[:-3].rstrip("/")

    def make(path_suffix: str) -> str:
        target_path = f"{root_path}{path_suffix}" or "/"
        return urlunsplit((parts.scheme, parts.netloc, target_path, "", ""))

    return {
        "health": make("/health"),
        "readyz": make("/readyz"),
        "models": make(f"{path}/models"[len(root_path) :]),
        "voices": make(f"{path}/voices"[len(root_path) :]),
    }


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_model_ids(payload: object) -> tuple[str, ...] | None:
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    ids: set[str] = set()
    for entry in data:
        if not isinstance(entry, Mapping):
            continue
        model_id = entry.get("id")
        if isinstance(model_id, str) and model_id:
            ids.add(model_id)
    return tuple(sorted(ids))


def _parse_voices(payload: object) -> tuple[VoiceCapabilityObservation, ...] | None:
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    voices: list[VoiceCapabilityObservation] = []
    for entry in data:
        if not isinstance(entry, Mapping):
            continue
        voice_id = entry.get("id")
        if not isinstance(voice_id, str) or not voice_id:
            continue
        raw_caps = entry.get("capabilities")
        caps = raw_caps if isinstance(raw_caps, Mapping) else {}
        voices.append(
            VoiceCapabilityObservation(
                voice_id=voice_id,
                available=_bool_or_none(entry.get("available")),
                variant=_str_or_none(entry.get("variant")),
                supports_speaker=_bool_or_none(caps.get("supports_speaker")),
                supports_instruction=_bool_or_none(caps.get("supports_instruction")),
                supports_clone=_bool_or_none(caps.get("supports_clone")),
            )
        )
    return tuple(sorted(voices, key=lambda item: item.voice_id))


async def probe_audio_capabilities(
    config: AudioProviderConfig,
    *,
    fetch_json: JsonFetcher | None = None,
) -> AudioCapabilityObservation:
    """Observe current SpeechRail routing capabilities without side effects."""

    if config.provider_name.casefold() != "speechrail":
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="not_applicable",
            assurance="not_applicable",
        )

    try:
        urls = _speechrail_urls(config.base_url)
    except ValueError:
        return AudioCapabilityObservation(
            provider_name=config.provider_name,
            status="invalid_config",
            assurance="legacy_observed",
            errors=("base_url_invalid",),
        )

    fetch = fetch_json or _default_fetch_json
    names = ("health", "readyz", "models", "voices")
    results = await asyncio.gather(
        *(fetch(urls[name], config.timeout_seconds) for name in names),
        return_exceptions=True,
    )
    responses: dict[str, ProbeHttpResponse] = {}
    errors: list[str] = []
    transport_failures = 0
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            transport_failures += 1
            errors.append(f"{name}_transport_error")
            continue
        responses[name] = result
        if result.status_code != 200:
            errors.append(f"{name}_http_{result.status_code}")

    health_payload = responses.get("health")
    health = health_payload.payload if health_payload is not None else {}
    health_map = health if isinstance(health, Mapping) else {}
    if health_payload is not None and health_payload.status_code == 200 and not isinstance(
        health, Mapping
    ):
        errors.append("health_invalid")

    ready_response = responses.get("readyz")
    ready: bool | None = None
    if ready_response is not None:
        if ready_response.status_code == 503:
            ready = False
        elif ready_response.status_code == 200 and isinstance(
            ready_response.payload, Mapping
        ):
            ready = _bool_or_none(ready_response.payload.get("ready"))
            if ready is None:
                errors.append("readyz_invalid")
        elif ready_response.status_code == 200:
            errors.append("readyz_invalid")

    models: tuple[str, ...] = ()
    model_response = responses.get("models")
    if model_response is not None and model_response.status_code == 200:
        parsed_models = _parse_model_ids(model_response.payload)
        if parsed_models is None:
            errors.append("models_invalid")
        else:
            models = parsed_models

    voices: tuple[VoiceCapabilityObservation, ...] = ()
    voice_response = responses.get("voices")
    if voice_response is not None and voice_response.status_code == 200:
        parsed_voices = _parse_voices(voice_response.payload)
        if parsed_voices is None:
            errors.append("voices_invalid")
        else:
            voices = parsed_voices

    if transport_failures == len(names):
        status: ProbeStatus = "unreachable"
    elif ready is True and not errors:
        status = "ready"
    elif ready is False:
        status = "not_ready"
    else:
        status = "degraded"

    return AudioCapabilityObservation(
        provider_name=config.provider_name,
        status=status,
        assurance="legacy_observed",
        ready=ready,
        service_version=_str_or_none(health_map.get("version")),
        profile=_str_or_none(health_map.get("profile")),
        asr_ready=_bool_or_none(health_map.get("asr_ready")),
        tts_ready=_bool_or_none(health_map.get("tts_ready")),
        model_ids=models,
        voices=voices,
        errors=tuple(sorted(set(errors))),
    )
