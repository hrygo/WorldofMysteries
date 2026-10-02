#!/usr/bin/env python3
"""Build the strict blind-identification set for the cast voices.

**What this tool is for.** V03 is satisfied by a listener naming each identity
from hearing it. The round on record does not settle that: it replayed one
sentence five times, after the listener had already heard every voice, so it
measured recognition rather than identification. This tool builds the set that
would settle it — and it is a script rather than a folder of audio because a
one-shot folder in a temporary directory is not evidence anybody can re-run.

**The design constraint that makes the result mean anything.** Every sentence is
rendered by *every* voice. A listener therefore cannot narrow the field with
"that sounds like something a doctor would say": topic, wording and register
carry no information about who is speaking, and only the voice can answer. The
orders within a sentence are shuffled for the same reason.

**What it refuses.**

* A sentence that is any identity's ``reference_text`` or ``validation_text``.
  Those are the lines the voices were cast from; a listener who has heard them
  has been primed, and the set would measure recall instead of identification.
* An answer key written inside the clips directory. The key is the one artifact
  that must not be next to what it explains.
* Clips that already exist. A half-written set that gets rendered into again is
  a set made of two different runs.
* Fewer than two identities or fewer than one sentence.

**It does not replace the human verdict.** This tool produces material and the
key. Under V03 a machine result never substitutes for a listener's decision.

**The voice map is an input, not something this tool derives.** A provider voice
id is derived from ``(world, identity, persona_revision)`` by the engine, so the
tool cannot know which world is live; the operator supplies the ids. Rendering a
clip publishes nothing — it is a read against a running service.

Usage::

    python3 scripts/voice_blind_set.py \\
        --voice-map voices.json \\
        --out <clips-dir> \\
        --key-out <answer-key.json> \\
        [--lines sentences.txt] [--base-url URL] [--seed N]

``voices.json`` maps a presentation identity to a provider voice id::

    {"narrator": "wom-...", "ida-finch": "wom-...", ...}

The API key is resolved the way the service itself resolves it —
``SPEECHRAIL_API_KEY`` first, then ``<app home>/config/.env`` — and is never
printed or written.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

CATALOG = (
    Path(__file__).resolve().parent.parent
    / "engine"
    / "infrastructure"
    / "voice_designs"
    / "catalog.json"
)


class BlindSetError(RuntimeError):
    """The requested set cannot be built as asked."""


def resolve_api_key(environ: dict[str, str] | None = None) -> str | None:
    """Find the service key without printing or persisting it."""
    values = os.environ if environ is None else environ
    key = (values.get("SPEECHRAIL_API_KEY") or "").strip()
    if key:
        return key
    app_home = (values.get("SPEECHRAIL_APP_HOME") or "").strip()
    root = (
        Path(app_home).expanduser().absolute()
        if app_home
        else Path.home() / "Library" / "Application Support" / "SpeechRail"
    )
    env_file = root / "config" / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() != "SPEECHRAIL_API_KEY":
            continue
        value = value.strip()
        if value[:1] in {'"', "'"} and len(value) > 1 and value[-1] == value[0]:
            value = value[1:-1]
        return value.strip() or None
    return None


def cast_lines(catalog_path: Path) -> set[str]:
    """Every line a voice was cast or cross-text validated from."""
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BlindSetError(f"catalog_unreadable: {exc}") from exc
    lines = set()
    for design in catalog.get("identities", []):
        for field in ("reference_text", "validation_text"):
            text = design.get(field)
            if isinstance(text, str) and text.strip():
                lines.add(text.strip())
    return lines


def read_sentences(path: Path | None, forbidden: set[str]) -> list[str]:
    if path is None:
        raise BlindSetError("no_sentences: pass --lines")
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BlindSetError(f"sentences_unreadable: {exc}") from exc
    sentences = [line.strip() for line in raw if line.strip() and not line.startswith("#")]
    if not sentences:
        raise BlindSetError("no_sentences: file held no usable lines")
    repeated = sorted(set(sentences) & forbidden)
    if repeated:
        raise BlindSetError(f"sentence_is_a_cast_line: {repeated[0]}")
    return sentences


def plan(
    identities: list[str],
    sentences: list[str],
    seed: int,
) -> list[dict[str, object]]:
    """Assign one clip per (sentence, voice), shuffling within each sentence."""
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    index = 0
    for number, sentence in enumerate(sentences, start=1):
        order = list(identities)
        rng.shuffle(order)
        for identity in order:
            index += 1
            rows.append(
                {
                    "clip": f"clip_{index:02d}.wav",
                    "sentence": number,
                    "text": sentence,
                    "identity": identity,
                }
            )
    return rows


def render(url: str, key: str, model: str, voice: str, text: str, dest: Path) -> None:
    body = json.dumps(
        {"model": model, "voice": voice, "input": text, "response_format": "wav"}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise BlindSetError(f"provider_refused_{exc.code}") from exc
    except OSError as exc:
        raise BlindSetError(f"provider_unreachable: {exc}") from exc
    if len(payload) < 45 or payload[:4] != b"RIFF":
        raise BlindSetError("provider_returned_no_audio")
    dest.write_bytes(payload)


def build(
    *,
    voice_map: dict[str, str],
    sentences: list[str],
    clips_dir: Path,
    key_path: Path,
    base_url: str,
    model: str,
    seed: int,
    api_key: str,
) -> list[dict[str, object]]:
    if len(voice_map) < 2:
        raise BlindSetError("need_at_least_two_identities")
    if not sentences:
        raise BlindSetError("need_at_least_one_sentence")
    if key_path.resolve().is_relative_to(clips_dir.resolve()):
        raise BlindSetError("answer_key_would_sit_next_to_the_clips")

    rows = plan(sorted(voice_map), sentences, seed)
    clips_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        dest = clips_dir / str(row["clip"])
        if dest.exists():
            raise BlindSetError(f"clip_exists: {row['clip']}")
    for row in rows:
        render(
            f"{base_url.rstrip('/')}/v1/audio/speech",
            api_key,
            model,
            voice_map[str(row["identity"])],
            str(row["text"]),
            clips_dir / str(row["clip"]),
        )
        row["voice_id"] = voice_map[str(row["identity"])]
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a strict blind voice set.")
    parser.add_argument("--voice-map", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--key-out", type=Path, required=True)
    parser.add_argument("--lines", type=Path, default=None)
    parser.add_argument("--base-url", default="http://127.0.0.1:8201")
    parser.add_argument("--model", default="tts-1")
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    args = parser.parse_args(argv)

    try:
        try:
            voice_map = json.loads(args.voice_map.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BlindSetError(f"voice_map_unreadable: {exc}") from exc
        if not isinstance(voice_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and k and v
            for k, v in voice_map.items()
        ):
            raise BlindSetError("voice_map_must_be_identity_to_voice_id")
        sentences = read_sentences(args.lines, cast_lines(args.catalog))
        api_key = resolve_api_key()
        if not api_key:
            print("error: no service key resolved", file=sys.stderr)
            return 2
        rows = build(
            voice_map=voice_map,
            sentences=sentences,
            clips_dir=args.out,
            key_path=args.key_out,
            base_url=args.base_url,
            model=args.model,
            seed=args.seed,
            api_key=api_key,
        )
    except BlindSetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(rows)} clips -> {args.out}")
    print(f"answer key -> {args.key_out}  (keep it away from the clips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
