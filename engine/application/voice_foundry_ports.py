"""Voice Foundry provider port: the seam between orchestration and a provider.

This module owns no transport, no provider SDK and no database. It states
exactly which voice-supply operations a provider must be able to perform,
which locales it may be *asked* about, what asset limits apply, and whether
it can render under a strict, evidence-gated policy.

Two rules drive the whole design:

* Capability is declared, never assumed. An operation the provider cannot
  perform is rejected up front instead of being silently skipped.
* A missing capability degrades explicitly. When a provider cannot gate
  rendering strictly, the decision says so and keeps subtitles on; the
  caller must never fall back to an unverified render that merely happens
  to succeed.

Locale handling is deliberately asymmetric. A provider advertises the exact
game locales it has been validated for; the adapter supplies a separate,
explicit map from game locale to provider locale. Nothing is inferred from
a provider's internal language tag, because ``language="zh"`` says nothing
about whether ``zh-TW`` was ever accepted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# The provider must normalize a reference/validation text to at least this many
# characters before it is accepted; shorter prompts do not carry enough
# phonetic evidence to judge a voice.
MIN_TEXT_CHARS = 20


class FoundryOperation(StrEnum):
    """The supply operations a Foundry adapter must be able to perform."""

    PREVIEW = "preview"
    CREATE = "create"
    QUERY = "query"
    CONFIRM = "confirm"
    VALIDATE = "validate"
    REVIEW = "review"
    PUBLISH = "publish"


class FoundryReviewVerdict(StrEnum):
    """The verdict domain a provider reports for a human review.

    Mirrors the provider-facing literal domain. ``NOT_REVIEWED`` is a real
    state, not a default that machine metrics may fill in.
    """

    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"
    NOT_REVIEWED = "not_reviewed"


# Our shipped evidence contract (contracts/schemas/voice_identity_evidence
# .schema.json) can only express ``pass``/``fail``/``not_run``/``pending`` for
# a human review status. ``warn`` has no lossless representation there, so it
# is deliberately absent from this mapping rather than folded into ``pass``:
# promoting a warning to a pass would widen what counts as accepted evidence,
# which is exactly the failure mode this port exists to prevent. Callers must
# handle WARN explicitly (see ``review_verdict_is_accepted``).
_REVIEW_VERDICT_TO_STATUS: Mapping[FoundryReviewVerdict, str] = {
    FoundryReviewVerdict.PASS: "pass",
    FoundryReviewVerdict.REJECT: "fail",
    FoundryReviewVerdict.NOT_REVIEWED: "not_run",
}

#: Evidence sections a provider must be able to evidence for a published voice.
REQUIRED_EVIDENCE_FIELDS = frozenset(
    {"execution", "reference", "output", "human", "publication", "rights"}
)


class VoiceFoundryPortError(ValueError):
    """A provider capability, limit or contract requirement is not satisfied.

    ``code`` is the stable, machine-readable reason. It is part of the port
    contract: callers branch on it, so codes are added, never repurposed.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PreviewRequest:
    """One candidate preview: description + reference text, no registration.

    Previewing must not register a production voice; it only produces media
    the operator can audition while choosing a candidate.
    """

    game_locale: str
    voice_description: str
    reference_text: str
    seed: int
    audio_bytes: int = 0

    def __post_init__(self) -> None:
        if self.audio_bytes < 0:
            raise VoiceFoundryPortError("audio_limit_exceeded")
        if self.seed < 0:
            raise VoiceFoundryPortError("invalid_seed")


@dataclass(frozen=True, slots=True)
class ProviderLocaleMap:
    """Explicit game-locale -> provider-locale mapping owned by the adapter."""

    mapping: Mapping[str, str]

    def __post_init__(self) -> None:
        for game_locale, provider_locale in self.mapping.items():
            if not game_locale or not provider_locale:
                raise VoiceFoundryPortError("unsupported_locale")

    def resolve(self, game_locale: str) -> str | None:
        return self.mapping.get(game_locale)


@dataclass(frozen=True, slots=True)
class LocaleAdmission:
    """A locale that cleared both the capability check and the explicit map."""

    game_locale: str
    provider_locale: str


@dataclass(frozen=True, slots=True)
class StrictRenderingDecision:
    """Whether formal rendering may run under a strict, gated policy."""

    admitted: bool
    reason_code: str | None
    retain_subtitles: bool


