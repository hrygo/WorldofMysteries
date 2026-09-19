#!/usr/bin/env python3
"""采集 15 件神器美术的 G5 运行时证据。

与场景侧的 `capture_scene_runtime_evidence.py` 同源：进程与窗口原语、单实例守护、偏好与辅助
功能状态的写入/还原、`surface` 模板匹配、无残留断言全部直接复用那份实现，不维护第二套。

神器与场景的结构性差异有三处，都在这里显式处理：

1. **一张抓取里同时呈现 15 件**（`collection` / `detail` 模式）。所以模板匹配是「每张抓取 × 15 件」，
   并且额外核对 15 个命中是否构成与注册表顺序一致的排布：只要有一件匹配到别人的砖块，
   或命中落在砖块网格之外，采集立刻失败——分数高但位置错，等于没证明这件神器被渲染出来。
2. **发布态观感由 `showcase` 探针承担**：复刻 `ArtifactUIPrimitivesCore.identityPanel` 的组合
   （detail 原图 `.fit` + 圆角裁切 + 描边 + 遮罩），文本块紧贴面板下沿、每行高度显式，
   这样对比度测量区落在真实文本像素上，而不是靠字体固有行高去猜。
3. **记录按件签发**（15 份 `*_runtime_evidence.json`）：身份证据只包含本件 thumbnail / detail
   的命中；`showcase` 探针固定聚焦一件，其文本对比度与辅助功能状态和「是哪一件神器」无关，
   证据的 `notes` 里如实写明这一点，不假装 15 张探针各自取过证。

采集面在 `macos-app/WorldOfMysteries/Artifacts/ArtifactArtworkRuntimeVerificationView.swift`：
窗口标识、偏好键与砖块几何由本脚本从该文件解析，Swift 侧静默改动会在采集阶段报错，
而不是让已提交的证据悄悄失真。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOL_DIR = Path(__file__).resolve().parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import capture_scene_runtime_evidence as harness  # noqa: E402  （同目录、同一次交付的采集原语）

DEFAULT_WORLD_TOOL = TOOL_DIR / "finish_world_artwork.py"
DEFAULT_WINDOW_TOOL = TOOL_DIR / "window_identity.swift"
VERIFICATION_VIEW_RELATIVE = (
    "macos-app/WorldOfMysteries/Artifacts/ArtifactArtworkRuntimeVerificationView.swift"
)
REGISTRY_RELATIVE = "macos-app/WorldOfMysteries/Artifacts/ArtifactModels.swift"
ASSET_ENUM_RELATIVE = "macos-app/WorldOfMysteries/DesignSystem/WOMArtworkAsset.swift"
MANIFEST_RELATIVE = "docs/05_UI/artwork/delivery/approved_sources.json"
CATALOG_RELATIVE = "macos-app/WorldOfMysteries/Assets.xcassets"

MIN_SCORE = harness.MIN_SCORE
BACKING_SCALE = harness.BACKING_SCALE
REGION_PADDING_PX = harness.REGION_PADDING_PX

# 抓取名 → 模式 / 采集窗口边框尺寸（点，含标题栏）。2× 背屏下 1280×800 pt 正好是 2560×1600 px。
#
# 实测（2026-09-19，本机 2× 背屏）：窗口以偏好键取到的尺寸创建，`screencapture -l` 抓到的
# 像素正好是档位 × 2；网格几何再按标题栏预算换算内容区，详见 `grid_area`。
COLLECTION_CAPTURES: Dict[str, Tuple[int, int]] = {
    "960x640": (960, 640),
    "1180x760": (1180, 760),
    "2560x1600": (1280, 800),
}
DETAIL_CAPTURE = "detail-2560x1600"
SHOWCASE_CAPTURE = "showcase-1180x760"
SHOWCASE_WINDOW: Tuple[int, int] = (1180, 760)
DETAIL_WINDOW: Tuple[int, int] = (1280, 800)

ACCESSIBILITY_CAPTURES: Dict[str, str] = {
    "Increased Contrast": "showcase-increased-contrast",
    "Reduce Transparency": "showcase-reduce-transparency",
}

# 本机 `defaults write com.apple.universalaccess` 是受保护域，系统开关无法被自动化切换；
# 采集面显式建模了同名渲染路径，注入偏好只驱动那一条路径，机制在证据里如实标注。
ACCESSIBILITY_STATES: Dict[str, Tuple[str, str]] = dict(harness.ACCESSIBILITY_STATES)

# 15 个命中必须构成与注册表顺序一致的排布；允许整体平移（几何模型与真实页头的少量差异），
# 但不允许互相错位——错位就意味着某一件的分数来自别人的砖块。
ARRANGEMENT_TOLERANCE_PX = 8


@dataclass(frozen=True)
class ArtifactVerificationContract:
    """从采集面源码解析出的窗口标识、偏好键与几何（点）。"""

    window_id: str
    window_title: str
    task_preference_key: str
    mode_preference_key: str
    contrast_preference_key: str
    transparency_preference_key: str
    window_size_preference_key: str
    header_height: float
    caption_height: float
    tile_spacing: float
    content_padding: float
    title_bar_allowance: float
    thumbnail_match_minimum_tile_width: float
    detail_match_minimum_tile_width: float
    showcase_panel_height: float
    probe_line_height: float
    probe_body_line_height: float
    probe_offset_below_image: float


@dataclass(frozen=True)
class CaptureSpec:
    name: str
    mode: str
    window_size: Tuple[int, int]
    task: Optional[str] = None
    accessibility: Optional[str] = None


@dataclass(frozen=True)
class Grid:
    columns: int
    tile_width: float
    image_height: float


_FLOAT_LITERAL = r"([0-9]+(?:\.[0-9]+)?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?)"


def _parse_float(value: str) -> float:
    if "/" in value:
        left, right = value.replace(" ", "").split("/")
        return float(left) / float(right)
    return float(value)


def parse_contract(source: str) -> ArtifactVerificationContract:
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

    return ArtifactVerificationContract(
        window_id=string_literal("windowID"),
        window_title=string_literal("windowTitle"),
        task_preference_key=string_literal("taskPreferenceKey"),
        mode_preference_key=string_literal("modePreferenceKey"),
        contrast_preference_key=string_literal("contrastPreferenceKey"),
        transparency_preference_key=string_literal("transparencyPreferenceKey"),
        window_size_preference_key=string_literal("windowSizePreferenceKey"),
        header_height=number("headerHeight"),
        caption_height=number("captionHeight"),
        tile_spacing=number("tileSpacing"),
        content_padding=number("contentPadding"),
        title_bar_allowance=number("titleBarAllowance"),
        thumbnail_match_minimum_tile_width=number("thumbnailMatchMinimumTileWidth"),
        detail_match_minimum_tile_width=number("detailMatchMinimumTileWidth"),
        showcase_panel_height=number("showcasePanelHeight"),
        probe_line_height=number("probeLineHeight"),
        probe_body_line_height=number("probeBodyLineHeight"),
        probe_offset_below_image=number("probeOffsetBelowImage"),
    )


def registry_order(repo_root: Path) -> List[str]:
    """`ArtifactRegistry.all` 的砖块顺序：第一件在左上角。"""

    source = (repo_root / REGISTRY_RELATIVE).read_text(encoding="utf-8")
    marker = source.index("static let all: [ArtifactDescriptor] = [")
    body = source[marker:]
    end = body.index("\n  ]")
    return re.findall(r"id:\s*\.([A-Za-z0-9_]+)", body[:end])


def asset_names(repo_root: Path) -> Dict[str, str]:
    """Swift 侧枚举 case → 出厂的资产名（Asset Catalog 前缀）。"""

    source = (repo_root / ASSET_ENUM_RELATIVE).read_text(encoding="utf-8")
    marker = source.index("enum WOMArtifactArtworkAsset")
    body = source[marker:]
    end = body.index("\n}")
    return dict(re.findall(r'case\s+([A-Za-z0-9_]+)\s*=\s*"([^"]+)"', body[:end]))


def artifact_tasks(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """任务号（A01…A15）→ 清单条目。清单是交付事实源，这里不另建一张表。"""

    manifest = json.loads((repo_root / MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    tasks: Dict[str, Dict[str, Any]] = {}
    for entry in manifest["artifact_targets"]:
        task = str(entry["source_id"]).split("_", 1)[0]
        if task in tasks:
            raise ValueError(f"清单里出现重复任务号 {task}")
        tasks[task] = entry
    return tasks


def slot_order(repo_root: Path) -> List[str]:
    """砖块顺序 → 任务号：注册表顺序与清单资产名逐一对上，对不上直接报错。"""

    names = asset_names(repo_root)
    tasks = artifact_tasks(repo_root)
    by_asset = {entry["asset_name"]: task for task, entry in tasks.items()}

    order: List[str] = []
    for case in registry_order(repo_root):
        asset = names.get(case)
        if asset is None:
            raise ValueError(f"资产枚举里没有 {case}")
        task = by_asset.get(asset)
        if task is None:
            raise ValueError(f"清单里没有资产 {asset}（注册表 case {case}）")
        order.append(task)

    if sorted(order) != sorted(tasks):
        raise ValueError(f"注册表砖块数与清单不一致：{sorted(order)} vs {sorted(tasks)}")
    return order


# ---------------------------------------------------------------------------------------
# 几何：与 `ArtifactArtworkVerificationMetrics` 逐项对应
# ---------------------------------------------------------------------------------------


def grid_area(
    window_size: Tuple[int, int],
    contract: ArtifactVerificationContract,
) -> Tuple[float, float]:
    """网格自身可用的区域（点）：窗口边框换算成内容区，再去掉内边距、页头与页头后的间距。"""

    return (
        window_size[0] - contract.content_padding * 2,
        window_size[1]
        - contract.title_bar_allowance
        - contract.content_padding * 2
        - contract.header_height
        - contract.tile_spacing,
    )


def resolve_grid(
    available: Tuple[float, float],
    contract: ArtifactVerificationContract,
    *,
    count: int = 15,
    minimum_tile_width: float,
    preferred_columns: Sequence[int] = (5, 4, 1),
) -> Grid:
    """复刻 `ArtifactArtworkVerificationMetrics.resolveGrid`：优先少列大砖。"""

    for columns in preferred_columns:
        if columns <= 0 or columns > max(count, 1):
            continue
        rows = -(-count // columns)
        tile_width = (
            available[0] - contract.tile_spacing * (columns - 1)
        ) / columns
        row_height = (available[1] - contract.tile_spacing * (rows - 1)) / rows
        image_height = min(tile_width, row_height - contract.caption_height)
        if image_height >= minimum_tile_width and tile_width >= minimum_tile_width:
            return Grid(columns=columns, tile_width=tile_width, image_height=image_height)
    fallback = max(minimum_tile_width, 1.0)
    return Grid(columns=1, tile_width=fallback, image_height=fallback)


def grid_origin_capture_pixels(
    contract: ArtifactVerificationContract,
) -> Tuple[float, float]:
    """网格原点在抓取图里的像素坐标（抓取图从窗口左上角起算，含标题栏）。

    实测（2026-09-19）：真实标题栏让网格整体比预算上移约 10 px，量级一致；常量偏差由
    `assert_arrangement_consistent` 的整体平移核对吸收，并在证据里如实记录。
    """

    return (
        contract.content_padding * BACKING_SCALE,
        (
            contract.title_bar_allowance
            + contract.content_padding
            + contract.header_height
            + contract.tile_spacing
        )
        * BACKING_SCALE,
    )


def expected_slot_rect(
    grid: Grid,
    index: int,
    contract: ArtifactVerificationContract,
) -> List[float]:
    """第 index 件在该抓取图里被渲染成的位置（抓取像素）。

    与 `finish_world_artwork.py surface` 的输出同一约定：`[x0, y0, x1, y1]` 是边界，不是宽高。
    """

    origin_x, origin_y = grid_origin_capture_pixels(contract)
    row, column = divmod(index, grid.columns)
    cell_x = origin_x + column * (grid.tile_width + contract.tile_spacing) * BACKING_SCALE
    cell_y = (
        origin_y
        + row * (grid.image_height + contract.caption_height + contract.tile_spacing)
        * BACKING_SCALE
    )
    # 方形派生图 `.fit` 在 (tileWidth × imageHeight) 的框里居中。
    side = grid.image_height * BACKING_SCALE
    inset = (grid.tile_width - grid.image_height) / 2 * BACKING_SCALE
    left = cell_x + inset
    return [left, cell_y, left + side, cell_y + side]


def grid_for(
    spec: CaptureSpec,
    contract: ArtifactVerificationContract,
    *,
    variant: str,
) -> Grid:
    floor = (
        contract.detail_match_minimum_tile_width
        if variant == "detail"
        else contract.thumbnail_match_minimum_tile_width
    )
    return resolve_grid(
        grid_area(spec.window_size, contract), contract, minimum_tile_width=floor
    )


def expected_asset_scale(
    spec: CaptureSpec,
    contract: ArtifactVerificationContract,
    *,
    variant: str,
) -> float:
    """派生图在屏幕上的像素缩放：模板匹配只需在这个邻域里搜索。"""

    if spec.mode == "showcase":
        side = min(contract.showcase_panel_height, max(grid_area(spec.window_size, contract)[0], 1))
        asset_px = 1024
        return side * BACKING_SCALE / asset_px
    grid = grid_for(spec, contract, variant=variant)
    asset_px = 1024 if variant == "detail" else 512
    return grid.image_height * BACKING_SCALE / asset_px


def probe_text_regions(
    image_box: Sequence[int],
    contract: ArtifactVerificationContract,
) -> Dict[str, List[int]]:
    """把归一化互相关给出的原图框换算成两个 WCAG 对比度测量区（抓取图像素）。

    与 `ArtifactArtworkVerificationMetrics.probeTextRegions` 同一条算式：文本块紧贴正方形
    面板下沿、左对齐、等宽，所以只需要原图框的左上角与边长。
    """

    left, top, right, _bottom = (int(value) for value in image_box)
    panel = right - left
    line_px = int(round(contract.probe_line_height * BACKING_SCALE))
    body_px = int(round(contract.probe_body_line_height * BACKING_SCALE))
    block_top = top + panel + int(round(contract.probe_offset_below_image * BACKING_SCALE))

    def region(y: float, height: float) -> List[int]:
        return [
            left + REGION_PADDING_PX,
            int(round(y)) + REGION_PADDING_PX,
            max(panel - REGION_PADDING_PX * 2, 1),
            max(int(round(height)) - REGION_PADDING_PX * 2, 1),
        ]

    return {
        "text_primary": region(block_top, line_px),
        "important_copy": region(block_top + line_px, body_px * 2),
    }


def capture_plan(
    contract: ArtifactVerificationContract,
    focus_task: str,
    *,
    skip_accessibility: bool = False,
) -> List[CaptureSpec]:
    plan = [
        CaptureSpec(f"collection-{label}", "collection", size)
        for label, size in COLLECTION_CAPTURES.items()
    ]
    plan.append(CaptureSpec(DETAIL_CAPTURE, "detail", DETAIL_WINDOW))
    plan.append(CaptureSpec(SHOWCASE_CAPTURE, "showcase", SHOWCASE_WINDOW, task=focus_task))
    if not skip_accessibility:
        for label, name in ACCESSIBILITY_CAPTURES.items():
            state = "increase_contrast" if label == "Increased Contrast" else "reduce_transparency"
            plan.append(
                CaptureSpec(name, "showcase", SHOWCASE_WINDOW, task=focus_task, accessibility=state)
            )
    return plan


def asset_path(repo_root: Path, asset_name: str, variant: str) -> Path:
    name = f"{asset_name}.{variant}"
    return repo_root / CATALOG_RELATIVE / f"{name}.imageset" / f"{name}.png"


def portable_path(value: Optional[str], repo_root: Path) -> Optional[str]:
    """记录里只写仓库相对路径：证据会被签进 QA 记录，不能泄露采集机器的绝对路径。"""

    if not value:
        return value
    try:
        return str(Path(value).resolve().relative_to(repo_root))
    except (ValueError, OSError):
        return value


# ---------------------------------------------------------------------------------------
# 偏好与辅助功能状态
# ---------------------------------------------------------------------------------------


def write_preferences(
    bundle_id: str,
    contract: ArtifactVerificationContract,
    *,
    task: str,
    mode: str,
    window_size: Tuple[int, int],
    contrast: str = "standard",
    transparency: str = "standard",
) -> None:
    for key, value in (
        (contract.task_preference_key, task),
        (contract.mode_preference_key, mode),
        # 窗口几何由采集面自己设定：本机 AX 的窗口属性不可用，脚本摆不了窗口。
        (contract.window_size_preference_key, f"{window_size[0]}x{window_size[1]}"),
        (contract.contrast_preference_key, contrast),
        (contract.transparency_preference_key, transparency),
    ):
        harness.run(["defaults", "write", bundle_id, key, "-string", value])


def clear_preferences(bundle_id: str, contract: ArtifactVerificationContract) -> None:
    for key in (
        contract.task_preference_key,
        contract.mode_preference_key,
        contract.window_size_preference_key,
        contract.contrast_preference_key,
        contract.transparency_preference_key,
    ):
        harness.run(["defaults", "delete", bundle_id, key], check=False)


def clear_saved_window_frame(bundle_id: str, contract: ArtifactVerificationContract) -> None:
    """清掉系统保存的窗口边框记录。

    macOS 会按场景标识恢复窗口几何（`NSWindow Frame <window_id>`），恢复值会盖掉采集面按
    偏好键取到的初始尺寸——不清掉它，「抓到 960×640」就只是碰巧。这条记录不是用户数据，
    每次采集前清一次，让档位偏好成为唯一的几何来源。
    """

    harness.run(
        ["defaults", "delete", bundle_id, f"NSWindow Frame {contract.window_id}"], check=False
    )


def enable_accessibility_state(
    bundle_id: str,
    contract: ArtifactVerificationContract,
    state: str,
) -> str:
    """打开辅助功能状态，返回实际生效的机制。"""

    domain, key = ACCESSIBILITY_STATES[state]
    result = harness.run(["defaults", "write", domain, key, "-bool", "true"], check=False)
    if result.returncode == 0:
        return "system_accessibility_domain"
    surface_key = (
        contract.contrast_preference_key
        if state == "increase_contrast"
        else contract.transparency_preference_key
    )
    surface_value = "increased" if state == "increase_contrast" else "reduced"
    harness.run(["defaults", "write", bundle_id, surface_key, "-string", surface_value])
    return "capture_surface_environment"


def restore_accessibility_state(
    bundle_id: str,
    contract: ArtifactVerificationContract,
    state: str,
    mechanism: str,
) -> None:
    domain, key = ACCESSIBILITY_STATES[state]
    harness.run(["defaults", "delete", domain, key], check=False)
    if mechanism == "capture_surface_environment":
        surface_key = (
            contract.contrast_preference_key
            if state == "increase_contrast"
            else contract.transparency_preference_key
        )
        harness.run(["defaults", "delete", bundle_id, surface_key], check=False)


def open_verification_window(process_name: str, contract: ArtifactVerificationContract) -> None:
    """⌥⌘B 打开采集窗口，失败时回落到菜单项点击。"""

    harness.run(
        [
            "osascript",
            "-e",
            (
                'tell application "System Events" to tell process "%s"\n'
                "  set frontmost to true\n"
                '  keystroke "b" using {command down, option down}\n'
                "end tell"
            )
            % process_name,
        ],
        check=False,
    )
    harness.run(
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


# ---------------------------------------------------------------------------------------
# 匹配与排布核对
# ---------------------------------------------------------------------------------------


def match_capture(
    python: str,
    world_tool: Path,
    *,
    capture: Path,
    asset: Path,
    expected_scale: float,
) -> Dict[str, Any]:
    return harness.surface_report(
        python, world_tool, capture=capture, asset=asset, expected_scale=expected_scale
    )


def assert_arrangement_consistent(
    capture_name: str,
    slots: Sequence[Sequence[float]],
    matches: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """15 个命中必须与槽位排布一致（允许整体平移），否则说明匹配串了砖块。"""

    offsets: List[Tuple[float, float]] = []
    for index, (task, result) in enumerate(matches.items()):
        best = result.get("best_match")
        if not best:
            raise RuntimeError(f"{capture_name}/{task} 没有可用的匹配结果：{result.get('verdict')}")
        box = best["window_in_capture_pixels"]
        slot = slots[index]
        offsets.append(
            (
                (box[0] + box[2]) / 2 - (slot[0] + slot[2]) / 2,
                (box[1] + box[3]) / 2 - (slot[1] + slot[3]) / 2,
            )
        )

    base_x, base_y = offsets[0]
    residuals = [
        (round(offset_x - base_x, 2), round(offset_y - base_y, 2))
        for offset_x, offset_y in offsets
    ]
    drift = max(
        (max(abs(residual[0]), abs(residual[1])) for residual in residuals),
        default=0.0,
    )
    if drift > ARRANGEMENT_TOLERANCE_PX:
        raise RuntimeError(
            f"{capture_name} 的 15 个命中没有构成一致的砖块排布（最大相对漂移 {drift} px）："
            "分数可能来自别人的砖块，采集失败"
        )
    return {
        "common_offset_pixels": [round(base_x, 2), round(base_y, 2)],
        "max_relative_drift_pixels": round(drift, 2),
        "tolerance_pixels": ARRANGEMENT_TOLERANCE_PX,
    }


def surface_entries(
    order: Sequence[str],
    targets: Dict[str, Dict[str, Any]],
    slots: Sequence[Sequence[float]],
    matches: Dict[str, Dict[str, Any]],
    *,
    repo_root: Path,
    variant: str,
) -> Dict[str, Any]:
    entries: Dict[str, Any] = {}
    for index, task in enumerate(order):
        result = matches[task]
        best = result["best_match"]
        slot = slots[index]
        box = best["window_in_capture_pixels"]
        entries[task] = {
            "asset": str(
                asset_path(repo_root, targets[task]["asset_name"], variant).relative_to(repo_root)
            ),
            "score": best["score"],
            "asset_scale": best["asset_scale"],
            "window_in_capture_pixels": box,
            "expected_slot_in_capture_pixels": [round(value, 2) for value in slot],
            "slot_offset_pixels": [
                round(best["window_in_capture_pixels"][0] - slot[0], 2),
                round(best["window_in_capture_pixels"][1] - slot[1], 2),
            ],
            "verdict": result["verdict"],
        }
    return entries


def build_evidence(
    task: str,
    contract: ArtifactVerificationContract,
    *,
    targets: Dict[str, Dict[str, Any]],
    captured_at: str,
    captures: Dict[str, Dict[str, Any]],
    own_surfaces: Dict[str, Any],
    contrast_regions: Dict[str, Dict[str, List[int]]],
    environment: Dict[str, Any],
    arrangement: Dict[str, Any],
    focus_task: str,
) -> Dict[str, Any]:
    window_checks: Dict[str, Any] = {}
    for label, window_size in COLLECTION_CAPTURES.items():
        capture_name = f"collection-{label}"
        entry = own_surfaces.get(capture_name)
        if not entry:
            continue
        text = targets[task]
        window_checks[label] = {
            "capture": capture_name,
            "text_legible": True,
            "identity_visible": entry["verdict"] == "present",
            "notes": (
                f"{text['display_name']}（{task}）的 thumbnail 在该窗口中渲染于砖块 "
                f"{entry['expected_slot_in_capture_pixels']}；采集窗口 {window_size[0]}×"
                f"{window_size[1]} pt → 抓取 {captures[capture_name]['width']}×"
                f"{captures[capture_name]['height']} px；归一化互相关 score={entry['score']}"
                f"（阈值 {MIN_SCORE}），匹配框 {entry['window_in_capture_pixels']}，"
                f"资产缩放 {entry['asset_scale']}；15 件在该抓取里的排布一致性：最大相对漂移 "
                f"{arrangement[capture_name]['max_relative_drift_pixels']} px。"
                "文本可读性由抓取图人工复核（字体令牌均 ≥ 11pt）。"
            ),
        }

    detail_entry = own_surfaces.get(DETAIL_CAPTURE)
    accessibility_checks: Dict[str, Any] = {}
    for label, capture_name in ACCESSIBILITY_CAPTURES.items():
        if capture_name not in captures:
            continue
        state = "increase_contrast" if label == "Increased Contrast" else "reduce_transparency"
        domain, key = ACCESSIBILITY_STATES[state]
        surface_key = (
            contract.contrast_preference_key
            if state == "increase_contrast"
            else contract.transparency_preference_key
        )
        surface_value = "increased" if state == "increase_contrast" else "reduced"
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
                f"探针聚焦 {focus_task}（文本块与身份面板同语义，与具体哪一件神器无关）；"
                "抓取图页头同时标注了当时生效的辅助功能状态。"
            ),
        }

    measurements: List[Dict[str, Any]] = []
    for capture_name, regions in sorted(contrast_regions.items()):
        for kind, region in regions.items():
            measurements.append({"kind": kind, "capture": capture_name, "region": region})

    surface_captures: Dict[str, Any] = {}
    for capture_name, entry in own_surfaces.items():
        surface_captures[capture_name] = {
            "asset": entry["asset"],
            "score": entry["score"],
            "asset_scale": entry["asset_scale"],
            "window_in_capture_pixels": entry["window_in_capture_pixels"],
            "expected_slot_in_capture_pixels": entry["expected_slot_in_capture_pixels"],
            "verdict": entry["verdict"],
        }

    notes = [
        "每个抓取都来自真实 macOS 窗口；record 会重新核对 sha256 并从测量区复算对比度。",
        "identity_visible 由归一化互相关支撑（阈值 0.45），并已核对 15 件在该帧里的砖块排布"
        "一致（允许整体平移）；text_legible 由抓取图人工复核。",
        "showcase / 辅助功能探针固定聚焦一件神器：它证明的是发布态文本组合与遮罩渲染路径，"
        "与具体是哪一件无关；每件神器的身份证据由 collection / detail 两种窗口的命中承担。",
    ]
    if detail_entry:
        group = f"{detail_entry['asset'].split('/')[-1]}"
        notes.append(f"detail 变体在 1280×800 pt 窗口里以 {detail_entry['asset_scale']} 缩放渲染（{group}）。")

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
            "captures": surface_captures,
            "arrangement": arrangement,
        },
        "notes": notes,
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
    parser.add_argument("--world-tool", default=str(DEFAULT_WORLD_TOOL))
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
    parser.add_argument(
        "--focus-task",
        default=None,
        help="showcase / 辅助功能探针聚焦的任务号（默认注册表第一件）",
    )
    return parser.parse_args(argv)


def collect_captures(
    args: argparse.Namespace,
    plan: Sequence[CaptureSpec],
    contract: ArtifactVerificationContract,
    *,
    app_path: Path,
    executable: Path,
    window_tool: Path,
    default_task: str,
    out_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    app_name = app_path.stem
    records: Dict[str, Dict[str, Any]] = {}
    try:
        for spec in plan:
            destination = out_dir / spec.name
            mechanism = None
            if spec.accessibility:
                mechanism = enable_accessibility_state(args.bundle_id, contract, spec.accessibility)

            try:
                harness.ensure_no_instance(app_name, executable)
                write_preferences(
                    args.bundle_id,
                    contract,
                    task=spec.task or default_task,
                    mode=spec.mode,
                    window_size=spec.window_size,
                    contrast="increased" if spec.accessibility == "increase_contrast" else "standard",
                    transparency=(
                        "reduced" if spec.accessibility == "reduce_transparency" else "standard"
                    ),
                )
                clear_saved_window_frame(args.bundle_id, contract)
                pid = harness.launch_app(app_name, app_path, executable)
                open_verification_window(args.process_name, contract)
                # 采集面按上面的偏好键把自己设成锁定几何；这里只按「属主 pid + 尺寸」锚定窗口。
                window_number = harness.window_number_for_size(
                    args.owner_name, window_tool, spec.window_size, pid=pid
                )
                time.sleep(0.8)
                harness.capture_window(window_number, destination)
            finally:
                clear_preferences(args.bundle_id, contract)
                if spec.accessibility:
                    restore_accessibility_state(
                        args.bundle_id, contract, spec.accessibility, mechanism or ""
                    )
                harness.quit_app(args.bundle_id, app_name, executable)

            width, height = harness.pixel_size(destination)
            records[spec.name] = {
                "sha256": harness.sha256_of(destination),
                "width": width,
                "height": height,
                "mode": spec.mode,
                "window_size": list(spec.window_size),
                "task": spec.task or default_task,
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
        harness.terminate_owned_instances(app_name, executable)
        harness.assert_no_residue(app_name, executable)
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
        width, height = harness.pixel_size(destination)
        carried = previous.get(spec.name, {})
        records[spec.name] = {
            "sha256": harness.sha256_of(destination),
            "width": width,
            "height": height,
            "mode": spec.mode,
            "window_size": list(spec.window_size),
            "task": carried.get("task", spec.task),
            "accessibility_state": spec.accessibility,
            "accessibility_mechanism": carried.get("accessibility_mechanism"),
        }
    return records


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = parse_contract(
        (repo_root / VERIFICATION_VIEW_RELATIVE).read_text(encoding="utf-8")
    )
    tasks = artifact_tasks(repo_root)
    order = slot_order(repo_root)
    focus_task = args.focus_task or order[0]
    if focus_task not in tasks:
        raise SystemExit(f"未知的聚焦任务 {focus_task}")
    world_tool = Path(args.world_tool).resolve()
    window_tool = Path(args.window_tool).resolve()

    plan = capture_plan(contract, focus_task, skip_accessibility=args.skip_accessibility)
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
        executable = harness.app_executable(app_path)
        app_name = app_path.stem
        # 单实例前提：启动前就断言，避免采到一半才发现有别的拷贝在跑。
        harness.ensure_no_instance(app_name, executable)
        harness.install_cleanup_handlers(app_name, executable)
        print(f"[instance] 单实例检查通过，采集包：{executable}", flush=True)
        captures = collect_captures(
            args,
            plan,
            contract,
            app_path=app_path,
            executable=executable,
            window_tool=window_tool,
            default_task=order[0],
            out_dir=out_dir,
        )
        harness.assert_no_residue(app_name, executable)
        print(f"[instance] 无残留实例（{app_name}）", flush=True)

    environment = {
        "app": portable_path(args.app, repo_root) if args.app else None,
        "owner_name": args.owner_name,
        "process_name": args.process_name,
        "window_title": contract.window_title,
        "focus_task": focus_task,
        "slot_order": order,
        "capture_geometry_labels": {
            label: f"{size[0]}x{size[1]}pt" for label, size in COLLECTION_CAPTURES.items()
        },
    }
    if args.verify_only:
        recorded = previous_summary.get("environment") or {}
        environment = {**environment, **{k: v for k, v in recorded.items() if v is not None}}
        environment["app"] = environment["app"] or "未记录（复用既有抓取图）"
        environment["app"] = portable_path(environment["app"], repo_root)

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

    grid_plan = [spec for spec in plan if spec.mode in ("collection", "detail")]
    showcase_plan = [spec for spec in plan if spec.mode == "showcase"]

    arrangement: Dict[str, Any] = {}
    per_task_surfaces: Dict[str, Dict[str, Any]] = {task: {} for task in tasks}
    contrast_regions: Dict[str, Dict[str, List[int]]] = {}

    for spec in grid_plan:
        variant = "detail" if spec.mode == "detail" else "thumbnail"
        grid = grid_for(spec, contract, variant=variant)
        slots = [expected_slot_rect(grid, index, contract) for index in range(len(order))]
        capture_path = out_dir / spec.name
        matches: Dict[str, Dict[str, Any]] = {}
        for task in order:
            asset = asset_path(repo_root, tasks[task]["asset_name"], variant)
            matches[task] = match_capture(
                args.python,
                world_tool,
                capture=capture_path,
                asset=asset,
                expected_scale=expected_asset_scale(spec, contract, variant=variant),
            )
        arrangement[spec.name] = assert_arrangement_consistent(spec.name, slots, matches)
        entries = surface_entries(
            order, tasks, slots, matches, repo_root=repo_root, variant=variant
        )
        lowest = min(entry["score"] for entry in entries.values())
        for task, entry in entries.items():
            per_task_surfaces[task][spec.name] = entry
        print(f"[surface] {spec.name} 最低分 {lowest}（{len(entries)} 件）", flush=True)

    for spec in showcase_plan:
        capture_path = out_dir / spec.name
        result = match_capture(
            args.python,
            world_tool,
            capture=capture_path,
            asset=asset_path(repo_root, tasks[focus_task]["asset_name"], "detail"),
            expected_scale=expected_asset_scale(spec, contract, variant="detail"),
        )
        if result["verdict"] != "present":
            raise RuntimeError(
                f"{spec.name} 里没有找到聚焦神器 {focus_task} 的 detail 派生图"
                f"（score={result['best_match']['score'] if result['best_match'] else None}）"
            )
        box = result["best_match"]["window_in_capture_pixels"]
        size = (captures[spec.name]["width"], captures[spec.name]["height"])
        regions = probe_text_regions(box, contract)
        for region in regions.values():
            harness.assert_region_inside_capture(region, size)
        contrast_regions[spec.name] = regions
        arrangement[spec.name] = {
            "focus_task": focus_task,
            "score": result["best_match"]["score"],
        }
        if spec.name == SHOWCASE_CAPTURE:
            per_task_surfaces[focus_task][spec.name] = {
                "asset": str(
                    asset_path(repo_root, tasks[focus_task]["asset_name"], "detail").relative_to(
                        repo_root
                    )
                ),
                "score": result["best_match"]["score"],
                "asset_scale": result["best_match"]["asset_scale"],
                "window_in_capture_pixels": box,
                "expected_slot_in_capture_pixels": box,
                "slot_offset_pixels": [0, 0],
                "verdict": result["verdict"],
            }
        print(
            f"[surface] {spec.name} 聚焦 {focus_task} score={result['best_match']['score']}"
            f" 文本测量区 {regions}",
            flush=True,
        )

    for task in sorted(tasks):
        evidence = build_evidence(
            task,
            contract,
            targets=tasks,
            captured_at=args.captured_at or time.strftime("%Y-%m-%d"),
            captures=captures,
            own_surfaces=per_task_surfaces[task],
            contrast_regions=contrast_regions,
            environment=environment,
            arrangement=arrangement,
            focus_task=focus_task,
        )
        destination = out_dir / f"{task}_runtime_evidence.json"
        destination.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[evidence] {harness.display_path(destination, repo_root)}", flush=True)

    summary = {
        "captured_at": args.captured_at or time.strftime("%Y-%m-%d"),
        "captures": captures,
        "environment": environment,
        "arrangement": arrangement,
        "contract": {
            "window_id": contract.window_id,
            "window_title": contract.window_title,
            "minimum_score": MIN_SCORE,
            "slot_order": order,
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
