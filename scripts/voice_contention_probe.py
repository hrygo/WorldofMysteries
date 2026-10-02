#!/usr/bin/env python3
"""Measure voice-render contention against a live story turn.

**Why this exists.** The delivery guide tells the foundry to start heavy voice
work only in an idle window, and lists "parallel optimisations must be justified
by measurement" as the rule for ever doing better. Nothing had ever measured
it, so the policy rested on intuition. This measures it.

**What it measures.** Two numbers, taken against the real local SpeechRail:

* ``ttfc_s`` -- seconds from a sealed request going out to the first audio
  chunk. This is what a waiting player actually feels.
* ``rtf``    -- render wall time divided by audio duration. Below 1.0 means
  synthesis outruns playback.

Each is taken twice: once on an idle service, and once while a real chat
completion is in flight on the local oMLX server. That pairing matters because
both services hold the same ``Qwen3-TTS-12Hz-1.7B`` bf16 weights on the same
Apple Silicon device -- a story turn is not an unrelated background job, it is
the other tenant of the same accelerator.

**What it deliberately does not claim.** It does not measure the foundry
casting path, multi-voice batches, thermal behaviour over long sessions, or
any second machine. A ratio from a handful of runs on one host is a
screening signal, and this script reports the raw numbers rather than a
verdict so the reader can judge. Per V03 no machine result substitutes for a
human verdict; per the delivery guide the measurement informs whether heavy
voice work may run during interaction, it does not certify quality.

Credentials are read from the locations the host config already uses and are
never printed, logged, or written into the report.

Usage::

    uv run --project engine --locked --extra dev python \
        scripts/voice_contention_probe.py --runs 3 [--json-out PATH]

Requires a running SpeechRail (``WOM_LIVE_BASE_URL`` /
``WOM_LIVE_API_KEY``) and a reachable oMLX for the concurrent turn.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

_SAMPLE_RATE = 24_000
_DEFAULT_TEXT = "雨从凌晨开始下，一直没有停的意思。"
_DEFAULT_LLM = "http://127.0.0.1:8000/v1"
_DEFAULT_MODEL = "KAT-Coder-V2.5-Dev-OptiQ-4bit"
_TURN_PROMPT = "用中文写一段约600字的廷根场景描写。"


def _omlx_key() -> str | None:
    """Read the local oMLX key from its documented config location."""
    path = Path.home() / ".omlx" / "settings.json"
    if not path.exists():
        return None
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = (settings.get("auth") or {}).get("api_key")
    return key if isinstance(key, str) and key else None


def _blocking_llm_turn(base_url: str, model: str, key: str) -> tuple[float, int]:
    """One real chat completion; returns (wall seconds, completion tokens)."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": _TURN_PROMPT}],
            "max_tokens": 900,
            "temperature": 0.7,
        }
    ).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.loads(response.read())
    return time.perf_counter() - started, payload["usage"]["completion_tokens"]


async def _render_once(base_url: str, api_key: str, voice: str, text: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
    from infrastructure.audio import (  # noqa: PLC0415 - needs the engine on the path
        AudioProviderConfig,
        RealtimeTTSChunk,
        RealtimeTTSRequest,
        SpeechRailRealtimeTTSAdapter,
        StdlibJSONWebSocketTransport,
    )

    config = AudioProviderConfig(base_url=base_url, api_key=api_key, asr_model="whisper-1")
    transport = StdlibJSONWebSocketTransport(timeout_seconds=300.0)
    adapter = SpeechRailRealtimeTTSAdapter(config, transport)
    marks: dict[str, float] = {}

    async def sink(_chunk: RealtimeTTSChunk) -> None:
        marks.setdefault("first", time.perf_counter())

    try:
        await adapter.connect(require_render_receipt=False)
        marks["ready"] = time.perf_counter()
        terminal = await adapter.render(
            RealtimeTTSRequest.create(text=text, voice=voice), sink
        )
    finally:
        await adapter.close()

    done = time.perf_counter()
    audio_seconds = terminal.total_frames / _SAMPLE_RATE
    return {
        "ttfc_s": round(marks["first"] - marks["ready"], 3),
        "rtf": round((done - marks["ready"]) / audio_seconds, 3),
        "audio_s": round(audio_seconds, 3),
    }


def _median(rows: list[dict], field: str) -> float:
    return statistics.median(row[field] for row in rows)


async def measure(args) -> dict:
    idle = [await _render_once(args.base_url, args.api_key, args.voice, args.text) for _ in range(args.runs)]

    llm_key = _omlx_key()
    if not llm_key:
        return {"verdict": "incomplete", "reason": "no omlx key found", "idle": idle}

    loop = asyncio.get_running_loop()
    concurrent = []
    for _ in range(args.runs):
        turn = loop.run_in_executor(
            None, _blocking_llm_turn, args.llm_base_url, args.llm_model, llm_key
        )
        await asyncio.sleep(args.turn_headstart_s)
        row = await _render_once(args.base_url, args.api_key, args.voice, args.text)
        turn_seconds, tokens = await turn
        row["llm_wall_s"] = round(turn_seconds, 2)
        row["llm_tokens_per_s"] = round(tokens / turn_seconds, 1)
        concurrent.append(row)

    idle_rtf, conc_rtf = _median(idle, "rtf"), _median(concurrent, "rtf")
    idle_ttfc, conc_ttfc = _median(idle, "ttfc_s"), _median(concurrent, "ttfc_s")
    return {
        "verdict": "measured",
        "runs_per_scenario": args.runs,
        "idle": idle,
        "concurrent_with_story_turn": concurrent,
        "rtf": {"idle": round(idle_rtf, 3), "concurrent": round(conc_rtf, 3),
                "ratio": round(conc_rtf / idle_rtf, 2) if idle_rtf else None},
        "ttfc_s": {"idle": round(idle_ttfc, 3), "concurrent": round(conc_ttfc, 3),
                   "ratio": round(conc_ttfc / idle_ttfc, 2) if idle_ttfc else None},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Voice/story resource contention probe.")
    parser.add_argument("--base-url", default=os.getenv("WOM_LIVE_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("WOM_LIVE_API_KEY", ""))
    parser.add_argument("--voice", default=os.getenv("WOM_LIVE_VOICE", "aiden"))
    parser.add_argument("--text", default=_DEFAULT_TEXT)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--llm-base-url", default=_DEFAULT_LLM)
    parser.add_argument("--llm-model", default=_DEFAULT_MODEL)
    parser.add_argument("--turn-headstart-s", type=float, default=0.15)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.base_url or not args.api_key:
        print(
            "error: --base-url and --api-key (or WOM_LIVE_BASE_URL / WOM_LIVE_API_KEY)"
            " must point at a running SpeechRail",
            file=sys.stderr,
        )
        return 2

    report = asyncio.run(measure(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        # Defence in depth: the record is meant to be committable.
        assert args.api_key not in rendered
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
