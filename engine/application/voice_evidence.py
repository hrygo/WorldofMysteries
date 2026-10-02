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

from application.voice_foundry_ports import GAME_TO_PROVIDER_LOCALE

#: A human verdict only counts when it actually passed. Machine metrics are
#: recorded separately and never fill this in.
_HUMAN_PASS = "pass"

#: The machine verdict for the cross-text revalidation. Same literal as the
#: human one, but a separate constant: a machine pass is not a human pass, and
#: the two are never interchangeable facts about a voice.
_MACHINE_PASS = "pass"

#: The evidence contract revision this module reads and writes.
EVIDENCE_SCHEMA_VERSION = "1.0"
_EVIDENCE_SCHEMA_VERSION = EVIDENCE_SCHEMA_VERSION

#: Cached audio follows a live revocation rather than waiting for the
#: provider to be asked. It is the stricter of the two policies the contract
#: allows, and it is the right default for a game that has already rendered a
#: line: a withdrawn voice should stop being heard before anyone gets round
#: to asking the service whether it is still fine.
_CACHED_PLAYBACK_REVOCATION_AWARE = "revocation_aware"
_CACHED_PLAYBACK_POLICIES = frozenset(
    {_CACHED_PLAYBACK_REVOCATION_AWARE, "provider_decision"}
)


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


def execution_requirements(
    *,
    provider_instance: str,
    voice_id: str,
    voice_revision: str,
    model_id: str,
    model_artifact_revision: str,
    model_catalog_revision: str,
    locale: str,
    usage: str,
    variant: str,
) -> ExecutionRequirements:
    """Pin the execution this render is about to run.

    Every value here has to come from the binding or the provider, never from
    the evidence document. That is not stylistic: ``VoiceEvidenceGate``
    compares these fields against the snapshot to decide
    ``EXECUTION_MISMATCH``, so a requirement built out of the evidence would
    be comparing the evidence with itself and the check could never fire.
    The gate is only worth having if the other side of the comparison is a
    fact about the world rather than a copy of the thing being checked.

    ``variant`` is therefore a required argument instead of a default. It is
    a property of the pipeline this build renders through, declared by the
    deployment, and the caller is the only place that knows it.
    """
    return ExecutionRequirements(
        provider_instance=provider_instance,
        voice_id=voice_id,
        voice_revision=voice_revision,
        model_id=model_id,
        model_artifact_revision=model_artifact_revision,
        model_catalog_revision=model_catalog_revision,
        variant=variant,
        locale=locale,
        usage=usage,
    )


def evidence_document(
    bundle: object,
    *,
    provider_instance: str,
    voice_id: str,
    voice_revision: str,
    created_at: str,
    expires_at: str | None = None,
    revoked: bool = False,
    cached_playback_policy: str = _CACHED_PLAYBACK_REVOCATION_AWARE,
) -> dict[str, object]:
    """Assemble the complete evidence document the contract describes.

    A provider bundle carries six sections and an identity. The contract
    document carries those plus eight more top-level facts, and until this
    existed nobody produced them: the worker stored the six sections, the
    repository stamped a row time, and the document that the schema
    describes was never written down anywhere. Anything reading the snapshot
    back therefore had to invent the difference.

    The four values supplied here are exactly the ones this repository knows
    and the provider does not report: which instance and which voice the
    snapshot is about, when it was minted, and — for ``expires_at`` — that
    there is no expiry policy yet, which ``None`` states rather than hides.
    """
    return {
        "schema_version": _EVIDENCE_SCHEMA_VERSION,
        "evidence_id": bundle.evidence_id,
        "evidence_digest": bundle.evidence_digest,
        "provider_instance": provider_instance,
        "voice_id": voice_id,
        "voice_revision": voice_revision,
        "execution": dict(bundle.execution),
        "reference": dict(bundle.reference),
        "output": dict(bundle.output),
        "human": dict(bundle.human),
        "publication": dict(bundle.publication),
        "rights": dict(bundle.rights),
        "created_at": created_at,
        "expires_at": expires_at,
        "revoked": revoked,
        "cached_playback_policy": cached_playback_policy,
    }


