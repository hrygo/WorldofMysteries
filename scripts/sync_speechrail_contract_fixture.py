#!/usr/bin/env python3
"""Refresh the pinned SpeechRail Realtime contract fixture.

The fixture under ``fixtures/speechrail_contract/`` is a read-only snapshot of
the upstream machine schema plus a shared case set.  This script copies the
schema files from a local SpeechRail checkout and rewrites ``manifest.json``
with the source commit, per-file digests and the verified implementation
deltas the consumer depends on.

It never imports SpeechRail Python code and never writes outside the fixture
directory.  Usage:

    python3 scripts/sync_speechrail_contract_fixture.py /path/to/SpeechRail
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "fixtures" / "speechrail_contract"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# Paths copied verbatim from the upstream checkout.
SNAPSHOT_FILES = (
    "contracts/realtime-events.schema.json",
    "contracts/realtime-field-matrix.json",
)

# Deltas the WoM adapters rely on.  Each one was read from the pinned upstream
# source, not inferred from the schema alone.  Keep the wording factual: an
# entry is removed only after the pinned source no longer supports it.
VERIFIED_DELTAS = (
    {
        "id": "realtime_contract_version",
        "statement": (
            "contracts/realtime-openai.md declares contract version 4.0.0 with "
            "effect date 2026-09-25 and provides no alias or /v2 compatibility layer."
        ),
        "evidence": ["contracts/realtime-openai.md"],
    },
    {
        "id": "client_session_event",
        "statement": (
            "session.update is the only accepted client session event; "
            "transcription_session.update is rejected with unsupported_operation."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "session_audio_shape",
        "statement": (
            "The client session object accepts only type, audio and speechrail; audio.input "
            "carries format, transcription, turn_detection and an optional speechrail override. "
            "Flat input_audio_format and input_audio_transcription are rejected."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "session_speechrail_fields",
        "statement": (
            "session.speechrail requires task and accepts tts, alignment, diarization, "
            "endpointing, expected_asr_revision and expected_tts_revision only. "
            "render_receipts and model_revision are rejected."
        ),
        "evidence": [
            "src/speechrail/compatibility/openai_realtime.py",
            "contracts/realtime-events.schema.json",
        ],
    },
    {
        "id": "wire_sample_rate",
        "statement": (
            "The wire accepts audio/pcm at 24000 Hz mono only; any other rate is rejected "
            "as unsupported_audio_format before the first audio frame."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "tts_incremental_protocol",
        "statement": (
            "speechrail.tts.create is removed. The caller submits "
            "speechrail.tts.start, zero-based speechrail.tts.append_text segments and "
            "speechrail.tts.finish_text; speechrail.tts.cancel accepts type, event_id and "
            "request_id only."
        ),
        "evidence": [
            "src/speechrail/compatibility/openai_realtime.py",
            "contracts/realtime-events.schema.json",
        ],
    },
    {
        "id": "tts_start_voice_revision_field",
        "statement": (
            "speechrail.tts.start requires task and names the voice pin voice_revision; "
            "expected_voice_revision is rejected."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "tts_terminal_events",
        "statement": (
            "Each utterance ends with exactly one speechrail.tts.completed, "
            "speechrail.tts.cancelled or speechrail.tts.failed. completed carries task_id, "
            "request_id and generated_samples and no inline render receipt."
        ),
        "evidence": [
            "src/speechrail/application/realtime_openai.py",
            "contracts/realtime-events.schema.json",
        ],
    },
    {
        "id": "tts_text_ack",
        "statement": (
            "speechrail.tts.text_accepted acknowledges each append with append_sequence, "
            "accepted_codepoints and total_codepoints; append_sequence is distinct from the "
            "transport sequence."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "asr_no_commit_or_clear_ack",
        "statement": (
            "The service emits no input_audio_buffer.committed, input_audio_buffer.cleared, "
            "input_audio_buffer.speech_started, input_audio_buffer.speech_stopped or "
            "conversation.item.created event. clear is a local discard semantic."
        ),
        "evidence": [
            "contracts/realtime-openai.md",
            "src/speechrail/http/routes/realtime_openai.py",
        ],
    },
    {
        "id": "asr_automatic_item_rollover",
        "statement": (
            "The service can commit additional ASR items on its own (rollover, VAD stop, "
            "admission), so one logical input turn may span several items and one "
            "conversation.item.input_audio_transcription.completed event."
        ),
        "evidence": ["src/speechrail/application/realtime_openai.py"],
    },
    {
        "id": "asr_commit_barrier",
        "statement": (
            "Client events are handled sequentially on one queue (only speechrail.tts.cancel "
            "uses the control queue), and input_audio_buffer.commit waits for the ASR reader "
            "before returning. A following identical session.update is therefore handled after "
            "the commit and acknowledged by session.updated. This is a pinned-implementation "
            "consumer barrier, not an OpenAI guarantee."
        ),
        "evidence": [
            "src/speechrail/http/routes/realtime_openai.py",
            "src/speechrail/application/realtime_openai.py",
        ],
    },
    {
        "id": "error_envelope",
        "statement": (
            "The error envelope carries request_id at the top level and the rejected client "
            "event id inside error.event_id; the client must not read request_id from the "
            "error object."
        ),
        "evidence": ["src/speechrail/compatibility/openai_realtime.py"],
    },
    {
        "id": "envelope_sequence",
        "statement": (
            "Every server event carries event_id, session_id and a connection-scoped "
            "sequence that starts at 1 and increases by one. The wire schema allows 0 as a "
            "floor, so the consumer accepts a first sequence of 0 or 1 and then requires "
            "strict continuity."
        ),
        "evidence": [
            "src/speechrail/http/routes/realtime_openai.py",
            "contracts/realtime-events.schema.json",
        ],
    },
    {
        "id": "render_receipt_rest",
        "statement": (
            "The render receipt is completed before the success terminal and is read over REST "
            "at /v1/speechrail/audio/receipts/by-request/{request_id}. Its audio integrity "
            "boundary is pcm16_after_transport_send."
        ),
        "evidence": [
            "src/speechrail/application/tts_stream.py",
            "contracts/openapi.yaml",
        ],
    },
    {
        "id": "revision_pattern",
        "statement": (
            "A wire revision matches ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$; it is not a "
            "40-character hex git sha."
        ),
        "evidence": ["contracts/realtime-events.schema.json"],
    },
    {
        "id": "capability_discovery_is_not_a_lease",
        "statement": (
            "GET /v1/speechrail/capabilities is metadata only: it does not start workers, "
            "reserve admission or prove voice quality. operations.http_speech and "
            "operations.realtime_speech are separate capability entries."
        ),
        "evidence": [
            "src/speechrail/application/capability_snapshot.py",
            "contracts/openapi.yaml",
        ],
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _upstream_commit(checkout: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"cannot resolve upstream commit: {exc}") from exc
    return completed.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", help="path to a local SpeechRail checkout")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing fixture instead of rewriting it",
    )
    args = parser.parse_args(argv)

    checkout = Path(args.checkout).expanduser().resolve()
    if not (checkout / "contracts" / "realtime-events.schema.json").is_file():
        raise SystemExit(f"{checkout} is not a SpeechRail checkout")

    commit = _upstream_commit(checkout)
    manifest: dict[str, object] = {
        "manifest_version": "1.0",
        "repository": "https://github.com/hrygo/SpeechRail",
        "commit": commit,
        "realtime_contract_version": "4.0.0",
        "sync_command": (
            "python3 scripts/sync_speechrail_contract_fixture.py <speechrail-checkout>"
        ),
        "files": {},
        "verified_deltas": list(VERIFIED_DELTAS),
    }

    changed = False
    for relative in SNAPSHOT_FILES:
        source = checkout / relative
        target = FIXTURE_DIR / Path(relative).name
        digest = _sha256(source)
        if args.check:
            if not target.is_file() or _sha256(target) != digest:
                print(f"stale snapshot: {target.name}", file=sys.stderr)
                return 1
        else:
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or _sha256(target) != digest:
                shutil.copyfile(source, target)
                changed = True
        manifest["files"][Path(relative).name] = {
            "source_path": relative,
            "sha256": digest,
        }

    cases_path = FIXTURE_DIR / "cases.json"
    if not cases_path.is_file():
        raise SystemExit("fixtures/speechrail_contract/cases.json is missing")
    manifest["files"]["cases.json"] = {
        "source_path": "fixtures/speechrail_contract/cases.json",
        "sha256": _sha256(cases_path),
        "locally_authored": True,
    }

    rendered = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if args.check:
        if not MANIFEST_PATH.is_file() or MANIFEST_PATH.read_text() != rendered:
            print("manifest.json is stale", file=sys.stderr)
            return 1
        print(f"fixture matches SpeechRail {commit}")
        return 0

    if not MANIFEST_PATH.is_file() or MANIFEST_PATH.read_text() != rendered:
        MANIFEST_PATH.write_text(rendered)
        changed = True
    print(f"pinned SpeechRail {commit}{' (updated)' if changed else ' (unchanged)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
