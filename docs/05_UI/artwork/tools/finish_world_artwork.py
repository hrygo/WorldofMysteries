#!/usr/bin/env python3
"""Deterministic macOS finishing pipeline for approved World / Scene sources.

This tool implements the postprocess order that the image contracts already lock, so the
finishing steps are reproducible instead of being a series of undocumented desktop edits:

1. ``crop``     — exact source crop declared by the contract;
2. ``repair``   — masked local structural repair by copying a nearby region (never generative);
3. ``sr``       — one Real-ESRGAN pass to the oversampled working image (Apple Silicon MPS);
4. ``grade``    — material / colour-luminance grade at working resolution;
5. ``master``   — controlled downsample to the 4096x2560 Production Master;
6. ``fidelity`` — evidence that the master still carries the approved source structure.
7. ``record``   — assemble the QA and provenance records from the verified stage bytes.

It performs no generative reconstruction: the only learned operation is the single super
resolution pass, and ``fidelity`` reports how far the finished image drifted from the approved
source so an invented object cannot pass silently.

``record`` refuses to write an approved record unless the whole postprocess chain is present and
byte-verified, and it refuses to mark G5 runtime QA as passed unless real runtime evidence exists.

Requirements: ``torch`` (with MPS), ``numpy`` and ``Pillow``. The Real-ESRGAN weights are not
committed; pass ``--weights`` and record the SHA256 you used.

Example:

    python3 docs/05_UI/artwork/tools/finish_world_artwork.py sr \
      --input W1_CROP_1584x990.png --output W1_WORK_6336x3960.png \
      --weights RealESRGAN_x4plus.pth

    python3 docs/05_UI/artwork/tools/finish_world_artwork.py record \
      --task W1 --work-dir .hacf/tmp/wom-art/work \
      --runtime-evidence .hacf/tmp/wom-art/work/W1_runtime_evidence.json \
      --qa docs/05_UI/artwork/qa/W1_WORLD_HERO.qa.json \
      --provenance docs/05_UI/artwork/provenance/W1_WORLD_HERO.provenance.json
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgb(path: Path) -> Image.Image:
    image = Image.open(path)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


_SRGB_PROFILE_BYTES: bytes | None = None


def srgb_profile_bytes() -> bytes:
    """Explicit sRGB profile, so every finishing output is verifiable instead of untagged."""

    global _SRGB_PROFILE_BYTES
    if _SRGB_PROFILE_BYTES is None:
        from PIL import ImageCms

        profile = ImageCms.createProfile("sRGB")
        _SRGB_PROFILE_BYTES = ImageCms.ImageCmsProfile(profile).tobytes()
    return _SRGB_PROFILE_BYTES


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        path,
        format="PNG",
        optimize=False,
        compress_level=6,
        icc_profile=srgb_profile_bytes(),
    )


def report(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def describe(image: Image.Image, path: Path) -> Dict[str, Any]:
    return {
        "path": path.name,
        "width": image.width,
        "height": image.height,
        "sha256": sha256_of(path),
    }


# --------------------------------------------------------------------------------------
# 1. Exact source crop
# --------------------------------------------------------------------------------------


def command_crop(args: argparse.Namespace) -> int:
    left, top, right, bottom = (int(part) for part in args.rect.split(","))
    source = load_rgb(Path(args.input))
    cropped = source.crop((left, top, right, bottom))
    if args.width and args.height and cropped.size != (args.width, args.height):
        raise SystemExit(
            f"crop produced {cropped.width}x{cropped.height}, contract expects "
            f"{args.width}x{args.height}"
        )
    save_png(cropped, Path(args.output))
    report(
        {
            "operation": "exact_16_10_source_crop",
            "rect_pixels": [left, top, right, bottom],
            "input": describe(source, Path(args.input)),
            "output": describe(cropped, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 2. Masked local structural repair (copy, never generate)
# --------------------------------------------------------------------------------------


def command_repair(args: argparse.Namespace) -> int:
    """Copy a same-scale region over a defect and feather the seam.

    Every operation is recorded, so G3 review can see exactly which pixels were replaced.
    """

    source = load_rgb(Path(args.input))
    canvas = np.asarray(source).astype(np.float32)
    ops = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    records: List[Dict[str, Any]] = []

    for op in ops:
        src = tuple(int(v) for v in op["from"])
        dst = tuple(int(v) for v in op["to"])
        width = dst[2] - dst[0]
        height = dst[3] - dst[1]
        if src[2] - src[0] != width or src[3] - src[1] != height:
            raise SystemExit("repair source and destination must have identical size")
        if width <= 0 or height <= 0:
            raise SystemExit("repair rectangle must be positive")

        patch = canvas[src[1] : src[3], src[0] : src[2]].copy()
        if op.get("flip") == "horizontal":
            patch = patch[:, ::-1]
        elif op.get("flip") == "vertical":
            patch = patch[::-1, :]

        feather = max(1, min(int(op.get("feather", 12)), width // 2, height // 2))
        alpha = np.ones((height, width), dtype=np.float32)
        ramp_x = np.linspace(0.0, 1.0, feather, dtype=np.float32)
        ramp_y = np.linspace(0.0, 1.0, feather, dtype=np.float32)
        alpha[:feather, :] *= ramp_y[:, None]
        alpha[-feather:, :] *= ramp_y[::-1][:, None]
        alpha[:, :feather] *= ramp_x[None, :]
        alpha[:, -feather:] *= ramp_x[::-1][None, :]
        alpha = alpha[:, :, None]

        region = canvas[dst[1] : dst[3], dst[0] : dst[2]]
        canvas[dst[1] : dst[3], dst[0] : dst[2]] = patch * alpha + region * (1.0 - alpha)
        records.append(
            {
                "from": list(src),
                "to": list(dst),
                "flip": op.get("flip"),
                "feather": feather,
                "reason": op.get("reason", ""),
            }
        )

    repaired = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), mode="RGB")
    save_png(repaired, Path(args.output))
    report(
        {
            "operation": "macos_local_structural_repair",
            "generative": False,
            "ops": records,
            "input": describe(source, Path(args.input)),
            "output": describe(repaired, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 3. Single conservative super resolution pass (Real-ESRGAN x4plus, MPS)
# --------------------------------------------------------------------------------------


def _build_rrdbnet(num_feat: int = 64, num_block: int = 23, num_grow_ch: int = 32):
    import torch
    from torch import nn

    class ResidualDenseBlock(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
            self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, inplace=True)

        def forward(self, x):  # type: ignore[override]
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
            return x5 * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.rdb1 = ResidualDenseBlock()
            self.rdb2 = ResidualDenseBlock()
            self.rdb3 = ResidualDenseBlock()

        def forward(self, x):  # type: ignore[override]
            out = self.rdb3(self.rdb2(self.rdb1(x)))
            return out * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv_first = nn.Conv2d(3, num_feat, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB() for _ in range(num_block)])
            self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_last = nn.Conv2d(num_feat, 3, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, inplace=True)

        def forward(self, x):  # type: ignore[override]
            import torch.nn.functional as functional

            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(
                self.conv_up1(functional.interpolate(feat, scale_factor=2, mode="nearest"))
            )
            feat = self.lrelu(
                self.conv_up2(functional.interpolate(feat, scale_factor=2, mode="nearest"))
            )
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    return RRDBNet()


def _load_weights(model, weights_path: Path) -> str:
    import torch

    payload = torch.load(str(weights_path), map_location="cpu", weights_only=True)
    for key in ("params_ema", "params", "state_dict"):
        if isinstance(payload, dict) and key in payload:
            state = payload[key]
            source = key
            break
    else:
        state = payload
        source = "state_dict"
    cleaned = {name.replace("module.", "", 1): value for name, value in state.items()}
    model.load_state_dict(cleaned, strict=True)
    return source


def command_sr(args: argparse.Namespace) -> int:
    import torch

    source = load_rgb(Path(args.input))
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = _build_rrdbnet().to(device).eval()
    weight_source = _load_weights(model, Path(args.weights))

    tile, overlap = int(args.tile), int(args.overlap)
    scale = 4
    width, height = source.width, source.height
    canvas = np.zeros((height * scale, width * scale, 3), dtype=np.float32)
    weights = np.zeros((height * scale, width * scale, 1), dtype=np.float32)
    array = np.asarray(source).astype(np.float32) / 255.0

    step = max(1, tile - overlap)
    with torch.no_grad():
        for top in range(0, height, step):
            for left in range(0, width, step):
                bottom = min(top + tile, height)
                right = min(left + tile, width)
                if bottom - top < overlap or right - left < overlap:
                    continue
                patch = array[top:bottom, left:right]
                tensor = torch.from_numpy(patch).permute(2, 0, 1).unsqueeze(0).to(device)
                try:
                    output = model(tensor)
                except RuntimeError:
                    model.to("cpu")
                    device = torch.device("cpu")
                    tensor = tensor.to(device)
                    output = model(tensor)
                result = output.squeeze(0).permute(1, 2, 0).float().cpu().numpy()
                result = np.clip(result, 0.0, 1.0)

                blend = np.ones(result.shape[:2], dtype=np.float32)
                feather = min(overlap, result.shape[0] // 2, result.shape[1] // 2)
                if feather > 0:
                    ramp_x = np.linspace(0.0, 1.0, feather, dtype=np.float32)
                    ramp_y = np.linspace(0.0, 1.0, feather, dtype=np.float32)
                    if top > 0:
                        blend[:feather, :] *= ramp_y[:, None]
                    if bottom < height:
                        blend[-feather:, :] *= ramp_y[::-1][:, None]
                    if left > 0:
                        blend[:, :feather] *= ramp_x[None, :]
                    if right < width:
                        blend[:, -feather:] *= ramp_x[::-1][None, :]
                blend = blend[:, :, None]

                y0, x0 = top * scale, left * scale
                region = canvas[y0 : y0 + result.shape[0], x0 : x0 + result.shape[1]]
                weight_region = weights[y0 : y0 + result.shape[0], x0 : x0 + result.shape[1]]
                region += result * blend
                weight_region += blend

    weights = np.where(weights <= 0.0, 1.0, weights)
    finished = canvas / weights
    finished = (np.clip(finished, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    working = Image.fromarray(finished, mode="RGB")
    save_png(working, Path(args.output))
    report(
        {
            "operation": "macos_primary_super_resolution",
            "method": "Real-ESRGAN RRDBNet x4 (single pass)",
            "device": str(device),
            "weights": Path(args.weights).name,
            "weights_sha256": sha256_of(Path(args.weights)),
            "weights_state_key": weight_source,
            "tile": tile,
            "overlap": overlap,
            "scale": scale,
            "downstream_downsample": args.downstream or None,
            "input": describe(source, Path(args.input)),
            "output": describe(working, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 4. Material restoration + colour / luminance grade
# --------------------------------------------------------------------------------------

# Grade profile "subtle-illustration-v1".
#
# Values are deliberately conservative: the goal is a readable dark-fantasy image with
# separated materials, not a photographic HDR look. Every number is part of the record so a
# reviewer can reproduce or reject the grade.
GRADE_PROFILE: Dict[str, float] = {
    "shadow_lift_gamma": 1.10,
    "midtone_contrast": 0.06,
    "highlight_knee": 0.90,
    "detail_radius": 2.0,
    "detail_amount": 0.35,
    "detail_noise_floor": 0.004,
    "clarity_radius": 24.0,
    "clarity_amount": 0.08,
    "saturation": 1.03,
    "warm_highlight_red": 1.012,
    "warm_highlight_blue": 0.988,
}


def _box_blur_1d(values: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Separable box blur built from cumulative sums (deterministic, no extra dependencies)."""

    if radius <= 0:
        return values
    window = radius * 2 + 1
    padded = np.pad(values, [(radius, radius) if i == axis else (0, 0) for i in range(values.ndim)])
    cumulative = np.cumsum(padded, axis=axis)
    zero_shape = list(cumulative.shape)
    zero_shape[axis] = 1
    cumulative = np.concatenate([np.zeros(zero_shape, dtype=cumulative.dtype), cumulative], axis=axis)
    upper = np.take(cumulative, np.arange(window, cumulative.shape[axis]), axis=axis)
    lower = np.take(cumulative, np.arange(0, cumulative.shape[axis] - window), axis=axis)
    return (upper - lower) / float(window)