def evidence_record(document: Mapping[str, object]) -> VoiceEvidenceRecord | None:
    """Rebuild the gate's record from a stored document, or refuse.

    Absence and corruption deny in the same direction here, and that is the
    point: both mean no admitted evidence, so both stop synthesis. Raising
    instead would force every caller to catch, and a caller that caught it by
    carrying on would have turned a storage fault into an unreviewed voice.
    """
    sections: dict[str, Mapping[str, object]] = {}
    for name in ("execution", "reference", "output", "human", "publication", "rights"):
        value = document.get(name)
        if not isinstance(value, Mapping):
            return None
        sections[name] = value

    text_fields = {
        name: _text(document.get(name))
        for name in (
            "schema_version",
            "evidence_id",
            "evidence_digest",
            "provider_instance",
            "voice_id",
            "voice_revision",
            "created_at",
            "cached_playback_policy",
        )
    }
    if any(not value for value in text_fields.values()):
        return None
    if text_fields["schema_version"] != _EVIDENCE_SCHEMA_VERSION:
        return None
    expires_at = document.get("expires_at")
    if expires_at is not None and not isinstance(expires_at, str):
        return None
    revoked = document.get("revoked")
    if not isinstance(revoked, bool):
        return None
    if text_fields["cached_playback_policy"] not in _CACHED_PLAYBACK_POLICIES:
        return None

    return VoiceEvidenceRecord(
        evidence_id=text_fields["evidence_id"],
        evidence_digest=text_fields["evidence_digest"],
        provider_instance=text_fields["provider_instance"],
        voice_id=text_fields["voice_id"],
        voice_revision=text_fields["voice_revision"],
        execution=sections["execution"],
        reference=sections["reference"],
        output=sections["output"],
        human=sections["human"],
        publication=sections["publication"],
        rights=sections["rights"],
        created_at=text_fields["created_at"],
        expires_at=expires_at,
        revoked=revoked,
        cached_playback_policy=text_fields["cached_playback_policy"],
    )


def render_execution(
    *,
    provider_instance: str,
    voice_id: str,
    voice_revision: str | None,
    model_id: str,
    model_artifact_revision: str | None,
    model_catalog_revision: str,
    game_locale: str,
    phase: str,
    variant: str,
) -> ExecutionRequirements | None:
    """Pin the render about to happen, or report that a fact is missing.

    ``game_locale`` is translated to the provider's locale before it is
    recorded, because that is the language the render is actually verified
    in and therefore the one the gate has to compare against. The evidence
    says ``zh`` — the adapter took it from the candidate the provider
    validated — while the scope says ``zh-CN``. Handing the scope's spelling
    straight through made every render an ``EXECUTION_MISMATCH``, for every
    locale this build supports, which is the same as having no audio at all.

    ``phase`` becomes the usage, and that is the whole reason a scope carries
    one. The binding key includes it, so the same identity cast for narration
    and for dialogue is two bindings; a voice cleared to narrate has not been
    cleared to speak, and the rights a review granted are rights to a use.
    The two vocabularies are the same pair on both sides — the scope phases
    are exactly the permitted usages — so this is a rename, not a judgement.

    ``None`` means the binding carries no reviewed voice to pin: a binding may
    be reserved before anyone has listened to it, and a render cannot claim an
    artefact revision that does not exist yet. The caller blocks rather than
    substituting a default, because a guessed artefact revision would let the
    gate compare the render against a voice nobody approved.

    A locale outside the map is refused the same way, rather than passed
    through: a voice can only have been verified in a language the provider
    was asked for, and a scope nobody can translate has no evidence to match.
    """
    if not voice_revision or not model_artifact_revision:
        return None
    locale = GAME_TO_PROVIDER_LOCALE.resolve(game_locale)
    if locale is None:
        return None
    return execution_requirements(
        provider_instance=provider_instance,
        voice_id=voice_id,
        voice_revision=voice_revision,
        model_id=model_id,
        model_artifact_revision=model_artifact_revision,
        model_catalog_revision=model_catalog_revision,
        variant=variant,
        locale=locale,
        usage=phase,
    )


async def load_evidence_record(
    store: object,
    provider_instance: str,
    evidence_id: str,
) -> VoiceEvidenceRecord | None:
    """Read one stored snapshot back into the record the gate judges.

    A store that raises is treated exactly like a store that has nothing: the
    binding points at evidence this process cannot produce, and both mean no
    admitted evidence. Letting the failure escape instead would push a
    storage fault into the delivery path, where it would be caught by a
    handler that turns exceptions into "unavailable" anyway — further from the
    decision than the decision itself.
    """
    try:
        snapshot = await store.load_evidence(provider_instance, evidence_id)
    except Exception:  # noqa: BLE001 - absence and unreadability both deny
        return None
    document = getattr(snapshot, "snapshot", None)
    if not isinstance(document, Mapping):
        return None
    return evidence_record(document)


__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceRejection",
    "EvidenceVerdict",
    "ExecutionRequirements",
    "VoiceEvidenceGate",
    "VoiceEvidenceRecord",
    "evidence_document",
    "evidence_record",
    "execution_requirements",
    "load_evidence_record",
    "render_execution",
]
