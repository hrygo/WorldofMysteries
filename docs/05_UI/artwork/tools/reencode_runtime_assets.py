#!/usr/bin/env python3
"""重编码 Asset Catalog 里的运行时大图，并留下可复算的保真度证据。

两档策略，风险级别不同
----------------------

`--tier lossless`（默认，可无条件执行）
    2560x1600 的运行时插画以 8-bit RGBA PNG 入库时单张 3.7-8.5 MB，但 alpha 通道实测全为
    255（全不透明），等于白占体积。丢掉这个空 alpha 通道、用 zlib level 9 重新打包，实测
    单张缩小约 22%，且**逐像素完全一致**：工具会对重编码前后的 RGB24 原始平面各算一次
    SHA256，只有两者相等才算通过。这是可以无条件写入的优化。

`--tier heic`（默认不执行，需要人工视觉签核）
    HEIC 的体积优势很大，但对这套插画并不免费。实测（Xcode 27 / macOS 26 部署目标）：

        Q85  → 约 0.8 MB，PSNR 31-40 dB，SSIM 0.92-0.98   ← 体积好看，画质有真实损失
        Q100 → 约 3.5-5.0 MB，PSNR 50.6-51.6 dB，SSIM 0.9972-0.9976

    把质量从 Q85 拉到 Q98 只让 PSNR 中位数从 37.31 升到 37.45，说明损失来自色度下采样而
    不是质量档位——HEIC 换不来"近无损"。因此该档必须满足显式的 PSNR/SSIM 门槛（默认
    48 dB / 0.995）才会落盘，且不接受在未经视觉复核的情况下替换已 USER_APPROVED 的资产。

范围
----
只处理运行时插画（`wom.art.world.*`、`wom.art.scene.*`、`wom.art.artifact.*.detail|thumbnail`）。
噪声纹理（`Texture*`）在有损编码下会丢颗粒、图标本身很小、AppIcon 由系统按需生成多尺寸，
都不参与重编码。master 与 6K 中间产物永远不在此工具的处理范围内。

用法
----
    # 无损档：先看计划，再落盘
    python3 docs/05_UI/artwork/tools/reencode_runtime_assets.py
    python3 docs/05_UI/artwork/tools/reencode_runtime_assets.py --apply --update-provenance

    # HEIC 档：需要显式指定质量档，并先补齐视觉复核
    python3 docs/05_UI/artwork/tools/reencode_runtime_assets.py --tier heic --quality 100
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
ASSETS_ROOT = REPO_ROOT / "macos-app/WorldOfMysteries/Assets.xcassets"
PROVENANCE_DIR = REPO_ROOT / "docs/05_UI/artwork/provenance"
QA_DIR = REPO_ROOT / "docs/05_UI/artwork/qa"

# 只有大型插画/照片型运行时资源参与重编码；纹理与图标保持原格式。
PHOTOGRAPHIC_PATTERNS = (
    re.compile(r"^wom\.art\.(world|scene)\.[a-z0-9.\-]+$"),
    re.compile(r"^wom\.art\.artifact\.[a-z0-9\-]+\.(detail|thumbnail)$"),
)


def is_photographic_asset(asset_name: str) -> bool:
    return any(pattern.match(asset_name) for pattern in PHOTOGRAPHIC_PATTERNS)


class ToolError(RuntimeError):
    pass


def run(cmd: list[str], *, binary_output: bool = False) -> bytes | str:
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ToolError(
            f"命令失败 ({proc.returncode}): {' '.join(cmd)}\n"
            f"stderr: {proc.stderr.decode('utf-8', 'replace').strip()[:400]}"
        )
    return proc.stdout if binary_output else proc.stdout.decode("utf-8", "replace")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgb24_plane_sha256(path: Path) -> str:
    """解码成 RGB24 原始平面后的哈希：与容器、编码器、有无 alpha 通道都无关。"""
    raw = run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        binary_output=True,
    )
    assert isinstance(raw, bytes)
    return hashlib.sha256(raw).hexdigest()


def pixel_dimensions(path: Path) -> tuple[int, int]:
    out = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    width = int(re.search(r"pixelWidth:\s*(\d+)", out).group(1))  # type: ignore[union-attr]
    height = int(re.search(r"pixelHeight:\s*(\d+)", out).group(1))  # type: ignore[union-attr]
    return width, height


def color_profile(path: Path) -> str | None:
    out = run(["sips", "-g", "profile", str(path)])
    match = re.search(r"profile:\s*(.+)", out)
    return match.group(1).strip() if match else None


def alpha_range(path: Path) -> tuple[int, int]:
    """返回 alpha 通道的 (最小值, 最大值)；没有 alpha 通道时视为全不透明。"""
    probe = run(["sips", "-g", "hasAlpha", str(path)])
    if re.search(r"hasAlpha:\s*no", probe, re.IGNORECASE):
        return 255, 255
    raw = run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(path),
            "-vf", "alphaextract", "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ],
        binary_output=True,
    )
    assert isinstance(raw, bytes)
    if not raw:
        raise ToolError(f"alpha 通道读取为空: {path}")
    return min(raw), max(raw)


def fidelity_metrics(reference: Path, candidate: Path) -> dict[str, float]:
    """用 ffmpeg 在 RGB 空间比对解码后的候选图与原始图。

    psnr / ssim 的统计行是 info 级日志（写在 stderr），用 `-v error` 会让正则匹配不到而
    静默退化成 0 分，所以这里显式取 info 级输出。
    """

    def measure(filter_expr: str) -> str:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-v", "info",
                "-i", str(candidate), "-i", str(reference),
                "-lavfi", filter_expr, "-f", "null", "-",
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ToolError(
                f"ffmpeg 保真度度量失败 ({proc.returncode}): {filter_expr}\n"
                f"stderr: {proc.stderr.decode('utf-8', 'replace').strip()[:300]}"
            )
        return proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")

    match = re.search(
        r"average:\s*([0-9.]+|inf)", measure("[0]format=rgb24[a];[1]format=rgb24[b];[a][b]psnr")
    )
    if not match:
        raise ToolError("无法解析 ffmpeg PSNR 输出")
    metrics = {"psnr_db": float("inf") if match.group(1) == "inf" else float(match.group(1))}
    match = re.search(
        r"All:\s*([0-9.]+)", measure("[0]format=rgb24[a];[1]format=rgb24[b];[a][b]ssim")
    )
    if not match:
        raise ToolError("无法解析 ffmpeg SSIM 输出")
    metrics["ssim"] = float(match.group(1))
    return metrics


@dataclass
class AssetResult:
    asset_name: str
    source_filename: str
    status: str
    tier: str
    reason: str | None = None
    source_bytes: int = 0
    encoded_bytes: int = 0
    source_sha256: str = ""
    encoded_sha256: str = ""
    width: int = 0
    height: int = 0
    alpha_removed: bool = False
    pixel_identity: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    encoded_filename: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "asset_name": self.asset_name,
            "tier": self.tier,
            "source_filename": self.source_filename,
            "status": self.status,
            "source_bytes": self.source_bytes,
            "source_sha256": self.source_sha256,
            "width": self.width,
            "height": self.height,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.status == "accepted":
            payload.update(
                {
                    "encoded_filename": self.encoded_filename,
                    "encoded_bytes": self.encoded_bytes,
                    "encoded_sha256": self.encoded_sha256,
                    "alpha_channel_removed": self.alpha_removed,
                    "bytes_ratio": round(self.source_bytes / self.encoded_bytes, 3) if self.encoded_bytes else None,
                }
            )
            if self.pixel_identity:
                payload["pixel_identity"] = self.pixel_identity
            if self.metrics:
                payload["fidelity"] = self.metrics
        return payload


def discover_imagesets() -> list[Path]:
    return sorted(
        path
        for path in ASSETS_ROOT.glob("*.imageset")
        if is_photographic_asset(path.name.removesuffix(".imageset"))
    )


def _single_png_payload(imageset: Path) -> tuple[dict[str, Any], Path, dict[str, Any]] | None:
    contents_path = imageset / "Contents.json"
    contents = json.loads(contents_path.read_text(encoding="utf-8"))
    entries = [
        entry
        for entry in contents.get("images", [])
        if entry.get("filename") and str(entry["filename"]).lower().endswith(".png")
    ]
    if len(entries) != 1:
        return None
    return contents, contents_path, entries[0]


def encode_lossless(imageset: Path, *, apply: bool, workdir: Path) -> AssetResult:
    asset_name = imageset.name.removesuffix(".imageset")
    payload = _single_png_payload(imageset)
    if payload is None:
        return AssetResult(asset_name, "", "skipped", "lossless", "png_payload_count != 1")
    _, _, entry = payload
    source = imageset / str(entry["filename"])

    result = AssetResult(
        asset_name=asset_name,
        source_filename=source.name,
        status="pending",
        tier="lossless",
        source_bytes=source.stat().st_size,
        source_sha256=sha256_of(source),
    )
    result.width, result.height = pixel_dimensions(source)

    lo, hi = alpha_range(source)
    if lo != hi or lo != 255:
        result.status = "skipped"
        result.reason = f"alpha_in_use(min={lo},max={hi})"
        return result

    candidate = workdir / f"{source.stem}.repacked.png"
    run(
        [
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(source),
            "-pix_fmt", "rgb24", "-compression_level", "9", str(candidate), "-y",
        ]
    )

    if pixel_dimensions(candidate) != (result.width, result.height):
        result.status = "rejected"
        result.reason = "dimension_drift"
        return result

    before = rgb24_plane_sha256(source)
    after = rgb24_plane_sha256(candidate)
    if before != after:
        result.status = "rejected"
        result.reason = "pixel_identity_violated"
        return result
    result.pixel_identity = f"rgb24_plane_sha256={after}"

    if color_profile(source) != color_profile(candidate):
        result.status = "rejected"
        result.reason = f"color_profile_changed({color_profile(source)} -> {color_profile(candidate)})"
        return result

    if candidate.stat().st_size >= result.source_bytes:
        result.status = "skipped"
        result.reason = "no_size_gain"
        return result

    result.alpha_removed = True
    result.encoded_filename = source.name
    result.encoded_bytes = candidate.stat().st_size
    result.metrics = fidelity_metrics(source, candidate)

    if apply:
        shutil.copy2(candidate, source)
        result.encoded_bytes = source.stat().st_size
        result.encoded_sha256 = sha256_of(source)
    else:
        result.encoded_sha256 = sha256_of(candidate)
    result.status = "accepted"
    return result


def encode_heic(
    imageset: Path, *, quality: int, min_psnr: float, min_ssim: float, apply: bool, workdir: Path
) -> AssetResult:
    asset_name = imageset.name.removesuffix(".imageset")
    payload = _single_png_payload(imageset)
    if payload is None:
        return AssetResult(asset_name, "", "skipped", "heic", "png_payload_count != 1")
    contents, contents_path, entry = payload
    source = imageset / str(entry["filename"])

    result = AssetResult(
        asset_name=asset_name,
        source_filename=source.name,
        status="pending",
        tier="heic",
        source_bytes=source.stat().st_size,
        source_sha256=sha256_of(source),
    )
    result.width, result.height = pixel_dimensions(source)

    lo, hi = alpha_range(source)
    if lo != hi or lo != 255:
        result.status = "skipped"
        result.reason = f"alpha_in_use(min={lo},max={hi})"
        return result

    heic_path = workdir / f"{source.stem}.heic"
    decoded = workdir / f"{source.stem}.decoded.png"
    run(["sips", "-s", "format", "heic", "-s", "formatOptions", str(quality), str(source), "--out", str(heic_path)])
    run(["sips", "-s", "format", "png", str(heic_path), "--out", str(decoded)])

    if pixel_dimensions(decoded) != (result.width, result.height):
        result.status = "rejected"
        result.reason = "dimension_drift"
        return result

    result.metrics = fidelity_metrics(source, decoded)
    psnr = result.metrics.get("psnr_db", 0.0)
    ssim = result.metrics.get("ssim", 0.0)
    if psnr < min_psnr or ssim < min_ssim:
        result.status = "rejected"
        result.reason = f"fidelity_below_threshold(psnr={psnr:.2f},ssim={ssim:.5f})"
        return result

    result.encoded_filename = source.with_suffix(".heic").name
    result.encoded_bytes = heic_path.stat().st_size
    result.encoded_sha256 = sha256_of(heic_path)

    if apply:
        target = imageset / result.encoded_filename
        shutil.copy2(heic_path, target)
        entry["filename"] = result.encoded_filename
        contents_path.write_text(
            json.dumps(contents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        source.unlink()
        result.encoded_sha256 = sha256_of(target)
        result.encoded_bytes = target.stat().st_size
    result.status = "accepted"
    return result


def catalog_payload_matches(imageset: Path, expected_sha256: str) -> bool:
    """与 finish_*_artwork.py 的 catalog evidence 同口径：目录里实际放的载荷必须与记录一致。"""
    contents = json.loads((imageset / "Contents.json").read_text(encoding="utf-8"))
    for entry in contents.get("images", []):
        filename = entry.get("filename")
        if filename and (imageset / filename).is_file():
            return sha256_of(imageset / filename) == expected_sha256
    return False


def patch_provenance(results: list[AssetResult], *, quality: int | None, report_path: Path) -> list[str]:
    accepted = {item.asset_name: item for item in results if item.status == "accepted"}
    if not accepted:
        return []
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated: list[str] = []
    for path in sorted(PROVENANCE_DIR.glob("*.provenance.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        touched = False
        for derivative in data.get("derivatives", []):
            item = accepted.get(derivative.get("asset_name"))
            if not item:
                continue
            derivative["sha256"] = item.encoded_sha256
            derivative["bytes"] = item.encoded_bytes
            if item.tier == "lossless":
                derivative["lossless_repack"] = {
                    "stage": "runtime_catalog_lossless_repack",
                    "encoder": "ffmpeg png (zlib level 9)",
                    "alpha_channel_removed": item.alpha_removed,
                    "alpha_was_uniformly_opaque": True,
                    "pixel_identity": item.pixel_identity,
                    "bytes_before": item.source_bytes,
                    "bytes_after": item.encoded_bytes,
                    "recorded_at": recorded_at,
                    "evidence_report": str(report_path.relative_to(REPO_ROOT)),
                }
            else:
                derivative["container"] = "HEIC"
                derivative["runtime_encoding"] = {
                    "codec": "HEIC",
                    "encoder": "sips (ImageIO)",
                    "quality": quality,
                    "source_container": "PNG",
                    "source_sha256": item.source_sha256,
                    "source_bytes": item.source_bytes,
                    "fidelity": {
                        "method": "decode with ImageIO (sips) then ffmpeg psnr/ssim in rgb24",
                        "psnr_db": round(item.metrics.get("psnr_db", 0.0), 3),
                        "ssim": round(item.metrics.get("ssim", 0.0), 6),
                    },
                    "recorded_at": recorded_at,
                    "evidence_report": str(report_path.relative_to(REPO_ROOT)),
                    "requires_visual_signoff": True,
                }
            derivative["catalog_payload_verified"] = catalog_payload_matches(
                ASSETS_ROOT / f"{item.asset_name}.imageset", item.encoded_sha256
            )
            touched = True
        if touched:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            updated.append(path.name)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", choices=("lossless", "heic"), default="lossless")
    parser.add_argument("--quality", type=int, default=100, help="HEIC 质量（默认 100：更低档实测画质不达标）")
    parser.add_argument("--min-psnr", type=float, default=48.0, help="HEIC 接受门槛 PSNR(dB)，默认 48")
    parser.add_argument("--min-ssim", type=float, default=0.995, help="HEIC 接受门槛 SSIM，默认 0.995")
    parser.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    parser.add_argument("--update-provenance", action="store_true", help="同步更新 provenance 记录")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.tier == "heic" and args.apply and not args.update_provenance:
        print("拒绝执行：HEIC 档必须同时更新 provenance（--update-provenance）。", file=sys.stderr)
        return 2

    imagesets = discover_imagesets()
    if not imagesets:
        print("未发现符合条件的 imageset。", file=sys.stderr)
        return 1

    report_path = args.report or (
        QA_DIR / f"runtime_{args.tier}_repack_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    )
    results: list[AssetResult] = []
    with tempfile.TemporaryDirectory(prefix="wom-reencode-") as tmp:
        workdir = Path(tmp)
        for imageset in imagesets:
            if args.tier == "lossless":
                result = encode_lossless(imageset, apply=args.apply, workdir=workdir)
            else:
                result = encode_heic(
                    imageset,
                    quality=args.quality,
                    min_psnr=args.min_psnr,
                    min_ssim=args.min_ssim,
                    apply=args.apply,
                    workdir=workdir,
                )
            results.append(result)
            if result.status == "accepted":
                extra = ""
                if result.metrics:
                    extra = f" PSNR {result.metrics.get('psnr_db', 0.0):.2f} dB SSIM {result.metrics.get('ssim', 0.0):.5f}"
                print(
                    f"[accepted] {result.asset_name}: {result.source_bytes / 1048576:.2f} MB -> "
                    f"{result.encoded_bytes / 1048576:.2f} MB "
                    f"({result.source_bytes / result.encoded_bytes:.2f}x){extra}"
                )
            else:
                print(f"[{result.status}] {result.asset_name}: {result.reason}")

    accepted = [item for item in results if item.status == "accepted"]
    totals: dict[str, Any] = {
        "candidates": len(results),
        "accepted": len(accepted),
        "skipped": sum(1 for item in results if item.status == "skipped"),
        "rejected": sum(1 for item in results if item.status == "rejected"),
        "bytes_before": sum(item.source_bytes for item in accepted),
        "bytes_after": sum(item.encoded_bytes for item in accepted),
    }
    if totals["bytes_after"]:
        totals["bytes_saved"] = totals["bytes_before"] - totals["bytes_after"]
        totals["compression_ratio"] = round(totals["bytes_before"] / totals["bytes_after"], 3)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "docs/05_UI/artwork/tools/reencode_runtime_assets.py",
        "tier": args.tier,
        "mode": "apply" if args.apply else "dry-run",
        "quality": args.quality if args.tier == "heic" else None,
        "thresholds": (
            {"min_psnr_db": args.min_psnr, "min_ssim": args.min_ssim} if args.tier == "heic" else None
        ),
        "policy": "lossless 档要求逐像素一致；heic 档要求保真度达标且经人工视觉签核。",
        "totals": totals,
        "assets": [item.as_dict() for item in results],
    }

    if args.apply:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_touched: list[str] = []
        if args.update_provenance:
            provenance_touched = patch_provenance(
                results, quality=args.quality if args.tier == "heic" else None, report_path=report_path
            )
        report["provenance_updated"] = provenance_touched
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n报告已写入 {report_path.relative_to(REPO_ROOT)}")
        if provenance_touched:
            print(f"provenance 已更新：{len(provenance_touched)} 份")
    else:
        print("\n（dry-run：未写入任何文件；加 --apply 才落盘）")

    print(json.dumps(totals, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