def _gaussian_like_blur(values: np.ndarray, radius: float) -> np.ndarray:
    """Three box passes approximate a Gaussian closely enough for local-contrast work."""

    step = max(1, int(round(radius / 1.5)))
    result = values
    for _ in range(3):
        result = _box_blur_1d(result, step, axis=0)
        result = _box_blur_1d(result, step, axis=1)
    return result


def _edge_limited_unsharp(values: np.ndarray, radius: float, amount: float, noise_floor: float) -> np.ndarray:
    """Unsharp mask in float space so the boost cannot clip either end of the range.

    Pillow's ``UnsharpMask`` operates on 8-bit data and clips, which crushed W1's night shadows.
    Here the detail signal is attenuated where there is no real edge (noise floor) and where the
    pixel is already near black or near white.
    """

    blurred = _gaussian_like_blur(values, radius)
    detail = values - blurred
    if noise_floor > 0:
        gate = np.clip(np.abs(detail) / noise_floor, 0.0, 1.0)
    else:
        gate = np.ones_like(detail)
    headroom = np.clip(1.0 - np.abs(2.0 * values - 1.0) ** 2, 0.0, 1.0)
    return values + amount * detail * gate * headroom


def _soft_clip(values: np.ndarray, knee: float) -> np.ndarray:
    """Compress the top of the range instead of clipping the crimson moon into a flat disk."""

    above = values > knee
    if not np.any(above):
        return values
    scaled = (values[above] - knee) / (1.0 - knee)
    values = values.copy()
    values[above] = knee + (1.0 - knee) * (1.0 - np.exp(-scaled))
    return values


def _grade_array(array: np.ndarray, profile: Dict[str, float]) -> np.ndarray:
    values = np.clip(array, 0.0, 1.0)
    values = np.power(values, 1.0 / profile["shadow_lift_gamma"])

    # Midtone micro-contrast only: the bell weight keeps deep shadows and highlights untouched, so
    # the grade separates materials without crushing the night.
    smooth = values * values * (3.0 - 2.0 * values)
    bell = np.clip(1.0 - np.abs(2.0 * values - 1.0) ** 2, 0.0, 1.0)
    values = values + (smooth - values) * profile["midtone_contrast"] * bell
    values = _soft_clip(values, profile["highlight_knee"])

    values = _edge_limited_unsharp(
        values, profile["detail_radius"], profile["detail_amount"], profile["detail_noise_floor"]
    )
    values = _edge_limited_unsharp(values, profile["clarity_radius"], profile["clarity_amount"], 0.0)
    values = np.clip(values, 0.0, 1.0)

    luminance = values @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    values = luminance[..., None] + (values - luminance[..., None]) * profile["saturation"]

    warm = np.clip((luminance - 0.5) * 2.0, 0.0, 1.0)[..., None]
    tint = np.array(
        [profile["warm_highlight_red"], 1.0, profile["warm_highlight_blue"]], dtype=np.float32
    )
    values = values * (1.0 - warm) + values * tint * warm
    return np.clip(values, 0.0, 1.0)


