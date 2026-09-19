#!/usr/bin/env python3
"""Capture real macOS Component Gallery runtime screenshots.

The app is relaunched for every specimen. UserDefaults select the verification scenario and
requested default window size before launch, so capture does not depend on Accessibility-driven
clicking or scrolling. Only the process launched by this script is ever terminated.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parents[2]
SCENE_HELPER = DEFAULT_REPO_ROOT / "docs/05_UI/artwork/tools/capture_scene_runtime_evidence.py"
WINDOW_HELPER_SOURCE = r"""import CoreGraphics
import Foundation

guard CommandLine.arguments.count > 1, let wantedPID = Int(CommandLine.arguments[1]) else {
    FileHandle.standardError.write(Data("usage: window_identity_by_pid.swift <pid>\\n".utf8))
    exit(2)
}

guard let windows = CGWindowListCopyWindowInfo(
    [.optionOnScreenOnly, .excludeDesktopElements],
    kCGNullWindowID
) as? [[String: Any]] else {
    exit(1)
}

for window in windows {
    let pid = window[kCGWindowOwnerPID as String] as? Int ?? -1
    guard pid == wantedPID else { continue }
    let number = window[kCGWindowNumber as String] as? Int ?? -1
    let layer = window[kCGWindowLayer as String] as? Int ?? -1
    let bounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let width = Int((bounds["Width"] as? Double ?? 0).rounded())
    let height = Int((bounds["Height"] as? Double ?? 0).rounded())
    print(
        "{\\\"window_number\\\": \\(number), \\\"pid\\\": \\(pid), "
            + "\\\"width\\\": \\(width), \\\"height\\\": \\(height), \\\"layer\\\": \\(layer)}"
    )
}
"""

spec = importlib.util.spec_from_file_location("wom_scene_capture", SCENE_HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot import capture helpers: {SCENE_HELPER}")
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)

ENABLED_KEY = "wom.gallery.verification.enabled"
SCENARIO_KEY = "wom.gallery.verification.scenario"
WIDTH_KEY = "wom.gallery.verification.width"
HEIGHT_KEY = "wom.gallery.verification.height"


@dataclass(frozen=True)
class CaptureSpec:
    scenario: str
    width: int
    height: int

    @property
    def filename(self) -> str:
        return f"{self.scenario}-{self.width}x{self.height}.jpg"


def capture_plan() -> List[CaptureSpec]:
    # Five priority components at the product default; flagship physical/artifact surfaces also
    # cover minimum and spacious widths to expose compression or excess-empty-space defects.
    return [
        CaptureSpec("pendulum", 960, 640),
        CaptureSpec("pendulum", 1180, 760),
        CaptureSpec("pendulum", 1440, 900),
        CaptureSpec("tarot", 1180, 760),
        CaptureSpec("probability-die", 960, 640),
        CaptureSpec("probability-die", 1180, 760),
        CaptureSpec("probability-die", 1440, 900),
        CaptureSpec("worldline", 1180, 760),
        CaptureSpec("character-codex", 1180, 760),
    ]


def run(command: Sequence[str], *, check: bool = True, timeout: float = 180.0):
    return helpers.run(command, check=check, timeout=timeout)


def write_preferences(bundle_id: str, item: CaptureSpec) -> None:
    commands = [
        ["defaults", "write", bundle_id, ENABLED_KEY, "-bool", "true"],
        ["defaults", "write", bundle_id, SCENARIO_KEY, "-string", item.scenario],
        ["defaults", "write", bundle_id, WIDTH_KEY, "-float", str(item.width)],
        ["defaults", "write", bundle_id, HEIGHT_KEY, "-float", str(item.height)],
    ]
    for command in commands:
        run(command)


def clear_preferences(bundle_id: str) -> None:
    for key in (ENABLED_KEY, SCENARIO_KEY, WIDTH_KEY, HEIGHT_KEY):
        run(["defaults", "delete", bundle_id, key], check=False)


def windows_for_pid(pid: int, window_tool: Path) -> List[Dict[str, int]]:
    result = run(["swift", str(window_tool), str(pid)], check=False)
    windows: List[Dict[str, int]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            windows.append(json.loads(line))
    return windows


def primary_window(pid: int, window_tool: Path, timeout: float = 30.0) -> Dict[str, int]:
    deadline = time.time() + timeout
    seen: List[Dict[str, int]] = []
    while time.time() < deadline:
        seen = windows_for_pid(pid, window_tool)
        candidates = [
            window
            for window in seen
            if window.get("layer") == 0
            and window.get("width", 0) >= 500
            and window.get("height", 0) >= 400
        ]
        if candidates:
            return max(candidates, key=lambda item: item["width"] * item["height"])
        time.sleep(0.4)
    raise RuntimeError(f"no primary layer-0 window for pid {pid}; seen={seen}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    app_path = Path(args.app).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    window_tool = out_dir / "window_identity_by_pid.swift"
    window_tool.write_text(WINDOW_HELPER_SOURCE, encoding="utf-8")

    executable = helpers.app_executable(app_path)
    app_name = app_path.stem
    helpers.ensure_no_instance(app_name, executable)
    helpers.install_cleanup_handlers(app_name, executable)

    captures: Dict[str, Dict[str, Any]] = {}
    try:
        for item in capture_plan():
            write_preferences(args.bundle_id, item)
            pid = helpers.launch_app(app_name, app_path, executable)
            try:
                window = primary_window(pid, window_tool)
                time.sleep(1.0)
                destination = out_dir / item.filename
                helpers.capture_window(int(window["window_number"]), destination)
                pixel_width, pixel_height = helpers.pixel_size(destination)
                captures[item.filename] = {
                    "scenario": item.scenario,
                    "requested_window_points": [item.width, item.height],
                    "observed_window_points": [window["width"], window["height"]],
                    "pixel_size": [pixel_width, pixel_height],
                    "sha256": helpers.sha256_of(destination),
                }
                print(
                    f"[gallery-capture] {item.filename} "
                    f"requested={item.width}x{item.height}pt "
                    f"observed={window['width']}x{window['height']}pt "
                    f"pixels={pixel_width}x{pixel_height}",
                    flush=True,
                )
            finally:
                helpers.quit_app(args.bundle_id, app_name, executable)
                clear_preferences(args.bundle_id)
    finally:
        clear_preferences(args.bundle_id)
        helpers.terminate_owned_instances(app_name, executable)
        helpers.assert_no_residue(app_name, executable)

    summary = {
        "source_head": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "app": str(app_path),
        "capture_count": len(captures),
        "captures": captures,
    }
    (out_dir / "capture-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[gallery-capture] wrote {len(captures)} captures to {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
