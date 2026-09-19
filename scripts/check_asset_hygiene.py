#!/usr/bin/env python3
"""资产卫生门禁：阻止仓库被大体积二进制无声撑大。

为什么需要
----------
美术资产会持续推进（场景、神器、后续卡牌内容），而在此之前的门禁档案没有任何一条检查
文件体积：仓库可以在没人注意的情况下从 193 MB 长到几个 GB，代价是每次 clone、每个 CI
job 的下载量以及 GitHub 对仓库健康度的干预。

检查项
------
1. **单文件预算**（硬失败）：任何入库文件的体积不得超过 `--max-file-mib`（默认 20 MiB）。
   GitHub 在 50 MiB 会告警、100 MiB 直接拒绝推送，本阈值留出明显余量，目的是在触线之前
   就被拦住，而不是等平台报错。
2. **二进制总量预算**（硬失败）：入库的图片/音频/视频/字体等二进制合计不得超过
   `--max-total-mib`（默认 200 MiB）。
3. **本机资产存在性**（默认仅报告）：`docs/05_UI/assets/` 与 `docs/05_UI/artwork/workbench/`
   是不入库的本机资产，本地跑时报告是否在位；加 `--strict-local` 才把缺失视为失败
   （CI 上必然缺失，因此默认不失败）。

用法
----
    python3 scripts/check_asset_hygiene.py            # CI / 门禁用
    python3 scripts/check_asset_hygiene.py --strict-local   # 本机完整核验
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff", ".tif", ".bmp", ".heic", ".avif",
    ".icns", ".ico", ".pdf", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".mp4", ".mov",
    ".ttf", ".otf", ".woff", ".woff2", ".sqlite", ".db", ".zip", ".tar", ".gz",
}

# 不入库的本机资产目录：必须留在项目目录内、由 .gitignore 排除。
LOCAL_ONLY_DIRS = (
    "docs/05_UI/assets/01_概念参考",
    "docs/05_UI/assets/02_img_gen",
    "docs/05_UI/artwork/workbench",
)


def tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
    )
    return [item for item in proc.stdout.decode("utf-8").split("\0") if item]


def human(mebibytes: float) -> str:
    return f"{mebibytes:.1f} MiB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-file-mib", type=float, default=20.0)
    parser.add_argument("--max-total-mib", type=float, default=200.0)
    parser.add_argument("--warn-total-mib", type=float, default=170.0)
    parser.add_argument("--strict-local", action="store_true")
    args = parser.parse_args(argv)

    files = tracked_files()
    failures: list[str] = []
    biggest: list[tuple[float, str]] = []
    total = 0.0
    binary_count = 0

    for relative in files:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        size_mib = path.stat().st_size / 1048576
        biggest.append((size_mib, relative))
        if path.suffix.lower() in BINARY_SUFFIXES:
            total += size_mib
            binary_count += 1
        if size_mib > args.max_file_mib:
            failures.append(
                f"单文件超预算：{relative} = {human(size_mib)} > {human(args.max_file_mib)}"
            )

    biggest.sort(reverse=True)
    print("== 入库二进制资产 ==")
    print(f"文件数：{binary_count}    合计：{human(total)}    "
          f"预算：{human(args.max_total_mib)}（告警线 {human(args.warn_total_mib)}）")
    print("体积 top 5：")
    for size_mib, relative in biggest[:5]:
        print(f"  {human(size_mib):>10}  {relative}")

    if total > args.max_total_mib:
        failures.append(
            f"二进制总量超预算：{human(total)} > {human(args.max_total_mib)}；"
            "请按 docs/05_UI/artwork/Asset_Storage_Policy_v1.0.md 分层，把母版/中间产物留在 workbench/"
        )
    elif total > args.warn_total_mib:
        print(f"⚠️  二进制总量已接近预算（{human(total)} / {human(args.max_total_mib)}），"
              "下次新增资产前先看存储策略。")

    print("\n== 本机资产（不入库，应留在项目目录内）==")
    for relative in LOCAL_ONLY_DIRS:
        path = REPO_ROOT / relative
        if path.is_dir():
            payloads = [p for p in path.rglob("*") if p.is_file()]
            size_mib = sum(p.stat().st_size for p in payloads) / 1048576
            print(f"  ✅ {relative}: {len(payloads)} 个文件 / {human(size_mib)}")
        else:
            message = f"  {'❌' if args.strict_local else 'ℹ️ '} {relative}: 本机不存在"
            print(message)
            if args.strict_local:
                failures.append(f"本机资产缺失：{relative}")

    print()
    if failures:
        print("资产卫生门禁失败：")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("资产卫生门禁通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
