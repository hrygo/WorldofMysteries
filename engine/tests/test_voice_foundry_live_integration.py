"""Live SpeechRail integration for the Voice Foundry supply chain (VF-32).

Everything else in this suite proves the chain against a stand-in. This is the
only test that talks to a real service, because acceptance criterion 6 says
explicitly that simulated tests do not substitute for real acceptance.

It is opt-in and never runs in CI:

    WOM_LIVE_SPEECHRAIL=1 uv run --locked --extra dev pytest -q \
        tests/test_voice_foundry_live_integration.py -v

Credentials come from SpeechRail's own discovery (``SPEECHRAIL_API_KEY``, else
the managed app home's ``config/.env``) and are never printed or asserted on.
The voice described below is a synthetic probe: it exists to exercise the
mechanism and deliberately corresponds to no canon character, because a
made-up sound attached to a real identity is the one thing this repository
must never do on its own.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

import pytest

from application.voice_foundry_ports import (
    AssetRequest,
    ConfirmRequest,
    CreateRequest,
    FoundryReviewVerdict,
    PreviewRequest,
    VoiceFoundryPortError,
)
from infrastructure.audio.config import AudioProviderConfig
from infrastructure.audio.voice_foundry_adapter import (
    FoundryExecutionPolicy,
    SpeechRailVoiceFoundryAdapter,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("WOM_LIVE_SPEECHRAIL") != "1",
    reason="live SpeechRail integration is opt-in (WOM_LIVE_SPEECHRAIL=1)",
)

PROBE_INSTRUCTION = (
    "一位中年男性讲述者。语速中等偏慢，咬字清晰，情感克制，"
    "不使用戏剧化的抑扬顿挫。这是为了验证铸造链路而合成的探针音色，"
    "不对应任何正典人物。"
)
PROBE_REFERENCE = "夜色沉下来的时候，港口的灯一盏一盏亮起，海风把缆绳吹得轻轻作响。"
PROBE_VALIDATION = "他没有回答，只是把信折好放回抽屉，然后望向窗外尚未熄灭的灯。"


def _discover_key() -> None:
    """Put SpeechRail's own key in the environment without revealing it."""
    if os.environ.get("SPEECHRAIL_API_KEY", "").strip():
        return
    home = os.environ.get("SPEECHRAIL_APP_HOME")
    base = (
        Path(home).expanduser()
        if home and home.strip()
        else Path.home() / "Library" / "Application Support" / "SpeechRail"
    )
    try:
        lines = (base / "config" / ".env").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return
    for raw in lines:
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if separator and name.strip() == "SPEECHRAIL_API_KEY":
            parsed = value.strip()
            if len(parsed) >= 2 and parsed[0] in "'\"" and parsed[-1] == parsed[0]:
                parsed = parsed[1:-1]
            if parsed:
                os.environ["SPEECHRAIL_API_KEY"] = parsed
            return


def _adapter() -> SpeechRailVoiceFoundryAdapter:
    _discover_key()
    config = AudioProviderConfig.from_env()
    return SpeechRailVoiceFoundryAdapter(
        config,
        preview_model=config.tts_model,
        execution_policy=FoundryExecutionPolicy(
            model_id="live-probe",
            variant="live-probe",
            validation_policy_revision="live-probe-1",
            processing_fingerprint=hashlib.sha256(b"wom-live-probe").hexdigest(),
            allowed_usages=frozenset({"dialogue", "narration"}),
            scope_ref="live-probe",
        ),
    )


@pytest.mark.asyncio
async def test_the_supply_chain_runs_against_a_real_speechrail():
    """Preview, cast, confirm, re-read the reference, validate, review, publish.

    The step this exists for is the reference re-read. Upstream refuses an asset
    read that does not name the revision it expects, so a client that omits
    that header never hears the voice it is being asked to approve. Every other
    assertion here is ordinary; that one is the whole reason the test is real.
    """
    adapter = _adapter()
    voice_id = "wom_probe_" + uuid.uuid4().hex[:12]
    candidate_id: str | None = None
    try:
        preview = await adapter.preview(
            PreviewRequest(
                game_locale="zh-CN",
                voice_description=PROBE_INSTRUCTION,
                reference_text=PROBE_REFERENCE,
                seed=7,
            )
        )
        assert preview.audio_bytes > 0

        created = await adapter.create(
            CreateRequest(
                voice_id=voice_id,
                name="集成探针 / live probe",
                instruction=PROBE_INSTRUCTION,
                reference_text=PROBE_REFERENCE,
                seed=7,
                provider_locale="zh",
                idempotency_key="live-probe-" + uuid.uuid4().hex[:8],
            )
        )
        candidate_id = created.candidate_id

        confirmed = await adapter.confirm(
            created.candidate_id,
            ConfirmRequest(reference_text=PROBE_REFERENCE),
        )
        # Binding the reference moves the design. Holding the older revision
        # would make every later call — including the asset reads below —
        # describe a voice that no longer exists.
        assert confirmed.candidate_revision != created.candidate_revision
        assert confirmed.reference_confirmed is True

        reference = await adapter.read_asset(
            AssetRequest(
                candidate_id=confirmed.candidate_id,
                candidate_revision=confirmed.candidate_revision,
            )
        )
        assert reference.audio
        assert reference.audio_digest == hashlib.sha256(reference.audio).hexdigest()
        assert len(reference.audio) == reference.audio_bytes

        validation = await adapter.validate(
            confirmed.candidate_id,
            test_text=PROBE_VALIDATION,
            capability_key="quality.render",
        )
        assert validation.candidate_revision == confirmed.candidate_revision

        cross_text = await adapter.read_asset(
            AssetRequest(
                candidate_id=confirmed.candidate_id,
                candidate_revision=confirmed.candidate_revision,
                validation_id=validation.validation_id,
            )
        )
        assert cross_text.audio

        evidence = await adapter.review(
            confirmed.candidate_id,
            validation_id=validation.validation_id,
            identity=FoundryReviewVerdict.PASS,
            naturalness=FoundryReviewVerdict.PASS,
        )
        assert evidence.evidence_id

        published = await adapter.publish(
            confirmed.candidate_id,
            expected_candidate_revision=confirmed.candidate_revision,
        )
        assert published.voice_id == voice_id
        assert published.voice_revision
        assert published.evidence.evidence_digest
        candidate_id = None
    finally:
        if candidate_id is not None:
            await _cancel(adapter, candidate_id)


async def _cancel(adapter: SpeechRailVoiceFoundryAdapter, candidate_id: str) -> None:
    """Best-effort cleanup: a probe must not leave a live candidate behind."""
    try:
        await adapter._fetch(
            "POST",
            adapter._url(f"voice-designs/{candidate_id}/cancel"),
            # A JSON body has to declare that it is JSON or the provider
            # rejects it before it ever reaches the cancel route, and the
            # probe quietly leaves a live candidate behind.
            adapter._headers({"Content-Type": "application/json"}),
            b'{"reason_code": "live_probe_cleanup"}',
            1 << 20,
            30.0,
        )
    except (VoiceFoundryPortError, asyncio.TimeoutError, OSError):
        pass
