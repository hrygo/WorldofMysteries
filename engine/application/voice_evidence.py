"""One admission decision for voice evidence, shared by casting and rendering.

Casting, sealing and rendering all need the same answer to two *different*
questions, and conflating them is how a revoked voice keeps speaking:

``synthesis_allowed``
    May we run new synthesis for this voice? Requires evidence that is
    present, ours, unrevoked, unexpired, human-approved, granted for this
    usage, and matched to the exact execution the caller will run.

``cached_playback_allowed``
    May audio that was already produced still play? This deliberately does
    *not* inherit every synthesis failure. Expiry blocks new work without
    retroactively condemning audio that was validly produced, while
    revocation reaches cached bytes — otherwise a cache becomes the loophole
    that outlives a takedown.

Dynamic revocation is handled by observation, not by rewriting history: an
old evidence snapshot is never mutated. A live provider observation, when the
snapshot's policy defers to the provider, is what stops playback.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

#: A human verdict only counts when it actually passed. Machine metrics are
#: recorded separately and never fill this in.
_HUMAN_PASS = "pass"

#: The machine verdict for the cross-text revalidation. Same literal as the
#: human one, but a separate constant: a machine pass is not a human pass, and
#: the two are never interchangeable facts about a voice.
_MACHINE_PASS = "pass"


class EvidenceRejection(StrEnum):
    """Stable, machine-readable reason a voice was not admitted."""

    NONE = "none"
    MISSING = "missing"
    IDENTITY_MISMATCH = "identity_mismatch"
    REVOKED = "revoked"
    EXPIRED = "expired"
    OUTPUT_CHECK_INCOMPLETE = "output_check_incomplete"
    HUMAN_REVIEW_INCOMPLETE = "human_review_incomplete"
    EXECUTION_MISMATCH = "execution_mismatch"
    USAGE_NOT_GRANTED = "usage_not_granted"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class ExecutionRequirements:
    """Exactly what the caller is about to run, pinned before admission.

    ``model_artifact_revision`` and ``model_catalog_revision`` are separate on
    purpose: an old catalogue entry must never be accepted as if it described
    the current model artifact.
    """

    provider_instance: str
    voice_id: str
    voice_revision: str
    model_id: str
    model_artifact_revision: str
    model_catalog_revision: str
    variant: str
    locale: str
    usage: str


@dataclass(frozen=True, slots=True)
class VoiceEvidenceRecord:
    """One stored evidence snapshot, exactly as persisted."""

    evidence_id: str
    evidence_digest: str
    provider_instance: str
    voice_id: str
    voice_revision: str
    execution: Mapping[str, object]
    reference: Mapping[str, object]
    output: Mapping[str, object]
    human: Mapping[str, object]
    publication: Mapping[str, object]
    rights: Mapping[str, object]
    created_at: str
    expires_at: str | None
    revoked: bool
    cached_playback_policy: str


@dataclass(frozen=True, slots=True)
class EvidenceVerdict:
    """The two answers, kept separate on purpose."""

    synthesis_allowed: bool
    cached_playback_allowed: bool
    reason: EvidenceRejection
    detail: str | None = None


def _denied(reason: EvidenceRejection, detail: str | None = None) -> EvidenceVerdict:
    return EvidenceVerdict(
        synthesis_allowed=False,
        cached_playback_allowed=False,
        reason=reason,
        detail=detail,
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A stored timestamp without an offset is ambiguous; refuse to guess.
    return parsed if parsed.tzinfo is not None else None


class VoiceEvidenceGate:
    """Decide whether evidence admits a synthesis, a playback, or neither."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._now = clock or (lambda: datetime.now(UTC))

    def admit(
        self,
        evidence: VoiceEvidenceRecord | None,
        requirements: ExecutionRequirements,
        *,
        provider_revoked: bool | None = None,
    ) -> EvidenceVerdict:
        if evidence is None:
            return _denied(EvidenceRejection.MISSING)

        if (
            evidence.provider_instance != requirements.provider_instance
            or evidence.voice_id != requirements.voice_id
            or evidence.voice_revision != requirements.voice_revision
        ):
            return _denied(EvidenceRejection.IDENTITY_MISMATCH)

        policy = evidence.cached_playback_policy
        # The snapshot's own revocation always blocks new synthesis. Whether it
        # also stops cached bytes depends on the policy: under
        # ``revocation_aware`` we stop them here, while ``provider_decision``
        # waits for a live observation.
        if evidence.revoked or provider_revoked:
            cached_allowed = False if policy == "revocation_aware" or provider_revoked else True
            return EvidenceVerdict(
                synthesis_allowed=False,
                cached_playback_allowed=cached_allowed,
                reason=EvidenceRejection.REVOKED,
            )

        allowed_usages = evidence.rights.get("allowed_usages")
        if not isinstance(allowed_usages, list) or requirements.usage not in allowed_usages:
            return _denied(EvidenceRejection.USAGE_NOT_GRANTED)

        identity = _text(evidence.human.get("identity_status"))
        naturalness = _text(evidence.human.get("naturalness_status"))
        if identity != _HUMAN_PASS or naturalness != _HUMAN_PASS:
            return _denied(EvidenceRejection.HUMAN_REVIEW_INCOMPLETE)

        # The reference check and the output check are separate facts, and
        # synthesis depends on the second one. Reference confirmation says the
        # voice reproduces the sample it was designed from; only a cross-text
        # revalidation says it renders text nobody has heard yet, which is
        # exactly what every line of dialogue is. A bundle carrying a passed
        # reference and a passed human review but an unrun or failed output
        # check describes a voice that has never been asked to speak.
        #
        # Reading this is what makes the field load-bearing. Left unread, a
        # default of ``not_run`` passed the gate, so a cold voice with no
        # synthesis-time verification could be rendered into the game while
        # the evidence claimed a complete acceptance chain.
        if _text(evidence.output.get("status")) != _MACHINE_PASS:
            return _denied(EvidenceRejection.OUTPUT_CHECK_INCOMPLETE)

        execution = evidence.execution
        if (
            _text(execution.get("model_id")) != requirements.model_id
            or _text(execution.get("model_artifact_revision"))
            != requirements.model_artifact_revision
            or _text(execution.get("variant")) != requirements.variant
            or _text(execution.get("locale")) != requirements.locale
            or _text(execution.get("model_catalog_revision")) != requirements.model_catalog_revision
        ):
            return _denied(EvidenceRejection.EXECUTION_MISMATCH)

        if _text(evidence.publication.get("state")) != "published" or not _text(
            evidence.publication.get("published_revision")
        ):
            return _denied(EvidenceRejection.INCOMPLETE)

        expires_at = _parse_instant(evidence.expires_at)
        if evidence.expires_at is not None and expires_at is None:
            return _denied(EvidenceRejection.INCOMPLETE, "unreadable_expiry")
        if expires_at is not None and expires_at <= self._now():
            # New synthesis stops, but audio that was validly produced keeps
            # its playback right: expiry is about trust going forward.
            return EvidenceVerdict(
                synthesis_allowed=False,
                cached_playback_allowed=True,
                reason=EvidenceRejection.EXPIRED,
            )

        return EvidenceVerdict(
            synthesis_allowed=True,
            cached_playback_allowed=True,
            reason=EvidenceRejection.NONE,
        )


__all__ = [
    "EvidenceRejection",
    "EvidenceVerdict",
    "ExecutionRequirements",
    "VoiceEvidenceGate",
    "VoiceEvidenceRecord",
]