@dataclass(frozen=True, slots=True)
class VoiceFoundryCapabilities:
    """What one provider instance can actually do, declared up front."""

    operations: frozenset[FoundryOperation]
    accepted_game_locales: frozenset[str]
    max_reference_chars: int
    max_validation_chars: int
    max_audio_bytes: int
    max_audio_seconds: int
    strict_rendering: bool
    evidence_fields: frozenset[str]
    remote_cancel: bool

    def require(self, operation: FoundryOperation) -> None:
        """Fail closed when the provider cannot perform ``operation``."""
        if operation not in self.operations:
            raise VoiceFoundryPortError("provider_capability_missing")

    def validate_preview(self, request: PreviewRequest) -> None:
        """Check a preview against declared limits before any provider call."""
        if (
            len(request.reference_text) < MIN_TEXT_CHARS
            or len(request.reference_text) > self.max_reference_chars
        ):
            raise VoiceFoundryPortError("reference_text_out_of_range")
        if request.audio_bytes > self.max_audio_bytes:
            raise VoiceFoundryPortError("audio_limit_exceeded")

    def validate_validation_text(self, text: str) -> None:
        """Cross-text validation must be as long as a reference, within limits."""
        if len(text) < MIN_TEXT_CHARS or len(text) > self.max_validation_chars:
            raise VoiceFoundryPortError("validation_text_out_of_range")

    def require_evidence_fields(self, fields: frozenset[str]) -> None:
        """Reject a provider that cannot evidence everything we must record."""
        if not fields <= self.evidence_fields:
            raise VoiceFoundryPortError("provider_contract_unsupported")


@dataclass(frozen=True, slots=True)
class PreviewResult:
    """Media for one audition. It registers nothing and proves nothing."""

    preview_id: str
    audio_digest: str
    audio_bytes: int
    duration_seconds: float
    recipe: Mapping[str, object]
    recipe_digest: str


@dataclass(frozen=True, slots=True)
class CreateRequest:
    """Register one private candidate from a chosen recipe.

    ``idempotency_key`` must be stable across retries: an unknown create result
    is reconciled with the *same* key and the same ``voice_id``, never by
    minting a new identity.
    """

    voice_id: str
    name: str
    instruction: str
    reference_text: str
    seed: int
    provider_locale: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CandidateState:
    """Provider-reported candidate state plus its opaque revision token."""

    candidate_id: str
    candidate_revision: str
    state: str
    reference_confirmed: bool


