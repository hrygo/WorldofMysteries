"""神器 G5 采集脚本的回归测试。

采集脚本只有在「它的几何模型等于采集面自己的几何」时才可信：这里解析真实的 Swift 源码与
`finish_artifact_artwork.py` 的记录契约，砖块几何、窗口名、偏好键、抓取序列任何一侧静默
改动都会在这里失败，而不是让已提交的运行时证据悄悄失真。

Run::

    python3 -m unittest docs/05_UI/artwork/tools/tests/test_capture_artifact_runtime_evidence.py -v
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parent.parent / "capture_artifact_runtime_evidence.py"
FINISH_TOOL = Path(__file__).resolve().parent.parent / "finish_artifact_artwork.py"
REPO_ROOT = Path(__file__).resolve().parents[5]
VERIFICATION_VIEW = (
    REPO_ROOT / "macos-app/WorldOfMysteries/Artifacts/ArtifactArtworkRuntimeVerificationView.swift"
)
SWIFT_TESTS = REPO_ROOT / "macos-app/WorldOfMysteriesTests/ArtifactArtworkRuntimeVerificationTests.swift"


def load_harness():
    spec = importlib.util.spec_from_file_location("capture_artifact_runtime_evidence", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses 需要模块已在 sys.modules 里注册才能解析注解。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def finish_tool_literal(name: str):
    """从记录工具里读出元组常量：这里不导入它（那需要 numpy / Pillow）。"""

    tree = ast.parse(FINISH_TOOL.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"finish_artifact_artwork.py 里没有常量 {name}")


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_contract(VERIFICATION_VIEW.read_text(encoding="utf-8"))

    def test_contract_mirrors_the_swift_capture_surface(self) -> None:
        contract = self.contract
        self.assertEqual(contract.window_id, "artifact-artwork-verification")
        self.assertEqual(contract.window_title, "神器美术运行时校验")
        self.assertEqual(contract.task_preference_key, "wom.artwork.verification.artifact.task")
        self.assertEqual(contract.mode_preference_key, "wom.artwork.verification.artifact.mode")
        self.assertEqual(
            contract.contrast_preference_key, "wom.artwork.verification.artifact.contrast"
        )
        self.assertEqual(
            contract.transparency_preference_key, "wom.artwork.verification.artifact.transparency"
        )
        self.assertEqual(
            contract.window_size_preference_key, "wom.artwork.verification.artifact.windowsize"
        )

        self.assertEqual(contract.header_height, 44)
        self.assertEqual(contract.caption_height, 18)
        self.assertEqual(contract.tile_spacing, 12)
        self.assertEqual(contract.content_padding, 12)
        self.assertEqual(contract.title_bar_allowance, 28)
        self.assertEqual(contract.thumbnail_match_minimum_tile_width, 32)
        self.assertEqual(contract.detail_match_minimum_tile_width, 62)
        self.assertEqual(contract.showcase_panel_height, 220)
        self.assertEqual(contract.probe_line_height, 14)
        self.assertEqual(contract.probe_body_line_height, 16)
        self.assertEqual(contract.probe_offset_below_image, 0)

    def test_swift_contract_test_pins_the_same_numbers(self) -> None:
        swift_test = SWIFT_TESTS.read_text(encoding="utf-8")
        for literal in (
            "headerHeight == 44",
            "captionHeight == 18",
            "tileSpacing == 12",
            "contentPadding == 12",
            "titleBarAllowance == 28",
            "thumbnailMatchMinimumTileWidth == 32",
            "detailMatchMinimumTileWidth == 62",
            "showcasePanelHeight == 220",
            "probeLineHeight == 14",
            "probeBodyLineHeight == 16",
            "probeOffsetBelowImage == 0",
        ):
            self.assertIn(literal, swift_test)


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()

    def test_slot_order_is_a_permutation_of_the_manifest_tasks(self) -> None:
        order = self.harness.slot_order(REPO_ROOT)
        tasks = self.harness.artifact_tasks(REPO_ROOT)

        self.assertEqual(len(order), 15)
        self.assertEqual(len(set(order)), 15)
        self.assertEqual(sorted(order), sorted(tasks))
        # 砖块顺序来自 `ArtifactRegistry.all`，不是清单的完成顺序。
        self.assertEqual(order[0], "A07")
        self.assertEqual(order[1], "A01")

    def test_asset_names_resolve_to_shipped_catalog_imagesets(self) -> None:
        tasks = self.harness.artifact_tasks(REPO_ROOT)
        for task, entry in tasks.items():
            for variant in ("thumbnail", "detail"):
                path = self.harness.asset_path(REPO_ROOT, entry["asset_name"], variant)
                self.assertTrue(path.is_file(), f"{task} 缺少 {path.name}")


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_contract(VERIFICATION_VIEW.read_text(encoding="utf-8"))
        self.order = self.harness.slot_order(REPO_ROOT)
        self.plan = self.harness.capture_plan(self.contract, self.order[0])

    def test_plan_matches_the_record_tool_sequence(self) -> None:
        sequence = finish_tool_literal("RUNTIME_EVIDENCE_SEQUENCE")
        self.assertEqual([spec.name for spec in self.plan], list(sequence))

    def test_collection_windows_carry_the_locked_geometries(self) -> None:
        labels = finish_tool_literal("ARTIFACT_WINDOW_CHECKS")
        self.assertEqual(tuple(self.harness.COLLECTION_CAPTURES), tuple(labels))

        plan = {spec.name: spec for spec in self.plan}
        for label, geometry in self.harness.COLLECTION_CAPTURES.items():
            spec = plan[f"collection-{label}"]
            self.assertEqual(spec.mode, "collection")
            self.assertEqual(spec.window_size, geometry)
        # 2× 背屏让 2560×1600 这一档的抓取像素正好等于派生图的显式上限。
        self.assertEqual(
            tuple(
                value * self.harness.BACKING_SCALE
                for value in self.harness.COLLECTION_CAPTURES["2560x1600"]
            ),
            (2560, 1600),
        )

    def test_accessibility_states_match_the_record_tool(self) -> None:
        states = finish_tool_literal("ARTIFACT_ACCESSIBILITY_STATES")
        self.assertEqual(tuple(self.harness.ACCESSIBILITY_CAPTURES), tuple(states))

        showcase = [spec for spec in self.plan if spec.mode == "showcase"]
        self.assertEqual(len(showcase), 3)
        self.assertEqual(
            {spec.accessibility for spec in showcase},
            {None, "increase_contrast", "reduce_transparency"},
        )
        for spec in showcase:
            self.assertEqual(spec.window_size, self.harness.SHOWCASE_WINDOW)
            self.assertEqual(spec.task, self.order[0])

    def test_accessibility_can_be_skipped_for_a_first_pass(self) -> None:
        plan = self.harness.capture_plan(self.contract, self.order[0], skip_accessibility=True)
        self.assertEqual(len(plan), 5)
        self.assertFalse(any(spec.accessibility for spec in plan))


class GeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_contract(VERIFICATION_VIEW.read_text(encoding="utf-8"))
        self.order = self.harness.slot_order(REPO_ROOT)
        self.plan = {spec.name: spec for spec in self.harness.capture_plan(self.contract, self.order[0])}

    def grid(self, capture: str, variant: str):
        return self.harness.grid_for(self.plan[capture], self.contract, variant=variant)

    def test_grid_resolution_matches_the_swift_arithmetic(self) -> None:
        cases = {
            "collection-960x640": ("thumbnail", 5, 151.33333333333334),
            "collection-1180x760": ("thumbnail", 5, 191.33333333333334),
            "collection-2560x1600": ("thumbnail", 5, 204.66666666666669),
            "detail-2560x1600": ("detail", 5, 204.66666666666669),
        }
        for capture, (variant, columns, image_height) in cases.items():
            grid = self.grid(capture, variant)
            self.assertEqual(grid.columns, columns, capture)
            self.assertAlmostEqual(grid.image_height, image_height, places=4, msg=capture)

    def test_every_locked_window_keeps_the_tiles_above_the_match_floor(self) -> None:
        for capture, variant in (
            ("collection-960x640", "thumbnail"),
            ("collection-1180x760", "thumbnail"),
            ("collection-2560x1600", "thumbnail"),
            ("detail-2560x1600", "detail"),
        ):
            grid = self.grid(capture, variant)
            floor = (
                self.contract.detail_match_minimum_tile_width
                if variant == "detail"
                else self.contract.thumbnail_match_minimum_tile_width
            )
            self.assertGreaterEqual(grid.image_height, floor, capture)
            self.assertLessEqual(grid.image_height, grid.tile_width, capture)

    def test_expected_asset_scales_stay_inside_the_search_span(self) -> None:
        cases = {
            "collection-960x640": 0.5911,
            "collection-1180x760": 0.7474,
            "collection-2560x1600": 0.7995,
            "detail-2560x1600": 0.3997,
        }
        for capture, expected in cases.items():
            variant = "detail" if capture.startswith("detail") else "thumbnail"
            scale = self.harness.expected_asset_scale(self.plan[capture], self.contract, variant=variant)
            self.assertAlmostEqual(scale, expected, places=3, msg=capture)

        showcase = self.harness.expected_asset_scale(
            self.plan["showcase-1180x760"], self.contract, variant="detail"
        )
        self.assertAlmostEqual(showcase, 220 * 2 / 1024, places=4)

    def test_slots_are_reading_order_and_inside_the_capture(self) -> None:
        for capture, variant in (
            ("collection-960x640", "thumbnail"),
            ("collection-1180x760", "thumbnail"),
            ("collection-2560x1600", "thumbnail"),
            ("detail-2560x1600", "detail"),
        ):
            spec = self.plan[capture]
            grid = self.grid(capture, variant)
            slots = [
                self.harness.expected_slot_rect(grid, index, self.contract) for index in range(15)
            ]
            width = spec.window_size[0] * self.harness.BACKING_SCALE
            height = spec.window_size[1] * self.harness.BACKING_SCALE
            for index, slot in enumerate(slots):
                # 约定与 `surface` 一致：`[x0, y0, x1, y1]`。
                self.assertGreater(slot[2], slot[0], capture)
                self.assertGreater(slot[3], slot[1], capture)
                self.assertGreaterEqual(slot[0], 0, capture)
                self.assertLessEqual(slot[2], width, f"{capture} 槽位 {index} 越界")
                self.assertLessEqual(slot[3], height, f"{capture} 槽位 {index} 越界")
            for index in range(1, len(slots)):
                previous = slots[index - 1]
                current = slots[index]
                self.assertTrue(
                    current[0] > previous[0] or current[1] > previous[1],
                    f"{capture} 槽位 {index} 没有按阅读顺序推进",
                )

    def test_probe_regions_land_on_the_text_block(self) -> None:
        regions = self.harness.probe_text_regions([100, 200, 540, 640], self.contract)
        primary = regions["text_primary"]
        copy = regions["important_copy"]

        panel = 440  # 2× 下的 220 点面板
        self.assertEqual(primary[0], 100 + self.harness.REGION_PADDING_PX)
        self.assertEqual(primary[1], 200 + panel + self.harness.REGION_PADDING_PX)
        self.assertEqual(copy[1], primary[1] + self.contract.probe_line_height * 2)
        self.assertEqual(primary[2], panel - self.harness.REGION_PADDING_PX * 2)
        self.assertEqual(
            primary[3], int(self.contract.probe_line_height * 2) - self.harness.REGION_PADDING_PX * 2
        )
        self.assertEqual(
            copy[3], int(self.contract.probe_body_line_height * 4) - self.harness.REGION_PADDING_PX * 2
        )


class ArrangementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_contract(VERIFICATION_VIEW.read_text(encoding="utf-8"))
        self.order = self.harness.slot_order(REPO_ROOT)
        spec = self.harness.capture_plan(self.contract, self.order[0])[0]
        self.grid = self.harness.grid_for(spec, self.contract, variant="thumbnail")
        self.slots = [
            self.harness.expected_slot_rect(self.grid, index, self.contract)
            for index in range(len(self.order))
        ]

    def matches(self, boxes):
        return {
            task: {"verdict": "present", "best_match": {"window_in_capture_pixels": box, "score": 0.6}}
            for task, box in zip(self.order, boxes)
        }

    def boxes_from_slots(self, offset=(0.0, 0.0), *, rounding: bool = True):
        def place(value: float) -> float:
            return float(round(value)) if rounding else value

        return [
            [
                place(slot[0] + offset[0]),
                place(slot[1] + offset[1]),
                place(slot[2] + offset[0]),
                place(slot[3] + offset[1]),
            ]
            for slot in self.slots
        ]

    def test_consistent_arrangement_passes(self) -> None:
        report = self.harness.assert_arrangement_consistent(
            "collection-960x640", self.slots, self.matches(self.boxes_from_slots())
        )
        # 槽位坐标本身是小数，取整到整像素后每件会有不到 1 px 的舍入差。
        self.assertLessEqual(report["max_relative_drift_pixels"], 1.0)

    def test_constant_offset_is_calibration_not_confusion(self) -> None:
        report = self.harness.assert_arrangement_consistent(
            "collection-960x640",
            self.slots,
            self.matches(self.boxes_from_slots((7.0, -5.0), rounding=False)),
        )
        self.assertAlmostEqual(report["max_relative_drift_pixels"], 0.0, places=6)
        self.assertEqual(report["common_offset_pixels"], [7.0, -5.0])

    def test_shuffled_matches_are_rejected(self) -> None:
        boxes = self.boxes_from_slots()
        boxes[3], boxes[9] = boxes[9], boxes[3]
        with self.assertRaises(RuntimeError):
            self.harness.assert_arrangement_consistent(
                "collection-960x640", self.slots, self.matches(boxes)
            )

    def test_missing_match_is_rejected(self) -> None:
        matches = self.matches(self.boxes_from_slots())
        matches[self.order[2]] = {"verdict": "not_found", "best_match": None}
        with self.assertRaises(RuntimeError):
            self.harness.assert_arrangement_consistent("collection-960x640", self.slots, matches)


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_contract(VERIFICATION_VIEW.read_text(encoding="utf-8"))
        self.order = self.harness.slot_order(REPO_ROOT)
        self.targets = self.harness.artifact_tasks(REPO_ROOT)
        self.captures = {}
        for spec in self.harness.capture_plan(self.contract, self.order[0]):
            self.captures[spec.name] = {
                "sha256": "0" * 64,
                "width": spec.window_size[0] * 2,
                "height": spec.window_size[1] * 2,
                "mode": spec.mode,
                "window_size": list(spec.window_size),
                "task": spec.task,
                "accessibility_state": spec.accessibility,
                "accessibility_mechanism": (
                    "capture_surface_environment" if spec.accessibility else None
                ),
            }
        self.surface = {
            "score": 0.61,
            "asset_scale": 0.59,
            "window_in_capture_pixels": [50, 192, 353, 495],
            "expected_slot_in_capture_pixels": [50.27, 192.0, 302.67, 302.67],
            "slot_offset_pixels": [-0.27, 0.0],
            "verdict": "present",
        }
        self.contrast_regions = {
            "showcase-1180x760": {
                "text_primary": [104, 644, 432, 20],
                "important_copy": [104, 672, 432, 56],
            },
            "showcase-increased-contrast": {
                "text_primary": [104, 644, 432, 20],
                "important_copy": [104, 672, 432, 56],
            },
            "showcase-reduce-transparency": {
                "text_primary": [104, 644, 432, 20],
                "important_copy": [104, 672, 432, 56],
            },
        }
        self.arrangement = {
            name: {
                "common_offset_pixels": [0.0, 0.0],
                "max_relative_drift_pixels": 0.0,
                "tolerance_pixels": self.harness.ARRANGEMENT_TOLERANCE_PX,
            }
            for name in self.captures
        }
        self.arrangement["showcase-1180x760"] = {"focus_task": self.order[0], "score": 0.61}

    def own_surfaces_for(self, task: str):
        asset_name = self.targets[task]["asset_name"]
        surfaces = {}
        for capture, spec in zip(
            ("collection-960x640", "collection-1180x760", "collection-2560x1600"),
            ("thumbnail", "thumbnail", "thumbnail"),
        ):
            surfaces[capture] = dict(
                self.surface,
                asset=f"macos-app/WorldOfMysteries/Assets.xcassets/{asset_name}.{spec}.imageset/"
                f"{asset_name}.{spec}.png",
            )
        surfaces["detail-2560x1600"] = dict(
            self.surface,
            asset=f"macos-app/WorldOfMysteries/Assets.xcassets/{asset_name}.detail.imageset/"
            f"{asset_name}.detail.png",
        )
        return surfaces

    def evidence(self, task: str):
        return self.harness.build_evidence(
            task,
            self.contract,
            targets=self.targets,
            captured_at="2026-09-19",
            captures=self.captures,
            own_surfaces=self.own_surfaces_for(task),
            contrast_regions=self.contrast_regions,
            environment={
                "app": "build/WorldOfMysteries.app",
                "owner_name": "诡秘世界",
                "process_name": "WorldOfMysteries",
                "window_title": self.contract.window_title,
                "focus_task": self.order[0],
                "slot_order": self.order,
            },
            arrangement=self.arrangement,
            focus_task=self.order[0],
        )

    def test_evidence_carries_everything_the_record_tool_recomputes(self) -> None:
        evidence = self.evidence("A01")

        self.assertEqual(evidence["task"], "A01")
        self.assertEqual(
            sorted(evidence["window_checks"]),
            sorted(finish_tool_literal("ARTIFACT_WINDOW_CHECKS")),
        )
        self.assertEqual(
            sorted(evidence["accessibility_checks"]),
            sorted(finish_tool_literal("ARTIFACT_ACCESSIBILITY_STATES")),
        )

        digests = {entry["file"]: entry["sha256"] for entry in evidence["captures"]}
        for label, entry in evidence["window_checks"].items():
            self.assertIn(entry["capture"], digests, label)
            self.assertIs(entry["identity_visible"], True)
            self.assertIs(entry["text_legible"], True)
        for state, entry in evidence["accessibility_checks"].items():
            self.assertIn(entry["capture"], digests, state)
            self.assertIs(entry["artwork_readable"], True)
            self.assertIn("不声称改动了系统开关", entry["notes"])

        kinds = {measurement["kind"] for measurement in evidence["contrast"]["measurements"]}
        self.assertEqual(kinds, {"text_primary", "important_copy"})
        for measurement in evidence["contrast"]["measurements"]:
            self.assertIn(measurement["capture"], digests)
            self.assertEqual(len(measurement["region"]), 4)
            for value in measurement["region"]:
                self.assertIsInstance(value, int)

        surface = evidence["surface_verification"]
        self.assertEqual(surface["minimum_score"], self.harness.MIN_SCORE)
        self.assertTrue(surface["captures"])
        for capture, entry in surface["captures"].items():
            self.assertIn(capture, digests)
            self.assertEqual(entry["verdict"], "present")
            self.assertGreaterEqual(entry["score"], self.harness.MIN_SCORE)

    def test_evidence_names_only_repository_relative_assets(self) -> None:
        text = json.dumps(self.evidence("A05"), ensure_ascii=False)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("file://", text)
        self.assertIn("Assets.xcassets/", text)

    def test_every_task_gets_its_own_file_and_own_identity_asset(self) -> None:
        for task in sorted(self.targets):
            evidence = self.evidence(task)
            self.assertEqual(evidence["task"], task)
            for entry in evidence["surface_verification"]["captures"].values():
                self.assertIn(self.targets[task]["asset_name"], entry["asset"])


if __name__ == "__main__":
    unittest.main()
