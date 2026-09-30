"""SpeechRail adapter for the Voice Foundry provider port.

This is the only module that knows SpeechRail's wire shape. It maps the
application-layer :class:`VoiceFoundryPort` onto the real
``/v1/voice-designs`` routes and deliberately imports nothing from the
SpeechRail source tree — the upstream contract is re-declared here from
observed request/response shapes, so an upstream change surfaces as a
failing test rather than as silent behaviour drift.

Three rules shape the mapping:

* Wire requests carry exactly the fields SpeechRail accepts. Its request
  models set ``extra="forbid"``, so one invented field is a 422.
* Identifiers and revisions are opaque strings. Upstream uses ``vd_`` /
  ``vv_`` candidate/validation ids and ``vr_`` revisions; those formats are
  checked at the edge and never re-derived or parsed.
* Anything the provider cannot prove is refused. A published voice whose
  execution evidence cannot be filled raises ``provider_contract_unsupported``
  instead of being assembled from plausible defaults.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from application.voice_foundry_ports import (
    REQUIRED_EVIDENCE_FIELDS,
    AssetRequest,
    AssetResult,
    CandidateState,
    ConfirmRequest,
    CreateRequest,
    EvidenceBundle,
    FoundryOperation,
    FoundryReviewVerdict,
    PreviewRequest,
    PreviewResult,
    ProviderLocaleMap,
    PublishResult,
    ValidationResult,
    VoiceFoundryCapabilities,
    VoiceFoundryPortError,
    admit_foundry_locale,
    review_verdict_to_status,
)

from .config import AudioProviderConfig

MAX_JSON_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_REFERENCE_CHARS = 240
MAX_VALIDATION_CHARS = 240
MAX_AUDIO_SECONDS = 60

_CANDIDATE_ID = re.compile(r"^vd_[0-9a-f]{24}$")
_VALIDATION_ID = re.compile(r"^vv_[0-9a-f]{24}$")
_CANDIDATE_REVISION = re.compile(r"^vr_[0-9a-f]{32}$")
_VOICE_ID = re.compile(r"^[a-z0-9_-]{1,64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: SpeechRail advertises ``language="zh"`` only. Stating that mapping here —
#: rather than inferring it from the tag — is what stops zh-TW from being
#: silently treated as accepted.
GAME_TO_PROVIDER_LOCALE = ProviderLocaleMap({"zh-CN": "zh"})

_RETRY_STATUS = frozenset({500, 502, 503, 504})
_STATUS_CODES = {
    400: "foundry_rejected",
    401: "foundry_unauthorized",
    403: "foundry_forbidden",
    404: "foundry_not_found",
    409: "foundry_conflict",
    422: "foundry_rejected",
    429: "foundry_busy",
}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """One raw HTTP reply. Bodies stay bytes; the caller decides how to read."""

    status_code: int
    body: bytes


@dataclass(frozen=True, slots=True)
class FoundryExecutionPolicy:
    """The execution identity this deployment enforces, declared not inferred.

    ``model_id``/``variant`` name what SpeechRail reports; the policy revision
    and processing fingerprint describe what *we* enforce, so they cannot be
    read off a provider response and must be supplied deliberately.
    """

    model_id: str
    variant: str
    validation_policy_revision: str
    processing_fingerprint: str
    allowed_usages: frozenset[str]
    scope_ref: str

    def __post_init__(self) -> None:
        if not _DIGEST.match(self.processing_fingerprint):
            raise VoiceFoundryPortError("provider_contract_unsupported")
        if not self.allowed_usages or not self.allowed_usages <= {
            "dialogue",
            "narration",
        }:
            raise VoiceFoundryPortError("provider_contract_unsupported")


class _NoRedirect(HTTPRedirectHandler):
    """A redirect could move a voice-design call across a trust boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def _sync_send(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    max_bytes: int,
    timeout: float,
) -> HttpResponse:
    opener = build_opener(_NoRedirect)
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise VoiceFoundryPortError("foundry_response_too_large")
            return HttpResponse(status_code=int(response.status), body=payload)
    except HTTPError as exc:
        payload = exc.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise VoiceFoundryPortError("foundry_response_too_large") from exc
        return HttpResponse(status_code=int(exc.code), body=payload)
    except (URLError, TimeoutError, OSError) as exc:
        raise VoiceFoundryPortError("foundry_transient") from exc


