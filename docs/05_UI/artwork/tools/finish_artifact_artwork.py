#!/usr/bin/env python3
"""Deterministic macOS finishing pipeline for approved Artifact object sources.

The World / Scene path has its own 4096x2560 horizontal pipeline in
``finish_world_artwork.py``. An Artifact object is a square, single-object image with a
different runtime contract, so it gets its own explicit order instead of being squeezed
through the scene stages:

1. ``square-crop`` — deterministic centred 1:1 safety crop of the approved source (never a
   stretch, never an upscale);
2. ``sr``          — one Real-ESRGAN pass to the oversampled working image (Apple Silicon MPS);
3. ``grade``       — material / colour-luminance grade at working resolution;
4. ``master``      — controlled downsample to the 2048x2048 Artifact Master;
5. ``derive``      — 1024x1024 ``.detail`` and 512x512 ``.thumbnail`` from that same master;
6. ``fidelity``    — evidence that the master still carries the approved source structure;
7. ``record``      — assemble the QA and provenance records from the verified stage bytes.
8. ``contact-sheet`` — 96x96 preview sheet for the human legibility read.

Every output is written as PNG with an explicit sRGB ICC profile. The approved sources carry no
ICC tag, so the tagging is part of the fix rather than a cosmetic detail.

The source images are lower resolution than the 2048x2048 Master baseline (the widest source is
1371px on its short edge), so the master is recorded as a finished / super-resolved Master. It is
never described as a native 2048x2048 generation.

``record`` is fail-closed: it refuses to write a record unless every stage output is present and
byte-identical to its stage report, the fidelity verdict passed, the derivatives came from that
same master at the contract sizes, the Asset Catalog payloads match the derivatives, and each
gate that is marked ``PASSED`` has its own evidence. A missing evidence file is an open gate,
never a pass and never a crash.

Requirements: ``torch`` (with MPS), ``numpy`` and ``Pillow``. The Real-ESRGAN weights are not
committed; pass ``--weights`` and the SHA256 actually used is recorded in the provenance record.

Example:

    python3 docs/05_UI/artwork/tools/finish_artifact_artwork.py square-crop \
      --input A01_ARRODES_MIRROR/source.png --output work/A01_01_square_1254x1254.png

    python3 docs/05_UI/artwork/tools/finish_artifact_artwork.py record \
      --task A01 --work-dir docs/05_UI/artwork/workbench/artifacts/A01_ARRODES_MIRROR \
      --inspection docs/05_UI/artwork/qa/G3_artifact_structural_inspection_2026-09-18.json \
      --qa docs/05_UI/artwork/qa/A01_ARRODES_MIRROR.qa.json \
      --provenance docs/05_UI/artwork/provenance/A01_ARRODES_MIRROR.provenance.json

    # 工作目录长期归宿是 workbench/（本机资产，不入库）：母版必须留在项目目录内，
    # 不能只放在 .hacf/tmp 之类的临时目录，见 ../Asset_Storage_Policy_v1.0.md。
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

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
DEFAULT_MANIFEST = REPO_ROOT / "docs/05_UI/artwork/delivery/approved_sources.json"
DEFAULT_CANON_EVIDENCE = REPO_ROOT / "docs/05_UI/artwork/delivery/canon_evidence.json"

# 美术方向对「装饰性铭刻文字」的批准：产品「无文字画面」政策不覆盖类符文铭刻，但例外必须来自
# 一份可审计、可复算的决定文件——工具不做默认放行，决定没覆盖到就保持 gate 打开。
DEFAULT_TEXT_DECISION = REPO_ROOT / "docs/05_UI/artwork/contracts/art_direction_text_decision.json"
DECORATIVE_TEXT_DECISION_KIND = "ACCEPT_DECORATIVE_INSCRIPTIONAL_TEXT"
DECORATIVE_TEXT_DEFECT_PREFIX = "baked_readable_text"
PROVENANCE_PENDING_STATUS = (
    "SELECTED_SOURCE_LOCKED_MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING"
)

# 运行时证据的复算原语（截图摘要校验、WCAG 对比度、归一化互相关）只有一份实现：世界/场景
# 工具已经把它们用在 W1..W6 的 G5 上。神器记录复用同一份，阈值与算法不会在两套交付之间漂移。
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import finish_world_artwork as world_tool  # noqa: E402
DEFAULT_REGISTRY = REPO_ROOT / "macos-app/WorldOfMysteries/DesignSystem/WOMArtworkAsset.swift"

MASTER_SIZE = (2048, 2048)
DETAIL_SIZE = (1024, 1024)
THUMBNAIL_SIZE = (512, 512)
GRADE_PROFILE_NAME = "subtle-illustration-v1"
FIDELITY_THRESHOLDS = {
    "mean_absolute_difference_max": 12.0,
    "luminance_correlation_min": 0.97,
    "edge_structure_correlation_min": 0.80,
}


# --------------------------------------------------------------------------------------
# Artifact registry: the manifest stays the single source of truth
# --------------------------------------------------------------------------------------


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def artifact_targets(manifest_path: Path = DEFAULT_MANIFEST) -> Dict[str, Dict[str, Any]]:
    """Key the 15 Artifact targets by work task id (A01..A15)."""

    manifest = load_json(manifest_path)
    targets = manifest["artifact_targets"]
    if [t["order"] for t in targets] != list(range(1, 16)):
        raise SystemExit("manifest artifact order drifted; refusing to guess artifact identities")
    result: Dict[str, Dict[str, Any]] = {}
    for target in targets:
        task = f"A{target['order']:02d}"
        if not target.get("source_id"):
            raise SystemExit(
                f"{task} has no approved source bound in the manifest; finishing needs a source"
            )
        result[task] = dict(target)
    return result


# --------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgb(path: Path) -> Image.Image:
    """Decode to RGB and detach from the file handle, so a decoded image owns no open file."""

    with Image.open(path) as image:
        if image.mode != "RGB":
            return image.convert("RGB")
        return image.copy()


_SRGB_PROFILE_BYTES: bytes | None = None

# LittleCMS stamps the ICC profile date/time tag with the current wall clock when the profile is
# generated, so the seconds field alone made two identical finishing runs produce different PNG
# bytes. The tag is normalised to a fixed instant here: every finishing output then depends only
# on its input bytes and the recorded parameters.
FIXED_PROFILE_DATE = (2026, 1, 1, 0, 0, 0)


def srgb_profile_bytes() -> bytes:
    """Explicit sRGB profile, so every finishing output is verifiable instead of untagged."""

    global _SRGB_PROFILE_BYTES
    if _SRGB_PROFILE_BYTES is None:
        import struct

        from PIL import ImageCms

        profile = bytearray(
            ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        )
        if len(profile) < 100 or bytes(profile[36:40]) != b"acsp":
            raise SystemExit("generated sRGB profile is not a valid ICC profile header")
        profile[24:36] = struct.pack(">6H", *FIXED_PROFILE_DATE)
        _SRGB_PROFILE_BYTES = bytes(profile)
    return _SRGB_PROFILE_BYTES


def save_png(image: Image.Image, path: Path) -> None:
    path = Path(path)
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
        "path": Path(path).name,
        "width": image.width,
        "height": image.height,
        "sha256": sha256_of(Path(path)),
    }


def pixel_sha256(path: Path) -> str:
    """Container-independent identity: the decoded pixel stream, not the PNG framing."""

    return hashlib.sha256(load_rgb(path).tobytes()).hexdigest()


def _luminance(array: np.ndarray) -> np.ndarray:
    return array @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _edge_map(luminance: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(luminance)
    return np.sqrt(gx * gx + gy * gy)


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


# --------------------------------------------------------------------------------------
# 1. Deterministic centred 1:1 safety crop
# --------------------------------------------------------------------------------------


def square_crop_rect(width: int, height: int, size: int | None = None) -> Tuple[int, int, int, int]:
    """Largest centred square, or an explicit square edge if it fits.

    Sources are cropped, never stretched and never padded with invented content. The rectangle is
    a pure function of the decoded size, so the same source always produces the same crop.
    """

    edge = min(width, height) if size is None else int(size)
    if edge <= 0:
        raise ValueError("square crop size must be positive")
    if edge > min(width, height):
        raise ValueError(
            f"refusing to crop a {width}x{height} source into {edge}x{edge}: "
            "the square would need to be invented rather than cropped"
        )
    left = (width - edge) // 2
    top = (height - edge) // 2
    return (left, top, left + edge, top + edge)


def command_square_crop(args: argparse.Namespace) -> int:
    source = load_rgb(Path(args.input))
    rect = square_crop_rect(source.width, source.height, args.size)
    cropped = source.crop(rect)
    save_png(cropped, Path(args.output))
    report(
        {
            "operation": "deterministic_centred_square_safety_crop",
            "generative": False,
            "upscale": False,
            "rect_pixels": list(rect),
            "removed_pixels": {
                "left": rect[0],
                "top": rect[1],
                "right": source.width - rect[2],
                "bottom": source.height - rect[3],
            },
            "input": describe(source, Path(args.input)),
            "output": describe(cropped, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 2. Single conservative super resolution pass (Real-ESRGAN x4plus, MPS)
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
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x

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
            state, source = payload[key], key
            break
    else:
        state, source = payload, "state_dict"
    cleaned = {name.replace("module.", "", 1): value for name, value in state.items()}
    model.load_state_dict(cleaned, strict=True)
    return source


def command_sr(args: argparse.Namespace) -> int:
    import torch

    source = load_rgb(Path(args.input))
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = _build_rrdbnet().to(device).eval()
    weight_source = _load_weights(model, Path(args.weights))

    tile, overlap, scale = int(args.tile), int(args.overlap), 4
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
                result = np.clip(output.squeeze(0).permute(1, 2, 0).float().cpu().numpy(), 0.0, 1.0)

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
                canvas[y0 : y0 + result.shape[0], x0 : x0 + result.shape[1]] += result * blend
                weights[y0 : y0 + result.shape[0], x0 : x0 + result.shape[1]] += blend

    weights = np.where(weights <= 0.0, 1.0, weights)
    finished = np.clip(canvas / weights, 0.0, 1.0)
    working = Image.fromarray((finished * 255.0 + 0.5).astype(np.uint8), mode="RGB")
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
            "passes": 1,
            "input": describe(source, Path(args.input)),
            "output": describe(working, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 3. Material restoration + colour / luminance grade
# --------------------------------------------------------------------------------------

# Grade profile "subtle-illustration-v1" — identical numbers to the World / Scene path so the
# whole Premium Art set shares one reproducible look. Every value is part of the record.
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


def _edge_limited_unsharp(
    values: np.ndarray, radius: float, amount: float, noise_floor: float
) -> np.ndarray:
    """Unsharp mask in float space so the boost cannot clip either end of the range.

    Pillow's ``UnsharpMask`` operates on 8-bit data and clips, which crushes night shadows. Here
    the detail signal is attenuated where there is no real edge (noise floor) and where the pixel
    is already near black or near white.
    """

    blurred = _gaussian_like_blur(values, radius)
    detail = values - blurred
    gate = np.clip(np.abs(detail) / noise_floor, 0.0, 1.0) if noise_floor > 0 else np.ones_like(detail)
    headroom = np.clip(1.0 - np.abs(2.0 * values - 1.0) ** 2, 0.0, 1.0)
    return values + amount * detail * gate * headroom


def _soft_clip(values: np.ndarray, knee: float) -> np.ndarray:
    """Compress the top of the range instead of clipping bright metal into a flat white blob."""

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
    if args.profile != GRADE_PROFILE_NAME:
        raise SystemExit(f"unknown grade profile: {args.profile}")
    profile = dict(GRADE_PROFILE)

    values = _grade_array(np.asarray(source).astype(np.float32) / 255.0, profile)
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
# 4. Controlled downsample to the Artifact Master
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
            "operation": "controlled_downsample_to_artifact_master",
            "resample": "Lanczos",
            "input": describe(source, Path(args.input)),
            "output": describe(master, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 5. Deterministic same-master derivatives
# --------------------------------------------------------------------------------------


def command_derive(args: argparse.Namespace) -> int:
    master = load_rgb(Path(args.master))
    if master.size != MASTER_SIZE:
        raise SystemExit(
            f"derivatives must come from the {MASTER_SIZE[0]}x{MASTER_SIZE[1]} master, "
            f"got {master.width}x{master.height}"
        )

    outputs: List[Dict[str, Any]] = []
    for size, asset_name, output, derivation in (
        (DETAIL_SIZE, args.detail_asset, args.detail_output, "full_frame_downsample_from_master"),
        (
            THUMBNAIL_SIZE,
            args.thumbnail_asset,
            args.thumbnail_output,
            "full_frame_downsample_from_master",
        ),
    ):
        derived = master.resize(size, resample=Image.LANCZOS)
        save_png(derived, Path(output))
        outputs.append(
            {
                "asset_name": asset_name,
                "path": Path(output).name,
                "width": derived.width,
                "height": derived.height,
                "sha256": sha256_of(Path(output)),
                "derivation": derivation,
            }
        )

    report(
        {
            "operation": "deterministic_same_master_derivatives",
            "tool": "docs/05_UI/artwork/tools/finish_artifact_artwork.py",
            "generative": False,
            "independent_regeneration": False,
            "resample": "Lanczos",
            "input": describe(master, Path(args.master)),
            "detail": outputs[0],
            "thumbnail": outputs[1],
            "derivatives": outputs,
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 6. Fidelity evidence: the finished image still carries the approved source
# --------------------------------------------------------------------------------------


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
    blocks = difference[:height, :width].mean(axis=2).reshape(
        height // block, block, width // block, block
    ).mean(axis=(1, 3))

    payload: Dict[str, Any] = {
        "operation": "fidelity_check_against_approved_source",
        "reference": describe(reference_image, Path(args.reference)),
        "candidate": describe(candidate_image, Path(args.candidate)),
        "candidate_compared_at": list(reference_image.size),
        "mean_absolute_difference_0_255": round(float(difference.mean()), 3),
        "p99_block_difference_0_255": round(float(np.percentile(blocks, 99)), 3),
        "max_block_difference_0_255": round(float(blocks.max()), 3),
        "luminance_correlation": round(luminance_correlation, 4),
        "edge_structure_correlation": round(edge_correlation, 4),
        "thresholds": dict(FIDELITY_THRESHOLDS),
    }
    payload["verdict"] = (
        "passed"
        if payload["mean_absolute_difference_0_255"] <= FIDELITY_THRESHOLDS["mean_absolute_difference_max"]
        and payload["luminance_correlation"] >= FIDELITY_THRESHOLDS["luminance_correlation_min"]
        and payload["edge_structure_correlation"]
        >= FIDELITY_THRESHOLDS["edge_structure_correlation_min"]
        else "failed"
    )
    report(payload)
    return 0 if payload["verdict"] == "passed" else 1


# --------------------------------------------------------------------------------------
# 7. Contact sheet for the 96x96 legibility read
# --------------------------------------------------------------------------------------


def command_contact_sheet(args: argparse.Namespace) -> int:
    """Tile every finished master at a small preview size next to a 96x96 sample.

    The sheet is review material for a human, not a gate: ``record`` never reads it as evidence.
    """

    paths = [Path(part) for part in args.inputs]
    labels = args.labels or [path.stem for path in paths]
    if len(labels) != len(paths):
        raise SystemExit("--labels must match --inputs one for one")

    cell = int(args.cell)
    columns = int(args.columns)
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell, rows * cell), (16, 16, 18))
    for index, path in enumerate(paths):
        tile = load_rgb(path).resize((cell, cell), resample=Image.LANCZOS)
        sheet.paste(tile, ((index % columns) * cell, (index // columns) * cell))
    save_png(sheet, Path(args.output))
    report(
        {
            "operation": "artifact_preview_contact_sheet",
            "cell": cell,
            "labels": labels,
            "output": describe(sheet, Path(args.output)),
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 8. Asset Catalog publication
# --------------------------------------------------------------------------------------


def imageset_manifest(payload_name: str) -> Dict[str, Any]:
    return {
        "images": [
            {"filename": payload_name, "idiom": "universal", "scale": "1x"},
            {"idiom": "universal", "scale": "2x"},
            {"idiom": "universal", "scale": "3x"},
        ],
        "info": {"author": "xcode", "version": 1},
    }


def command_publish_catalog(args: argparse.Namespace) -> int:
    """Publish the two runtime derivatives into the Asset Catalog.

    Masters deliberately have no variant and are never published. The command refuses to
    overwrite an existing imageset so a published payload can only change through an explicit
    removal and a new, recorded run.
    """

    work_dir = Path(args.work_dir)
    catalog_root = Path(args.catalog_root)
    derive_report = load_json(work_dir / f"{args.task}_report_derive.json")
    published: List[Dict[str, Any]] = []

    for key, expected in (("detail", DETAIL_SIZE), ("thumbnail", THUMBNAIL_SIZE)):
        entry = derive_report[key]
        asset_name = entry["asset_name"]
        source = work_dir / Path(entry["path"]).name
        if not source.is_file():
            raise SystemExit(f"missing {key} derivative {source.name}")
        if sha256_of(source) != entry["sha256"]:
            raise SystemExit(f"{key} derivative bytes do not match its report")
        if (entry["width"], entry["height"]) != expected:
            raise SystemExit(
                f"{asset_name} is {entry['width']}x{entry['height']}, "
                f"the runtime contract requires {expected[0]}x{expected[1]}"
            )

        imageset = catalog_root / f"{asset_name}.imageset"
        if imageset.exists():
            raise SystemExit(f"refusing to overwrite the existing imageset {imageset}")
        imageset.mkdir(parents=True)
        payload_name = f"{asset_name}.png"
        payload = imageset / payload_name
        payload.write_bytes(source.read_bytes())
        write_json(imageset / "Contents.json", imageset_manifest(payload_name))
        published.append(
            {
                "asset_name": asset_name,
                "imageset": str(imageset),
                "payload": payload_name,
                "width": entry["width"],
                "height": entry["height"],
                "sha256": sha256_of(payload),
            }
        )

    report(
        {
            "operation": "publish_runtime_derivatives_to_asset_catalog",
            "catalog_root": str(catalog_root),
            "master_published": False,
            "payloads": published,
        }
    )
    return 0


# --------------------------------------------------------------------------------------
# 9. Fail-closed QA and provenance records
# --------------------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"record refused: {message}")


def _verified_stage(
    work_dir: Path, task: str, stage: str, expected_input_sha256: str | None = None
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


def _inspection_for(document: Dict[str, Any] | None, task: str) -> Dict[str, Any] | None:
    """Accept either one Artifact record or a bundle keyed by task."""

    if not document:
        return None
    if "scales_percent" in document:
        return document
    entry = (document.get("artifacts") or {}).get(task)
    if entry is None:
        return None
    merged = dict(document.get("protocol") or {})
    merged.update(entry)
    return merged


def _canon_claim(canon_evidence: Dict[str, Any] | None, artifact_id: str) -> Dict[str, Any] | None:
    if not canon_evidence:
        return None
    for claim in canon_evidence.get("claims", []):
        if claim.get("artifact_id") == artifact_id:
            return claim
    return None


def _canon_limit(canon_evidence: Dict[str, Any] | None, artifact_id: str) -> Dict[str, Any] | None:
    if not canon_evidence:
        return None
    for limit in canon_evidence.get("coverage_limits", []):
        if limit.get("artifact_id") == artifact_id:
            return limit
    return None


def _repo_relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:  # pragma: no cover - only for out-of-tree decision files
        return str(path)


def load_text_decision(
    path: Path | None, *, required: bool
) -> Tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    """Read the recorded art-direction decision on decorative lettering.

    A missing file is not an error unless the caller insists on one: records stay reproducible on
    a checkout that does not carry the decision, and the gates simply stay open. A file that is
    present but unreadable, of an unknown schema, or of a different decision kind is fatal.
    """

    candidate = Path(path) if path else None
    if candidate is None or not candidate.is_file():
        if required:
            raise SystemExit(
                f"text decision {candidate} is missing; refusing to apply an unrecorded decision"
            )
        return None, None
    try:
        document = load_json(candidate)
    except json.JSONDecodeError as error:
        raise SystemExit(f"text decision {candidate} is not valid JSON: {error}") from error
    if document.get("schema_version") != 1:
        raise SystemExit(f"text decision {candidate} has an unsupported schema_version")
    if document.get("decision") != DECORATIVE_TEXT_DECISION_KIND:
        raise SystemExit(
            f"text decision {candidate} records {document.get('decision')!r}, not "
            f"{DECORATIVE_TEXT_DECISION_KIND!r}"
        )
    reference = {
        "record": _repo_relative(candidate),
        "sha256": sha256_of(candidate),
        "decision": document.get("decision"),
        "decided_at": document.get("decided_at"),
        "decided_by": document.get("decided_by"),
    }
    return document, reference


def decision_block(
    reference: Dict[str, Any] | None, revised_gates: List[str], applied_at: str | None
) -> Dict[str, Any]:
    return dict(
        reference or {},
        applied_to=revised_gates,
        applied_at=applied_at or datetime.date.today().isoformat(),
    )


def verdict_from_gates(gates: Dict[str, Any]) -> Tuple[List[str], str]:
    pending = [name for name, gate in gates.items() if gate.get("status") != "PASSED"]
    return pending, ("PASSED" if not pending else "PRODUCTION_EVIDENCE_PENDING")


def qa_status_for(pending_gates: List[str]) -> str:
    return (
        "MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING"
        if "G4_production" not in pending_gates
        else "MACOS_FINISHING_PENDING"
    )


def reviewers_for(revised_gates: List[str]) -> List[str]:
    reviewers = [
        "interactive_art_direction_approval",
        "macos_finishing_pipeline_finish_artifact_artwork.py",
    ]
    if revised_gates:
        reviewers.append("art_direction_text_decision")
    return reviewers


def apply_text_decision_to_gates(
    gates: Dict[str, Any],
    decision: Dict[str, Any] | None,
    reference: Dict[str, Any] | None,
    artwork_id: str,
    applied_at: str | None,
) -> List[str]:
    """Close G0/G3 for lettering the art direction has accepted, and nothing else.

    The exception is deliberately narrow: only defects whose id starts with the tool's own
    lettering vocabulary can be cleared, only when the inspection recorded that exact defect, and
    only for an artwork the decision names. Any other unrecorded or structural defect keeps G3
    open.
    """

    entry = ((decision or {}).get("artifacts") or {}).get(artwork_id)
    if not entry or not entry.get("text_approved"):
        return []
    accepted_ids = list(entry.get("accepted_defects") or [])
    revised: List[str] = []

    g0 = gates.get("G0_semantic") or {}
    findings = g0.get("baked_text_findings") or []
    if (
        g0.get("status") != "PASSED"
        and g0.get("typography_detected")
        and (g0.get("primary_read") or "").strip()
        and findings
    ):
        g0["status"] = "PASSED"
        g0["status_basis"] = "ART_DIRECTION_ACCEPTED_DECORATIVE_INSCRIPTION"
        g0["accepted_text_findings"] = findings
        g0["text_decision"] = decision_block(reference, ["G0_semantic"], applied_at)
        g0["notes"] = [
            note for note in g0.get("notes", []) if "text-free art" not in note
        ] + [
            "The baked lettering was accepted as decorative inscription "
            f"({entry.get('note') or 'engraved and spine lettering is material, not product copy'}), "
            "so G0 passes without regenerating the source."
        ]
        revised.append("G0_semantic")

    g3 = gates.get("G3_structure") or {}
    if g3.get("status") != "PASSED":
        defects = list(g3.get("defects_found") or [])
        for defect in accepted_ids:
            if not defect.startswith(DECORATIVE_TEXT_DEFECT_PREFIX):
                raise SystemExit(
                    f"decision {reference.get('record')} accepts {defect!r}, which is not a "
                    "recorded lettering defect; only baked-text findings can be accepted"
                )
            if defect not in defects:
                raise SystemExit(
                    f"decision {reference.get('record')} accepts {defect!r}, which the inspection "
                    "did not record for this artwork; refusing to clear an unrecorded defect"
                )
        scales = {int(value) for value in g3.get("inspection_scales_percent", [])}
        blocking = [defect for defect in defects if defect not in accepted_ids]
        if (
            accepted_ids
            and not blocking
            and {25, 100, 200} <= scales
            and (g3.get("method") or "").strip()
        ):
            g3["status"] = "PASSED"
            g3["accepted_defects"] = accepted_ids
            g3["blocking_defects"] = []
            g3["text_decision"] = decision_block(reference, ["G3_structure"], applied_at)
            g3["notes"] = [
                note for note in g3.get("notes", []) if "Defects were recorded" not in note
            ] + [
                "The only recorded defects are the accepted decorative lettering; nothing else "
                "remains, so G3 passes."
            ]
            revised.append("G3_structure")
    return revised


def _evaluate_structural(inspection: Dict[str, Any] | None) -> Tuple[str, Dict[str, Any]]:
    if not inspection:
        return "PENDING_MACOS_FINISHING", {
            "notes": ["No 25/100/200% structural inspection record is attached yet."]
        }
    scales = {int(value) for value in inspection.get("scales_percent", [])}
    defects = inspection.get("defects_found", [])
    method = (inspection.get("method") or "").strip()
    passed = {25, 100, 200} <= scales and not defects and bool(method)
    record: Dict[str, Any] = {
        "inspection_scales_percent": sorted(scales),
        "method": method,
        "defects_found": defects,
        "inspected_at": inspection.get("inspected_at"),
        "notes": [
            "Structural review performed locally on the finished 2048x2048 master at "
            "25/100/200%.",
            "The finishing chain contains no generative step beyond one super-resolution pass, so "
            "it cannot invent micro-text or new objects; the inspection confirms the printed "
            "result matches that.",
        ],
    }
    for key in (
        "architecture_errors",
        "repetition_errors",
        "gibberish_or_fake_text",
        "human_or_vehicle_errors",
        "baked_text_findings",
    ):
        record[key] = inspection.get(key) or []
    for key in (
        "readability_note",
        "detail_note",
        "seam_note",
        "text_like_glyph_check",
        "structural_repetition_check",
    ):
        if inspection.get(key) is not None:
            record[key] = inspection[key]
    if inspection.get("defects_found"):
        record["notes"].append("Defects were recorded, so G3 stays open rather than passing.")
    return ("PASSED" if passed else "PENDING_MACOS_FINISHING"), record


def _catalog_evidence(catalog_root: Path | None, asset_names: List[str]) -> Dict[str, Any]:
    if catalog_root is None:
        return {"status": "NOT_CHECKED"}
    entries: List[Dict[str, Any]] = []
    for asset_name in asset_names:
        imageset = Path(catalog_root) / f"{asset_name}.imageset"
        if not imageset.is_dir():
            return {"status": "MISSING", "missing": asset_name}
        for entry in load_json(imageset / "Contents.json").get("images", []):
            filename = entry.get("filename")
            if not filename:
                continue
            payload = imageset / filename
            if not payload.is_file():
                return {"status": "MISSING", "missing": f"{asset_name}.imageset/{filename}"}
            with Image.open(payload) as opened:
                has_icc = bool(opened.info.get("icc_profile"))
                width, height = opened.size
            entries.append(
                {
                    "asset_name": asset_name,
                    "payload": payload.name,
                    "width": width,
                    "height": height,
                    "sha256": sha256_of(payload),
                    "icc_profile": "sRGB IEC61966-2.1" if has_icc else None,
                }
            )
    return {"status": "VERIFIED", "payloads": entries}


ARTIFACT_WINDOW_CHECKS: Tuple[str, ...] = ("960x640", "1180x760", "2560x1600")
ARTIFACT_ACCESSIBILITY_STATES: Tuple[str, ...] = ("Increased Contrast", "Reduce Transparency")
RUNTIME_EVIDENCE_SEQUENCE: Tuple[str, ...] = (
    "collection-960x640",
    "collection-1180x760",
    "collection-2560x1600",
    "detail-2560x1600",
    "showcase-1180x760",
    "showcase-increased-contrast",
    "showcase-reduce-transparency",
)


def _evaluate_runtime(
    payload: Dict[str, Any] | None,
    evidence_dir: Path,
) -> Tuple[str, Dict[str, Any], List[str]]:
    """神器的 G5：窗口、辅助功能状态与「派生图确实被渲染」三件事都要有可复算的像素依据。

    截图只算证据当它仍然等于记录里的字节；对比度一律由本工具从测量区重算，证据文件里
    声明的任何比值都被忽略；模板匹配分由采集脚本产出（低于阈值时脚本直接失败），这里只
    接受 `verdict == "present"` 且不低于阈值的条目。
    """

    if not payload:
        return (
            "PENDING_RUNTIME_QA",
            {
                "window_checks": {size: None for size in ARTIFACT_WINDOW_CHECKS},
                "accessibility_checks": {state: None for state in ARTIFACT_ACCESSIBILITY_STATES},
                "notes": [
                    "Artifact collection, detail and accessibility window checks have not been "
                    "captured yet."
                ],
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
    for size in ARTIFACT_WINDOW_CHECKS:
        entry = window_checks.get(size)
        if not entry:
            problems.append(f"window {size} not captured")
            verified_windows[size] = None
            continue
        digest = world_tool._verified_capture(
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
    for state in ARTIFACT_ACCESSIBILITY_STATES:
        entry = accessibility_checks.get(state)
        if not entry:
            problems.append(f"accessibility state {state} not captured")
            verified_states[state] = None
            continue
        digest = world_tool._verified_capture(
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

    # 「出厂的派生图确实出现在这一帧里」：每一张抓取都必须带着不低于阈值的匹配结论。
    surface = payload.get("surface_verification") or {}
    threshold = surface.get("minimum_score")
    if not isinstance(threshold, (int, float)):
        problems.append("surface verification has no minimum score")
    else:
        for capture_name, entry in (surface.get("captures") or {}).items():
            if not isinstance(entry, dict):
                problems.append(f"surface verification for {capture_name} is malformed")
                continue
            world_tool._verified_capture(
                capture_name, evidence_dir, digests, problems, f"surface {capture_name}"
            )
            score = entry.get("score")
            if entry.get("verdict") != "present" or not isinstance(score, (int, float)):
                problems.append(f"surface verification for {capture_name} is not a confirmed match")
            elif score < threshold:
                problems.append(
                    f"surface verification for {capture_name} scored {score} below {threshold}"
                )

    # 对比度从点名的测量区复算：证据里声明的比值不算数。
    computed: Dict[str, List[Dict[str, Any]]] = {}
    for index, measurement in enumerate((payload.get("contrast") or {}).get("measurements") or []):
        kind = measurement.get("kind")
        label = f"contrast measurement {index}"
        if kind not in ("text_primary", "important_copy"):
            problems.append(f"{label} has an unsupported kind {kind!r}")
            continue
        capture = measurement.get("capture")
        if world_tool._verified_capture(capture, evidence_dir, digests, problems, label) is None:
            continue
        region = measurement.get("region")
        if not (
            isinstance(region, list)
            and len(region) == 4
            and all(isinstance(value, int) for value in region)
        ):
            problems.append(f"{label} needs an integer region [x, y, width, height]")
            continue
        image = world_tool.load_rgb(evidence_dir / str(capture))
        x, y, width, height = region
        if (
            width <= 0
            or height <= 0
            or x < 0
            or y < 0
            or x + width > image.width
            or y + height > image.height
        ):
            problems.append(f"{label} region falls outside the capture")
            continue
        ratio = round(
            world_tool._wcag_contrast_ratio(np.asarray(image.crop((x, y, x + width, y + height)))),
            2,
        )
        computed.setdefault(kind, []).append(
            {"kind": kind, "capture": Path(str(capture)).name, "region": region, "ratio": ratio}
        )

    thresholds = world_tool.CONTRAST_THRESHOLDS
    primary = min((entry["ratio"] for entry in computed.get("text_primary", [])), default=None)
    important = min((entry["ratio"] for entry in computed.get("important_copy", [])), default=None)
    if primary is None:
        problems.append("no recomputable primary-text contrast measurement was provided")
    elif primary < thresholds["text_primary_min"]:
        problems.append(
            f"primary text contrast {primary}:1 is below the {thresholds['text_primary_min']}:1 minimum"
        )
    if important is None:
        problems.append("no recomputable important-copy contrast measurement was provided")
    elif important < thresholds["important_long_copy_target"]:
        problems.append(
            f"important copy contrast {important}:1 is below the "
            f"{thresholds['important_long_copy_target']}:1 target"
        )

    record = dict(payload)
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
        "thresholds": dict(thresholds),
    }
    record["notes"] = [
        "Captured from the real macOS window surface; every capture is re-hashed against the "
        "recorded digest before its claims are accepted.",
        "Template matching is produced by the capture harness against the shipped derivative; the "
        "record refuses a capture whose recorded verdict is not a confirmed match.",
    ]
    if problems:
        record["unmet_requirements"] = problems
        return "PENDING_RUNTIME_QA", record, problems
    return "PASSED", record, []


def command_record(args: argparse.Namespace) -> int:
    targets = artifact_targets(Path(args.manifest))
    _require(args.task in targets, f"unknown artifact task {args.task}")
    target = targets[args.task]
    artwork_id = f"{args.task}_{target['source_id'].split('_', 1)[1]}"
    asset_name = target["asset_name"]
    detail_name = f"{asset_name}.detail"
    thumbnail_name = f"{asset_name}.thumbnail"
    work_dir = Path(args.work_dir)
    reviewed_at = args.reviewed_at or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d"
    )

    crop_report, crop_path = _verified_stage(work_dir, args.task, "square_crop")
    sr_report, _ = _verified_stage(
        work_dir, args.task, "sr", crop_report["output"]["sha256"]
    )
    grade_report, _ = _verified_stage(
        work_dir, args.task, "grade", sr_report["output"]["sha256"]
    )
    master_report, master_path = _verified_stage(
        work_dir, args.task, "master", grade_report["output"]["sha256"]
    )
    master_sha = master_report["output"]["sha256"]
    _require(
        (master_report["output"]["width"], master_report["output"]["height"]) == MASTER_SIZE,
        f"the master is not {MASTER_SIZE[0]}x{MASTER_SIZE[1]}",
    )
    _require(crop_report["upscale"] is False, "the square safety crop upscaled the source")

    fidelity = load_json(work_dir / f"{args.task}_report_fidelity.json")
    _require(
        fidelity["candidate"]["sha256"] == master_sha,
        "the fidelity report does not describe the master on disk",
    )
    _require(
        fidelity["reference"]["sha256"] == crop_report["output"]["sha256"],
        "the fidelity report does not compare against the locked source crop",
    )
    _require(fidelity["verdict"] == "passed", "fidelity against the approved source failed")

    derive_report = load_json(work_dir / f"{args.task}_report_derive.json")
    _require(
        derive_report["input"]["sha256"] == master_sha,
        "the derivatives were not produced from this master",
    )
    _require(
        derive_report["detail"]["asset_name"] == detail_name
        and derive_report["thumbnail"]["asset_name"] == thumbnail_name,
        "the derivative report names a different runtime identity",
    )
    derivative_paths: Dict[str, Path] = {}
    for key, expected in (("detail", DETAIL_SIZE), ("thumbnail", THUMBNAIL_SIZE)):
        entry = derive_report[key]
        path = work_dir / Path(entry["path"]).name
        _require(path.is_file(), f"missing {key} derivative {path.name}")
        _require(
            sha256_of(path) == entry["sha256"],
            f"{key} derivative bytes do not match its report",
        )
        _require(
            (entry["width"], entry["height"]) == expected,
            f"the {key} derivative is not {expected[0]}x{expected[1]}",
        )
        derivative_paths[key] = path

    catalog = _catalog_evidence(
        Path(args.catalog_root) if args.catalog_root else None, [detail_name, thumbnail_name]
    )
    if catalog["status"] == "VERIFIED":
        by_name = {entry["asset_name"]: entry for entry in catalog["payloads"]}
        for key, name in (("detail", detail_name), ("thumbnail", thumbnail_name)):
            entry = by_name.get(name)
            _require(entry is not None, f"the catalog has no payload for {name}")
            _require(
                entry["sha256"] == derive_report[key]["sha256"],
                f"the catalog payload for {name} is not the finished derivative",
            )
        catalog["matches_derivatives"] = True

    inspection = _inspection_for(
        load_json(Path(args.inspection)) if args.inspection and Path(args.inspection).is_file() else None,
        args.task,
    )
    canon_evidence = (
        load_json(Path(args.canon_evidence))
        if args.canon_evidence and Path(args.canon_evidence).is_file()
        else None
    )
    canon_claim = _canon_claim(canon_evidence, target["artifact_id"])
    canon_limit = _canon_limit(canon_evidence, target["artifact_id"])

    # ---- G0: what the finished object actually reads as ---------------------------------
    if inspection and (inspection.get("primary_read") or "").strip():
        typography = bool(inspection.get("typography_detected"))
        g0_status = "PENDING_MACOS_FINISHING" if typography else "PASSED"
        g0: Dict[str, Any] = {
            "status": g0_status,
            "primary_read": inspection.get("primary_read"),
            "secondary_read": inspection.get("secondary_read"),
            "generic_fantasy_read": inspection.get("generic_fantasy_read"),
            "typography_detected": typography,
            "dominant_subject": inspection.get("dominant_subject"),
            "notes": [
                "Read from the finished 2048x2048 master, not from the source file alone.",
            ],
            "status_basis": "FINISHED_MASTER_READ_PLUS_EXPLICIT_USER_SOURCE_APPROVAL",
            "approval_reference": target.get("approval_record"),
            "baked_text_findings": inspection.get("baked_text_findings") or [],
        }
        if typography:
            g0["notes"].append(
                "Baked readable typography was detected in the approved source, so G0 stays open "
                "rather than passing. Product policy is text-free art; this needs an explicit "
                "user/art-direction decision (accept or re-generate the source)."
            )
    else:
        g0 = {
            "status": "PENDING_MACOS_FINISHING",
            "notes": ["No finished-master semantic read is attached yet."],
        }

    # ---- G1: Canon consistency, only where primary evidence exists ----------------------
    if canon_claim and (inspection or {}).get("canon_consistency_note"):
        g1: Dict[str, Any] = {
            "status": "PASSED",
            "status_basis": "PRIMARY_EVIDENCE_PLUS_FINISHED_MASTER_CONSISTENCY",
            "canon_claim": canon_claim["claim"],
            "evidence": {
                "source_type": canon_claim.get("source_type"),
                "chapter": canon_claim.get("chapter"),
                "chapter_title": canon_claim.get("chapter_title"),
                "coverage": canon_claim.get("coverage"),
            },
            "not_verified": canon_claim.get("not_verified", []),
            "canon_consistency_note": inspection["canon_consistency_note"],
            "evidence_reference": "docs/05_UI/artwork/delivery/canon_evidence.json",
        }
    else:
        g1 = {
            "status": "PENDING_CANON_REVIEW",
            "notes": [
                "Visual approval is not Canon verification. This object has no verified primary "
                "form claim recorded in docs/05_UI/artwork/delivery/canon_evidence.json, so G1 "
                "stays open until the Canon review is recorded."
            ],
            "coverage_limit": canon_limit,
            "canon_consistency_note": (inspection or {}).get("canon_consistency_note"),
        }
    g1["shipping_approved"] = False

    # ---- G2: composition safety of the 1:1 crop -----------------------------------------
    crop_safe = bool((inspection or {}).get("crop_safety_note"))
    g2: Dict[str, Any] = {
        "status": "PASSED" if crop_safe else "PENDING_MACOS_FINISHING",
        "aspect_ratio": "1:1",
        "source_native_size": [
            crop_report["input"]["width"],
            crop_report["input"]["height"],
        ],
        "source_crop_rect_pixels": crop_report["rect_pixels"],
        "source_crop_output": {
            "width": crop_report["output"]["width"],
            "height": crop_report["output"]["height"],
            "sha256": crop_report["output"]["sha256"],
        },
        "crop_rule": "deterministic_centred_maximal_square",
        "upscale": False,
        "crop_safety_note": (inspection or {}).get("crop_safety_note"),
        "notes": [
            "Non-square sources are cropped to the largest centred square; nothing is stretched "
            "and no canvas is invented.",
        ],
    }
    if not crop_safe:
        g2["notes"].append("No recorded subject-safety read for the crop, so G2 stays open.")

    # ---- G3: structural inspection ------------------------------------------------------
    g3_status, g3 = _evaluate_structural(inspection)
    g3["status"] = g3_status

    # ---- G4: production evidence --------------------------------------------------------
    g4_checks = {
        "master_dimensions": True,
        "derivatives_from_same_master": True,
        "derivative_dimensions": True,
        "fidelity_passed": True,
        "catalog_matches_derivatives": catalog["status"] == "VERIFIED",
    }
    g4: Dict[str, Any] = {
        "status": "PASSED" if all(g4_checks.values()) else "PENDING_MACOS_FINISHING",
        "master_dimensions": {"width": MASTER_SIZE[0], "height": MASTER_SIZE[1]},
        "runtime_dimensions": {
            detail_name: {"width": DETAIL_SIZE[0], "height": DETAIL_SIZE[1]},
            thumbnail_name: {"width": THUMBNAIL_SIZE[0], "height": THUMBNAIL_SIZE[1]},
        },
        "color_profile": "sRGB IEC61966-2.1 (explicit ICC on every finishing output)",
        "format": "PNG",
        "sha256": {
            detail_name: derive_report["detail"]["sha256"],
            thumbnail_name: derive_report["thumbnail"]["sha256"],
        },
        "asset_names": [detail_name, thumbnail_name],
        "master_sha256": master_sha,
        "derivative_tool": "docs/05_UI/artwork/tools/finish_artifact_artwork.py",
        "catalog": catalog,
        "notes": [
            "The 2048x2048 master is a finished / super-resolved master; the largest approved "
            "source is smaller than the master baseline.",
            "Runtime payloads are the contract 1024x1024 detail and 512x512 thumbnail derived "
            "from that one master.",
        ],
        "checks": g4_checks,
    }
    if not g4_checks["catalog_matches_derivatives"]:
        g4["notes"].append("The Asset Catalog payloads are not verified against the derivatives.")

    # ---- G5: runtime ----------------------------------------------------------------
    runtime_evidence_path = Path(args.runtime_evidence) if args.runtime_evidence else None
    g5_status, g5_record, runtime_problems = _evaluate_runtime(
        load_json(runtime_evidence_path) if runtime_evidence_path else None,
        runtime_evidence_path.parent if runtime_evidence_path else Path("."),
    )
    g5 = dict(
        {
            "status": g5_status,
            "window_sizes": list(ARTIFACT_WINDOW_CHECKS),
            "accessibility_states": list(ARTIFACT_ACCESSIBILITY_STATES),
        },
        **g5_record,
    )

    gates = {
        "G0_semantic": g0,
        "G1_canon_atmosphere": g1,
        "G2_composition": g2,
        "G3_structure": g3,
        "G4_production": g4,
        "G5_runtime": g5,
    }
    text_decision, text_decision_reference = load_text_decision(
        Path(args.text_decision) if args.text_decision else None, required=False
    )
    revised_gates = apply_text_decision_to_gates(
        gates, text_decision, text_decision_reference, artwork_id, reviewed_at
    )
    pending_gates, final_verdict = verdict_from_gates(gates)

    source_sha = crop_report["input"]["sha256"]
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
            "sha256": crop_report["output"]["sha256"],
            "photometry": photometry(crop_path),
        },
        "photometry_rules": {
            "shadow_clip": "luminance <= 2 of 255",
            "highlight_clip": "luminance >= 253 of 255",
        },
        "fidelity": {
            "mean_absolute_difference_0_255": fidelity["mean_absolute_difference_0_255"],
            "luminance_correlation": fidelity["luminance_correlation"],
            "edge_structure_correlation": fidelity["edge_structure_correlation"],
            "verdict": fidelity["verdict"],
        },
        "catalog": catalog,
        "production_host": "Apple Silicon macOS workstation; MPS super-resolution, deterministic tools",
        "real_esrgan_weights_sha256": sr_report.get("weights_sha256"),
        "independent_derivative_generation": False,
    }

    qa = {
        "artwork_id": artwork_id,
        "artifact_id": target["artifact_id"],
        "asset_name": asset_name,
        "contract_version": 1,
        "status": qa_status_for(pending_gates),
        "selected_candidate_id": f"{args.task}_SELECTED_SOURCE",
        "source": {
            "source_id": target["source_id"],
            "sha256": source_sha,
            "native_size": [crop_report["input"]["width"], crop_report["input"]["height"]],
            "visual_approval": "USER_APPROVED",
            "approval_record": target.get("approval_record"),
            "generation_id": args.generation_id,
        },
        "gates": gates,
        "final_verdict": final_verdict,
        "pending_gates": pending_gates,
        "reviewers": reviewers_for(revised_gates),
        "reviewed_at": reviewed_at,
        "production_contract": {
            "artifact_master_baseline": list(MASTER_SIZE),
            "artifact_detail": list(DETAIL_SIZE),
            "artifact_thumbnail": list(THUMBNAIL_SIZE),
            "one_source_per_image": True,
            "baked_text_allowed": False,
            "independent_derivative_generation_allowed": False,
            "macos_finishing_required": True,
        },
        "task_id": args.task,
        "production_evidence": production_evidence,
    }
    if revised_gates:
        qa["text_policy_decision"] = decision_block(
            text_decision_reference, revised_gates, reviewed_at
        )

    provenance = {
        "artwork_id": artwork_id,
        "artifact_id": target["artifact_id"],
        "status": (
            "SELECTED_SOURCE_LOCKED_MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING"
            if final_verdict == "PRODUCTION_EVIDENCE_PENDING"
            else "APPROVED"
        ),
        "source": {
            "source_id": target["source_id"],
            "sha256": source_sha,
            "native_width": crop_report["input"]["width"],
            "native_height": crop_report["input"]["height"],
            "generation_id": args.generation_id,
            "visual_approval": "USER_APPROVED",
            "approval_record": target.get("approval_record"),
        },
        "postprocess": [
            {
                "stage": "macos_square_safety_crop",
                "operation": crop_report["operation"],
                "generative": False,
                "rect_pixels": crop_report["rect_pixels"],
                "removed_pixels": crop_report["removed_pixels"],
                "output_width": crop_report["output"]["width"],
                "output_height": crop_report["output"]["height"],
                "sha256": crop_report["output"]["sha256"],
                "pixel_sha256": pixel_sha256(crop_path),
                "container_note": "PNG container hashes are encoder dependent, so a byte mismatch "
                "against a hash produced by a different encoder is not evidence of a different "
                "crop. pixel_sha256 identifies the decoded pixels independently of container "
                "framing.",
                "status": "COMPLETE",
            },
            {
                "stage": "macos_local_structural_repair",
                "status": "NOT_REQUIRED",
                "basis": inspection.get("repair_basis") if inspection else None,
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
                "generative": False,
                "output_width": grade_report["output"]["width"],
                "output_height": grade_report["output"]["height"],
                "sha256": grade_report["output"]["sha256"],
            },
            {
                "stage": "oversample_downsample_to_2048x2048_artifact_master",
                "status": "COMPLETE",
                "operation": master_report["operation"],
                "resample": master_report["resample"],
                "output_width": master_report["output"]["width"],
                "output_height": master_report["output"]["height"],
                "sha256": master_report["output"]["sha256"],
                "pixel_sha256": pixel_sha256(master_path),
                "master_is_native_generation": False,
                "master_quality_note": "Finished / super-resolved Master. The approved source is "
                "smaller than the 2048x2048 baseline, so this is not a native 2048x2048 "
                "generation.",
            },
            {
                "stage": "deterministic_derivatives",
                "status": "COMPLETE",
                "tool": derive_report["tool"],
                "independent_regeneration": False,
                "derivatives": [
                    {
                        "asset_name": derive_report["detail"]["asset_name"],
                        "width": derive_report["detail"]["width"],
                        "height": derive_report["detail"]["height"],
                        "sha256": derive_report["detail"]["sha256"],
                        "derivation": "full_frame_downsample_from_master",
                    },
                    {
                        "asset_name": derive_report["thumbnail"]["asset_name"],
                        "width": derive_report["thumbnail"]["width"],
                        "height": derive_report["thumbnail"]["height"],
                        "sha256": derive_report["thumbnail"]["sha256"],
                        "derivation": "full_frame_downsample_from_master",
                    },
                ],
            },
            {
                "stage": "runtime_qa",
                "status": g5["status"],
                "unmet_requirements": g5.get("unmet_requirements", ["runtime evidence missing"]),
                "evidence": QA_EVIDENCE_PATH.format(artwork_id=artwork_id),
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
            "pixel_sha256": pixel_sha256(master_path),
            "storage": "not committed; masters stay out of the Asset Catalog and out of git",
        },
        "derivatives": [
            {
                "asset_name": detail_name,
                "width": DETAIL_SIZE[0],
                "height": DETAIL_SIZE[1],
                "sha256": derive_report["detail"]["sha256"],
                "derivation": "full_frame_downsample_from_master",
                "catalog_payload_verified": catalog["status"] == "VERIFIED",
            },
            {
                "asset_name": thumbnail_name,
                "width": THUMBNAIL_SIZE[0],
                "height": THUMBNAIL_SIZE[1],
                "sha256": derive_report["thumbnail"]["sha256"],
                "derivation": "full_frame_downsample_from_master",
                "catalog_payload_verified": catalog["status"] == "VERIFIED",
            },
        ],
        "gates": {name: gate["status"] for name, gate in gates.items()},
        "shipping_approved": False,
    }
    if revised_gates:
        provenance["text_policy_decision"] = decision_block(
            text_decision_reference, revised_gates, reviewed_at
        )

    if pending_gates and args.require_complete:
        report(
            {
                "operation": "record",
                "result": "INCOMPLETE",
                "task": args.task,
                "pending_gates": pending_gates,
                "qa": str(args.qa),
                "provenance": str(args.provenance),
            }
        )
        return 1

    write_json(Path(args.qa), qa)
    write_json(Path(args.provenance), provenance)
    report(
        {
            "operation": "record",
            "result": "RECORDED",
            "task": args.task,
            "artwork_id": artwork_id,
            "final_verdict": final_verdict,
            "pending_gates": pending_gates,
            "qa": str(args.qa),
            "provenance": str(args.provenance),
        }
    )
    return 0


def command_apply_text_decision(args) -> int:
    """Revise G0/G3 of an already recorded Artifact from a recorded decorative-text decision.

    运行时截图证据不入库，历史记录里的 G5 无法在本地重放，所以整条 `record` 无法为已交付的成品
    重跑。本命令只施加美术方向决定并复算派生字段，其余 gate 逐字沿用输入记录，同时把输入记录的
    sha256 记入决定凭据，便于审计「哪一份记录被哪一条决定修订过」。
    """

    qa_path = Path(args.qa)
    provenance_path = Path(args.provenance)
    decision, reference = load_text_decision(Path(args.decision), required=True)

    qa = load_json(qa_path)
    provenance = load_json(provenance_path)
    artwork_id = qa.get("artwork_id")
    if not artwork_id or provenance.get("artwork_id") != artwork_id:
        raise SystemExit(
            "QA and provenance records do not describe the same artwork; refusing to revise"
        )

    gates = qa.get("gates") or {}
    recorded = {name: gate.get("status") for name, gate in gates.items()}
    if provenance.get("gates") != recorded:
        raise SystemExit(
            "QA and provenance gate statuses disagree; refusing to revise either record"
        )

    source_record_sha256 = sha256_of(qa_path)
    revised = apply_text_decision_to_gates(
        gates, decision, reference, artwork_id, args.applied_at
    )
    if not revised:
        report(
            {
                "operation": "apply-text-decision",
                "result": "NO_CHANGE",
                "reason": "the recorded decision does not cover this artwork",
                "qa": str(qa_path),
                "decision": reference.get("record"),
            }
        )
        return 0

    pending_gates, final_verdict = verdict_from_gates(gates)
    block = dict(
        decision_block(reference, revised, args.applied_at),
        revised_from_record_sha256=source_record_sha256,
    )
    qa["status"] = qa_status_for(pending_gates)
    qa["pending_gates"] = pending_gates
    qa["final_verdict"] = final_verdict
    qa["text_policy_decision"] = block
    if "art_direction_text_decision" not in (qa.get("reviewers") or []):
        qa["reviewers"] = list(qa.get("reviewers") or []) + ["art_direction_text_decision"]

    if final_verdict == "PASSED":
        provenance["status"] = "APPROVED"
    elif provenance.get("status") != PROVENANCE_PENDING_STATUS:
        raise SystemExit(
            f"provenance status {provenance.get('status')!r} is not the finishing-pending value; "
            "refusing to rewrite it"
        )
    provenance["gates"] = {name: gate.get("status") for name, gate in gates.items()}
    provenance["text_policy_decision"] = block

    write_json(qa_path, qa)
    write_json(provenance_path, provenance)
    report(
        {
            "operation": "apply-text-decision",
            "result": "REVISED",
            "artwork_id": artwork_id,
            "revised_gates": revised,
            "pending_gates": pending_gates,
            "final_verdict": final_verdict,
            "decision": reference.get("record"),
            "qa": str(qa_path),
            "provenance": str(provenance_path),
        }
    )
    return 0


QA_EVIDENCE_PATH = "docs/05_UI/artwork/qa/{artwork_id}.qa.json"


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="operation", required=True)

    crop = sub.add_parser("square-crop", help="deterministic centred 1:1 safety crop")
    crop.add_argument("--input", required=True)
    crop.add_argument("--output", required=True)
    crop.add_argument("--size", type=int, default=None, help="explicit square edge (default: largest)")
    crop.set_defaults(handler=command_square_crop)

    sr = sub.add_parser("sr", help="one Real-ESRGAN x4 pass on MPS")
    sr.add_argument("--input", required=True)
    sr.add_argument("--output", required=True)
    sr.add_argument("--weights", required=True)
    sr.add_argument("--tile", type=int, default=512)
    sr.add_argument("--overlap", type=int, default=32)
    sr.add_argument("--downstream", default=None)
    sr.set_defaults(handler=command_sr)

    grade = sub.add_parser("grade", help="material / colour-luminance grade")
    grade.add_argument("--input", required=True)
    grade.add_argument("--output", required=True)
    grade.add_argument("--profile", default=GRADE_PROFILE_NAME)
    grade.set_defaults(handler=command_grade)

    master = sub.add_parser("master", help="controlled downsample to the Artifact Master")
    master.add_argument("--input", required=True)
    master.add_argument("--output", required=True)
    master.add_argument("--width", type=int, default=MASTER_SIZE[0])
    master.add_argument("--height", type=int, default=MASTER_SIZE[1])
    master.set_defaults(handler=command_master)

    derive = sub.add_parser("derive", help="same-master detail and thumbnail derivatives")
    derive.add_argument("--master", required=True)
    derive.add_argument("--detail-asset", required=True)
    derive.add_argument("--detail-output", required=True)
    derive.add_argument("--thumbnail-asset", required=True)
    derive.add_argument("--thumbnail-output", required=True)
    derive.set_defaults(handler=command_derive)

    fidelity = sub.add_parser("fidelity", help="fidelity evidence against the approved source")
    fidelity.add_argument("--reference", required=True)
    fidelity.add_argument("--candidate", required=True)
    fidelity.set_defaults(handler=command_fidelity)

    sheet = sub.add_parser("contact-sheet", help="small preview sheet for the human read")
    sheet.add_argument("--inputs", nargs="+", required=True)
    sheet.add_argument("--labels", nargs="*", default=None)
    sheet.add_argument("--output", required=True)
    sheet.add_argument("--cell", type=int, default=96)
    sheet.add_argument("--columns", type=int, default=5)
    sheet.set_defaults(handler=command_contact_sheet)

    publish = sub.add_parser("publish-catalog", help="publish .detail / .thumbnail imagesets")
    publish.add_argument("--task", required=True)
    publish.add_argument("--work-dir", required=True)
    publish.add_argument("--catalog-root", required=True)
    publish.set_defaults(handler=command_publish_catalog)

    record = sub.add_parser("record", help="assemble QA and provenance from verified stage bytes")
    record.add_argument("--task", required=True)
    record.add_argument("--work-dir", required=True)
    record.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    record.add_argument("--canon-evidence", default=str(DEFAULT_CANON_EVIDENCE))
    record.add_argument("--inspection", default=None)
    record.add_argument(
        "--runtime-evidence",
        default=None,
        help="G5 window / accessibility evidence captured from the real macOS window (JSON)",
    )
    record.add_argument("--catalog-root", default=None)
    record.add_argument("--generation-id", default=None)
    record.add_argument("--reviewed-at", default=None)
    record.add_argument(
        "--text-decision",
        default=str(DEFAULT_TEXT_DECISION),
        help="recorded art-direction decision on decorative lettering (G0/G3 exception)",
    )
    record.add_argument("--qa", required=True)
    record.add_argument("--provenance", required=True)
    record.add_argument("--require-complete", action="store_true")
    record.set_defaults(handler=command_record)

    text = sub.add_parser(
        "apply-text-decision",
        help="revise G0/G3 of an existing record from a recorded decorative-text decision",
    )
    text.add_argument("--qa", required=True)
    text.add_argument("--provenance", required=True)
    text.add_argument("--decision", default=str(DEFAULT_TEXT_DECISION))
    text.add_argument("--applied-at", default=None)
    text.set_defaults(handler=command_apply_text_decision)

    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
