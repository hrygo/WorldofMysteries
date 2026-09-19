#!/usr/bin/env python3
"""为「不入库但必须留在项目目录内」的美术母版生成/校验 manifest。

母版（4K/6K）体积在 GB 量级，按 `Asset_Storage_Policy_v1.0.md` 不进 Git；但"不进 Git"
不等于"可以不可追溯"。本工具把 `workbench/` 里的母版逐个记录为
（相对路径、字节数、SHA256），并可选地与 provenance 中登记的 `master.sha256` 交叉核对，
从而在没有二进制进仓库的前提下，仍能回答两个问题：

    1. 这台机器上的母版还在不在、有没有被改动？
    2. 现存的母版是否就是当初审批通过的那一份？

manifest 只含文本与哈希，不含绝对路径，因此可以随仓库分发。

用法
----
    python3 docs/05_UI/artwork/tools/local_store_manifest.py generate
    python3 docs/05_UI/artwork/tools/local_store_manifest.py verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]

REPO_ROOT = DEFAULT_REPO_ROOT
WORKBENCH = REPO_ROOT / "docs/05_UI/artwork/workbench"
PROVENANCE_DIR = REPO_ROOT / "docs/05_UI/artwork/provenance"
# manifest 自身入库（只含文本与哈希），母版本体才是不入库的 workbench。
MANIFEST = REPO_ROOT / "docs/05_UI/artwork/local_store_manifest.json"


def set_repo_root(root: Path) -> None:
    """允许对另一个 checkout（例如主工作区）的母版库生成/校验 manifest。

    母版是不入库的本机资产，只存在于持有它们的那个 checkout 里；从隔离工作区执行本工具时，
    需要用 --repo-root 指向真正存放母版的仓库根目录。
    """
    global REPO_ROOT, WORKBENCH, PROVENANCE_DIR, MANIFEST
    REPO_ROOT = root.resolve()
    WORKBENCH = REPO_ROOT / "docs/05_UI/artwork/workbench"
    PROVENANCE_DIR = REPO_ROOT / "docs/05_UI/artwork/provenance"
    MANIFEST = REPO_ROOT / "docs/05_UI/artwork/local_store_manifest.json"

# 母版文件命名约定（来自 finish_world_artwork.py / finish_artifact_artwork.py）。
MASTER_PATTERN = re.compile(r"^(?P<task>[AW]\d{1,2})_(?P<stage>MASTER_\d+x\d+|\d{2}_[a-z]+).*\.(png|jpg|jpeg|tiff)$")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_master_hashes() -> dict[str, str]:
    """任务前缀（W1 / A01）-> master.sha256（仅取登记了哈希的条目）。

    provenance 用 `W1_WORLD_HERO` / `A01_ARRODES_MIRROR` 这类 artwork_id，而工作目录里的
    文件名只带 `W1_MASTER_4096x2560.png` 这样的任务前缀，因此按前缀归并；前缀后必须紧跟
    下划线，避免 `W1` 误配到 `W10`。
    """
    result: dict[str, str] = {}
    for path in sorted(PROVENANCE_DIR.glob("*.provenance.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        master = data.get("master") or {}
        artwork_id = data.get("artwork_id", "")
        if master.get("sha256") and "_" in artwork_id:
            result[artwork_id.split("_", 1)[0]] = master["sha256"]
    return result


def survey() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not WORKBENCH.is_dir():
        return entries
    for path in sorted(p for p in WORKBENCH.rglob("*") if p.is_file()):
        if path.name == MANIFEST.name:
            continue
        match = MASTER_PATTERN.match(path.name)
        entries.append(
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "task": match.group("task") if match else None,
                "stage": match.group("stage") if match else None,
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
            }
        )
    return entries


def command_generate(entries: list[dict[str, Any]]) -> int:
    known = provenance_master_hashes()
    for entry in entries:
        task = entry.get("task")
        expected = known.get(task) if task else None
        entry["provenance_master_sha256"] = expected
        entry["matches_provenance_master"] = (entry["sha256"] == expected) if expected else None
    manifest = {
        "$comment": "本机母版库索引；不含二进制、不含绝对路径。策略见 ../Asset_Storage_Policy_v1.0.md",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": "docs/05_UI/artwork/workbench",
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "entries": entries,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    matched = sum(1 for entry in entries if entry["matches_provenance_master"])
    print(f"已写入 {MANIFEST.relative_to(REPO_ROOT)}：{len(entries)} 个文件，"
          f"{manifest['total_bytes'] / 1073741824:.2f} GB，与 provenance 母版哈希一致 {matched} 个")
    return 0


def command_verify() -> int:
    if not MANIFEST.is_file():
        print(f"缺少 manifest：{MANIFEST.relative_to(REPO_ROOT)}，先执行 generate。", file=sys.stderr)
        return 1
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recorded_by_path = {entry["path"]: entry for entry in recorded.get("entries", [])}
    problems: list[str] = []
    for path, entry in recorded_by_path.items():
        absolute = REPO_ROOT / path
        if not absolute.is_file():
            problems.append(f"母版缺失：{path}")
            continue
        if sha256_of(absolute) != entry["sha256"]:
            problems.append(f"母版被改动（SHA256 不一致）：{path}")
    for entry in survey():
        if entry["path"] not in recorded_by_path:
            problems.append(f"manifest 未登记的新文件：{entry['path']}")
    known = provenance_master_hashes()
    for entry in recorded_by_path.values():
        task = entry.get("task")
        # 只有 MASTER_ 阶段的文件才应该等于 provenance 里登记的母版哈希；
        # crop / super-resolution / grade 等中间产物本来就与母版不同。
        stage = entry.get("stage") or ""
        if task and stage.startswith("MASTER") and task in known and known[task] != entry["sha256"]:
            problems.append(f"与 provenance 登记的母版哈希不一致：{entry['path']}")
    if problems:
        print("母版库校验失败：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(f"母版库校验通过：{len(recorded_by_path)} 个文件与 manifest、provenance 一致。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    args = parser.parse_args(argv)
    set_repo_root(args.repo_root)
    if args.command == "generate":
        return command_generate(survey())
    return command_verify()


if __name__ == "__main__":
    raise SystemExit(main())
