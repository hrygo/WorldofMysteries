"""Unified voice evidence admission (VF-04A).

One decision layer serves casting, sealing and rendering. Its central rule is
that "may I synthesize new audio" and "may this cached audio still play" are
different questions: expiry can block new synthesis without condemning audio
that was validly produced, and revocation must be able to stop playback even
when the bytes are already on disk.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from application.voice_evidence import (
    ExecutionRequirements,
    EvidenceRejection,
    VoiceEvidenceGate,
    VoiceEvidenceRecord,
    evidence_document,
    evidence_record,
    execution_requirements,
    load_evidence_record,
    render_execution,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def requirements(**overrides) -> ExecutionRequirements:
    base = {
        "provider_instance": "speechrail-local",
        "voice_id": "wom-klein",
        "voice_revision": "wvr_1",
        "model_id": "qwen3-tts",
        "model_artifact_revision": "art-1",
        "model_catalog_revision": "cat-1",
        "variant": "custom_voice",
        "locale": "zh",
        "usage": "dialogue",
    }
    base.update(overrides)
    return ExecutionRequirements(**base)


def evidence(**overrides) -> VoiceEvidenceRecord:
    base = {
        "evidence_id": "ev_1",
        "evidence_digest": "a" * 64,
        "provider_instance": "speechrail-local",
        "voice_id": "wom-klein",
        "voice_revision": "wvr_1",
        "execution": {
            "model_id": "qwen3-tts",
            "model_artifact_revision": "art-1",
            "variant": "custom_voice",
            "locale": "zh",
            "model_catalog_revision": "cat-1",
        },
        "reference": {"status": "pass", "audio_digest": "b" * 64, "text_digest": "c" * 64},
        "output": {
            "status": "pass",
            "validation_id": "vv_1",
            "audio_digest": "d" * 64,
            "text_digest": None,
        },
        "human": {
            "identity_status": "pass",
            "naturalness_status": "pass",
            "review_id": "rv_1",
        },
        "publication": {"state": "published", "published_revision": "wvr_1"},
        "rights": {"allowed_usages": ["dialogue"], "scope_ref": "klein-visible"},
        "created_at": (NOW - timedelta(days=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
        "revoked": False,
        "cached_playback_policy": "revocation_aware",
    }
    base.update(overrides)
    return VoiceEvidenceRecord(**base)


def gate() -> VoiceEvidenceGate:
    return VoiceEvidenceGate(clock=lambda: NOW)


def test_complete_matching_evidence_admits_both_questions():
    verdict = gate().admit(evidence(), requirements())
    assert verdict.synthesis_allowed is True
    assert verdict.cached_playback_allowed is True
    assert verdict.reason is EvidenceRejection.NONE


def test_missing_evidence_denies_synthesis():
    verdict = gate().admit(None, requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.cached_playback_allowed is False
    assert verdict.reason is EvidenceRejection.MISSING


@pytest.mark.parametrize("status", ["not_run", "pending", "fail", "", "unknown"])
def test_a_voice_without_a_passed_output_check_cannot_synthesize(status):
    """The output check is the only machine fact about unseen text.

    Reference confirmation proves the voice reproduces its design sample; a
    passed human review proves a person liked what they heard. Neither says
    the voice can render the next line of dialogue, which is text nobody has
    heard. Left ungated, a bundle whose revalidation never ran — the normal
    state of a voice that has only ever been auditioned against its reference
    — was admitted for synthesis while claiming a complete acceptance chain.
    """
    unverified = evidence(output={"status": status, "validation_id": "vv_1"})
    verdict = gate().admit(unverified, requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.OUTPUT_CHECK_INCOMPLETE


def test_evidence_without_an_output_section_at_all_cannot_synthesize():
    """A missing section is a fact about the evidence, not a pass.

    Older snapshots predate the field. Reading absence as anything but
    ``not_run`` would let every pre-existing bundle keep a synthesis right it
    was never granted.
    """
    legacy = replace(evidence(), output={})
    verdict = gate().admit(legacy, requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.OUTPUT_CHECK_INCOMPLETE


def test_a_failed_output_check_denies_cached_playback_too():
    """An acceptance hole and trust decay are different, and split differently.

    Expiry lets cached audio keep playing: the voice *was* accepted, and only
    the acceptance aged out. A missing or failed output check says something
    stronger — the chain that would have justified this voice never
    completed, so cached audio from it has no acceptance behind it at all.
    That is the same verdict an incomplete human review already produces, and
    it is deliberately the harsher of the two.
    """
    failed = evidence(output={"status": "fail", "validation_id": "vv_1"})
    verdict = gate().admit(failed, requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.cached_playback_allowed is False
    assert verdict.reason is EvidenceRejection.OUTPUT_CHECK_INCOMPLETE


class _Bundle:
    """The shape a provider hands back, with nothing invented on top."""

    evidence_id = "ev_1"
    evidence_digest = "a" * 64
    execution = {"model_id": "qwen3-tts"}
    reference = {"status": "pass", "audio_digest": "b" * 64, "text_digest": "c" * 64}
    output = {"status": "pass", "validation_id": "vv_1", "audio_digest": None, "text_digest": None}
    human = {"identity_status": "pass", "naturalness_status": "pass"}
    publication = {"state": "published", "published_revision": "wvr_1"}
    rights = {"allowed_usages": ["dialogue"], "scope_ref": "klein-visible"}


def document(**overrides) -> dict:
    base = evidence_document(
        _Bundle(),
        provider_instance="speechrail-local",
        voice_id="wom-klein",
        voice_revision="wvr_1",
        created_at=NOW.isoformat(),
    )
    base.update(overrides)
    return base


def test_a_stored_document_reads_back_into_an_admittable_record():
    record = evidence_record(document())
    assert record is not None
    assert record.evidence_id == "ev_1"
    assert record.provider_instance == "speechrail-local"
    assert record.voice_id == "wom-klein"
    assert record.voice_revision == "wvr_1"
    assert record.cached_playback_policy == "revocation_aware"
    assert record.revoked is False


@pytest.mark.parametrize(
    "section", ["execution", "reference", "output", "human", "publication", "rights"]
)
def test_a_document_missing_a_section_reads_as_no_evidence(section):
    """A half-written snapshot is not a partially trusted one.

    Refusing here means the gate denies with ``missing``, which is the same
    answer it gives for no snapshot at all. Anything else would let a
    truncated write keep a voice renderable.
    """
    broken = document()
    del broken[section]
    assert evidence_record(broken) is None

    not_a_mapping = document()
    not_a_mapping[section] = ["not", "a", "section"]
    assert evidence_record(not_a_mapping) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "2.0"},
        {"schema_version": ""},
        {"evidence_id": ""},
        {"evidence_digest": ""},
        {"provider_instance": ""},
        {"voice_id": ""},
        {"voice_revision": ""},
        {"created_at": ""},
        {"cached_playback_policy": "whenever"},
        {"cached_playback_policy": ""},
        {"revoked": "false"},
        {"revoked": None},
        {"expires_at": 12345},
    ],
)
def test_a_document_with_an_unusable_top_level_fact_reads_as_no_evidence(overrides):
    """Absent and malformed deny alike.

    A future schema revision is refused rather than guessed at: reading an
    unknown document as a known one is how a voice gets admitted on the
    strength of fields this build has never heard of.
    """
    assert evidence_record(document(**overrides)) is None


def test_execution_is_pinned_independently_of_the_evidence():
    """The gate's comparison is only worth making if both sides are separate.

    Requirements built from the provider and the binding can disagree with a
    stored snapshot; that disagreement is the ``EXECUTION_MISMATCH`` the gate
    exists to catch. Building them from the snapshot instead would make every
    field match by construction.
    """
    def pinned(**overrides):
        base = {
            "provider_instance": "speechrail-local",
            "voice_id": "wom-klein",
            "voice_revision": "wvr_1",
            "model_id": "qwen3-tts",
            "model_artifact_revision": "art-1",
            "model_catalog_revision": "cat-1",
            "locale": "zh",
            "usage": "dialogue",
            "variant": "custom_voice",
        }
        base.update(overrides)
        return execution_requirements(**base)

    declared = pinned()
    assert declared.variant == "custom_voice"

    # The whole point: a render declared against facts the snapshot does not
    # carry is refused. The stored execution names only a model, so the
    # artefact, variant, locale and catalogue revision all diverge — and the
    # gate can only see that because the two sides were built separately.
    stored = evidence_record(document())
    assert stored is not None
    verdict = gate().admit(stored, declared)
    assert verdict.reason is EvidenceRejection.EXECUTION_MISMATCH


def _render_pinned(**overrides):
    base = {
        "provider_instance": "speechrail-local",
        "voice_id": "wom-klein",
        "voice_revision": "wvr_1",
        "model_id": "qwen3-tts",
        "model_artifact_revision": "art-1",
        "model_catalog_revision": "cat-1",
        "game_locale": "zh-CN",
        "phase": "dialogue",
        "variant": "custom_voice",
    }
    base.update(overrides)
    return render_execution(**base)


def test_the_scope_phase_is_the_usage_a_review_has_to_have_granted():
    """The same identity cast twice is two bindings, and two rights.

    A voice cleared to narrate has not been cleared to speak. The binding key
    already treats those as different scopes, so the usage a render declares
    is the phase it renders under — not a second decision free to drift from
    it.
    """
    assert _render_pinned(phase="narration").usage == "narration"
    assert _render_pinned(phase="dialogue").usage == "dialogue"


def test_a_render_is_pinned_in_the_locale_the_provider_verified():
    """The scope's locale and the provider's are not two spellings of one.

    Evidence records the language the provider actually validated — the
    adapter reads it off the candidate — while a scope carries the locale the
    product is written in. Passing the scope's spelling straight through made
    every render an ``EXECUTION_MISMATCH`` against evidence minted by this
    very provider, for every locale the build supports. That reads as a
    broken gate; it is a comparison of two different questions.
    """
    assert _render_pinned(game_locale="zh-CN").locale == "zh"


@pytest.mark.parametrize("game_locale", ["zh", "en-US", "", "zh_CN"])
def test_a_locale_the_provider_cannot_render_pins_no_execution(game_locale):
    """A scope nobody can translate has no evidence to match.

    Falling back to the input spelling would reintroduce exactly the mismatch
    this translation exists to remove, and would do it silently for any locale
    added to a scope without being added to the map.
    """
    assert _render_pinned(game_locale=game_locale) is None


@pytest.mark.parametrize(
    "missing",
    [
        {"voice_revision": None},
        {"model_artifact_revision": None},
        {"voice_revision": "", "model_artifact_revision": None},
    ],
)
def test_a_binding_with_no_reviewed_voice_pins_no_execution(missing):
    """A binding may be reserved before anyone has listened to it.

    Such a binding has no artefact revision, so a render cannot name one. A
    placeholder would let the gate compare this render against a voice nobody
    approved, which is the check agreeing with itself.
    """
    assert _render_pinned(**missing) is None


class _Snapshot:
    def __init__(self, snapshot):
        self.snapshot = snapshot


class _Store:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    async def load_evidence(self, provider_instance, evidence_id):
        if isinstance(self._snapshot, Exception):
            raise self._snapshot
        return self._snapshot


async def test_a_stored_snapshot_is_read_back_into_a_judged_record():
    store = _Store(_Snapshot(document()))
    record = await load_evidence_record(store, "speechrail-local", "ev_1")
    assert record is not None
    assert record.evidence_id == "ev_1"


@pytest.mark.parametrize(
    "store",
    [
        _Store(RuntimeError("no such evidence")),
        _Store(None),
        _Store(_Snapshot("not a document")),
        _Store(_Snapshot({"schema_version": "1.0"})),
    ],
)
async def test_evidence_that_cannot_be_read_is_no_evidence(store):
    """Absence and unreadability deny in the same direction.

    A store that raises, a snapshot that is not a document, and a document
    missing every section all mean the render cannot be admitted. Letting the
    failure escape would push a storage fault into the delivery path, where a
    handler converts it to "unavailable" anyway — further from the decision
    than the decision itself.
    """
    assert await load_evidence_record(store, "speechrail-local", "ev_1") is None


def test_expiry_blocks_new_synthesis_but_not_already_produced_audio():
    """Expiry means we can no longer trust the voice for new work; it does not
    retroactively condemn audio that was validly produced."""
    stale = evidence(expires_at=(NOW - timedelta(seconds=1)).isoformat())
    verdict = gate().admit(stale, requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.EXPIRED
    assert verdict.cached_playback_allowed is True


def test_revocation_stops_cached_playback_too():
    """A cache must not be a way around a revocation."""
    verdict = gate().admit(evidence(revoked=True), requirements())
    assert verdict.synthesis_allowed is False
    assert verdict.cached_playback_allowed is False
    assert verdict.reason is EvidenceRejection.REVOKED


def test_provider_decision_policy_defers_playback_to_live_observation():
    observed = evidence(revoked=True, cached_playback_policy="provider_decision")
    # The snapshot alone is not enough to condemn cached bytes...
    assert gate().admit(observed, requirements()).cached_playback_allowed is True
    # ...but a live provider observation that the voice is gone stops them.
    verdict = gate().admit(observed, requirements(), provider_revoked=True)
    assert verdict.cached_playback_allowed is False
    assert verdict.reason is EvidenceRejection.REVOKED


def test_machine_passing_never_substitutes_for_the_human_verdict():
    for status in ("not_run", "pending", "fail"):
        verdict = gate().admit(
            evidence(
                human={
                    "identity_status": status,
                    "naturalness_status": "pass",
                    "review_id": "rv_1",
                }
            ),
            requirements(),
        )
        assert verdict.synthesis_allowed is False
        assert verdict.reason is EvidenceRejection.HUMAN_REVIEW_INCOMPLETE


def test_stale_model_artifact_does_not_pass_as_the_current_one():
    """An old catalogue revision must not masquerade as the current model."""
    verdict = gate().admit(evidence(), requirements(model_artifact_revision="art-2"))
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.EXECUTION_MISMATCH


def test_evidence_for_another_voice_or_provider_never_admits():
    assert gate().admit(evidence(), requirements(voice_id="wom-other")).reason is (
        EvidenceRejection.IDENTITY_MISMATCH
    )
    assert (
        gate().admit(evidence(), requirements(provider_instance="other-provider")).reason
        is EvidenceRejection.IDENTITY_MISMATCH
    )


def test_usage_outside_the_granted_rights_is_refused():
    verdict = gate().admit(evidence(), requirements(usage="narration"))
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.USAGE_NOT_GRANTED


def test_an_unpublished_candidate_is_not_evidence_of_a_usable_voice():
    """A candidate that never published cannot back a formal render, even
    though every other section looks complete."""
    verdict = gate().admit(
        evidence(publication={"state": "", "published_revision": ""}),
        requirements(),
    )
    assert verdict.synthesis_allowed is False
    assert verdict.reason is EvidenceRejection.INCOMPLETE

    # An expiry we cannot even read is a broken record, not a silent pass.
    unreadable = replace(evidence(), expires_at="not-a-timestamp")
    assert gate().admit(unreadable, requirements()).reason is (EvidenceRejection.INCOMPLETE)


def test_every_rejection_carries_a_stable_machine_readable_reason():
    verdict = gate().admit(evidence(revoked=True), requirements())
    assert isinstance(verdict.reason, EvidenceRejection)
    assert verdict.reason.value == "revoked"