def command_grade(args: argparse.Namespace) -> int:
    source = load_rgb(Path(args.input))
    profile = dict(GRADE_PROFILE)
    if args.profile != "subtle-illustration-v1":
        raise SystemExit(f"unknown grade profile: {args.profile}")

    values = np.asarray(source).astype(np.float32) / 255.0
    values = _grade_array(values, profile)
    # Material separation (micro detail plus a low clarity pass) happens in float space above, at
    # the oversampled working resolution, so the master downsample keeps clean edges.
    graded = Image.fromarray((np.clip(values, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), mode="RGB")
    save_png(graded, Path(args.output))
    report(
        {
            "operation": "macos_material_restoration_and_color_luminance_grade",
            "profile": args.profile,
            "parameters": profile,
            "generative": False,
            "input": describe(source, Path(args.input)),
            "output": describe(graded, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 5. Controlled downsample to the Production Master
# --------------------------------------------------------------------------------------


def command_master(args: argparse.Namespace) -> int:
    source = load_rgb(Path(args.input))
    target = (int(args.width), int(args.height))
    if source.width < target[0] or source.height < target[1]:
        raise SystemExit(
            f"refusing to upscale {source.width}x{source.height} into master "
            f"{target[0]}x{target[1]}: the master must come from an oversampled working image"
        )
    master = source.resize(target, resample=Image.LANCZOS)
    save_png(master, Path(args.output))
    report(
        {
            "operation": "controlled_downsample_to_production_master",
            "resample": "Lanczos",
            "input": describe(source, Path(args.input)),
            "output": describe(master, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 6. Fidelity evidence: the finished image still carries the approved source
# --------------------------------------------------------------------------------------


def _luminance(array: np.ndarray) -> np.ndarray:
    return array @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _edge_map(luminance: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(luminance)
    return np.sqrt(gx * gx + gy * gy)


def command_fidelity(args: argparse.Namespace) -> int:
    reference_image = load_rgb(Path(args.reference))
    candidate_image = load_rgb(Path(args.candidate))
    reference = np.asarray(reference_image).astype(np.float32)
    candidate = np.asarray(
        candidate_image.resize(reference_image.size, resample=Image.LANCZOS)
    ).astype(np.float32)

    difference = np.abs(reference - candidate)
    reference_luminance = _luminance(reference)
    candidate_luminance = _luminance(candidate)
    reference_luminance = reference_luminance - reference_luminance.mean()
    candidate_luminance = candidate_luminance - candidate_luminance.mean()
    luminance_correlation = float(
        (reference_luminance * candidate_luminance).mean()
        / (reference_luminance.std() * candidate_luminance.std() + 1e-9)
    )

    reference_edges = _edge_map(_luminance(reference))
    candidate_edges = _edge_map(_luminance(candidate))
    edge_correlation = float(
        ((reference_edges - reference_edges.mean()) * (candidate_edges - candidate_edges.mean())).mean()
        / (reference_edges.std() * candidate_edges.std() + 1e-9)
    )

    block = 16
    height = reference.shape[0] // block * block
    width = reference.shape[1] // block * block
    blocks = difference[:height, :width].mean(axis=2)
    blocks = blocks.reshape(height // block, block, width // block, block).mean(axis=(1, 3))

    payload = {
        "operation": "fidelity_check_against_approved_source",
        "reference": describe(reference_image, Path(args.reference)),
        "candidate": describe(candidate_image, Path(args.candidate)),
        "candidate_compared_at": list(reference_image.size),
        "mean_absolute_difference_0_255": round(float(difference.mean()), 3),
        "p99_block_difference_0_255": round(float(np.percentile(blocks, 99)), 3),
        "max_block_difference_0_255": round(float(blocks.max()), 3),
        "luminance_correlation": round(luminance_correlation, 4),
        "edge_structure_correlation": round(edge_correlation, 4),
        "thresholds": {
            "mean_absolute_difference_max": 12.0,
            "luminance_correlation_min": 0.97,
            "edge_structure_correlation_min": 0.80,
        },
    }
    payload["verdict"] = (
        "passed"
        if payload["mean_absolute_difference_0_255"]
        <= payload["thresholds"]["mean_absolute_difference_max"]
        and payload["luminance_correlation"] >= payload["thresholds"]["luminance_correlation_min"]
        and payload["edge_structure_correlation"]
        >= payload["thresholds"]["edge_structure_correlation_min"]
        else "failed"
    )
    report(payload)
    return 0 if payload["verdict"] == "passed" else 1


# --------------------------------------------------------------------------------------
# 6b. Runtime surface verification
# --------------------------------------------------------------------------------------


def _max_normalised_correlation(
    capture: np.ndarray, template: np.ndarray
) -> Tuple[float, Tuple[int, int]]:
    """Maximum normalised cross-correlation and its window origin.

    FFT cross-correlation plus integral-image local statistics, so a screenshot can be checked
    against the shipped asset instead of being judged by eye.
    """

    ch, cw = capture.shape
    th, tw = template.shape
    if th > ch or tw > cw:
        return 0.0, (0, 0)

    height = ch + th
    width = cw + tw
    capture_fft = np.fft.rfft2(capture.astype(np.float64), s=(height, width))
    template_fft = np.fft.rfft2(template.astype(np.float64), s=(height, width))
    # numpy's irfft2 already returns the plain correlation sum here (verified against a
    # brute-force NCC), so the raw output is directly comparable with the integral-image
    # statistics below. Scaling it again produced scores in the 1e5 range instead of ~1.
    correlation = np.fft.irfft2(capture_fft * np.conj(template_fft), s=(height, width))[
        : ch - th + 1, : cw - tw + 1
    ]

    values = capture.astype(np.float64)
    cumsum = np.cumsum(np.cumsum(values, axis=0), axis=1)
    cumsum = np.pad(cumsum, ((1, 0), (1, 0)))
    squared = np.cumsum(np.cumsum(values * values, axis=0), axis=1)
    squared = np.pad(squared, ((1, 0), (1, 0)))

    window_sum = (
        cumsum[th:, tw:] - cumsum[:-th, tw:] - cumsum[th:, :-tw] + cumsum[:-th, :-tw]
    )
    window_square_sum = (
        squared[th:, tw:] - squared[:-th, tw:] - squared[th:, :-tw] + squared[:-th, :-tw]
    )

    count = float(th * tw)
    template_mean = float(template.mean())
    local_mean = window_sum / count
    numerator = correlation - count * local_mean * template_mean
    local_variance = np.maximum(window_square_sum - count * local_mean * local_mean, 0.0)
    template_variance = float(((template - template_mean) ** 2).sum())
    denominator = np.sqrt(local_variance * template_variance)
    # A near-flat window has a meaningless 0/0 ratio that can dwarf a real match, so those
    # positions are excluded instead of being normalised by an epsilon.
    usable = local_variance > 4.0
    normalised = np.where(usable, numerator / np.maximum(denominator, 1e-9), -1.0)
    index = int(np.argmax(normalised))
    return float(normalised.ravel()[index]), (
        index % normalised.shape[1],
        index // normalised.shape[1],
    )


def command_surface(args: argparse.Namespace) -> int:
    capture_image = load_rgb(Path(args.capture))
    asset_image = load_rgb(Path(args.asset))

    search_scale = 1.0
    if capture_image.width > args.search_width:
        search_scale = args.search_width / capture_image.width
        capture_image = capture_image.resize(
            (args.search_width, max(1, round(capture_image.height * search_scale))),
            Image.LANCZOS,
        )
    capture = _luminance(np.asarray(capture_image).astype(np.float32))

    best: Dict[str, Any] | None = None
    for scale in np.linspace(args.min_scale, args.max_scale, args.steps):
        width = int(round(asset_image.width * scale * search_scale))
        height = int(round(asset_image.height * scale * search_scale))
        if width < 32 or height < 20 or width > capture_image.width or height > capture_image.height:
            continue
        template = _luminance(
            np.asarray(asset_image.resize((width, height), Image.LANCZOS)).astype(np.float32)
        )
        score, (x, y) = _max_normalised_correlation(capture, template)
        if best is None or score > best["score"]:
            best = {
                "score": round(score, 4),
                "asset_scale": round(float(scale), 3),
                "window_in_capture_pixels": [
                    int(round(x / search_scale)),
                    int(round(y / search_scale)),
                    int(round((x + width) / search_scale)),
                    int(round((y + height) / search_scale)),
                ],
                "window_size_on_screen": [width, height],
            }

    payload: Dict[str, Any] = {
        "operation": "runtime_surface_asset_presence",
        "capture": describe(capture_image, Path(args.capture)),
        "asset": describe(asset_image, Path(args.asset)),
        "search_scale": round(search_scale, 4),
        "scales_tested": {"min": args.min_scale, "max": args.max_scale, "steps": args.steps},
        "best_match": best,
        "minimum_score": args.min_score,
    }
    payload["verdict"] = (
        "present" if best and best["score"] >= args.min_score else "not_found"
    )
    report(payload)
    return 0 if payload["verdict"] == "present" else 1


# --------------------------------------------------------------------------------------
# 7. QA / provenance record assembly
# --------------------------------------------------------------------------------------

# The six runtime slots, the locked source behind each one and the wide anchor that the source
# review proposed: W3/W4 from ``delivery/crop_review.json``, W2/W5/W6 from
# ``delivery/additional_scene_crops.json``. An anchor is re-validated against the real window
# surface before the record may claim a runtime pass.
SCENES: Dict[str, Dict[str, Any]] = {
    "W1": {
        "artwork_id": "W1_WORLD_HERO",
        "source_id": "S01_WORLD_HERO",
        "asset_name": "wom.art.world.hero",
        "wide_anchor": "top",
        "contract": "docs/05_UI/artwork/contracts/W1_WORLD_HERO.contract.json",
        "g0_basis": "PASSED_V3 (explicit interactive art-direction approval of the locked source)",
        "g1_basis": "PASSED_V3_ART_DIRECTION",
        "g0_primary_read": "stylized late-Victorian occult metropolis",
        "g0_secondary_read": "Evernight crimson moon and hidden supernatural order",
    },
    "W2": {
        "artwork_id": "W2_GRAY_FOG",
        "source_id": "S07_GRAY_FOG",
        "asset_name": "wom.art.world.gray-fog",
        "wide_anchor": "top",
        "contract": None,
        "g0_basis": (
            "USER_APPROVED_SOURCE_DIRECTION_R2 (game-oriented floating-city reading accepted as "
            "a visual metaphor; not a literal Canon reconstruction)"
        ),
        "g1_basis": "USER_APPROVED_SOURCE_DIRECTION_R2",
        "g0_primary_read": "floating gothic city above an unbroken fog sea",
        "g0_secondary_read": (
            "branching bridges, stairways and hooded observers as an order-above-the-world metaphor"
        ),
        "g1_superseded_criteria": [
            "generic_high_fantasy_max_5: the accepted source is a stylised floating-city reading; "
            "the older austere-fog brief criterion is explicitly superseded by the user direction "
            "decision recorded in the approval update, not silently scored as passed",
        ],
    },
    "W3": {
        "artwork_id": "W3_RITUAL_ALTAR",
        "source_id": "S04_RITUAL_TEMPLE",
        "asset_name": "wom.art.scene.ritual-altar",
        "wide_anchor": "center",
        "contract": None,
        "g0_basis": "USER_APPROVED_SOURCE_R1 (approved temple source for the ritual slot)",
        "g1_basis": "USER_APPROVED_SOURCE_R1",
        "g0_primary_read": "candle-lit gothic temple interior with a robed officiant at a raised altar",
        "g0_secondary_read": (
            "repeating non-textual astrological emblems on banner cloth and vestments"
        ),
    },
    "W4": {
        "artwork_id": "W4_CODEX_ARCHIVE",
        "source_id": "S03_CODEX_LIBRARY",
        "asset_name": "wom.art.scene.codex-archive",
        "wide_anchor": "bottom",
        "contract": None,
        "g0_basis": "USER_APPROVED_SOURCE_R1 (approved library source for the archive slot)",
        "g1_basis": "USER_APPROVED_SOURCE_R1",
        "g0_primary_read": "tall gothic library and archive hall with a reading gallery",
        "g0_secondary_read": (
            "wet night city seen through the window; candle-lit desks with books and instruments"
        ),
    },
    "W5": {
        "artwork_id": "W5_FATE_WORLDLINE",
        "source_id": "S08_FATE_WORLDLINE",
        "asset_name": "wom.art.scene.fate-worldline",
        "wide_anchor": "top",
        "contract": None,
        "g0_basis": (
            "USER_APPROVED_SOURCE_DIRECTION_R2 (worldline observation metaphor; no domain "
            "cosmology is asserted)"
        ),
        "g1_basis": "USER_APPROVED_SOURCE_DIRECTION_R2",
        "g0_primary_read": "astronomical observation hall with an armillary orrery and suspended glass orbs",
        "g0_secondary_read": (
            "luminous threads linking worlds; robed figures recording at lecterns"
        ),
    },
    "W6": {
        "artwork_id": "W6_ARTIFACT_VAULT",
        "source_id": "S09_ARTIFACT_VAULT",
        "asset_name": "wom.art.scene.artifact-vault",
        "wide_anchor": "center",
        "contract": None,
        "g0_basis": (
            "USER_APPROVED_SOURCE_DIRECTION_R2 (containment-vault environment; its centre object "
            "is decoration, not a sixteenth Artifact)"
        ),
        "g1_basis": "USER_APPROVED_SOURCE_DIRECTION_R2",
        "g0_primary_read": "museum-like containment vault of glazed display cases",
        "g0_secondary_read": (
            "chained ember object, iron grilles and cabinets framing sealed objects as evidence"
        ),
    },
}

SOURCE_APPROVAL_REFERENCE = "docs/05_UI/artwork/delivery/World_Scene_Approval_Update_2026-09-18.md"
CROP_REFERENCE = "docs/05_UI/artwork/delivery/crop_review.json"
ADDITIONAL_CROP_REFERENCE = "docs/05_UI/artwork/delivery/additional_scene_crops.json"
DERIVATIVE_TOOL = "docs/05_UI/artwork/tools/derive_world_artwork.swift"

MASTER_SIZE = (4096, 2560)
WIDE_HEIGHT = 1536

# Identity survival, deliberately simple and stated in the record so anyone can recompute it
# instead of trusting an unexplained "moon presence" score.
RED_DOMINANT_RULE = "R >= 80 and R - max(G, B) >= 40"
SHADOW_CLIP_RULE = "luminance <= 2 of 255"
HIGHLIGHT_CLIP_RULE = "luminance >= 253 of 255"

CONTRAST_THRESHOLDS = {"text_primary_min": 4.5, "important_long_copy_target": 7.0}

UNSCORED_CRITERIA_NOTE = (
    "W1's numeric art-direction sub-scores were never produced for this scene. This pass rests "
    "on the explicit user source-direction approval plus the reading recorded here, not on an "
    "invented score; nothing in this record should be read as a scored artistic judgement."
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_optional_json(path: str | None) -> Dict[str, Any] | None:
    """A missing evidence file is an open gate, never a crash and never a pass."""

    if not path or not Path(path).is_file():
        return None
    return load_json(path)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def merge_records(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge, so historical selection evidence survives a record refresh."""

    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_records(merged[key], value)
        else:
            merged[key] = value
    return merged


def pixel_sha256(path: Path) -> str:
    """Container-independent identity: the decoded pixel stream, not the PNG framing."""

    return hashlib.sha256(load_rgb(path).tobytes()).hexdigest()


def photometry(path: Path) -> Dict[str, Any]:
    luminance = _luminance(np.asarray(load_rgb(path)).astype(np.float32))
    return {
        "mean_luminance_0_255": round(float(luminance.mean()), 2),
        "luminance_p05_0_255": round(float(np.percentile(luminance, 5)), 2),
        "luminance_p50_0_255": round(float(np.percentile(luminance, 50)), 2),
        "luminance_p95_0_255": round(float(np.percentile(luminance, 95)), 2),
        "shadow_clip_pct": round(float((luminance <= 2.0).mean() * 100.0), 3),
        "highlight_clip_pct": round(float((luminance >= 253.0).mean() * 100.0), 3),
    }


def red_dominant_fraction(path: Path) -> float:
    array = np.asarray(load_rgb(path)).astype(np.int16)
    mask = (
        (array[..., 0] >= 80)
        & ((array[..., 0] - array[..., 1]) >= 40)
        & ((array[..., 0] - array[..., 2]) >= 40)
    )
    return round(float(mask.mean() * 100.0), 3)


def wide_crop_rect(anchor: str) -> List[int]:
    if anchor == "top":
        top = 0
    elif anchor == "bottom":
        top = MASTER_SIZE[1] - WIDE_HEIGHT
    elif anchor == "center":
        top = (MASTER_SIZE[1] - WIDE_HEIGHT) // 2
    else:
        raise SystemExit(f"unsupported wide anchor: {anchor}")
    return [0, top, MASTER_SIZE[0], top + WIDE_HEIGHT]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"record refused: {message}")


def _verified_stage(
    work_dir: Path,
    task: str,
    stage: str,
    expected_input_sha256: str | None = None,
) -> Tuple[Dict[str, Any], Path]:
    """Read one stage report and prove that the bytes on disk still match that report."""

    report_path = work_dir / f"{task}_report_{stage}.json"
    _require(report_path.is_file(), f"missing {report_path.name} for the finishing chain")
    payload = load_json(report_path)
    name = (payload.get("output") or {}).get("path")
    _require(bool(name), f"{stage} report has no output path")
    output_path = work_dir / Path(name).name
    _require(output_path.is_file(), f"missing stage output {output_path.name}")
    actual = sha256_of(output_path)
    recorded = (payload.get("output") or {}).get("sha256")
    _require(
        actual == recorded,
        f"{stage} output bytes no longer match its report "
        f"({actual[:12]} on disk vs {str(recorded)[:12]} recorded)",
    )
    if expected_input_sha256 is not None:
        stage_input = (payload.get("input") or {}).get("sha256")
        _require(
            stage_input == expected_input_sha256,
            f"{stage} was not run on the previous stage output "
            f"({str(stage_input)[:12]} vs {str(expected_input_sha256)[:12]})",
        )
    return payload, output_path


def _inspection_for(
    document: Dict[str, Any] | None, task: str
) -> Dict[str, Any] | None:
    """Accept either one scene record or a bundle keyed by task."""

    if not document:
        return None
    if "scales_percent" in document:
        return document
    scenes = document.get("scenes") or {}
    entry = scenes.get(task)
    if entry is None:
        return None
    merged = dict(document.get("protocol") or {})
    merged.update(entry)
    return merged


def _evaluate_inspection(payload: Dict[str, Any] | None) -> Tuple[str, Dict[str, Any]]:
    if not payload:
        return "PENDING_MACOS_FINISHING", {
            "notes": ["No 25/100/200% structural inspection record is attached yet."]
        }
    scales = {int(value) for value in payload.get("scales_percent", [])}
    defects = payload.get("defects_found", [])
    method = (payload.get("method") or "").strip()
    passed = {25, 100, 200} <= scales and not defects and bool(method)
    record: Dict[str, Any] = {
        "inspection_scales_percent": sorted(scales),
        "method": method,
        "defects_found": defects,
        "architecture_errors": [],
        "repetition_errors": [],
        "gibberish_or_fake_text": [],
        "human_or_vehicle_errors": [],
        "inspected_at": payload.get("inspected_at"),
        "notes": [
            "Structural review performed locally on the finished 4096x2560 master at 25/100/200%.",
            "The finishing chain contains no generative step beyond one super-resolution pass, so "
            "it cannot invent micro-text or new objects; the inspection confirms the printed "
            "result matches that.",
        ],
    }
    for key in (
        "readability_note",
        "detail_note",
        "seam_note",
        "text_like_glyph_check",
        "structural_repetition_check",
    ):
        if payload.get(key) is not None:
            record[key] = payload[key]
    return ("PASSED" if passed else "PENDING_MACOS_FINISHING"), record


def _relative_luminance(pixels: np.ndarray) -> np.ndarray:
    """WCAG 2.2 relative luminance for 8-bit sRGB pixels."""

    channel = pixels.astype(np.float64) / 255.0
    linear = np.where(channel <= 0.03928, channel / 12.92, ((channel + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


def _wcag_contrast_ratio(pixels: np.ndarray) -> float:
    """Contrast of a captured region: p95 luminance approximates ink, p05 the backing surface."""

    luminance = _relative_luminance(pixels.reshape(-1, pixels.shape[-1]))
    lighter = float(np.percentile(luminance, 95))
    darker = float(np.percentile(luminance, 5))
    if lighter < darker:
        lighter, darker = darker, lighter
    return (lighter + 0.05) / (darker + 0.05)


def _verified_capture(
    reference: Any,
    evidence_dir: Path,
    digests: Dict[str, str],
    problems: List[str],
    label: str,
) -> str | None:
    """A screenshot only counts as evidence when the bytes are still the recorded ones."""

    if not isinstance(reference, str) or not reference.strip():
        problems.append(f"{label}: no capture file named")
        return None
    path = Path(reference)
    if path.is_absolute():
        problems.append(f"{label}: capture must be a file name relative to the evidence file")
        return None
    resolved = evidence_dir / path
    if not resolved.is_file():
        problems.append(f"{label}: capture {reference} is missing next to the evidence file")
        return None
    declared = digests.get(path.name)
    if declared is None:
        problems.append(f"{label}: capture {reference} is not listed in captures[]")
        return None
    actual = sha256_of(resolved)
    if declared != actual:
        problems.append(
            f"{label}: capture {reference} no longer matches its recorded sha256 "
            f"({actual[:12]} vs {str(declared)[:12]})"
        )
        return None
    return actual


def _evaluate_runtime(
    payload: Dict[str, Any] | None,
    expected_anchor: str,
    evidence_dir: Path,
) -> Tuple[str, Dict[str, Any], List[str]]:
    if not payload:
        return (
            "PENDING_RUNTIME_QA",
            {
                "window_checks": {
                    "960x640": None,
                    "1180x760": None,
                    "2560x1600": None,
                    "2400x900": None,
                },
                "accessibility_checks": {
                    "Increased Contrast": None,
                    "Reduce Transparency": None,
                },
                "notes": ["Runtime window and accessibility checks have not been captured yet."],
            },
            ["runtime evidence missing"],
        )

    problems: List[str] = []
    window_checks = payload.get("window_checks") or {}
    accessibility_checks = payload.get("accessibility_checks") or {}
    digests = {
        Path(str(entry.get("file"))).name: entry.get("sha256")
        for entry in (payload.get("captures") or [])
        if isinstance(entry, dict) and entry.get("file")
    }

    verified_windows: Dict[str, Any] = {}
    for size in ("960x640", "1180x760", "2560x1600", "2400x900"):
        entry = window_checks.get(size)
        if not entry:
            problems.append(f"window {size} not captured")
            verified_windows[size] = None
            continue
        digest = _verified_capture(
            entry.get("capture"), evidence_dir, digests, problems, f"window {size}"
        )
        if entry.get("text_legible") is not True:
            problems.append(f"window {size} text legibility not confirmed")
        if entry.get("identity_visible") is not True:
            problems.append(f"window {size} identity motif not confirmed")
        verified_windows[size] = {
            "capture": Path(str(entry.get("capture"))).name,
            "capture_sha256": digest,
            "text_legible": entry.get("text_legible"),
            "identity_visible": entry.get("identity_visible"),
            "notes": entry.get("notes"),
        }

    verified_states: Dict[str, Any] = {}
    for state in ("Increased Contrast", "Reduce Transparency"):
        entry = accessibility_checks.get(state)
        if not entry:
            problems.append(f"accessibility state {state} not captured")
            verified_states[state] = None
            continue
        digest = _verified_capture(
            entry.get("capture"), evidence_dir, digests, problems, f"accessibility {state}"
        )
        if entry.get("text_legible") is not True or entry.get("artwork_readable") is not True:
            problems.append(f"accessibility state {state} not confirmed usable")
        verified_states[state] = {
            "capture": Path(str(entry.get("capture"))).name,
            "capture_sha256": digest,
            "text_legible": entry.get("text_legible"),
            "artwork_readable": entry.get("artwork_readable"),
            "notes": entry.get("notes"),
        }

    # Contrast is recomputed from the named capture regions. A declared ratio in the evidence
    # file is ignored, so a number cannot be asserted into the record.
    computed: Dict[str, List[Dict[str, Any]]] = {}
    for index, measurement in enumerate((payload.get("contrast") or {}).get("measurements") or []):
        kind = measurement.get("kind")
        label = f"contrast measurement {index}"
        if kind not in ("text_primary", "important_copy"):
            problems.append(f"{label} has an unsupported kind {kind!r}")
            continue
        capture = measurement.get("capture")
        if _verified_capture(capture, evidence_dir, digests, problems, label) is None:
            continue
        region = measurement.get("region")
        if not (
            isinstance(region, list)
            and len(region) == 4
            and all(isinstance(value, int) for value in region)
        ):
            problems.append(f"{label} needs an integer region [x, y, width, height]")
            continue
        image = load_rgb(evidence_dir / str(capture))
        x, y, width, height = region
        if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > image.width or y + height > image.height:
            problems.append(f"{label} region falls outside the capture")
            continue
        ratio = round(
            _wcag_contrast_ratio(np.asarray(image.crop((x, y, x + width, y + height)))), 2
        )
        computed.setdefault(kind, []).append(
            {
                "kind": kind,
                "capture": Path(str(capture)).name,
                "region": region,
                "ratio": ratio,
            }
        )

    primary = min((entry["ratio"] for entry in computed.get("text_primary", [])), default=None)
    important = min((entry["ratio"] for entry in computed.get("important_copy", [])), default=None)
    if primary is None:
        problems.append("no recomputable primary-text contrast measurement was provided")
    elif primary < CONTRAST_THRESHOLDS["text_primary_min"]:
        problems.append(
            f"primary text contrast {primary}:1 is below the {CONTRAST_THRESHOLDS['text_primary_min']}:1 minimum"
        )
    if important is None:
        problems.append("no recomputable important-copy contrast measurement was provided")
    elif important < CONTRAST_THRESHOLDS["important_long_copy_target"]:
        problems.append(
            f"important copy contrast {important}:1 is below the "
            f"{CONTRAST_THRESHOLDS['important_long_copy_target']}:1 target"
        )

    record = dict(payload)
    record["wide_anchor_under_test"] = expected_anchor
    record["window_checks"] = verified_windows
    record["accessibility_checks"] = verified_states
    record["contrast"] = {
        "method": (
            "Recomputed from the named capture regions by this tool: WCAG 2.2 relative luminance, "
            "p95 percentile as text ink against p05 as the backing surface. Any ratio declared in "
            "the evidence file is ignored."
        ),
        "measurements": [entry for group in computed.values() for entry in group],
        "text_primary_contrast_min": primary,
        "important_copy_contrast_min": important,
        "thresholds": CONTRAST_THRESHOLDS,
    }
    record["notes"] = [
        "Captured from the real macOS window surface; every capture is re-hashed against the "
        "recorded digest before its claims are accepted.",
        "The wide header anchor under test is the one recorded in the derivative report.",
    ]
    if problems:
        record["unmet_requirements"] = problems
        return "PENDING_RUNTIME_QA", record, problems
    return "PASSED", record, []


def _catalog_evidence(catalog_root: Path | None, asset_names: List[str]) -> Dict[str, Any]:
    if catalog_root is None:
        return {"status": "NOT_CHECKED"}
    entries: List[Dict[str, Any]] = []
    for asset_name in asset_names:
        imageset = catalog_root / f"{asset_name}.imageset"
        if not imageset.is_dir():
            return {"status": "MISSING", "missing": asset_name}
        manifest = load_json(imageset / "Contents.json")
        for entry in manifest.get("images", []):
            filename = entry.get("filename")
            if not filename:
                continue
            payload = imageset / filename
            if not payload.is_file():
                return {
                    "status": "MISSING",
                    "missing": f"{asset_name}.imageset/{filename}",
                }
            with Image.open(payload) as opened:
                has_icc_profile = bool(opened.info.get("icc_profile"))
                width, height = opened.size
            entries.append(
                {
                    "asset_name": asset_name,
                    "payload": payload.name,
                    "width": width,
                    "height": height,
                    "sha256": sha256_of(payload),
                    "icc_profile": "sRGB IEC61966-2.1" if has_icc_profile else None,
                }
            )
    return {"status": "VERIFIED", "payloads": entries}


def command_record(args: argparse.Namespace) -> int:
    scene = SCENES[args.task]
    work_dir = Path(args.work_dir)
    asset_name = scene["asset_name"]
    wide_name = f"{asset_name}.wide"
    anchor = scene["wide_anchor"]
    reviewed_at = args.reviewed_at or datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%d")

    crop_report, crop_path = _verified_stage(work_dir, args.task, "crop")
    sr_report, _ = _verified_stage(work_dir, args.task, "sr", crop_report["output"]["sha256"])
    grade_report, _ = _verified_stage(work_dir, args.task, "grade", sr_report["output"]["sha256"])
    master_report, master_path = _verified_stage(
        work_dir, args.task, "master", grade_report["output"]["sha256"]
    )
    master_sha = master_report["output"]["sha256"]

    fidelity_report = load_json(work_dir / f"{args.task}_report_fidelity.json")
    _require(
        fidelity_report["candidate"]["sha256"] == master_sha,
        "the fidelity report does not describe the master on disk",
    )
    _require(fidelity_report["verdict"] == "passed", "fidelity against the approved source failed")
    _require(
        fidelity_report["reference"]["sha256"] == crop_report["output"]["sha256"],
        "the fidelity report does not compare against the locked source crop",
    )

    derivative_report = load_json(work_dir / f"{args.task}_report_derivatives.json")
    _require(
        derivative_report["input"]["sha256"] == master_sha,
        "the derivatives were not produced from this master",
    )
    _require(
        derivative_report.get("wideAnchor") == anchor,
        f"derivative wide anchor is {derivative_report.get('wideAnchor')!r}, "
        f"scene requires {anchor!r}",
    )
    runtime_path = work_dir / Path(derivative_report["runtime"]["path"]).name
    wide_path = work_dir / Path(derivative_report["wide"]["path"]).name
    for path, key in ((runtime_path, "runtime"), (wide_path, "wide")):
        _require(path.is_file(), f"missing derivative {path.name}")
        _require(
            sha256_of(path) == derivative_report[key]["sha256"],
            f"{key} derivative bytes do not match its report",
        )
    runtime_size = derivative_report["runtime"]["size"]
    wide_size = derivative_report["wide"]["size"]
    _require(
        (runtime_size["width"], runtime_size["height"]) == (2560, 1600),
        "the runtime derivative is not 2560x1600",
    )
    _require(
        (wide_size["width"], wide_size["height"]) == (2400, 900),
        "the wide derivative is not 2400x900",
    )

    source_sha = crop_report["input"]["sha256"]
    if args.source:
        source_path = Path(args.source)
        _require(source_path.is_file(), f"missing approved source {source_path}")
        source_sha = sha256_of(source_path)
        _require(
            source_sha == crop_report["input"]["sha256"],
            "the approved source on disk no longer matches the source the crop was made from",
        )

    g3_status, g3_record = _evaluate_inspection(
        _inspection_for(load_optional_json(args.inspection), args.task)
    )
    runtime_evidence_path = Path(args.runtime_evidence) if args.runtime_evidence else None
    g5_status, g5_record, runtime_problems = _evaluate_runtime(
        load_optional_json(args.runtime_evidence),
        anchor,
        runtime_evidence_path.parent if runtime_evidence_path else Path("."),
    )

    runtime_sha = derivative_report["runtime"]["sha256"]
    wide_sha = derivative_report["wide"]["sha256"]
    crop_sha = crop_report["output"]["sha256"]

    identity = {
        "rule": RED_DOMINANT_RULE,
        "master_red_dominant_pct": red_dominant_fraction(master_path),
        "wide_red_dominant_pct": red_dominant_fraction(wide_path),
    }
    identity["wide_vs_master_ratio"] = round(
        identity["wide_red_dominant_pct"] / max(identity["master_red_dominant_pct"], 1e-6), 3
    )
    identity["wide_retains_identity"] = identity["wide_vs_master_ratio"] >= 0.6

    catalog = _catalog_evidence(
        Path(args.catalog_root) if args.catalog_root else None, [asset_name, wide_name]
    )
    if catalog.get("status") == "VERIFIED":
        by_asset = {entry["asset_name"]: entry for entry in catalog["payloads"]}
        _require(
            asset_name in by_asset and wide_name in by_asset,
            "the Asset Catalog payload set is incomplete",
        )
        catalog["matches_derivatives"] = (
            by_asset[asset_name]["sha256"] == runtime_sha
            and by_asset[wide_name]["sha256"] == wide_sha
        )
        _require(
            catalog["matches_derivatives"],
            "the Asset Catalog payload is not byte-identical to the finished derivative",
        )

    # The verdict is derived from the whole gate set, not from a hand-picked subset: a scene whose
    # wide crop lost its identity motif must not be approvable just because G3 and G5 are green.
    gate_statuses = {
        "G0_semantic": "PASSED",
        "G1_canon_atmosphere": "PASSED",
        "G2_composition": (
            "PASSED"
            if identity["wide_retains_identity"] and g5_status == "PASSED"
            else "PENDING_RUNTIME_QA"
        ),
        "G3_structure": g3_status,
        "G4_production": (
            "PASSED" if catalog.get("status") == "VERIFIED" else "PENDING_CATALOG_INGESTION"
        ),
        "G5_runtime": g5_status,
    }
    all_gates_passed = all(status == "PASSED" for status in gate_statuses.values())
    verdict = "PASSED" if all_gates_passed else "PRODUCTION_EVIDENCE_PENDING"
    status = (
        "MACOS_FINISHING_COMPLETE_RUNTIME_QA_PASSED"
        if all_gates_passed
        else "MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING"
    )

    production_evidence = {
        "master": {
            "width": MASTER_SIZE[0],
            "height": MASTER_SIZE[1],
            "sha256": master_sha,
            "pixel_sha256": pixel_sha256(master_path),
            "photometry": photometry(master_path),
        },
        "approved_source_crop": {
            "width": crop_report["output"]["width"],
            "height": crop_report["output"]["height"],
            "sha256": crop_sha,
            "photometry": photometry(crop_path),
        },
        "photometry_rules": {
            "shadow_clip": SHADOW_CLIP_RULE,
            "highlight_clip": HIGHLIGHT_CLIP_RULE,
        },
        "identity_survival": identity,
        "fidelity": {
            "mean_absolute_difference_0_255": fidelity_report["mean_absolute_difference_0_255"],
            "luminance_correlation": fidelity_report["luminance_correlation"],
            "edge_structure_correlation": fidelity_report["edge_structure_correlation"],
            "verdict": fidelity_report["verdict"],
        },
        "catalog": catalog,
        "production_host": "Apple Silicon macOS workstation; MPS super-resolution, deterministic tools",
    }

    qa_path = Path(args.qa)
    qa_base = load_json(qa_path) if qa_path.is_file() else {}
    base_g0 = ((qa_base.get("gates") or {}).get("G0_semantic")) or {}
    base_g1 = ((qa_base.get("gates") or {}).get("G1_canon_atmosphere")) or {}

    g0_update: Dict[str, Any] = {
        "status": gate_statuses["G0_semantic"],
        "status_basis": scene["g0_basis"],
        "approval_reference": SOURCE_APPROVAL_REFERENCE,
    }
    if "primary_read" not in base_g0:
        # A gate record is only reviewable if it says what was read. W1's original art-direction
        # reading is kept as written; the other scenes get the reading taken from the finished
        # master, clearly attributed, with the unscored criteria stated instead of implied.
        g0_update.update(
            {
                "primary_read": scene["g0_primary_read"],
                "secondary_read": scene["g0_secondary_read"],
                "read_recorded_by": (
                    "world-scene finishing review: direct inspection of the finished 4096x2560 "
                    "master"
                ),
                "scored_criteria": None,
                "unscored_criteria_note": UNSCORED_CRITERIA_NOTE,
            }
        )

    g1_update: Dict[str, Any] = {
        "status": gate_statuses["G1_canon_atmosphere"],
        "status_basis": scene["g1_basis"],
        "approval_reference": SOURCE_APPROVAL_REFERENCE,
    }
    if "era_credibility_5" not in base_g1:
        g1_update.update(
            {
                "world_contradictions": [],
                "world_contradictions_basis": (
                    "these images assert no Canon architecture, ownership or cosmology; the "
                    "source-direction approval records the metaphor framing explicitly"
                ),
                "scored_criteria": None,
                "unscored_criteria_note": UNSCORED_CRITERIA_NOTE,
            }
        )
    if scene.get("g1_superseded_criteria"):
        g1_update["superseded_criteria"] = scene["g1_superseded_criteria"]

    qa_updates = {
        "artwork_id": scene["artwork_id"],
        "task_id": args.task,
        "status": status,
        "final_verdict": verdict,
        "gates": {
            "G0_semantic": g0_update,
            "G1_canon_atmosphere": g1_update,
            "G2_composition": {
                # G2 covers both the source-frame survival and the real runtime framing.
                "status": gate_statuses["G2_composition"],
                "source_crop_rect_pixels": crop_report["rect_pixels"],
                "source_crop_output": {
                    "width": crop_report["output"]["width"],
                    "height": crop_report["output"]["height"],
                    "sha256": crop_sha,
                },
                "wide_anchor": anchor,
                "wide_master_crop_pixels": wide_crop_rect(anchor),
                "crop_reference": (
                    CROP_REFERENCE if args.task in ("W1", "W3", "W4") else ADDITIONAL_CROP_REFERENCE
                ),
                "wide_crop_survival_pass": "PASS" if identity["wide_retains_identity"] else "FAIL",
                "runtime_crop_survival_pass": g5_status == "PASSED",
                "identity_survival": identity,
            },
            "G3_structure": dict({"status": g3_status}, **g3_record),
            "G4_production": {
                "status": gate_statuses["G4_production"],
                "master_dimensions": {"width": MASTER_SIZE[0], "height": MASTER_SIZE[1]},
                "runtime_dimensions": {
                    asset_name: {"width": 2560, "height": 1600},
                    wide_name: {"width": 2400, "height": 900},
                },
                "color_profile": "sRGB IEC61966-2.1 (explicit ICC on every finishing output)",
                "format": "PNG",
                "sha256": {asset_name: runtime_sha, wide_name: wide_sha},
                "master_sha256": master_sha,
                "asset_names": [asset_name, wide_name],
                "derivative_tool": DERIVATIVE_TOOL,
                "catalog": catalog,
            },
            "G5_runtime": dict(
                {
                    "status": g5_status,
                    "window_sizes": ["960x640", "1180x760", "2560x1600", "2400x900"],
                    "accessibility_states": ["Increased Contrast", "Reduce Transparency"],
                },
                **g5_record,
            ),
        },
        "production_evidence": production_evidence,
        "reviewers": [
            "interactive_art_direction_approval",
            "macos_finishing_pipeline_finish_world_artwork.py",
        ],
        "reviewed_at": reviewed_at,
    }
    write_json(qa_path, merge_records(qa_base, qa_updates))

    contract_crop_sha = None
    if scene["contract"] and Path(scene["contract"]).is_file():
        contract_crop_sha = load_json(Path(scene["contract"])).get("composition", {}).get(
            "source_lock", {}
        ).get("cropped_sha256")

    provenance_path = Path(args.provenance)
    provenance_base = load_json(provenance_path) if provenance_path.is_file() else {}
    provenance_updates = {
        "artwork_id": scene["artwork_id"],
        "status": (
            "APPROVED" if all_gates_passed else "SELECTED_SOURCE_LOCKED_MACOS_FINISHING_PENDING"
        ),
        "source": {
            "source_id": scene["source_id"],
            "sha256": source_sha,
            "native_width": crop_report["input"]["width"],
            "native_height": crop_report["input"]["height"],
        },
        "postprocess": [
            {
                "stage": "server_exact_16_10_crop",
                "operation": "crop_1px_each_edge",
                "output_width": crop_report["output"]["width"],
                "output_height": crop_report["output"]["height"],
                "contract_declared_container_sha256": contract_crop_sha,
                "sha256": crop_sha,
                "pixel_sha256": pixel_sha256(crop_path),
                "container_note": (
                    "PNG container hashes are encoder dependent, so a byte mismatch against a hash "
                    "produced by a different encoder is expected and is not evidence of a different "
                    "crop. pixel_sha256 identifies the decoded pixels independently of container "
                    "framing; the working crop is produced deterministically from the locked source "
                    "and the contract crop rectangle."
                ),
                "status": "COMPLETE",
            },
            {
                "stage": "macos_local_structural_repair",
                "status": "NOT_REQUIRED",
                "basis": g3_record.get("method") or "no structural inspection record attached",
                "generative_operations": False,
            },
            {
                "stage": "macos_primary_super_resolution",
                "status": "COMPLETE",
                "engine": sr_report["method"],
                "device": sr_report["device"],
                "weights": sr_report["weights"],
                "weights_sha256": sr_report["weights_sha256"],
                "tile": sr_report["tile"],
                "overlap": sr_report["overlap"],
                "scale": sr_report["scale"],
                "downstream_downsample": sr_report["downstream_downsample"],
                "output_width": sr_report["output"]["width"],
                "output_height": sr_report["output"]["height"],
                "sha256": sr_report["output"]["sha256"],
                "passes": 1,
            },
            {
                "stage": "macos_material_restoration_and_color_luminance_grade",
                "status": "COMPLETE",
                "profile": grade_report["profile"],
                "parameters": grade_report["parameters"],
                "generative": grade_report["generative"],
                "output_width": grade_report["output"]["width"],
                "output_height": grade_report["output"]["height"],
                "sha256": grade_report["output"]["sha256"],
            },
            {
                "stage": "oversample_downsample_to_4096x2560_master",
                "status": "COMPLETE",
                "operation": master_report["operation"],
                "resample": master_report["resample"],
                "output_width": master_report["output"]["width"],
                "output_height": master_report["output"]["height"],
                "sha256": master_sha,
                "pixel_sha256": production_evidence["master"]["pixel_sha256"],
            },
            {
                "stage": "deterministic_derivatives",
                "status": "COMPLETE",
                "tool": DERIVATIVE_TOOL,
                "wide_crop_anchor": anchor,
                "wide_master_crop_pixels": wide_crop_rect(anchor),
                "derivatives": [
                    {
                        "asset_name": asset_name,
                        "width": runtime_size["width"],
                        "height": runtime_size["height"],
                        "sha256": runtime_sha,
                        "derivation": "full_frame_downsample_from_master",
                    },
                    {
                        "asset_name": wide_name,
                        "width": wide_size["width"],
                        "height": wide_size["height"],
                        "sha256": wide_sha,
                        "derivation": (
                            f"{anchor}_aligned_{MASTER_SIZE[0]}x{WIDE_HEIGHT}_crop_from_master_"
                            "then_downsample"
                        ),
                        "crop_anchor": anchor,
                    },
                ],
            },
            {
                "stage": "runtime_qa",
                "status": g5_status,
                "unmet_requirements": runtime_problems,
                "evidence": f"docs/05_UI/artwork/qa/{qa_path.name}",
            },
        ],
        "master": {
            "path": master_path.name,
            "width": MASTER_SIZE[0],
            "height": MASTER_SIZE[1],
            "format": "PNG",
            "color_profile": "sRGB IEC61966-2.1 (explicit ICC)",
            "runtime_loadable": False,
            "sha256": master_sha,
            "pixel_sha256": production_evidence["master"]["pixel_sha256"],
        },
        "derivatives": [
            {
                "asset_name": asset_name,
                "width": 2560,
                "height": 1600,
                "sha256": runtime_sha,
                "derivation": "full_frame_downsample_from_master",
                "catalog_payload_verified": catalog.get("matches_derivatives", False),
            },
            {
                "asset_name": wide_name,
                "width": 2400,
                "height": 900,
                "sha256": wide_sha,
                "derivation": (
                    f"{anchor}_aligned_{MASTER_SIZE[0]}x{WIDE_HEIGHT}_crop_from_master_then_downsample"
                ),
                "crop_anchor": anchor,
                "catalog_payload_verified": catalog.get("matches_derivatives", False),
            },
        ],
        "qa_record": f"docs/05_UI/artwork/qa/{qa_path.name}",
        "production_evidence": production_evidence,
        "approved_at": reviewed_at if all_gates_passed else None,
        "approved_basis": (
            "Locked approved source direction + byte-verified macOS finishing chain + G0-G5 "
            "evidence with captured runtime checks"
        )
        if all_gates_passed
        else None,
    }
    if provenance_base.get("copyright_note") is None:
        provenance_updates["copyright_note"] = (
            "AI-assisted original artwork; no official commercial asset copying."
        )
    write_json(provenance_path, merge_records(provenance_base, provenance_updates))

    report(
        {
            "task": args.task,
            "artwork_id": scene["artwork_id"],
            "final_verdict": verdict,
            "gates": {
                "G2": qa_updates["gates"]["G2_composition"]["status"],
                "G3": g3_status,
                "G4": qa_updates["gates"]["G4_production"]["status"],
                "G5": g5_status,
            },
            "master_sha256": master_sha,
            "derivatives": {asset_name: runtime_sha, wide_name: wide_sha},
            "identity_survival": identity,
            "runtime_problems": runtime_problems,
            "qa": str(qa_path),
            "provenance": str(provenance_path),
        }
    )
    if args.require_complete and not all_gates_passed:
        return 1
    return 0


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    crop = sub.add_parser("crop", help="exact contract crop of an approved source")
    crop.add_argument("--input", required=True)
    crop.add_argument("--output", required=True)
    crop.add_argument("--rect", required=True, help="left,top,right,bottom in pixels")
    crop.add_argument("--width", type=int)
    crop.add_argument("--height", type=int)
    crop.set_defaults(func=command_crop)

    repair = sub.add_parser("repair", help="masked local structural repair by region copy")
    repair.add_argument("--input", required=True)
    repair.add_argument("--output", required=True)
    repair.add_argument("--ops", required=True, help="JSON list of from/to rectangles")
    repair.set_defaults(func=command_repair)

    sr = sub.add_parser("sr", help="single Real-ESRGAN x4 pass on Apple Silicon")
    sr.add_argument("--input", required=True)
    sr.add_argument("--output", required=True)
    sr.add_argument("--weights", required=True)
    sr.add_argument("--tile", type=int, default=512)
    sr.add_argument("--overlap", type=int, default=32)
    sr.add_argument("--downstream", help="planned downsample target, recorded for provenance")
    sr.set_defaults(func=command_sr)

    grade = sub.add_parser("grade", help="material restoration and colour-luminance grade")
    grade.add_argument("--input", required=True)
    grade.add_argument("--output", required=True)
    grade.add_argument("--profile", default="subtle-illustration-v1")
    grade.set_defaults(func=command_grade)

    master = sub.add_parser("master", help="controlled downsample to the Production Master")
    master.add_argument("--input", required=True)
    master.add_argument("--output", required=True)
    master.add_argument("--width", type=int, default=4096)
    master.add_argument("--height", type=int, default=2560)
    master.set_defaults(func=command_master)

    fidelity = sub.add_parser("fidelity", help="compare a finished image with the approved source")
    fidelity.add_argument("--reference", required=True)
    fidelity.add_argument("--candidate", required=True)
    fidelity.set_defaults(func=command_fidelity)

    surface = sub.add_parser(
        "surface",
        help="verify that a window capture really contains the shipped asset",
    )
    surface.add_argument("--capture", required=True, help="window screenshot PNG")
    surface.add_argument("--asset", required=True, help="shipped derivative PNG")
    surface.add_argument("--search-width", type=int, default=1600)
    surface.add_argument("--min-scale", type=float, default=0.12)
    surface.add_argument("--max-scale", type=float, default=1.0)
    surface.add_argument("--steps", type=int, default=26)
    surface.add_argument("--min-score", type=float, default=0.45)
    surface.set_defaults(func=command_surface)

    record = sub.add_parser(
        "record",
        help="assemble the QA / provenance records from the verified finishing chain",
    )
    record.add_argument("--task", required=True, choices=sorted(SCENES))
    record.add_argument("--work-dir", required=True)
    record.add_argument("--source", help="locked approved source PNG, re-hashed as evidence")
    record.add_argument("--catalog-root", help="Assets.xcassets root that received the derivatives")
    record.add_argument("--inspection", help="G3 structural inspection record (JSON)")
    record.add_argument("--runtime-evidence", help="G5 window / accessibility evidence (JSON)")
    record.add_argument("--qa", required=True)
    record.add_argument("--provenance", required=True)
    record.add_argument("--reviewed-at", default=None, help="ISO date, defaults to today (UTC)")
    record.add_argument(
        "--require-complete",
        action="store_true",
        help="exit non-zero unless every gate reaches PASSED",
    )
    record.set_defaults(func=command_record)

    return parser


def main(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