@dataclass(frozen=True, slots=True)
class ConfirmRequest:
    """Bind the candidate's current reference audio.

    Confirmation is about the *current* reference: changing the reference
    text invalidates a previous confirmation, so the text travels with the
    call instead of being implied by an earlier create.
    """

    reference_text: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """One machine validation pass over cross-text audio."""

    validation_id: str
    candidate_id: str
    candidate_revision: str
    capability_key: str
    audio_digest: str
    text_digest: str
    passed: bool


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Everything we must persist to evidence one published voice.

    Field values mirror contracts/schemas/voice_identity_evidence.schema.json
    so the snapshot can be validated against the shipped contract unchanged.
    """

    evidence_id: str
    evidence_digest: str
    execution: Mapping[str, object]
    reference: Mapping[str, object]
    output: Mapping[str, object]
    human: Mapping[str, object]
    publication: Mapping[str, object]
    rights: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AssetRequest:
    """Read one exact asset so audition binds a real digest, not a promise.

    ``candidate_revision`` is mandatory, not advisory. The provider moves a
    candidate to a new revision every time its reference audio is rebound, and
    its asset endpoints reject a read that does not name the revision they
    expect. More importantly for us: audio read at the wrong revision describes
    a different voice than the one the evidence and the review will describe.
    The revision travels with the request so "the reference a listener hears"
    and "the reference we recorded" cannot drift apart.
    """

    candidate_id: str
    candidate_revision: str
    validation_id: str | None = None


@dataclass(frozen=True, slots=True)
class AssetResult:
    audio_digest: str
    audio_bytes: int
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class PublishResult:
    """A published voice plus the evidence that justified publishing it."""

    candidate_id: str
    candidate_revision: str
    voice_id: str
    voice_revision: str
    evidence: EvidenceBundle


class VoiceFoundryPort(Protocol):
    """The voice-supply operations Foundry orchestration depends on.

    An adapter implements this against one provider and must not import that
    provider's SDK into the domain or application layers. Every method either
    returns a typed result or raises :class:`VoiceFoundryPortError`; none of
    them may return a partial success that reads like a complete one.

    ``capabilities`` is the single source of truth for what this instance may
    be asked to do. Callers check it before starting an operation so an
    unsupported capability fails as a clear reason code instead of an opaque
    transport error halfway through.
    """

    @property
    def capabilities(self) -> VoiceFoundryCapabilities: ...

    @property
    def locale_map(self) -> ProviderLocaleMap: ...

    async def preview(self, request: PreviewRequest) -> PreviewResult:
        """Render audition media for one candidate recipe."""
        ...

    async def create(self, request: CreateRequest) -> CandidateState:
        """Register a private candidate under a stable identity."""
        ...

    async def query(self, candidate_id: str) -> CandidateState:
        """Reconcile an unknown outcome without changing candidate identity."""
        ...

    async def confirm(self, candidate_id: str, request: ConfirmRequest) -> CandidateState:
        """Bind the current reference audio; changing text invalidates it."""
        ...

    async def validate(
        self,
        candidate_id: str,
        *,
        test_text: str,
        capability_key: str,
    ) -> ValidationResult:
        """Run machine validation over cross-text audio."""
        ...

    async def review(
        self,
        candidate_id: str,
        *,
        validation_id: str,
        identity: FoundryReviewVerdict,
        naturalness: FoundryReviewVerdict,
    ) -> EvidenceBundle:
        """Attach an explicit human verdict for one exact validation."""
        ...

    async def publish(
        self,
        candidate_id: str,
        *,
        expected_candidate_revision: str,
    ) -> PublishResult:
        """Publish one exact candidate revision and return its evidence."""
        ...

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        """Fetch one exact reference/validation asset for audition."""
        ...


class VoiceSupplyDriver(Protocol):
    """The half of supply that runs without a person deciding anything.

    A retry command is not a state edit. ADR-005 D9 requires an unknown
    provider outcome to be settled by *asking the provider* under the
    original idempotency key, and only then resumed — never by reopening the
    task, which would leave a half-created voice unaccounted for. So the
    command layer depends on this shape and the worker satisfies it
    structurally; neither imports the other.
    """

    async def advance(self, task_id: str) -> object:
        """Move one task forward by at most one durable step."""
        ...

    async def reconcile(self, task_id: str) -> int:
        """Settle every unknown operation on a task; return how many."""
        ...


def admit_foundry_locale(
    capabilities: VoiceFoundryCapabilities,
    locale_map: ProviderLocaleMap,
    game_locale: str,
) -> LocaleAdmission:
    """Admit a game locale only via an explicit, provider-specific map.

    A provider advertising ``zh`` never implies ``zh-TW`` is accepted; an
    unmapped or undeclared locale fails rather than being translated.
    """
    if game_locale not in capabilities.accepted_game_locales:
        raise VoiceFoundryPortError("unsupported_locale")
    provider_locale = locale_map.resolve(game_locale)
    if provider_locale is None:
        raise VoiceFoundryPortError("unsupported_locale")
    return LocaleAdmission(game_locale=game_locale, provider_locale=provider_locale)


def admit_strict_rendering(
    capabilities: VoiceFoundryCapabilities,
) -> StrictRenderingDecision:
    """Decide whether formal rendering may be evidence-gated.

    When the provider cannot gate strictly the caller keeps subtitles and
    reports ``strict_render_unsupported``; it must not route around the gate
    by rendering unverified and shipping the result anyway.
    """
    if not capabilities.strict_rendering:
        return StrictRenderingDecision(
            admitted=False,
            reason_code="strict_render_unsupported",
            retain_subtitles=True,
        )
    return StrictRenderingDecision(admitted=True, reason_code=None, retain_subtitles=False)


def review_verdict_is_accepted(verdict: FoundryReviewVerdict) -> bool:
    """Whether a human verdict counts as acceptance.

    ``WARN`` is not acceptance. It has no lossless representation in our
    evidence contract, and treating it as a pass would widen accepted
    evidence beyond what a human actually approved.
    """
    return _REVIEW_VERDICT_TO_STATUS.get(verdict) == "pass"


def review_verdict_to_status(verdict: FoundryReviewVerdict) -> str:
    """Project a verdict onto our evidence contract's status domain."""
    status = _REVIEW_VERDICT_TO_STATUS.get(verdict)
    if status is None:
        raise VoiceFoundryPortError("provider_contract_unsupported")
    return status


__all__ = [
    "MIN_TEXT_CHARS",
    "REQUIRED_EVIDENCE_FIELDS",
    "AssetRequest",
    "AssetResult",
    "CandidateState",
    "ConfirmRequest",
    "CreateRequest",
    "EvidenceBundle",
    "FoundryOperation",
    "FoundryReviewVerdict",
    "LocaleAdmission",
    "PreviewRequest",
    "PreviewResult",
    "ProviderLocaleMap",
    "PublishResult",
    "StrictRenderingDecision",
    "ValidationResult",
    "VoiceSupplyDriver",
    "VoiceFoundryCapabilities",
    "VoiceFoundryPort",
    "VoiceFoundryPortError",
    "admit_foundry_locale",
    "admit_strict_rendering",
    "review_verdict_is_accepted",
    "review_verdict_to_status",
]
