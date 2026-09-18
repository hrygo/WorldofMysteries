#!/usr/bin/env python3
"""Verify approved source bytes and stage them; never generate or approve shipping art."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import tempfile
import zlib

MAX_SOURCE_BYTES = 64 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_path(root: Path, name: str) -> Path:
    require(isinstance(name, str) and bool(name), "Empty/non-string source path")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and ".." not in relative.parts
            and "\\" not in name and ":" not in name, f"Unsafe relative path: {name}")
    base = root.resolve()
    result = base.joinpath(*relative.parts)
    require(result.resolve().is_relative_to(base), f"Path escapes root: {name}")
    cursor = base
    for part in relative.parts:
        cursor /= part
        require(not cursor.is_symlink(), f"Symlink refused: {name}")
    return result


def png_container_size(data: bytes) -> tuple[int, int]:
    """Check PNG structure/CRCs; this is transport validation, not visual QA."""
    require(len(data) <= MAX_SOURCE_BYTES, "Source exceeds byte limit")
    require(data.startswith(PNG_SIGNATURE), "Not a PNG")
    offset, dimensions, saw_data, ended = 8, None, False, False
    while offset < len(data):
        require(offset + 12 <= len(data), "Truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + length + 12
        require(end <= len(data), "Truncated PNG payload")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, "PNG CRC mismatch")
        if dimensions is None:
            require(kind == b"IHDR" and length == 13, "Missing PNG IHDR")
            dimensions = struct.unpack_from(">II", payload)
            require(all(0 < n <= 32768 for n in dimensions), "Invalid PNG dimensions")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG IHDR")
        require(kind != b"acTL", "Animated PNG is not an approved source format")
        saw_data |= kind == b"IDAT"
        offset = end
        if kind == b"IEND":
            require(length == 0 and saw_data and offset == len(data), "Invalid PNG ending")
            ended = True
            break
    require(ended and dimensions is not None, "Incomplete PNG")
    return dimensions


def validate_manifest(manifest: dict, registry_text: str | None = None) -> None:
    require(manifest.get("schema_version") == 1, "Unsupported manifest schema")
    sources = manifest["sources"]
    require(len(sources) == 6, "This approved intake must contain six sources")
    ids, filenames, hashes = set(), set(), set()
    for source in sources:
        sid = source["source_id"]
        require(sid not in ids, "Duplicate source ID")
        require(source["filename"] not in filenames, "Duplicate source path")
        require(source["sha256"] not in hashes, "Duplicate source image")
        safe_path(Path.cwd(), source["filename"])
        require(re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is not None, "Invalid SHA256")
        require(type(source["byte_size"]) is int
                and 0 < source["byte_size"] <= MAX_SOURCE_BYTES, "Invalid byte size")
        require(all(type(source[k]) is int and 0 < source[k] <= 32768
                    for k in ("width", "height")), "Invalid dimensions")
        require(source["visual_approval"] == "USER_APPROVED", "Missing visual approval")
        require(source["shipping_approved"] is False, "Source approval cannot approve shipping")
        ids.add(sid); filenames.add(source["filename"]); hashes.add(source["sha256"])
    worlds, artifacts = manifest["world_targets"], manifest["artifact_targets"]
    require(len(worlds) == 6 and len(artifacts) == 15, "Expected 6 world and 15 Artifact targets")
    require([w["task_id"] for w in worlds] == [f"W{i}" for i in range(1, 7)], "World task IDs drifted")
    require([a["order"] for a in artifacts] == list(range(1, 16)), "Artifact order drifted")
    require([a["phase"] for a in artifacts] == ["P0"] * 7 + ["P1"] * 8, "P0/P1 boundary drifted")
    targets = worlds + artifacts
    require(len({t["asset_name"] for t in targets}) == 21, "Duplicate runtime identity")
    assigned = [t["source_id"] for t in targets if t["source_id"] is not None]
    require(len(assigned) == len(set(assigned)) and set(assigned) <= ids, "Invalid source binding")
    supplemental = manifest["supplemental_sources"]
    require(len(supplemental) == len(set(supplemental)), "Duplicate supplemental source")
    require(set(supplemental) == ids - set(assigned), "Supplemental images must not fill missing slots")
    for target in targets:
        require(target["shipping_approved"] is False, "Intake cannot approve shipping")
    roles = {s["source_id"]: s["role"] for s in sources}
    allowed_roles = {"W1": "world_hero", "W3": "ritual_altar_candidate", "W4": "codex_archive_candidate"}
    for target in worlds:
        if target["source_id"] is not None:
            require(roles[target["source_id"]] == allowed_roles.get(target["task_id"]),
                    "Source scene semantics do not match the runtime target")
    require(worlds[0]["wide_anchor"] == "top", "W1 must preserve the crimson moon")
    if registry_text is not None:
        registry = dict(re.findall(r'case\s+(\w+)\s*=\s*"(wom\.art\.[^"]+)"', registry_text))
        actual = {t.get("registry_case", t.get("artifact_id")): t["asset_name"] for t in targets}
        require(actual == registry, "Manifest differs from the real typed artwork registry")


def verify_sources(manifest: dict, source_dir: Path) -> list[dict]:
    validate_manifest(manifest)
    records = []
    for source in manifest["sources"]:
        path = safe_path(source_dir, source["filename"])
        require(path.is_file(), f"Missing original source: {source['source_id']}")
        require(path.stat().st_size == source["byte_size"], f"Byte size mismatch: {source['source_id']}")
        with path.open("rb") as stream:
            data = stream.read(MAX_SOURCE_BYTES + 1)
        require(hashlib.sha256(data).hexdigest() == source["sha256"], f"SHA256 mismatch: {source['source_id']}")
        require(png_container_size(data) == (source["width"], source["height"]), "Dimension mismatch")
        records.append({"source_id": source["source_id"], "sha256": source["sha256"], "transport_verified": True})
    return records


def stage_sources(manifest: dict, source_dir: Path, destination: Path) -> None:
    verify_sources(manifest, source_dir)
    require(not destination.is_symlink() and not destination.exists(), "Destination exists; refusing overwrite")
    require(not any(p.endswith(".xcassets") or p.endswith(".imageset") for p in destination.parts),
            "Source intake must not write an Asset Catalog")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / (destination.name + ".intake.lock")
    with lock.open("x"):
        try:
            require(not destination.exists(), "Destination appeared during intake")
            with tempfile.TemporaryDirectory(prefix=".art-intake-", dir=destination.parent) as temp:
                staged = Path(temp) / "bundle"
                staged.mkdir()
                for source in manifest["sources"]:
                    target = safe_path(staged, source["filename"])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(safe_path(source_dir, source["filename"]), target)
                records = verify_sources(manifest, staged)
                (staged / "approved_sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
                (staged / "INTAKE_COMPLETE.json").write_text(json.dumps({"source_transport": records, "shipping_approved": False}, indent=2) + "\n")
                require(not destination.exists(), "Destination appeared during intake")
                os.rename(staged, destination)
        finally:
            lock.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["manifest", "verify", "stage"])
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("approved_sources.json"))
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--stage-dir", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        validate_manifest(manifest, args.registry.read_text() if args.registry else None)
        if args.operation != "manifest":
            require(args.source_dir is not None, "--source-dir is required")
            verify_sources(manifest, args.source_dir)
        if args.operation == "stage":
            require(args.stage_dir is not None, "--stage-dir is required")
            stage_sources(manifest, args.source_dir, args.stage_dir)
        print(json.dumps({"operation": args.operation, "result": "SOURCE_INTAKE_OK",
                          "source_count": len(manifest["sources"]), "shipping_approved": False,
                          "pending_world_generation": [w["task_id"] for w in manifest["world_targets"] if w["source_id"] is None],
                          "pending_artifact_generation": len(manifest["artifact_targets"])}, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Source intake failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
