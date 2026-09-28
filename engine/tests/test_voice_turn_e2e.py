"""Opt-in, fully real voice turn: App -> Engine -> model -> SpeechRail -> App.

Everything below the Swift driver is production code: the App's own
``VoiceInputPTTSession`` captures the system default microphone, the Engine's own
composition interprets the transcript with a live model, commits it through the
durable Domain path, seals a ``SpeechUnit`` and renders it with SpeechRail, and
the App's own ``EngineMediaPlaybackSession`` plays the verified PCM on the system
default output.

What the test adds is measurement, not behaviour: it plays a **synthesized**
stimulus out of the speaker so the loop can run unattended, and it asserts on the
PCM that actually crossed the media socket.

It is opt-in and never part of any gate profile, so the default local run and CI
stay hermetic::

    WOM_LIVE_VOICE_E2E=1 \\
    WOM_E2E_VOICE_ID=<content-addressed SpeechRail voice> \\
    WOM_LIVE_BASE_URL=http://127.0.0.1:8201/v1 \\
    WOM_LIVE_API_KEY=... \\
    WOM_MODEL_BASE_URL=http://127.0.0.1:8000/v1 \\
    WOM_MODEL_NAME=... \\
    WOM_MODEL_API_KEY=... \\
      uv run --extra dev pytest tests/test_voice_turn_e2e.py -v

Credentials are read from the environment only.  Nothing here prints, logs or
persists a key, a ticket or a private socket path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "macos-app/WorldOfMysteries"
ENGINE_DIR = ROOT / "engine"
ENGINE_PACKAGES = ("domain", "application", "infrastructure", "ai", "contracts")

sys.path.insert(0, str(ROOT / "scripts"))
import build_story_content as content_builder  # noqa: E402

OPT_IN = os.getenv("WOM_LIVE_VOICE_E2E", "").strip() == "1"
VOICE_ID = os.getenv("WOM_E2E_VOICE_ID", "").strip()
MODEL_BASE_URL = os.getenv("WOM_MODEL_BASE_URL", "").strip()
MODEL_NAME = os.getenv("WOM_MODEL_NAME", "").strip()

# A sentence the frozen scenario can actually answer, spoken slowly enough for
# the realtime recognizer to keep up over a laptop microphone.
SPOKEN_LINE = "我先别问病人的事，我想看看医生的反应。"

pytestmark = pytest.mark.skipif(
    not OPT_IN,
    reason="WOM_LIVE_VOICE_E2E=1 not set; the real voice turn is opt-in",
)

DRIVER_SOURCES = [
    "IPCEnvelope",
    "IPCFrameCodec",
    "MediaProtocol",
    "EngineRuntimeModels",
    "EngineSocketTransport",
    "EngineIPCClient",
    "EngineProcessManager",
    "EngineConnectionState",
    "StorySessionControl",
    "StoryExpressionControl",
    "StoryRequestJournal",
    "StorySubmissionCoordinator",
    "StorySessionModel",
    "AppState",
]
DRIVER_MEDIA_SOURCES = [
    "Media/EngineMediaPlaybackSession",
    "Media/MicrophoneCapture",
    "Media/NativePlayback",
    "Media/PlaybackInterruption",
    "Media/SpeechRailRealtimeASR",
    "Media/SpeechRailRealtimeASRConnection",
    "Media/SpeechRailRealtimeASRTurnCoordinator",
    "Media/UnixMediaFrameTransport",
    "Media/VoiceInputPTTSession",
    "Media/VoiceTurnController",
]


def _require_live_environment() -> None:
    missing = [
        name
        for name, value in (
            ("WOM_E2E_VOICE_ID", VOICE_ID),
            ("WOM_LIVE_BASE_URL", os.getenv("WOM_LIVE_BASE_URL", "")),
            ("WOM_LIVE_API_KEY", os.getenv("WOM_LIVE_API_KEY", "")),
            ("WOM_MODEL_BASE_URL", MODEL_BASE_URL),
            ("WOM_MODEL_NAME", MODEL_NAME),
            ("WOM_MODEL_API_KEY", os.getenv("WOM_MODEL_API_KEY", "")),
        )
        if not value
    ]
    if missing:
        pytest.skip("live voice turn needs " + ", ".join(missing))


@pytest.fixture(scope="module")
def voice_driver(tmp_path_factory):
    """Compile the production App media/IPC sources into one test driver."""
    _require_live_environment()
    compiler = shutil.which("swiftc")
    assert compiler, "The real voice turn requires the target Swift toolchain"
    binary = tmp_path_factory.mktemp("voice-e2e") / "driver"
    text = (SWIFT / "Artifacts/ArtifactModels.swift").read_text()
    context = text[text.index("public struct ArtifactContext:"):text.index("public enum ArtifactRiskBand:")]
    context_file = binary.parent / "ArtifactContext.swift"
    context_file.write_text("import Foundation\n" + context)
    sources = [str(SWIFT / f"{name}.swift") for name in DRIVER_SOURCES + DRIVER_MEDIA_SOURCES]
    result = subprocess.run(
        [compiler, "-swift-version", "6", "-strict-concurrency=complete", *sources,
         str(context_file), str(Path(__file__).parent / "fixtures/voice_turn_e2e_driver.swift"),
         "-o", str(binary)],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


@pytest.fixture(scope="module")
def story_engine(tmp_path_factory):
    """Staged module tree: production packages plus the test-only launcher."""
    from tests.test_app_engine_session import LAUNCHER_WRAPPER

    staged = tmp_path_factory.mktemp("voice-engine")
    for name in ENGINE_PACKAGES:
        shutil.copytree(ENGINE_DIR / name, staged / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    entry = staged / "infrastructure/ipc_server.py"
    production_bytes = entry.read_bytes()
    (staged / "infrastructure/_ipc_server_production.py").write_bytes(production_bytes)
    entry.write_text(LAUNCHER_WRAPPER, encoding="utf-8")
    (staged / "_wom_sqlite3.py").write_text(
        (Path(__file__).parent / "test_app_engine_session.py").read_text(encoding="utf-8").split(
            "HOST_SQLITE_SHIM = '''", 1)[1].split("'''", 1)[0],
        encoding="utf-8",
    )
    # Same artifact set the packaged runtime ships: the content database, the
    # frozen five-turn catalog the turn policy resolves from, and the episode
    # artifacts the settlement stage finalises against.
    payload = content_builder.build_payload()
    content_builder.write_artifact(
        staged / "infrastructure/story_content/canon.db", payload)
    content_builder.write_five_turn_directory(
        staged / "infrastructure/story_content", payload["seed"])
    content_builder.write_episode_artifacts(
        staged / "infrastructure/story_content")
    assert production_bytes == (ENGINE_DIR / "infrastructure/ipc_server.py").read_bytes()
    return staged


def test_real_voice_turn_speaks_a_committed_world(voice_driver, story_engine, tmp_path):
    _require_live_environment()
    environment = dict(os.environ)
    for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "WOM_TEST_RUNTIME_FAULT"):
        environment.pop(key, None)
    # The driver forwards only these; keep the same names so the App, the Engine
    # and the test all agree on one provider and one model.
    environment["SPEECHRAIL_BASE_URL"] = os.environ["WOM_LIVE_BASE_URL"]
    environment["SPEECHRAIL_API_KEY"] = os.environ["WOM_LIVE_API_KEY"]
    environment["WOM_E2E_VOICE_ID"] = VOICE_ID
    environment["WOM_E2E_SPOKEN"] = SPOKEN_LINE
    environment["WOM_MODEL_EXTRA_BODY"] = os.getenv("WOM_MODEL_EXTRA_BODY", "")

    data_root = tmp_path / "data"
    # AF_UNIX `sun_path` is capped at 104 bytes and pytest's tmp path is already
    # long, so the socket namespace gets its own short directory. Putting it
    # under tmp_path produces a local-only red that CI never sees.
    runtime_root = Path(tempfile.mkdtemp(prefix="wom-voice-runtime-"))
    try:
        result = subprocess.run(
            [str(voice_driver), sys.executable, str(story_engine), str(runtime_root), str(data_root)],
            capture_output=True, text=True, timeout=600, env=environment,
        )
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)
    assert result.returncode == 0, result.stdout + result.stderr

    facts = None
    for line in result.stdout.splitlines():
        if line.startswith("E2E "):
            facts = json.loads(line[len("E2E "):])
    assert facts is not None, result.stdout + result.stderr
    # pytest truncates a long dict in the assertion message, and the truncated
    # tail is exactly where the audio evidence lives. Report it as JSON.
    summary = json.dumps(facts, ensure_ascii=False, sort_keys=True)

    # The Engine must have proven both halves of the live path at startup rather
    # than degrading to the frozen fixture while still claiming to speak.
    assert facts["healthModelReady"] is True, summary
    assert facts["healthVoiceReady"] is True, summary

    # Real speech in: the recognizer heard the synthesized sentence.
    assert facts["transcript"], summary
    assert len(facts["transcript"]) >= 4, summary

    # A real Domain commit, not a canned one.
    assert facts["committedTurn"] == 1, summary
    assert facts["storyRevision"] >= 1, summary

    # A sealed unit bound to a content-addressed provider voice.
    assert facts["deliveryState"] == "ready", summary
    assert facts["speechUnitID"], summary
    assert facts["voiceID"], summary

    # Real audio out: verified PCM crossed the socket and reached the speaker.
    # A digital-silence regression would show peak == 0.
    assert facts["mediaFrames"] > 0, summary
    assert facts["mediaBytes"] > 0, summary
    assert facts["pcmPeak"] > 1000, summary
    assert facts["pcmRMSMilli"] > 100, summary
    assert facts["playedToDevice"] is True, summary