Transport = Callable[
    [str, str, Mapping[str, str], bytes | None, int, float],
    Awaitable[HttpResponse],
]


class SpeechRailVoiceFoundryAdapter:
    """Drive one SpeechRail instance through the Foundry supply port."""

    def __init__(
        self,
        config: AudioProviderConfig,
        *,
        preview_model: str,
        fetch: Transport | None = None,
        execution_policy: FoundryExecutionPolicy | None = None,
        strict_rendering_entitlement: str | None = None,
        max_audio_bytes: int = MAX_ASSET_BYTES,
        max_audio_seconds: int = MAX_AUDIO_SECONDS,
    ) -> None:
        self._base = self._validate_base(config.base_url)
        self._api_key = config.api_key
        self._timeout = config.timeout_seconds
        self._preview_model = preview_model
        self._execution_policy = execution_policy
        self._fetch = fetch or self._default_fetch
        self._capabilities = VoiceFoundryCapabilities(
            operations=frozenset(FoundryOperation),
            accepted_game_locales=frozenset(GAME_TO_PROVIDER_LOCALE.mapping),
            max_reference_chars=MAX_REFERENCE_CHARS,
            max_validation_chars=MAX_VALIDATION_CHARS,
            max_audio_bytes=max_audio_bytes,
            max_audio_seconds=max_audio_seconds,
            # Strict rendering is opt-in with a named entitlement. A REST header
            # does not prove the Realtime path the game actually renders on can
            # reject before first audio, so silence must never mean "yes".
            strict_rendering=strict_rendering_entitlement is not None,
            evidence_fields=REQUIRED_EVIDENCE_FIELDS,
            # Upstream exposes POST /{candidate_id}/cancel, which moves a live
            # candidate to cancelled and refuses an already published one.
            remote_cancel=True,
        )

    # -- capabilities ----------------------------------------------------

    @property
    def capabilities(self) -> VoiceFoundryCapabilities:
        return self._capabilities

    @property
    def locale_map(self) -> ProviderLocaleMap:
        return GAME_TO_PROVIDER_LOCALE

    # -- transport -------------------------------------------------------

    @staticmethod
    def _validate_base(base_url: str):
        parts = urlsplit(base_url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or not parts.path.rstrip("/").endswith("/v1")
        ):
            raise VoiceFoundryPortError("foundry_invalid_configuration")
        return parts

    def _url(self, suffix: str) -> str:
        return urlunsplit(
            (
                self._base.scheme,
                self._base.netloc,
                f"{self._base.path.rstrip('/')}/{suffix}",
                "",
                "",
            )
        )

    async def _default_fetch(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        max_bytes: int,
        timeout: float,
    ) -> HttpResponse:
        return await asyncio.to_thread(_sync_send, method, url, headers, body, max_bytes, timeout)

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "WorldOfMysteries-VoiceFoundry/1",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if extra:
            headers.update(extra)
        return headers

    async def _json(
        self,
        method: str,
        suffix: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        body = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        # A JSON body without its content type is not a JSON body as far as
        # the provider is concerned: SpeechRail parses request models from the
        # declared type, so every create/confirm/validate/review/publish came
        # back 422 before reaching any provider logic. Declaring it here rather
        # than per call site is what stops the next one from forgetting.
        merged = {"Content-Type": "application/json", **(headers or {})}
        response = await self._fetch(
            method,
            self._url(suffix),
            self._headers(merged),
            body,
            MAX_JSON_BYTES,
            self._timeout,
        )
        return self._decode(response)

    @staticmethod
    def _decode(response: HttpResponse) -> Mapping[str, object]:
        status = response.status_code
        if status >= 400:
            if status in _RETRY_STATUS:
                raise VoiceFoundryPortError("foundry_transient")
            code = _STATUS_CODES.get(status)
            raise VoiceFoundryPortError(code if code is not None else f"foundry_http_{status}")
        if not response.body:
            return {}
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VoiceFoundryPortError("foundry_invalid_json") from exc
        if not isinstance(decoded, Mapping):
            raise VoiceFoundryPortError("foundry_invalid_json")
        return decoded

    # -- supply operations -----------------------------------------------

    async def preview(self, request: PreviewRequest) -> PreviewResult:
        self._capabilities.require(FoundryOperation.PREVIEW)
        admitted = admit_foundry_locale(
            self._capabilities, GAME_TO_PROVIDER_LOCALE, request.game_locale
        )
        self._capabilities.validate_preview(request)
        # A preview is the one supply call whose success body is the audio
        # itself: the provider answers a design request with the rendered WAV
        # (OpenAI speech shape), not with a JSON envelope carrying a digest.
        # Reading it as JSON fails on the very response that means the voice
        # rendered, which is the opposite of what a supply failure looks like.
        response = await self._fetch(
            "POST",
            self._url("voices/previews"),
            self._headers({"Content-Type": "application/json"}),
            json.dumps(
                {
                    "model": self._preview_model,
                    "input": request.reference_text,
                    "instruction": request.voice_description,
                    "response_format": "wav",
                    "language": admitted.provider_locale,
                    "seed": request.seed,
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            MAX_ASSET_BYTES,
            self._timeout,
        )
        if response.status_code >= 400:
            self._decode(response)  # raises the mapped reason code
        audio = response.body
        recipe = {
            "preview_model": self._preview_model,
            "voice_description": request.voice_description,
            "seed": request.seed,
            "provider_locale": admitted.provider_locale,
        }
        return PreviewResult(
            preview_id=f"pv_{hashlib.sha256(audio).hexdigest()[:24]}",
            audio_digest=hashlib.sha256(audio).hexdigest(),
            audio_bytes=len(audio),
            duration_seconds=_wav_duration_seconds(audio),
            recipe=recipe,
            recipe_digest=hashlib.sha256(
                json.dumps(recipe, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            # The clip travels with its own digest: a preview nobody can play
            # is not an audition, and this is the payload the listening desk
            # hands to a reviewer.
            audio=audio,
        )

    async def create(self, request: CreateRequest) -> CandidateState:
        self._capabilities.require(FoundryOperation.CREATE)
        if not _VOICE_ID.match(request.voice_id):
            raise VoiceFoundryPortError("foundry_rejected")
        payload = await self._json(
            "POST",
            "voice-designs",
            payload={
                "voice_id": request.voice_id,
                "name": request.name,
                "instruction": request.instruction,
                "reference_text": request.reference_text,
                "seed": request.seed,
                "language": request.provider_locale,
            },
            headers={"Idempotency-Key": request.idempotency_key},
        )
        return _candidate_state(payload)

    async def query(self, candidate_id: str) -> CandidateState:
        self._capabilities.require(FoundryOperation.QUERY)
        _require_id(candidate_id, _CANDIDATE_ID, "foundry_not_found")
        return _candidate_state(await self._json("GET", f"voice-designs/{_seg(candidate_id)}"))

    async def confirm(self, candidate_id: str, request: ConfirmRequest) -> CandidateState:
        self._capabilities.require(FoundryOperation.CONFIRM)
        _require_id(candidate_id, _CANDIDATE_ID, "foundry_not_found")
        return _candidate_state(
            await self._json(
                "POST",
                f"voice-designs/{_seg(candidate_id)}/confirm",
                payload={"reference_text": request.reference_text},
            )
        )

    async def validate(
        self,
        candidate_id: str,
        *,
        test_text: str,
        capability_key: str,
    ) -> ValidationResult:
        self._capabilities.require(FoundryOperation.VALIDATE)
        _require_id(candidate_id, _CANDIDATE_ID, "foundry_not_found")
        self._capabilities.validate_validation_text(test_text)
        payload = await self._json(
            "POST",
            f"voice-designs/{_seg(candidate_id)}/validate",
            payload={"test_text": test_text, "capability_key": capability_key},
        )
        return _validation_result(payload, candidate_id, capability_key)

    async def review(
        self,
        candidate_id: str,
        *,
        validation_id: str,
        identity: FoundryReviewVerdict,
        naturalness: FoundryReviewVerdict,
        validation_audio_digest: str = "",
    ) -> EvidenceBundle:
        self._capabilities.require(FoundryOperation.REVIEW)
        _require_id(candidate_id, _CANDIDATE_ID, "foundry_not_found")
        _require_id(validation_id, _VALIDATION_ID, "foundry_not_found")
        # Refuse before the call: a verdict we cannot record losslessly must
        # never be sent upstream and then dropped on the way back.
        identity_status = review_verdict_to_status(identity)
        naturalness_status = review_verdict_to_status(naturalness)
        payload = await self._json(
            "POST",
            f"voice-designs/{_seg(candidate_id)}/validate",
            payload={
                "human_review": {
                    "validation_id": validation_id,
                    "identity": identity.value,
                    "naturalness": naturalness.value,
                }
            },
        )
        candidate = _nested_candidate(payload)
        return self._evidence(
            candidate,
            identity_status=identity_status,
            naturalness_status=naturalness_status,
            review_id=validation_id,
            validation_audio_digest=validation_audio_digest,
        )

    async def publish(
        self,
        candidate_id: str,
        *,
        expected_candidate_revision: str,
    ) -> PublishResult:
        self._capabilities.require(FoundryOperation.PUBLISH)
        _require_id(candidate_id, _CANDIDATE_ID, "foundry_not_found")
        _require_id(expected_candidate_revision, _CANDIDATE_REVISION, "foundry_conflict")
        payload = await self._json(
            "POST",
            f"voice-designs/{_seg(candidate_id)}/publish",
            payload={"expected_candidate_revision": expected_candidate_revision},
        )
        candidate = _nested_candidate(payload)
        state = _candidate_state(candidate)
        voice_id = _text_field(candidate, "target_voice_id", "")
        if not _VOICE_ID.match(voice_id):
            raise VoiceFoundryPortError("provider_contract_unsupported")
        published_revision = _optional_text(candidate, "published_voice_revision")
        if published_revision is None:
            raise VoiceFoundryPortError("provider_contract_unsupported")
        evidence = self._evidence(
            candidate,
            identity_status=None,
            naturalness_status=None,
            review_id=None,
            published_revision=published_revision,
        )
        return PublishResult(
            candidate_id=state.candidate_id,
            candidate_revision=state.candidate_revision,
            voice_id=voice_id,
            voice_revision=published_revision,
            evidence=evidence,
        )

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        _require_id(request.candidate_id, _CANDIDATE_ID, "foundry_not_found")
        # Both asset routes require the caller to name the revision it expects
        # (`SpeechRail-Expected-Candidate-Revision`); omitting it is a 428, not
        # a lenient default. The header is also the only thing that keeps the
        # audio we hash tied to the revision our evidence names.
        _require_id(
            request.candidate_revision, _CANDIDATE_REVISION, "foundry_conflict"
        )
        headers = {
            "SpeechRail-Expected-Candidate-Revision": request.candidate_revision,
        }
        if request.validation_id is None:
            suffix = f"voice-designs/{_seg(request.candidate_id)}/audio"
        else:
            _require_id(request.validation_id, _VALIDATION_ID, "foundry_not_found")
            suffix = (
                f"voice-designs/{_seg(request.candidate_id)}"
                f"/validations/{_seg(request.validation_id)}/audio"
            )
        response = await self._fetch(
            "GET",
            self._url(suffix),
            self._headers(headers),
            None,
            MAX_ASSET_BYTES,
            self._timeout,
        )
        if response.status_code >= 400:
            self._decode(response)  # raises the mapped reason code
        return AssetResult(
            audio_digest=hashlib.sha256(response.body).hexdigest(),
            audio_bytes=len(response.body),
            duration_seconds=0.0,
            # The payload travels with its own digest. Hashing it and dropping
            # it would let this call report success while leaving the caller
            # with nothing to audition — which is the one thing an asset read
            # exists for.
            audio=response.body,
        )

    # -- evidence --------------------------------------------------------

    def _evidence(
        self,
        candidate: Mapping[str, object],
        *,
        identity_status: str | None,
        naturalness_status: str | None,
        review_id: str | None,
        published_revision: str | None = None,
        validation_audio_digest: str = "",
    ) -> EvidenceBundle:
        """Assemble evidence from reported facts, or refuse to assemble it."""
        policy = self._execution_policy
        if policy is None:
            # Without a declared execution identity the execution section
            # cannot be filled. Inventing model/policy values here would yield
            # evidence that looks complete but proves nothing.
            raise VoiceFoundryPortError("provider_contract_unsupported")
        reference = _mapping(candidate, "reference")
        source_model = _mapping(candidate, "source_model")
        validation = _latest_validation(candidate)
        # Upstream reports `source_model.artifact` (which model) and
        # `source_model.revision` (which revision of that model). The evidence
        # contract wants the revision here; the model identity comes from the
        # declared policy, not from a provider string.
        artifact_revision = _text_field(source_model, "revision", "")
        if not artifact_revision:
            raise VoiceFoundryPortError("provider_contract_unsupported")
        reference_audio = _digest_field(reference, "audio_sha256")
        evidence_digest = hashlib.sha256(
            json.dumps(
                {
                    "candidate": candidate.get("id"),
                    "reference": dict(reference),
                    "validation": dict(validation),
                    "fingerprint": policy.processing_fingerprint,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return EvidenceBundle(
            evidence_id=f"ev_{evidence_digest[:24]}",
            evidence_digest=evidence_digest,
            execution={
                "model_id": policy.model_id,
                "model_artifact_revision": artifact_revision,
                "variant": policy.variant,
                "locale": _text_field(candidate, "language", ""),
                "validation_policy_revision": policy.validation_policy_revision,
                "processing_fingerprint": policy.processing_fingerprint,
                "model_catalog_revision": _text_field(validation, "model_catalog_revision", ""),
            },
            reference={
                "status": "pass",
                "audio_digest": reference_audio,
                "text_digest": _digest_field(reference, "text_sha256"),
            },
            output={
                "status": _text_field(validation, "machine_status", "not_run"),
                "capability_key": _text_field(validation, "capability_key", ""),
                "validation_id": _text_field(validation, "validation_id", ""),
            },
            human={
                "identity_status": identity_status
                or _text_field(validation, "identity_status", "not_run"),
                "naturalness_status": naturalness_status
                or _text_field(validation, "naturalness_status", "not_run"),
                "review_id": review_id or _text_field(validation, "validation_id", ""),
                "reference_audio_digest": reference_audio,
                # The provider publishes no digest for a validation, so this
                # is the caller's to supply: it is the digest of the asset the
                # caller actually read, which is the only one that describes
                # the audio a person approved. Reading it from the reply — as
                # this did, from a field the service does not publish — left
                # evidence that named a validation while saying nothing about
                # what was heard.
                "validation_audio_digest": validation_audio_digest,
            },
            publication={
                "state": "published",
                "published_revision": published_revision
                or _text_field(candidate, "published_voice_revision", ""),
            },
            rights={
                "allowed_usages": sorted(policy.allowed_usages),
                "scope_ref": policy.scope_ref,
            },
        )


# -- decoding helpers ------------------------------------------------------


def _seg(value: str) -> str:
    return quote(value, safe="")


def _require_id(value: str, pattern: re.Pattern[str], code: str) -> None:
    if not isinstance(value, str) or not pattern.match(value):
        raise VoiceFoundryPortError(code)


def _nested_candidate(payload: Mapping[str, object]) -> Mapping[str, object]:
    candidate = payload.get("candidate")
    if not isinstance(candidate, Mapping):
        raise VoiceFoundryPortError("provider_contract_unsupported")
    return candidate


def _mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise VoiceFoundryPortError("provider_contract_unsupported")
    return value


def _wav_duration_seconds(audio: bytes) -> float:
    """Read a rendered clip's length from its own WAV header.

    A preview used to arrive as a JSON envelope that stated the duration. It
    now arrives as the audio itself, so the length has to come from the bytes
    — a header this parser does not recognise is reported as unknown (0.0)
    rather than guessed at, because a wrong duration is worse than none.
    """
    if len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        return 0.0
    offset = 12
    byte_rate = 0
    while offset + 8 <= len(audio):
        chunk_id = audio[offset : offset + 4]
        chunk_size = int.from_bytes(audio[offset + 4 : offset + 8], "little")
        start = offset + 8
        end = start + chunk_size
        if end > len(audio):
            break
        if chunk_id == b"fmt " and chunk_size >= 16:
            byte_rate = int.from_bytes(audio[start + 8 : start + 12], "little")
        elif chunk_id == b"data":
            if byte_rate <= 0:
                return 0.0
            return round(chunk_size / byte_rate, 3)
        offset = end + (chunk_size % 2)
    return 0.0


def _text_field(payload: Mapping[str, object], key: str, default: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) and value else default


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _digest_field(payload: Mapping[str, object], key: str, *, required: bool = True) -> str:
    value = payload.get(key)
    if isinstance(value, str) and _DIGEST.match(value):
        return value
    if required:
        raise VoiceFoundryPortError("provider_contract_unsupported")
    return ""


def _candidate_state(payload: Mapping[str, object]) -> CandidateState:
    source = payload.get("candidate")
    if not isinstance(source, Mapping):
        source = payload
    candidate_id = _text_field(source, "id", "")
    revision = _text_field(source, "revision", "")
    _require_id(candidate_id, _CANDIDATE_ID, "provider_contract_unsupported")
    _require_id(revision, _CANDIDATE_REVISION, "provider_contract_unsupported")
    return CandidateState(
        candidate_id=candidate_id,
        candidate_revision=revision,
        state=_text_field(source, "state", "unknown"),
        reference_confirmed=bool(source.get("confirmed_at")),
    )


def _latest_validation(candidate: Mapping[str, object]) -> Mapping[str, object]:
    validations = candidate.get("validations")
    if not isinstance(validations, list) or not validations:
        raise VoiceFoundryPortError("provider_contract_unsupported")
    latest = validations[-1]
    if not isinstance(latest, Mapping):
        raise VoiceFoundryPortError("provider_contract_unsupported")
    return latest


def _validation_result(
    payload: Mapping[str, object], candidate_id: str, capability_key: str
) -> ValidationResult:
    # A validation is reported on the candidate that carries it, not as a
    # top-level field: the reply nests every validation the candidate holds and
    # the one just recorded is the last of them. Reading a top-level
    # `validation` that no longer exists yields an empty id, which fails as an
    # unsupported provider rather than as the cross-text check that just ran.
    source = payload.get("validation")
    if not isinstance(source, Mapping):
        candidate = _nested_candidate(payload)
        validations = candidate.get("validations")
        if not isinstance(validations, list) or not validations:
            raise VoiceFoundryPortError("provider_contract_unsupported")
        latest = validations[-1]
        if not isinstance(latest, Mapping):
            raise VoiceFoundryPortError("provider_contract_unsupported")
        source = latest
    validation_id = _text_field(source, "validation_id", "")
    _require_id(validation_id, _VALIDATION_ID, "provider_contract_unsupported")
    return ValidationResult(
        validation_id=validation_id,
        candidate_id=candidate_id,
        candidate_revision=_text_field(source, "candidate_revision", ""),
        capability_key=_text_field(source, "capability_key", capability_key),
        # A validation publishes no digest. The service holds
        # `output_wav_sha256` and `test_text_sha256` on the record and
        # deliberately keeps them out of the projection, so there is no field
        # name to read here — this adapter used to look for `audio_sha256`
        # and `text_sha256`, found neither, and returned an empty digest that
        # travelled all the way to the repository before anything refused it.
        #
        # The audio's identity is established by reading the asset instead,
        # which the caller does rather than this layer. Reporting a digest
        # here would mean reporting one this layer cannot stand behind.
        audio_digest="",
        text_digest="",
        passed=_text_field(source, "machine_status", "") == "pass",
    )


__all__ = [
    "GAME_TO_PROVIDER_LOCALE",
    "MAX_ASSET_BYTES",
    "MAX_JSON_BYTES",
    "FoundryExecutionPolicy",
    "HttpResponse",
    "SpeechRailVoiceFoundryAdapter",
]
