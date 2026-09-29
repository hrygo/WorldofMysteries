"""Voice Foundry provider port contract (VF-03A).

These tests pin the seam between Foundry orchestration and any concrete
voice provider. They deliberately test only the application-layer port:
no provider SDK, no HTTP, no database.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from application.voice_foundry_ports import (
    FoundryOperation,
    FoundryReviewVerdict,
    PreviewRequest,
    ProviderLocaleMap,
    VoiceFoundryCapabilities,
    VoiceFoundryPort,
    VoiceFoundryPortError,
    admit_foundry_locale,
    admit_strict_rendering,
    review_verdict_is_accepted,
    review_verdict_to_status,
)


def capabilities(**overrides) -> VoiceFoundryCapabilities:
    base = {
        "operations": frozenset(FoundryOperation),
        "accepted_game_locales": frozenset({"zh-CN"}),
        "max_reference_chars": 240,
        "max_validation_chars": 240,
        "max_audio_bytes": 8 * 1024 * 1024,
        "max_audio_seconds": 60,
        "strict_rendering": True,
        "evidence_fields": frozenset(
            {"execution", "reference", "output", "human", "publication", "rights"}
        ),
        "remote_cancel": False,
    }
    base.update(overrides)
    return VoiceFoundryCapabilities(**base)


def test_capabilities_are_immutable_and_fully_declared():
    caps = capabilities()
    with pytest.raises(AttributeError):
        caps.strict_rendering = False  # type: ignore[misc]
    # Every operation must be explicitly present in the declared set.
    assert set(caps.operations) == set(FoundryOperation)


def test_missing_operation_is_rejected_not_silently_downgraded():
    caps = capabilities(operations=frozenset({FoundryOperation.PREVIEW}))
    with pytest.raises(VoiceFoundryPortError) as excinfo:
        caps.require(FoundryOperation.PUBLISH)
    assert excinfo.value.code == "provider_capability_missing"


def test_locale_admission_uses_explicit_map_and_never_silently_translates():
    caps = capabilities()
    mapping = ProviderLocaleMap({"zh-CN": "zh"})

    admitted = admit_foundry_locale(caps, mapping, "zh-CN")
    assert admitted.provider_locale == "zh"
    assert admitted.game_locale == "zh-CN"

    # A provider that only ever advertised "zh" must NOT make "zh-TW" pass.
    with pytest.raises(VoiceFoundryPortError) as excinfo:
        admit_foundry_locale(caps, mapping, "zh-TW")
    assert excinfo.value.code == "unsupported_locale"

    with pytest.raises(VoiceFoundryPortError) as excinfo:
        admit_foundry_locale(caps, ProviderLocaleMap({}), "zh-CN")
    assert excinfo.value.code == "unsupported_locale"


def test_strict_rendering_absent_fails_closed_with_subtitles_retained():
    caps = capabilities(strict_rendering=False)
    decision = admit_strict_rendering(caps)
    assert decision.admitted is False
    assert decision.reason_code == "strict_render_unsupported"
    # Degradation is explicit: subtitles stay on, it never silently downgrades.
    assert decision.retain_subtitles is True

    admitted = admit_strict_rendering(capabilities())
    assert admitted.admitted is True
    assert admitted.reason_code is None
    assert admitted.retain_subtitles is False


def test_capability_limits_are_validated_before_any_provider_call():
    caps = capabilities(max_reference_chars=240, max_audio_bytes=1024)
    request = PreviewRequest(
        game_locale="zh-CN",
        voice_description="克制而警觉的年轻男性声音。",
        reference_text="这是用于确认音色的完整句子，必须足够长以通过校验。",
        seed=7,
    )
    # Within limits: accepted.
    caps.validate_preview(request)

    with pytest.raises(VoiceFoundryPortError) as excinfo:
        caps.validate_preview(
            PreviewRequest(
                game_locale="zh-CN",
                voice_description="克制而警觉的年轻男性声音。",
                reference_text="短",
                seed=7,
            )
        )
    assert excinfo.value.code == "reference_text_out_of_range"

    with pytest.raises(VoiceFoundryPortError) as excinfo:
        caps.validate_preview(replace(request, audio_bytes=2048))
    assert excinfo.value.code == "audio_limit_exceeded"


def test_evidence_fields_shortfall_is_provider_contract_unsupported():
    caps = capabilities(evidence_fields=frozenset({"reference"}))
    with pytest.raises(VoiceFoundryPortError) as excinfo:
        caps.require_evidence_fields({"execution", "reference"})
    assert excinfo.value.code == "provider_contract_unsupported"


def test_review_verdicts_match_provider_literal_domain():
    assert {v.value for v in FoundryReviewVerdict} == {
        "pass",
        "warn",
        "reject",
        "not_reviewed",
    }
    # A machine metric must never be able to fill in the human verdict.
    assert FoundryReviewVerdict.NOT_REVIEWED.value == "not_reviewed"


def test_warn_is_never_promoted_to_pass():
    """`warn` has no lossless slot in our evidence contract, so it must not
    silently become acceptance — that would widen what counts as reviewed."""
    assert review_verdict_is_accepted(FoundryReviewVerdict.PASS) is True
    assert review_verdict_is_accepted(FoundryReviewVerdict.WARN) is False
    assert review_verdict_is_accepted(FoundryReviewVerdict.REJECT) is False
    assert review_verdict_is_accepted(FoundryReviewVerdict.NOT_REVIEWED) is False

    # Projecting `warn` onto the evidence contract is refused outright rather
    # than approximated; the caller must escalate instead of guessing.
    with pytest.raises(VoiceFoundryPortError) as excinfo:
        review_verdict_to_status(FoundryReviewVerdict.WARN)
    assert excinfo.value.code == "provider_contract_unsupported"

    assert review_verdict_to_status(FoundryReviewVerdict.PASS) == "pass"
    assert review_verdict_to_status(FoundryReviewVerdict.REJECT) == "fail"
    assert review_verdict_to_status(FoundryReviewVerdict.NOT_REVIEWED) == "not_run"


def test_cross_text_validation_is_bounded_like_a_reference():
    caps = capabilities(max_validation_chars=240)
    caps.validate_validation_text("这是用于跨文本复验的另一句完整文本，不能与参考文本相同。")
    with pytest.raises(VoiceFoundryPortError) as excinfo:
        caps.validate_validation_text("短")
    assert excinfo.value.code == "validation_text_out_of_range"


def test_remote_cancel_is_declared_not_assumed():
    """Without a confirmed remote cancel, the port must not offer one."""
    assert capabilities(remote_cancel=False).remote_cancel is False
    assert capabilities(remote_cancel=True).remote_cancel is True


def test_port_declares_every_operation_an_adapter_must_implement():
    """Pins the port surface: dropping an operation silently would leave the
    Foundry worker calling a method no adapter promised to provide."""
    declared = {name for name in vars(VoiceFoundryPort) if not name.startswith("_")}
    assert declared == {
        "capabilities",
        "locale_map",
        "preview",
        "create",
        "query",
        "confirm",
        "validate",
        "review",
        "publish",
        "read_asset",
    }
    # Every operation the capabilities enum can express must be reachable.
    assert {member.value for member in FoundryOperation} <= {
        "preview",
        "create",
        "query",
        "confirm",
        "validate",
        "review",
        "publish",
    }
