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
