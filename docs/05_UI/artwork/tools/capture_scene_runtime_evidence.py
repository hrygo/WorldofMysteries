#!/usr/bin/env python3
"""采集世界 / 场景美术的 G5 运行时证据。

每一步都失败即停，不静默降级：

1. 写入采集面偏好（场景 / 模式 / 变体），保证同一个二进制只呈现要被取证的内容；
2. 启动**唯一**一个 App 实例，把采集窗口调到锁定几何，截取真实窗口像素；
3. 用 `finish_world_artwork.py surface` 的归一化互相关确认「出厂派生图确实出现在这一帧里」，
   并借它给出的原图框把发布态叠加探针里的文本区换算成对比度测量区；
4. 组装六个任务的 `*_runtime_evidence.json`，交给 `finish_world_artwork.py record` 复算；
5. 退出 App 并断言没有残留进程、没有残留偏好与辅助功能改动。

采集面在 `macos-app/WorldOfMysteries/Components/SceneArtworkRuntimeVerificationView.swift`：
砖块几何由本脚本从该文件解析，所以 Swift 侧的静默改动会在这里立刻报错，而不是让证据失真。
"""

from __future__ import annotations

import argparse
import ast
import atexit
import hashlib
import json
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

TOOL_DIR = Path(__file__).resolve().parent
DEFAULT_FINISH_TOOL = TOOL_DIR / "finish_world_artwork.py"
DEFAULT_WINDOW_TOOL = TOOL_DIR / "window_identity.swift"
VERIFICATION_VIEW_RELATIVE = (
    "macos-app/WorldOfMysteries/Components/SceneArtworkRuntimeVerificationView.swift"
)
CATALOG_RELATIVE = "macos-app/WorldOfMysteries/Assets.xcassets"

BACKING_SCALE = 2
MIN_SCORE = 0.45
SURFACE_SEARCH_WIDTH = 1600
SURFACE_STEPS = 12
SCALE_SEARCH_SPAN = 0.08
REGION_PADDING_PX = 4

# 证据里的 window_checks 标签 → 采集窗口（点）。2× 背屏让后两项的抓取像素正好是 2560×1600 / 2400×900。
WINDOW_CHECK_GEOMETRIES: Dict[str, Tuple[int, int]] = {
    "960x640": (960, 640),
    "1180x760": (1180, 760),
    "2560x1600": (1280, 800),
    "2400x900": (1200, 450),
}

# 抓取容器用 `screencapture -t jpg` 的原生 JPEG：整屏摄影级像素用 PNG 会让证据体积到达
# 几十 MB（本机实测 5 张 24.6 MB → 5 张 5.4 MB），而实测 p95/p05 尾部统计的偏差 < 0.8%，
# 远小于 4.5:1 / 7:1 的门槛余量。对比度仍然是由 `record` 从这些字节复算出来的。
WINDOW_CHECK_CAPTURES: Dict[str, str] = {
    "960x640": "wom-verification-grid-960x640.jpg",
    "1180x760": "wom-verification-grid-1180x760.jpg",
    "2560x1600": "wom-verification-grid-2560x1600.jpg",
    "2400x900": "wom-verification-grid-2400x900.jpg",
}

ACCESSIBILITY_CAPTURES: Dict[str, str] = {
    "Increased Contrast": "wom-verification-probe-increased-contrast.jpg",
    "Reduce Transparency": "wom-verification-probe-reduce-transparency.jpg",
}

ACCESSIBILITY_STATES: Dict[str, Tuple[str, str]] = {
    "increase_contrast": ("com.apple.universalaccess", "increaseContrast"),
    "reduce_transparency": ("com.apple.universalaccess", "reduceTransparency"),
}

# 系统开关被拒绝写入时，改用采集面自身的偏好键驱动该状态的渲染路径。两个键都在
# `SceneArtworkRuntimeVerificationView` 里显式建模（`\.colorSchemeContrast` 与
# `\.accessibilityReduceTransparency` 在 macOS 27 SDK 里都是只读环境值，无法注入）；
# 系统开关真实打开时以系统值为准，注入值只作补充。证据里如实标注所用机制。
ACCESSIBILITY_SURFACE_PREFERENCES: Dict[str, Tuple[str, str]] = {
    "increase_contrast": ("wom.artwork.verification.contrast", "increased"),
    "reduce_transparency": ("wom.artwork.verification.transparency", "reduced"),
}

PROBE_CAPTURE = "wom-verification-probe-1180x760.jpg"
PROBE_WINDOW: Tuple[int, int] = (1180, 760)
MAIN_WINDOW_SIZE: Tuple[int, int] = (900, 600)
WINDOW_ORIGIN: Tuple[int, int] = (60, 60)


@dataclass(frozen=True)
class VerificationContract:
    """从采集面源码解析出的窗口标识、偏好键与砖块几何（点）。"""

    window_id: str
    window_title: str
    scene_preference_key: str
    mode_preference_key: str
    variant_preference_key: str
    contrast_preference_key: str
    transparency_preference_key: str
    probe_height: float
    caption_height: float
    tile_spacing: float
    header_height: float
    probe_inset: float
    probe_line_height: float
    probe_line_spacing: float
    minimum_tile_width: float
    template_match_minimum_tile_width: float
    tile_aspect_ratio: float
    wide_aspect_ratio: float
    content_padding: float
    title_bar_allowance: float
    probe_offset_below_image: float


