#!/usr/bin/env python3
"""Per-axis separation analysis for cast voice auditions.

**What this tool is for.** The blind-listening record for the first cast says
the five voices are mutually distinguishable but that the margin is thin, and
it explicitly leaves one question open: *which* axis (pitch / rate / timbre)
carries that separation, so the next cast can widen the right one. This tool
exists to answer that question -- or to prove the material cannot answer it yet.

**It is deliberately built to refuse.** A hand analysis of the same five clips
produced three different "closest pair" answers depending on which frames were
averaged; the apparent worst pair moved between three different pairings. Two
of those three were noise. A tool that always prints a ranking teaches the next
person to trust a number that was never there. So this tool reports a verdict
of ``insufficient`` or ``unstable`` and prints no attribution when either
applies.

* ``insufficient`` -- some identity has fewer than ``--min-sentences`` clips,
  so per-voice estimates rest on too little text to separate the voice from the
  sentence it happened to be speaking.
* ``unstable`` -- the closest pair changes when the frame selection changes
  (voiced frames only vs every energy-bearing frame), meaning the ranking is an
  artefact of the estimator rather than a property of the voices.
* ``unreliable`` -- the closest pair is not actually separable on that axis: a
  bootstrap of its per-clip medians misclassifies more than
  ``--max-error-rate`` of the time, which is what two voices that genuinely
  share an axis look like.

Only when all three checks pass does it emit a per-axis weakest-link ranking.

**It does not replace the human verdict.** These are objective descriptors
computed on synthesized audio. Under V03 a machine result never substitutes for
a listener's decision; this output is a *screening* signal saying which pairs a
listener should be asked about, nothing more.

Usage (numpy + ffmpeg required; use the project environment, not bare
``python3``, which has no numpy)::

    uv run --project engine --locked --extra dev python \
        scripts/voice_axis_attribution.py <corpus-dir> [--json-out PATH]

The corpus directory holds one subdirectory per identity, each with one or more
audio files. One clip per identity is accepted but will normally yield
``insufficient``.

Exit status is 0 only when a verdict of ``attributable`` was reached, so the
tool can gate a pipeline rather than merely inform one. Every refusal is
reported with the reason that caused it.
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SAMPLE_RATE = 24_000
_FRAME_SECONDS = 0.04
_HOP_SECONDS = 0.01
_F0_MIN_HZ = 60
_F0_MAX_HZ = 400
_PERIODICITY_FLOOR = 0.3
_RMS_FLOOR = 0.01
_BOOTSTRAP_ROUNDS = 4000
_BOOTSTRAP_SEED = 7
_RATE_REFRACTORY_SECONDS = 0.08

AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


def _missing_dependency() -> str | None:
    """Return the first missing runtime dependency, or None if all present."""
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError:
        return (
            "numpy is required but absent from this interpreter. Run through "
            "the project environment instead of bare python3:\n"
            "  uv run --project engine --locked --extra dev python "
            "scripts/voice_axis_attribution.py <corpus-dir>"
        )
    if shutil.which("ffmpeg") is None:
        return "ffmpeg is required for decoding but was not found on PATH."
    return None


def _decode(path: Path):
    """Decode any input audio to mono float32 at the analysis sample rate."""
    import numpy as np

    raw = subprocess.run(
        [
            "ffmpeg", "-v", "quiet", "-i", str(path),
            "-f", "f32le", "-ac", "1", "-ar", str(_SAMPLE_RATE), "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _voiced_frame_starts(x) -> list[int]:
    """Frame offsets carrying enough energy and periodicity to trust."""
    import numpy as np

    win = int(_SAMPLE_RATE * _FRAME_SECONDS)
    hop = int(_SAMPLE_RATE * _HOP_SECONDS)
    lo = int(_SAMPLE_RATE / _F0_MAX_HZ)
    hi = int(_SAMPLE_RATE / _F0_MIN_HZ)
    starts: list[int] = []
    for i in range(0, max(len(x) - win, 0), hop):
        frame = x[i : i + win]
        if float(np.sqrt((frame**2).mean())) < _RMS_FLOOR:
            continue
        centred = frame - frame.mean()
        ac = np.correlate(centred, centred, "full")[win - 1 :]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        segment = ac[lo:hi]
        if segment.size == 0:
            continue
        if ac[int(np.argmax(segment)) + lo] < _PERIODICITY_FLOOR:
            continue
        starts.append(i)
    return starts


def _f0_per_frame(x, starts):
    """Per-frame F0 estimate; frames too aperiodic to estimate are dropped."""
    import numpy as np

    win = int(_SAMPLE_RATE * _FRAME_SECONDS)
    lo = int(_SAMPLE_RATE / _F0_MAX_HZ)
    hi = int(_SAMPLE_RATE / _F0_MIN_HZ)
    out = []
    for i in starts:
        frame = x[i : i + win]
        centred = frame - frame.mean()
        ac = np.correlate(centred, centred, "full")[win - 1 :]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        segment = ac[lo:hi]
        if segment.size == 0:
            continue
        if ac[int(np.argmax(segment)) + lo] < _PERIODICITY_FLOOR:
            continue
        out.append(_SAMPLE_RATE / (int(np.argmax(segment)) + lo))
    return np.array(out, dtype=float)


def _centroid_per_frame(x, starts):
    """Spectral centroid over the same frames, in Hz."""
    import numpy as np

    win = int(_SAMPLE_RATE * _FRAME_SECONDS)
    freqs = np.fft.rfftfreq(win, 1 / _SAMPLE_RATE)
    window = np.hanning(win)
    out = []
    for i in starts:
        frame = x[i : i + win]
        power = np.abs(np.fft.rfft(frame * window)) ** 2
        total = float(power.sum())
        if total <= 0:
            continue
        out.append(float((power * freqs).sum() / total))
    return np.array(out, dtype=float)


def _syllable_rate(x) -> float:
    """Syllable nuclei per second from a smoothed energy envelope."""
    import numpy as np

    hop = int(_SAMPLE_RATE * _HOP_SECONDS)
    win = hop * 20
    if len(x) < win * 5:
        return 0.0
    envelope = np.array(
        [float(np.sqrt((x[i : i + win] ** 2).mean())) for i in range(0, len(x) - win, hop)]
    )
    if envelope.size < 5:
        return 0.0
    smoothed = np.convolve(envelope, np.ones(5) / 5, mode="same")
    threshold = smoothed.mean() + 0.35 * smoothed.std()
    refractory = max(int(_RATE_REFRACTORY_SECONDS * _SAMPLE_RATE / hop), 1)
    peaks = 0
    i = 1
    while i < smoothed.size - 1:
        if smoothed[i] > threshold and smoothed[i] >= smoothed[i - 1] and smoothed[i] > smoothed[i + 1]:
            peaks += 1
            i += refractory
        else:
            i += 1
    duration = len(x) / _SAMPLE_RATE
    return peaks / duration if duration else 0.0


@dataclass(frozen=True)
class Axis:
    key: str
    label: str
    unit: str


AXES = (
    Axis("f0", "音高轴 F0", "Hz"),
    Axis("rate", "语速轴 rate", "syll/s"),
    Axis("centroid", "质感轴 spectral centroid", "Hz"),
)


@dataclass
class Identity:
    name: str
    clips: list[Path] = field(default_factory=list)
    # axis key -> per-clip estimates measured on voiced frames only
    voiced: dict[str, list[float]] = field(default_factory=dict)
    # axis key -> per-clip estimates measured over every analysed frame
    allframes: dict[str, list[float]] = field(default_factory=dict)


def _analysis_frames(x, voiced_only: bool) -> list[int]:
    """Frame offsets to measure on. The naive variant keeps only the energy gate.

    Sampling both is the point: the earlier hand analysis produced different
    "closest pair" answers purely by changing this choice, so a ranking that
    survives neither variant is an artefact of the estimator.
    """
    starts = _voiced_frame_starts(x)
    if voiced_only:
        return starts
    win = int(_SAMPLE_RATE * _FRAME_SECONDS)
    hop = int(_SAMPLE_RATE * _HOP_SECONDS)
    import numpy as np

    return [
        i
        for i in range(0, max(len(x) - win, 0), hop)
        if float(np.sqrt((x[i : i + win] ** 2).mean())) >= _RMS_FLOOR
    ]


def _measure(identity: Identity) -> None:
    """Fill ``voiced`` and ``allframes`` for one identity across all its clips."""
    import numpy as np

    for voiced_only, target in ((True, identity.voiced), (False, identity.allframes)):
        acc: dict[str, list[float]] = {axis.key: [] for axis in AXES}
        for clip in identity.clips:
            x = _decode(clip)
            starts = _analysis_frames(x, voiced_only)
            if not starts:
                continue
            f0 = _f0_per_frame(x, starts)
            centroid = _centroid_per_frame(x, starts)
            if f0.size == 0 or centroid.size == 0:
                continue
            acc["f0"].append(float(np.median(f0)))
            acc["centroid"].append(float(np.median(centroid)))
            acc["rate"].append(_syllable_rate(x))
        target.clear()
        target.update({key: values for key, values in acc.items() if values})


def _closest_pair(values: dict[str, float]) -> tuple[float, str, str]:
    ranked = sorted(
        (abs(values[a] - values[b]), a, b) for a, b in itertools.combinations(values, 2)
    )
    return ranked[0] if ranked else (0.0, "", "")


def _bootstrap_error_rate(np, first, second) -> float:
    """Misclassification rate when guessing which of two samples has higher median."""
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    hits = 0
    for _ in range(_BOOTSTRAP_ROUNDS):
        if np.median(np.random.choice(first, first.size)) > np.median(
            np.random.choice(second, second.size)
        ):
            hits += 1
    return 1 - max(hits, _BOOTSTRAP_ROUNDS - hits) / _BOOTSTRAP_ROUNDS


def _axis_values(identities: list[Identity], axis_key: str, variant: str) -> dict[str, float]:
    import numpy as np

    out: dict[str, float] = {}
    for i in identities:
        samples = (i.voiced if variant == "voiced" else i.allframes).get(axis_key, [])
        if samples:
            out[i.name] = float(np.median(samples))
    return out


def analyse(corpus: Path, min_sentences: int, max_error_rate: float) -> dict:
    import numpy as np

    identities: list[Identity] = []
    for entry in sorted(p for p in corpus.iterdir() if p.is_dir()):
        clips = sorted(f for f in entry.iterdir() if f.suffix.lower() in AUDIO_SUFFIXES)
        if clips:
            identities.append(Identity(name=entry.name, clips=clips))
    if len(identities) < 2:
        raise SystemExit(
            f"need at least two identity directories under {corpus}; found {len(identities)}"
        )
    for identity in identities:
        _measure(identity)

    reasons: list[str] = []

    # Guard 1 -- enough text per voice to tell the voice from the sentence.
    thin = [i.name for i in identities if len(i.clips) < min_sentences]
    if thin:
        reasons.append(
            f"素材不足：{', '.join(thin)} 每条身份少于 {min_sentences} 句。"
            "单句采样无法把音色差异与「碰巧念的是这句台词」分开。"
        )

    # Guard 2 -- the closest pair must not depend on the estimator.
    closest: dict[str, dict[str, tuple]] = {}
    unstable: list[str] = []
    for axis in AXES:
        per_variant = {
            variant: _closest_pair(_axis_values(identities, axis.key, variant))
            for variant in ("voiced", "allframes")
        }
        closest[axis.key] = per_variant
        if len({pair[1:] for pair in per_variant.values()}) > 1:
            unstable.append(axis.label)
    if unstable:
        reasons.append(
            "估计量不稳定：以下轴的「最接近配对」随帧选择改变，说明排序是估计量假象"
            "而非音色事实 —— " + ", ".join(unstable)
        )

    # Guard 3 -- the closest pair must actually be separable on that axis.
    unreliable: list[str] = []
    error_rates: dict[str, float] = {}
    if not unstable:
        for axis in AXES:
            _, a, b = closest[axis.key]["voiced"]
            first = np.array(next(i for i in identities if i.name == a).voiced[axis.key])
            second = np.array(next(i for i in identities if i.name == b).voiced[axis.key])
            if first.size < 2 or second.size < 2:
                unreliable.append(axis.label)
                continue
            rate = _bootstrap_error_rate(np, first, second)
            error_rates[axis.key] = round(rate, 4)
            if rate > max_error_rate:
                unreliable.append(axis.label)
        if unreliable:
            reasons.append(
                f"该轴上「最接近配对」的差异不可靠（bootstrap 判错率 > {max_error_rate}）"
                "，说明这两人在该轴上本就分不开 —— " + ", ".join(unreliable)
            )

    verdict = "attributable"
    if reasons:
        verdict = "insufficient" if thin else ("unstable" if unstable else "unreliable")

    axes_out = []
    for axis in AXES:
        entry: dict = {
            "axis": axis.label,
            "unit": axis.unit,
            "values": _axis_values(identities, axis.key, "voiced"),
            "values_allframes": _axis_values(identities, axis.key, "allframes"),
        }
        entry["values"] = {k: round(v, 2) for k, v in entry["values"].items()}
        entry["values_allframes"] = {
            k: round(v, 2) for k, v in entry["values_allframes"].items()
        }
        if verdict == "attributable":
            gap, a, b = closest[axis.key]["voiced"]
            entry["closest_pair"] = [a, b]
            entry["closest_gap"] = round(float(gap), 3)
            entry["bootstrap_error_rate"] = error_rates.get(axis.key)
        axes_out.append(entry)

    return {
        "verdict": verdict,
        "reasons": reasons,
        "corpus": str(corpus),
        "clips_per_identity": {i.name: len(i.clips) for i in identities},
        "axes": axes_out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-axis voice separation screening.")
    parser.add_argument("corpus", type=Path)
    parser.add_argument(
        "--min-sentences",
        type=int,
        default=3,
        help="clips required per identity before any attribution is emitted",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.1,
        help="bootstrap misclassification rate above which an axis is called unreliable",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    problem = _missing_dependency()
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    report = analyse(args.corpus, args.min_sentences, args.max_error_rate)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "attributable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