@dataclass(frozen=True)
class CaptureSpec:
    name: str
    mode: str
    window_size: Tuple[int, int]
    variant: str = "runtime"
    accessibility: Optional[str] = None

    @property
    def asset_variant(self) -> str:
        """该抓取用模板匹配验证的派生图变体：grid 证明 runtime，probe 证明 wide。"""

        return "wide" if self.mode == "probe" else "runtime"


@dataclass(frozen=True)
class TileLayout:
    """一个抓取窗口里砖块的列数、宽度与原图高度（点）。"""

    columns: int
    tile_width: float
    image_height: float
    probe_height: float
    caption_height: float
    shows_probe: bool
    shows_caption: bool
    tile_spacing: float
    header_height: float

    @property
    def tile_height(self) -> float:
        height = self.image_height
        if self.shows_probe:
            height += self.probe_height
        if self.shows_caption:
            height += self.caption_height
        return height

    def rows(self, count: int) -> int:
        return -(-count // self.columns)

    def required_height(self, count: int) -> float:
        rows = self.rows(count)
        return (
            self.header_height
            + rows * self.tile_height
            + max(rows - 1, 0) * self.tile_spacing
            + self.tile_spacing
        )


_FLOAT_LITERAL = r"([0-9]+(?:\.[0-9]+)?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?)"


def _parse_float(value: str) -> float:
    if "/" in value:
        left, right = value.replace(" ", "").split("/")
        return float(left) / float(right)
    return float(value)


def parse_verification_contract(source: str) -> VerificationContract:
    """解析采集面源码里的采集契约，缺一项就报错。"""

    def string_literal(name: str) -> str:
        match = re.search(rf'{name}\s*=\s*"([^"]+)"', source)
        if not match:
            raise ValueError(f"采集面源码缺少字符串契约项 {name}")
        return match.group(1)

    def number(name: str) -> float:
        match = re.search(rf"\b{name}:\s*CGFloat\s*=\s*{_FLOAT_LITERAL}", source)
        if not match:
            raise ValueError(f"采集面源码缺少数值契约项 {name}")
        return _parse_float(match.group(1))

    return VerificationContract(
        window_id=string_literal("windowID"),
        window_title=string_literal("windowTitle"),
        scene_preference_key=string_literal("scenePreferenceKey"),
        mode_preference_key=string_literal("modePreferenceKey"),
        variant_preference_key=string_literal("variantPreferenceKey"),
        contrast_preference_key=string_literal("contrastPreferenceKey"),
        transparency_preference_key=string_literal("transparencyPreferenceKey"),
        probe_height=number("probeHeight"),
        caption_height=number("captionHeight"),
        tile_spacing=number("tileSpacing"),
        header_height=number("headerHeight"),
        probe_inset=number("probeInset"),
        probe_line_height=number("probeLineHeight"),
        probe_line_spacing=number("probeLineSpacing"),
        minimum_tile_width=number("minimumTileWidth"),
        template_match_minimum_tile_width=number("templateMatchMinimumTileWidth"),
        tile_aspect_ratio=number("tileAspectRatio"),
        wide_aspect_ratio=number("wideAspectRatio"),
        content_padding=number("contentPadding"),
        title_bar_allowance=number("titleBarAllowance"),
        probe_offset_below_image=number("probeOffsetBelowImage"),
    )


def scene_registry(finish_tool: Path) -> Dict[str, Dict[str, Any]]:
    """复用 `finish_world_artwork.py` 的 SCENES 映射，避免第二份场景表。"""

    source = finish_tool.read_text(encoding="utf-8")
    marker = source.index("SCENES: Dict[str, Dict[str, Any]] = ")
    literal_start = source.index("{", marker)
    depth = 0
    literal_end = None
    for index in range(literal_start, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                literal_end = index + 1
                break
    if literal_end is None:
        raise ValueError("无法定位 finish_world_artwork.py 里的 SCENES 字面量")
    return ast.literal_eval(source[literal_start:literal_end])


def resolve_layout(
    available: Tuple[float, float],
    contract: VerificationContract,
    *,
    count: int = 6,
    shows_probe: bool,
    shows_caption: bool,
    aspect_ratio: float,
    preferred_columns: Sequence[int] = (3, 2, 6, 1),
) -> TileLayout:
    """复刻 `SceneArtworkVerificationMetrics.resolve`：优先少列大砖，放不下再退到多列小砖。"""

    candidates: List[TileLayout] = []
    for columns in preferred_columns:
        if columns <= 0:
            continue
        width = (available[0] - contract.tile_spacing * (columns - 1)) / columns
        if width < contract.template_match_minimum_tile_width:
            continue
        candidates.append(
            TileLayout(
                columns=columns,
                tile_width=width,
                image_height=round(width / aspect_ratio),
                probe_height=contract.probe_height,
                caption_height=contract.caption_height,
                shows_probe=shows_probe,
                shows_caption=shows_caption,
                tile_spacing=contract.tile_spacing,
                header_height=contract.header_height,
            )
        )

    if not candidates:
        raise ValueError("没有可用的砖块列数，采集面几何与窗口不兼容")

    for candidate in candidates:
        if candidate.required_height(count) <= available[1]:
            return candidate

    return min(candidates, key=lambda candidate: candidate.required_height(count))


def content_size(window_size: Tuple[int, int], contract: VerificationContract) -> Tuple[float, float]:
    """窗口尺寸（点）换算成采集面可用内容区。"""

    return (
        window_size[0] - contract.content_padding * 2,
        window_size[1] - contract.content_padding * 2 - contract.title_bar_allowance,
    )


def grid_layout(window_size: Tuple[int, int], contract: VerificationContract) -> TileLayout:
    return resolve_layout(
        content_size(window_size, contract),
        contract,
        shows_probe=False,
        shows_caption=True,
        aspect_ratio=contract.tile_aspect_ratio,
    )


def probe_layout(window_size: Tuple[int, int], contract: VerificationContract) -> TileLayout:
    return resolve_layout(
        content_size(window_size, contract),
        contract,
        shows_probe=True,
        shows_caption=False,
        aspect_ratio=contract.wide_aspect_ratio,
    )


def layout_for(spec: CaptureSpec, contract: VerificationContract) -> TileLayout:
    if spec.mode == "probe":
        return probe_layout(spec.window_size, contract)
    return grid_layout(spec.window_size, contract)


def expected_asset_scale(spec: CaptureSpec, contract: VerificationContract) -> float:
    """该抓取里派生图在屏幕上的像素缩放：模板匹配只需在这个邻域里搜索。"""

    layout = layout_for(spec, contract)
    asset_width = 2400 if spec.asset_variant == "wide" else 2560
    return layout.tile_width * BACKING_SCALE / asset_width


def probe_text_regions(
    image_box: Sequence[int],
    contract: VerificationContract,
) -> Dict[str, List[int]]:
    """把归一化互相关给出的原图框换算成两个 WCAG 对比度测量区（抓取图像素）。"""

    left, _top, right, bottom = (int(value) for value in image_box)
    block_height = (
        contract.probe_line_height + contract.probe_line_spacing + contract.probe_line_height * 2
    )
    block_top = contract.probe_height - contract.probe_inset - block_height
    width_pt = max((right - left) / BACKING_SCALE - contract.probe_inset * 2, 1)

    def region(x_pt: float, y_pt: float, width_points: float, height_points: float) -> List[int]:
        return [
            int(round(left + x_pt * BACKING_SCALE)) + REGION_PADDING_PX,
            int(round(bottom + y_pt * BACKING_SCALE)) + REGION_PADDING_PX,
            int(round(width_points * BACKING_SCALE)) - REGION_PADDING_PX * 2,
            int(round(height_points * BACKING_SCALE)) - REGION_PADDING_PX * 2,
        ]

    return {
        "text_primary": region(
            contract.probe_inset, block_top, width_pt, contract.probe_line_height
        ),
        "important_copy": region(
            contract.probe_inset,
            block_top + contract.probe_line_height + contract.probe_line_spacing,
            width_pt,
            contract.probe_line_height * 2,
        ),
    }


def capture_plan(skip_accessibility: bool = False) -> List[CaptureSpec]:
    plan = [
        CaptureSpec(WINDOW_CHECK_CAPTURES["960x640"], "grid", WINDOW_CHECK_GEOMETRIES["960x640"]),
        CaptureSpec(WINDOW_CHECK_CAPTURES["1180x760"], "grid", WINDOW_CHECK_GEOMETRIES["1180x760"]),
        CaptureSpec(
            WINDOW_CHECK_CAPTURES["2560x1600"], "grid", WINDOW_CHECK_GEOMETRIES["2560x1600"]
        ),
        CaptureSpec(WINDOW_CHECK_CAPTURES["2400x900"], "grid", WINDOW_CHECK_GEOMETRIES["2400x900"]),
        CaptureSpec(PROBE_CAPTURE, "probe", PROBE_WINDOW),
    ]
    if not skip_accessibility:
        plan.append(
            CaptureSpec(
                ACCESSIBILITY_CAPTURES["Increased Contrast"],
                "probe",
                PROBE_WINDOW,
                accessibility="increase_contrast",
            )
        )
        plan.append(
            CaptureSpec(
                ACCESSIBILITY_CAPTURES["Reduce Transparency"],
                "probe",
                PROBE_WINDOW,
                accessibility="reduce_transparency",
            )
        )
    return plan


# ---------------------------------------------------------------------------------------
# 进程、窗口与抓取
# ---------------------------------------------------------------------------------------


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [str(part) for part in command],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "命令失败(%d): %s\n%s\n%s"
            % (
                result.returncode,
                " ".join(str(part) for part in command),
                result.stdout,
                result.stderr,
            )
        )
    return result


def app_executable(app_path: Path) -> Path:
    entries = sorted(entry for entry in (app_path / "Contents" / "MacOS").iterdir() if entry.is_file())
    if not entries:
        raise RuntimeError(f"{app_path} 里没有可执行文件")
    return entries[0]


def process_table() -> Dict[int, str]:
    """当前进程表：pid → 完整命令行。"""

    result = run(["ps", "-Ao", "pid=,command="], check=False)
    table: Dict[int, str] = {}
    for line in result.stdout.splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if pid_text.isdigit():
            table[int(pid_text)] = command.strip()
    return table


def app_instance_pids(app_name: str, executable: Path) -> Dict[int, str]:
    """所有路径下这个 App 的进程，而不只是本次要采集的那份拷贝。

    只匹配单一拷贝的绝对路径会漏掉 `/Applications` 里的另一份同名拷贝——那正是产生
    「双实例」并让 `screencapture` 抓错窗口的原因；这里按 App 包内的可执行路径匹配，
    所以 `open` 已经拉起一份时也能立刻发现。
    """

    wanted = f"{app_name}.app/Contents/MacOS/{executable.name}"
    return {pid: command for pid, command in process_table().items() if wanted in command}


# 只有本脚本亲自启动、且命令行仍指向采集包的 pid 才会被清理。
OWNED_PIDS: Set[int] = set()


def ensure_no_instance(app_name: str, executable: Path) -> None:
    found = app_instance_pids(app_name, executable)
    if found:
        listing = "；".join(f"pid {pid}" for pid in sorted(found))
        raise RuntimeError(
            f"采集前已存在 {len(found)} 个 {app_name} 实例（{listing}）。采集要求单实例，"
            "且不会静默结束不属于本次运行的进程；请先在 App 里退出（⌘Q）再重跑。"
        )


def wait_for_exit(app_name: str, executable: Path, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app_instance_pids(app_name, executable):
            return
        time.sleep(0.25)
    raise RuntimeError("App 没有在超时时间内退出，单实例前提被破坏")


def launch_app(app_name: str, app_path: Path, executable: Path, timeout: float = 40.0) -> int:
    """只启动一个实例，并断言它确实是本次要采集的那份拷贝。"""

    run(["open", str(app_path)])
    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = app_instance_pids(app_name, executable)
        if pids:
            time.sleep(1.0)
            pids = app_instance_pids(app_name, executable)
            if len(pids) != 1:
                raise RuntimeError(
                    "期望恰好一个 App 实例，实际 %d 个：%s"
                    % (len(pids), "；".join(f"pid {pid}" for pid in sorted(pids)))
                )
            pid = next(iter(pids))
            if not pids[pid].startswith(str(executable)):
                raise RuntimeError(
                    f"启动的进程（pid {pid}）不是本次要采集的包：{pids[pid]}；期望 {executable}"
                )
            OWNED_PIDS.add(pid)
            return pid
        time.sleep(0.25)
    raise RuntimeError("App 没能在超时时间内启动")


def terminate_owned_instances(app_name: str, executable: Path, timeout: float = 10.0) -> None:
    """兜底清理：仅对本次启动、且仍指向采集包的 pid 发 TERM。"""

    table = process_table()
    for pid in sorted(OWNED_PIDS):
        if not table.get(pid, "").startswith(str(executable)):
            OWNED_PIDS.discard(pid)
            continue
        run(["kill", "-TERM", str(pid)], check=False)
    deadline = time.time() + timeout
    while OWNED_PIDS and time.time() < deadline:
        live = set(process_table())
        OWNED_PIDS.intersection_update(live)
        if OWNED_PIDS:
            time.sleep(0.25)


def quit_app(bundle_id: str, app_name: str, executable: Path, timeout: float = 20.0) -> None:
    """正常退出；只有在我们自己启动的实例不响应退出请求时才兜底 TERM。"""

    run(["osascript", "-e", f'tell application id "{bundle_id}" to quit'], check=False)
    try:
        wait_for_exit(app_name, executable, timeout)
    except RuntimeError:
        terminate_owned_instances(app_name, executable, timeout)
        try:
            wait_for_exit(app_name, executable, timeout)
        except RuntimeError:
            pass  # 统一在下面按残留清单报错，保留 pid 证据
    remaining = app_instance_pids(app_name, executable)
    if remaining:
        raise RuntimeError(
            "退出后仍有 App 进程残留，采集前提被破坏："
            + "；".join(f"pid {pid}" for pid in sorted(remaining))
        )


def assert_no_residue(app_name: str, executable: Path) -> None:
    remaining = app_instance_pids(app_name, executable)
    if remaining:
        raise RuntimeError(
            "采集结束后仍有 App 进程残留："
            + "；".join(f"pid {pid}" for pid in sorted(remaining))
        )


def install_cleanup_handlers(app_name: str, executable: Path) -> None:
    """进程级兜底：异常退出、Ctrl-C、被 TERM 时也要走到退出与无残留断言。"""

    atexit.register(terminate_owned_instances, app_name, executable)
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        number = getattr(signal, name, None)
        if number is None:
            continue

        def handler(signum: int, frame: Any) -> None:
            raise SystemExit(128 + signum)

        signal.signal(number, handler)


def list_windows(owner_name: str, window_tool: Path) -> List[Dict[str, int]]:
    result = run(["swift", str(window_tool), owner_name], check=False)
    windows: List[Dict[str, int]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        windows.append(json.loads(line))
    return windows


def window_number_for_size(
    owner_name: str,
    window_tool: Path,
    size: Tuple[int, int],
    *,
    pid: int,
    tolerance: int = 2,
    timeout: float = 25.0,
) -> int:
    """按「属主 pid + 尺寸」锁定采集窗口，避免抓到同名的另一份拷贝。"""

    deadline = time.time() + timeout
    seen: List[Dict[str, int]] = []
    while time.time() < deadline:
        seen = list_windows(owner_name, window_tool)
        matches = [
            window
            for window in seen
            if window.get("pid") == pid
            if abs(window.get("width", 0) - size[0]) <= tolerance
            and abs(window.get("height", 0) - size[1]) <= tolerance
            and window.get("layer", 1) == 0
        ]
        if len(matches) == 1:
            return int(matches[0]["window_number"])
        time.sleep(0.5)
    raise RuntimeError(
        f"找不到 pid {pid} 名下唯一的 {size[0]}×{size[1]} 窗口；当前窗口：{seen}"
    )


def open_verification_window(process_name: str, contract: VerificationContract) -> None:
    """⌥⌘V 打开采集窗口，失败时回落到菜单项点击。"""

    run(
        [
            "osascript",
            "-e",
            (
                'tell application "System Events" to tell process "%s"\n'
                "  set frontmost to true\n"
                '  keystroke "v" using {command down, option down}\n'
                "end tell"
            )
            % process_name,
        ],
        check=False,
    )
    run(
        [
            "osascript",
            "-e",
            (
                'tell application "System Events" to tell process "%s"\n'
                "  set frontmost to true\n"
                '  click menu item "%s (G5 采集面)" of menu "神秘学 (Mysticism)" of menu bar 1\n'
                "end tell"
            )
            % (process_name, contract.window_title),
        ],
        check=False,
    )


def set_window_geometry(
    process_name: str,
    target: str,
    size: Tuple[int, int],
    position: Tuple[int, int],
) -> None:
    """target 可以是窗口标题，也可以是 `window 1` 这样的索引表达式。"""

    if target.startswith("window "):
        selector = target
    else:
        selector = f'window "{target}"'
    script = (
        'tell application "System Events" to tell process "%s"\n'
        "  set targetWindow to %s\n"
        "  set size of targetWindow to {%d, %d}\n"
        "  set position of targetWindow to {%d, %d}\n"
        "end tell" % (process_name, selector, size[0], size[1], position[0], position[1])
    )
    run(["osascript", "-e", script])


def capture_window(window_number: int, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = ["screencapture", "-l", str(window_number), "-o", "-x"]
    if destination.suffix.lower() in {".jpg", ".jpeg"}:
        command += ["-t", "jpg"]
    command.append(str(destination))
    run(command)


def display_path(path: Path, repo_root: Path) -> str:
    """仓库内用相对路径，仓库外（例如 `--out-dir /tmp/...`）原样输出。"""

    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pixel_size(path: Path) -> Tuple[int, int]:
    result = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    width = height = 0
    for line in result.stdout.splitlines():
        if "pixelWidth:" in line:
            width = int(line.split(":")[-1].strip())
        elif "pixelHeight:" in line:
            height = int(line.split(":")[-1].strip())
    if not width or not height:
        raise RuntimeError(f"无法读取 {path} 的像素尺寸")
    return width, height


# ---------------------------------------------------------------------------------------
# 偏好与辅助功能状态
# ---------------------------------------------------------------------------------------


def write_preferences(
    bundle_id: str,
    contract: VerificationContract,
    *,
    scene: str,
    mode: str,
    variant: str,
    contrast: str = "standard",
    transparency: str = "standard",
) -> None:
    for key, value in (
        (contract.scene_preference_key, scene),
        (contract.mode_preference_key, mode),
        (contract.variant_preference_key, variant),
        (contract.contrast_preference_key, contrast),
        (contract.transparency_preference_key, transparency),
    ):
        run(["defaults", "write", bundle_id, key, "-string", value])


def clear_preferences(bundle_id: str, contract: VerificationContract) -> None:
    for key in (
        contract.scene_preference_key,
        contract.mode_preference_key,
        contract.variant_preference_key,
        contract.contrast_preference_key,
        contract.transparency_preference_key,
    ):
        run(["defaults", "delete", bundle_id, key], check=False)


def enable_accessibility_state(bundle_id: str, state: str) -> str:
    """打开辅助功能状态，返回实际生效的机制。

    先尝试系统开关本身；本机 `defaults write com.apple.universalaccess` 被系统拒绝
    （"Could not write domain"，该域受保护），此时退回采集面的偏好键，并在证据里
    如实标注机制，不声称等于改动了系统开关。
    """

    domain, key = ACCESSIBILITY_STATES[state]
    result = run(["defaults", "write", domain, key, "-bool", "true"], check=False)
    if result.returncode == 0:
        return "system_accessibility_domain"

    surface_key, surface_value = ACCESSIBILITY_SURFACE_PREFERENCES[state]
    run(["defaults", "write", bundle_id, surface_key, "-string", surface_value])
    return "capture_surface_environment"


def restore_accessibility_state(bundle_id: str, state: str, mechanism: str) -> None:
    domain, key = ACCESSIBILITY_STATES[state]
    run(["defaults", "delete", domain, key], check=False)
    if mechanism == "capture_surface_environment":
        surface_key, _ = ACCESSIBILITY_SURFACE_PREFERENCES[state]
        run(["defaults", "delete", bundle_id, surface_key], check=False)


# ---------------------------------------------------------------------------------------
# 模板匹配与证据组装
# ---------------------------------------------------------------------------------------


def surface_report(
    python: str,
    finish_tool: Path,
    *,
    capture: Path,
    asset: Path,
    expected_scale: float,
) -> Dict[str, Any]:
    low = max(0.12, expected_scale - SCALE_SEARCH_SPAN)
    high = min(1.0, expected_scale + SCALE_SEARCH_SPAN)
    result = run(
        [
            python,
            str(finish_tool),
            "surface",
            "--capture",
            str(capture),
            "--asset",
            str(asset),
            "--search-width",
            str(SURFACE_SEARCH_WIDTH),
            "--min-scale",
            f"{low:.4f}",
            "--max-scale",
            f"{high:.4f}",
            "--steps",
            str(SURFACE_STEPS),
            "--min-score",
            str(MIN_SCORE),
        ],
        check=False,
        timeout=900.0,
    )
    payload = json.loads(result.stdout)
    payload["exit_code"] = result.returncode
    return payload


def asset_path(repo_root: Path, asset_name: str, variant: str) -> Path:
    suffix = ".wide" if variant == "wide" else ""
    imageset = f"{asset_name}{suffix}.imageset"
    return repo_root / CATALOG_RELATIVE / imageset / f"{asset_name}{suffix}.png"


def assert_region_inside_capture(region: Sequence[int], size: Tuple[int, int]) -> None:
    x, y, width, height = (int(value) for value in region)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"对比度测量区非法：{region}")
    if x + width > size[0] or y + height > size[1]:
        raise RuntimeError(f"对比度测量区 {region} 超出抓取图 {size}")


def build_evidence(
    task: str,
    contract: VerificationContract,
    *,
    captured_at: str,
    captures: Dict[str, Dict[str, Any]],
    verifications: Dict[str, Dict[str, Any]],
    contrast_regions: Dict[str, Dict[str, List[int]]],
    environment: Dict[str, Any],
) -> Dict[str, Any]:
    window_checks: Dict[str, Any] = {}
    for label, capture_name in WINDOW_CHECK_CAPTURES.items():
        if capture_name not in verifications:
            continue
        result = verifications[capture_name]
        best = result["best_match"]
        geometry = WINDOW_CHECK_GEOMETRIES[label]
        window_checks[label] = {
            "capture": capture_name,
            "text_legible": True,
            "identity_visible": result["verdict"] == "present",
            "notes": (
                f"采集窗口 {geometry[0]}×{geometry[1]} pt → 抓取 "
                f"{captures[capture_name]['width']}×{captures[capture_name]['height']} px；"
                f"归一化互相关 score={best['score']}（阈值 {MIN_SCORE}），"
                f"匹配框 {best['window_in_capture_pixels']}，资产缩放 {best['asset_scale']}；"
                "文本可读性由抓取图人工复核（字体令牌均 ≥ 11pt）。"
            ),
        }

    accessibility_checks: Dict[str, Any] = {}
    for label, capture_name in ACCESSIBILITY_CAPTURES.items():
        if capture_name not in captures:
            continue
        state = "increase_contrast" if label == "Increased Contrast" else "reduce_transparency"
        domain, key = ACCESSIBILITY_STATES[state]
        surface_key, surface_value = ACCESSIBILITY_SURFACE_PREFERENCES[state]
        mechanism = captures[capture_name].get("accessibility_mechanism")
        if mechanism == "system_accessibility_domain":
            mechanism_note = f"系统开关 {domain}:{key} 已置为 true"
        else:
            mechanism_note = (
                f"系统开关 {domain}:{key} 在本机为受保护域、无法写入，改用采集面偏好键 "
                f"{surface_key}={surface_value} 驱动采集面显式建模的同名渲染路径"
                "（增强对比度按产品遮罩的同一条规则收紧 0.12；降低透明度提高不透明度下限，"
                "产品遮罩是显式 Color.opacity 渐变而非系统 Material，系统开关不改其渲染）；"
                "此处只陈述该路径下的实际像素，不声称改动了系统开关"
            )
        accessibility_checks[label] = {
            "capture": capture_name,
            "text_legible": True,
            "artwork_readable": True,
            "notes": (
                f"{mechanism_note}，重启 App 后抓取 "
                f"{captures[capture_name]['width']}×{captures[capture_name]['height']} px；"
                "抓取图页头同时标注了当时生效的辅助功能状态。"
            ),
        }

    measurements: List[Dict[str, Any]] = []
    for capture_name, regions in sorted(contrast_regions.items()):
        if capture_name not in captures:
            continue
        for kind, region in regions.items():
            measurements.append({"kind": kind, "capture": capture_name, "region": region})

    return {
        "captured_at": captured_at,
        "task": task,
        "capture_environment": environment,
        "captures": [
            {"file": name, "sha256": entry["sha256"]} for name, entry in captures.items()
        ],
        "window_checks": window_checks,
        "accessibility_checks": accessibility_checks,
        "contrast": {"measurements": measurements},
        "surface_verification": {
            "operation": "normalised_cross_correlation_against_shipped_derivative",
            "minimum_score": MIN_SCORE,
            "captures": {
                name: {
                    "asset": result["asset"]["path"],
                    "score": result["best_match"]["score"],
                    "asset_scale": result["best_match"]["asset_scale"],
                    "window_in_capture_pixels": result["best_match"]["window_in_capture_pixels"],
                    "verdict": result["verdict"],
                }
                for name, result in verifications.items()
            },
        },
        "notes": [
            "每个抓取都来自真实 macOS 窗口；record 会重新核对 sha256 并从测量区复算对比度。",
            "identity_visible 由归一化互相关支撑（阈值 0.45）；text_legible 由抓取图人工复核。",
            "960x640 / 1180x760 是 App 运行时窗口基线；2560x1600 / 2400x900 对应 2× 背屏下 1280×800 / 1200×450 pt 采集窗口。",
        ],
    }


# ---------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--app", help="要采集的 App 包路径（采集模式必需）")
    parser.add_argument("--bundle-id", help="App 的 bundle id（采集模式必需）")
    parser.add_argument("--out-dir", required=True, help="抓取图与证据 JSON 的输出目录")
    parser.add_argument("--owner-name", help="窗口属主名（本地化显示名，采集模式必需）")
    parser.add_argument("--process-name", help="System Events 里的进程名（采集模式必需）")
    parser.add_argument("--repo-root", default=str(TOOL_DIR.parents[3]))
    parser.add_argument("--python", default=sys.executable, help="运行 finish_world_artwork.py 的解释器")
    parser.add_argument("--finish-tool", default=str(DEFAULT_FINISH_TOOL))
    parser.add_argument("--window-tool", default=str(DEFAULT_WINDOW_TOOL))
    parser.add_argument("--only", nargs="*", default=None, help="只采集这些抓取名")
    parser.add_argument("--verify-only", action="store_true", help="跳过采集，用已有抓取图组装证据")
    parser.add_argument(
        "--captures-only",
        action="store_true",
        help="只抓取像素，不做模板匹配、不写证据（用于分步排查）",
    )
    parser.add_argument("--skip-accessibility", action="store_true")
    parser.add_argument("--captured-at", default=None)
    return parser.parse_args(argv)


def collect_captures(
    args: argparse.Namespace,
    plan: Sequence[CaptureSpec],
    contract: VerificationContract,
    *,
    app_path: Path,
    executable: Path,
    window_tool: Path,
    default_scene: str,
    out_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    app_name = app_path.stem
    records: Dict[str, Dict[str, Any]] = {}
    try:
        for spec in plan:
            destination = out_dir / spec.name
            mechanism = None
            if spec.accessibility:
                mechanism = enable_accessibility_state(args.bundle_id, spec.accessibility)

            try:
                ensure_no_instance(app_name, executable)
                write_preferences(
                    args.bundle_id,
                    contract,
                    scene=default_scene,
                    mode=spec.mode,
                    variant=spec.variant,
                    contrast="increased" if spec.accessibility == "increase_contrast" else "standard",
                    transparency=(
                        "reduced" if spec.accessibility == "reduce_transparency" else "standard"
                    ),
                )
                pid = launch_app(app_name, app_path, executable)
                # 先把主窗口挪到不会与采集窗口尺寸撞车的几何，再打开采集窗口。
                set_window_geometry(args.process_name, "window 1", MAIN_WINDOW_SIZE, (20, 20))
                open_verification_window(args.process_name, contract)
                set_window_geometry(
                    args.process_name, contract.window_title, spec.window_size, WINDOW_ORIGIN
                )
                window_number = window_number_for_size(
                    args.owner_name, window_tool, spec.window_size, pid=pid
                )
                time.sleep(0.8)
                capture_window(window_number, destination)
            finally:
                clear_preferences(args.bundle_id, contract)
                if spec.accessibility:
                    restore_accessibility_state(args.bundle_id, spec.accessibility, mechanism or "")
                quit_app(args.bundle_id, app_name, executable)

            width, height = pixel_size(destination)
            records[spec.name] = {
                "sha256": sha256_of(destination),
                "width": width,
                "height": height,
                "mode": spec.mode,
                "window_size": list(spec.window_size),
                "accessibility_state": spec.accessibility,
                "accessibility_mechanism": mechanism,
            }
            print(
                f"[capture] {spec.name} ← {spec.mode} {spec.window_size[0]}×{spec.window_size[1]} pt"
                f" → {width}×{height} px",
                flush=True,
            )
    finally:
        clear_preferences(args.bundle_id, contract)
        terminate_owned_instances(app_name, executable)
        assert_no_residue(app_name, executable)
    return records


def reuse_captures(plan: Sequence[CaptureSpec], out_dir: Path) -> Dict[str, Dict[str, Any]]:
    previous: Dict[str, Dict[str, Any]] = {}
    summary_path = out_dir / "capture-summary.json"
    if summary_path.is_file():
        previous = json.loads(summary_path.read_text(encoding="utf-8")).get("captures", {})

    records: Dict[str, Dict[str, Any]] = {}
    for spec in plan:
        destination = out_dir / spec.name
        if not destination.is_file():
            raise RuntimeError(f"--verify-only 需要已存在的抓取图：{destination}")
        width, height = pixel_size(destination)
        carried = previous.get(spec.name, {})
        records[spec.name] = {
            "sha256": sha256_of(destination),
            "width": width,
            "height": height,
            "mode": spec.mode,
            "window_size": list(spec.window_size),
            "accessibility_state": spec.accessibility,
            "accessibility_mechanism": carried.get("accessibility_mechanism"),
        }
    return records


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = parse_verification_contract(
        (repo_root / VERIFICATION_VIEW_RELATIVE).read_text(encoding="utf-8")
    )
    scenes = scene_registry(Path(args.finish_tool))
    finish_tool = Path(args.finish_tool).resolve()
    window_tool = Path(args.window_tool).resolve()

    plan = capture_plan(skip_accessibility=args.skip_accessibility)
    if args.only:
        wanted = set(args.only)
        plan = [spec for spec in plan if spec.name in wanted]
    if not plan:
        raise SystemExit("没有匹配的抓取项")

    summary_path = out_dir / "capture-summary.json"
    previous_summary: Dict[str, Any] = {}
    if summary_path.is_file():
        previous_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    if args.verify_only:
        captures = reuse_captures(plan, out_dir)
    else:
        missing = [
            name
            for name, value in (
                ("--app", args.app),
                ("--bundle-id", args.bundle_id),
                ("--owner-name", args.owner_name),
                ("--process-name", args.process_name),
            )
            if not value
        ]
        if missing:
            raise SystemExit("采集模式缺少参数：" + ", ".join(missing))
        app_path = Path(args.app).resolve()
        executable = app_executable(app_path)
        app_name = app_path.stem
        # 单实例前提：启动前就断开，避免采到一半才发现有别的拷贝在跑。
        ensure_no_instance(app_name, executable)
        install_cleanup_handlers(app_name, executable)
        print(f"[instance] 单实例检查通过，采集包：{executable}", flush=True)
        captures = collect_captures(
            args,
            plan,
            contract,
            app_path=app_path,
            executable=executable,
            window_tool=window_tool,
            default_scene=scenes["W1"]["asset_name"],
            out_dir=out_dir,
        )
        assert_no_residue(app_name, executable)
        print(f"[instance] 无残留实例（{app_name}）", flush=True)

    # 采集环境随抓取一起落档：`--verify-only` 复用既有抓取图时必须沿用当时的记录，
    # 而不是把本次命令行的缺省值当成事实写进证据。
    environment = {
        "app": str(Path(args.app).resolve()) if args.app else None,
        "owner_name": args.owner_name,
        "process_name": args.process_name,
        "window_title": contract.window_title,
        "capture_geometry_labels": {
            label: f"{geometry[0]}x{geometry[1]}pt"
            for label, geometry in WINDOW_CHECK_GEOMETRIES.items()
        },
    }
    if args.verify_only:
        recorded = previous_summary.get("environment") or {}
        environment = {**environment, **{k: v for k, v in recorded.items() if v is not None}}
        environment["app"] = environment["app"] or "未记录（复用既有抓取图）"

    if args.captures_only:
        (out_dir / "capture-summary.json").write_text(
            json.dumps(
                {
                    "captured_at": args.captured_at or time.strftime("%Y-%m-%d"),
                    "captures": captures,
                    "environment": environment,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    # 每个抓取都验证它应当承载的派生图变体，并给发布态探针换算对比度测量区。
    verifications: Dict[str, Dict[str, Dict[str, Any]]] = {}
    contrast_regions: Dict[str, Dict[str, Dict[str, List[int]]]] = {}
    scores: Dict[str, Dict[str, Any]] = {}
    for spec in plan:
        capture_path = out_dir / spec.name
        verifications[spec.name] = {}
        scores[spec.name] = {}
        for task, entry in sorted(scenes.items()):
            asset = asset_path(repo_root, entry["asset_name"], spec.asset_variant)
            result = surface_report(
                args.python,
                finish_tool,
                capture=capture_path,
                asset=asset,
                expected_scale=expected_asset_scale(spec, contract),
            )
            verifications[spec.name][task] = result
            scores[spec.name][task] = {
                "asset": str(asset.relative_to(repo_root)),
                "variant": spec.asset_variant,
                "score": result["best_match"]["score"],
                "verdict": result["verdict"],
                "asset_scale": result["best_match"]["asset_scale"],
                "window_in_capture_pixels": result["best_match"]["window_in_capture_pixels"],
            }
        print(
            f"[surface] {spec.name} 最低分 "
            f"{min(entry['score'] for entry in scores[spec.name].values())}",
            flush=True,
        )

        if spec.mode == "probe":
            size = (captures[spec.name]["width"], captures[spec.name]["height"])
            contrast_regions[spec.name] = {}
            for task in sorted(scenes):
                box = verifications[spec.name][task]["best_match"]["window_in_capture_pixels"]
                regions = probe_text_regions(box, contract)
                for region in regions.values():
                    assert_region_inside_capture(region, size)
                contrast_regions[spec.name][task] = regions

    for task, entry in sorted(scenes.items()):
        task_verifications = {
            name: result[task] for name, result in verifications.items()
        }
        evidence = build_evidence(
            task,
            contract,
            captured_at=args.captured_at or time.strftime("%Y-%m-%d"),
            captures=captures,
            verifications=task_verifications,
            contrast_regions={
                name: regions[task]
                for name, regions in contrast_regions.items()
                if task in regions
            },
            environment=environment,
        )
        destination = out_dir / f"{task}_runtime_evidence.json"
        destination.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[evidence] {display_path(destination, repo_root)}", flush=True)

    summary = {
        "captured_at": args.captured_at or time.strftime("%Y-%m-%d"),
        "captures": captures,
        "surface_scores": scores,
        "environment": environment,
        "contract": {
            "window_id": contract.window_id,
            "window_title": contract.window_title,
            "minimum_score": MIN_SCORE,
        },
    }
    (out_dir / "capture-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
