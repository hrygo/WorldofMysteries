"""Tests for the G5 runtime evidence capture harness.

The harness is only trustworthy if its view of the capture surface is the surface's own view:
these tests parse the real Swift source, so a tile geometry, window title or preference key that
changes on the Swift side fails here instead of silently invalidating committed evidence.

Run::

    python3 -m unittest docs/05_UI/artwork/tools/tests/test_capture_scene_runtime_evidence.py -v
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parent.parent / "capture_scene_runtime_evidence.py"
REPO_ROOT = Path(__file__).resolve().parents[5]
VERIFICATION_VIEW = (
    REPO_ROOT / "macos-app/WorldOfMysteries/Components/SceneArtworkRuntimeVerificationView.swift"
)
FINISH_TOOL = Path(__file__).resolve().parent.parent / "finish_world_artwork.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("capture_scene_runtime_evidence", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses 需要模块已在 sys.modules 里注册才能解析注解。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_verification_contract(
            VERIFICATION_VIEW.read_text(encoding="utf-8")
        )

    def test_contract_mirrors_the_swift_capture_surface(self) -> None:
        contract = self.contract
        self.assertEqual(contract.window_id, "scene-artwork-verification")
        self.assertEqual(contract.window_title, "场景美术运行时校验")
        self.assertEqual(contract.scene_preference_key, "wom.artwork.verification.scene")
        self.assertEqual(contract.mode_preference_key, "wom.artwork.verification.mode")
        self.assertEqual(contract.variant_preference_key, "wom.artwork.verification.variant")

        self.assertEqual(contract.probe_height, 72)
        self.assertEqual(contract.caption_height, 18)
        self.assertEqual(contract.tile_spacing, 12)
        self.assertEqual(contract.header_height, 44)
        self.assertEqual(contract.probe_inset, 12)
        self.assertEqual(contract.probe_line_height, 14)
        self.assertEqual(contract.probe_line_spacing, 2)
        self.assertEqual(contract.template_match_minimum_tile_width, 154)
        self.assertEqual(contract.tile_aspect_ratio, 16 / 10)
        self.assertEqual(contract.wide_aspect_ratio, 2400 / 900)
        self.assertEqual(contract.content_padding, 12)
        self.assertEqual(contract.title_bar_allowance, 28)
        self.assertEqual(contract.probe_offset_below_image, 0)

    def test_swift_contract_test_pins_the_same_numbers(self) -> None:
        swift_test = (
            REPO_ROOT
            / "macos-app/WorldOfMysteriesTests/SceneArtworkRuntimeVerificationTests.swift"
        ).read_text(encoding="utf-8")

        for literal in (
            "probeHeight == 72",
            "captionHeight == 18",
            "tileSpacing == 12",
            "headerHeight == 44",
            "probeInset == 12",
            "probeLineHeight == 14",
            "probeLineSpacing == 2",
            "templateMatchMinimumTileWidth == 154",
            "probeOffsetBelowImage == 0",
        ):
            self.assertIn(literal, swift_test)

    def test_capture_plan_labels_carry_the_locked_window_geometries(self) -> None:
        harness = self.harness
        plan = {spec.name: spec for spec in harness.capture_plan()}

        for label, geometry in harness.WINDOW_CHECK_GEOMETRIES.items():
            spec = plan[harness.WINDOW_CHECK_CAPTURES[label]]
            self.assertEqual(spec.mode, "grid")
            self.assertEqual(spec.window_size, geometry)
            self.assertEqual(spec.asset_variant, "runtime")

        # 2× 背屏让后两个标签的抓取像素正好等于派生图的原生像素。
        self.assertEqual(
            tuple(value * harness.BACKING_SCALE for value in harness.WINDOW_CHECK_GEOMETRIES["2560x1600"]),
            (2560, 1600),
        )
        self.assertEqual(
            tuple(value * harness.BACKING_SCALE for value in harness.WINDOW_CHECK_GEOMETRIES["2400x900"]),
            (2400, 900),
        )

        probe_specs = [spec for spec in plan.values() if spec.mode == "probe"]
        self.assertEqual(len(probe_specs), 3)
        self.assertEqual(
            {spec.accessibility for spec in probe_specs},
            {None, "increase_contrast", "reduce_transparency"},
        )
        for spec in probe_specs:
            self.assertEqual(spec.asset_variant, "wide")


class LayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_verification_contract(
            VERIFICATION_VIEW.read_text(encoding="utf-8")
        )

    def test_grid_layout_matches_the_swift_expectations(self) -> None:
        expected = {
            (960, 640): (3, 304.0),
            (1180, 760): (3, 1132 / 3),
            (1280, 800): (3, 1232 / 3),
            (1200, 450): (6, 186.0),
        }

        for window_size, (columns, tile_width) in expected.items():
            layout = self.harness.grid_layout(window_size, self.contract)
            self.assertEqual(layout.columns, columns, window_size)
            self.assertAlmostEqual(layout.tile_width, tile_width, places=6, msg=str(window_size))
            self.assertGreaterEqual(
                layout.tile_width, self.contract.template_match_minimum_tile_width
            )
            self.assertLessEqual(layout.required_height(6), self.harness.content_size(window_size, self.contract)[1] + 1e-9)

    def test_probe_layout_fits_the_probe_window(self) -> None:
        layout = self.harness.probe_layout((1180, 760), self.contract)
        self.assertEqual(layout.columns, 3)
        self.assertAlmostEqual(layout.tile_width, 1132 / 3, places=6)
        self.assertEqual(layout.image_height, 142)
        self.assertLessEqual(layout.required_height(6), self.harness.content_size((1180, 760), self.contract)[1])

    def test_expected_scale_tracks_the_rendered_tile(self) -> None:
        plan = {spec.name: spec for spec in self.harness.capture_plan()}
        grid = plan[self.harness.WINDOW_CHECK_CAPTURES["1180x760"]]
        probe = plan[self.harness.PROBE_CAPTURE]

        self.assertAlmostEqual(
            self.harness.expected_asset_scale(grid, self.contract),
            (1132 / 3) * 2 / 2560,
            places=6,
        )
        self.assertAlmostEqual(
            self.harness.expected_asset_scale(probe, self.contract),
            (1132 / 3) * 2 / 2400,
            places=6,
        )


class RegionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = load_harness()
        self.contract = self.harness.parse_verification_contract(
            VERIFICATION_VIEW.read_text(encoding="utf-8")
        )

    def test_probe_regions_sit_inside_the_probe_band(self) -> None:
        # 3 列探针砖块：宽 1150/3 点 → 766 px，wide 原图高 142 点 → 284 px。
        image_box = [200, 400, 200 + 754, 400 + 284]
        regions = self.harness.probe_text_regions(image_box, self.contract)

        probe_top = image_box[3]
        probe_bottom = probe_top + int(self.contract.probe_height * self.harness.BACKING_SCALE)

        for name, region in regions.items():
            with self.subTest(region=name):
                x, y, width, height = region
                self.assertGreaterEqual(x, image_box[0])
                self.assertGreater(x + width, x)
                self.assertGreaterEqual(y, probe_top)
                self.assertLessEqual(y + height, probe_bottom)

        primary = regions["text_primary"]
        important = regions["important_copy"]
        self.assertLess(primary[1], important[1])
        self.assertEqual(primary[0], important[0])

    def test_region_bounds_are_enforced(self) -> None:
        with self.assertRaises(RuntimeError):
            self.harness.assert_region_inside_capture([10, 10, 100, 100], (50, 50))
        self.harness.assert_region_inside_capture([10, 10, 30, 30], (50, 50))


class RegistryTests(unittest.TestCase):
    def test_scene_registry_matches_the_finishing_tool(self) -> None:
        harness = load_harness()
        scenes = harness.scene_registry(FINISH_TOOL)

        self.assertEqual(sorted(scenes), ["W1", "W2", "W3", "W4", "W5", "W6"])
        for task, entry in scenes.items():
            with self.subTest(task=task):
                runtime = harness.asset_path(REPO_ROOT, entry["asset_name"], "runtime")
                wide = harness.asset_path(REPO_ROOT, entry["asset_name"], "wide")
                self.assertTrue(runtime.is_file(), runtime)
                self.assertTrue(wide.is_file(), wide)
                self.assertEqual(runtime.name, f"{entry['asset_name']}.png")
                self.assertEqual(wide.name, f"{entry['asset_name']}.wide.png")


class VerifyOnlyTests(unittest.TestCase):
    """`--verify-only` 复用既有抓取图，因此不能再要求 --app，也不能覆盖采集环境记录。"""

    def test_verify_only_reuses_recorded_environment_without_an_app(self) -> None:
        harness = load_harness()
        recorded_app = "/tmp/wom-worktrees/feat-scene/WorldOfMysteries.app"
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory)
            (out_dir / "capture-summary.json").write_text(
                json.dumps(
                    {
                        "captured_at": "2026-09-19",
                        "captures": {},
                        "environment": {
                            "app": recorded_app,
                            "owner_name": "诡秘世界",
                            "process_name": "WorldOfMysteries",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            plan = harness.capture_plan()
            harness.reuse_captures = lambda plan, out_dir: {
                spec.name: {
                    "sha256": "0" * 64,
                    "width": 2360,
                    "height": 1520,
                    "mode": spec.mode,
                    "window_size": list(spec.window_size),
                    "accessibility_state": spec.accessibility,
                    "accessibility_mechanism": "capture_surface_environment",
                }
                for spec in plan
            }
            harness.surface_report = lambda *args, **kwargs: {
                "asset": {"path": "Assets.xcassets/wom.art.world.hero.imageset/x.png"},
                "best_match": {
                    "score": 0.9,
                    "asset_scale": 0.5,
                    "window_in_capture_pixels": [10, 10, 1140, 700],
                },
                "verdict": "present",
            }

            self.assertEqual(harness.main(["--out-dir", str(out_dir), "--verify-only"]), 0)
            evidence = json.loads(
                (out_dir / "W1_runtime_evidence.json").read_text(encoding="utf-8")
            )

        self.assertEqual(evidence["capture_environment"]["app"], recorded_app)
        self.assertEqual(evidence["capture_environment"]["owner_name"], "诡秘世界")
        self.assertIn("surface_verification", evidence)


class SingleInstanceTests(unittest.TestCase):
    """采集期间必须只有一个 App 进程，而且每条退出路径都要清干净。

    这些测试用假的进程表与假的命令执行器跑真实的守护代码：`ps` 与 `kill` 的结果都由
    测试驱动，所以能断言「只杀自己启动的 pid」「有别的拷贝在跑就先停下」这类语义。
    """

    APP_NAME = "WorldOfMysteries"

    def setUp(self) -> None:
        self.harness = load_harness()
        self.executable = Path(
            "/tmp/wom-worktrees/feat-scene/WorldOfMysteries.app/Contents/MacOS/WorldOfMysteries"
        )
        # 同一份 App 装在 /Applications 时的可执行路径：`pgrep -f` 的单路径匹配会漏掉它。
        self.foreign_copy = "/Applications/WorldOfMysteries.app/Contents/MacOS/WorldOfMysteries"
        self.table: dict[int, str] = {}
        self.commands: list[list[str]] = []

        self.harness.process_table = lambda: dict(self.table)
        self.addCleanup(self.harness.OWNED_PIDS.clear)
        original_run = self.harness.run

        def fake_run(command, *, check=True, timeout=180.0):
            parts = [str(part) for part in command]
            self.commands.append(parts)
            if parts[0] == "open":
                # 只有本次要采集的那份拷贝会被 launch 出来；已有进程不被覆盖。
                self.table.setdefault(101, str(self.executable))
            elif parts[0] == "kill" and parts[-1].isdigit():
                self.table.pop(int(parts[-1]), None)
            return subprocess.CompletedProcess(parts, 0, "", "")

        self.harness.run = fake_run
        self.addCleanup(setattr, self.harness, "run", original_run)

    def killed_pids(self) -> list[str]:
        return [command[2] for command in self.commands if command[0] == "kill"]

    def test_instance_lookup_covers_every_copy_of_the_app(self) -> None:
        self.table = {101: str(self.executable), 202: f"{self.foreign_copy} -psn_0_1"}

        found = self.harness.app_instance_pids(self.APP_NAME, self.executable)

        self.assertEqual(sorted(found), [101, 202], "只按单一路径匹配会漏掉别的拷贝")

    def test_preflight_stops_before_touching_someone_elses_instance(self) -> None:
        self.table = {202: self.foreign_copy}

        with self.assertRaises(RuntimeError) as caught:
            self.harness.ensure_no_instance(self.APP_NAME, self.executable)

        self.assertIn("202", str(caught.exception))
        self.assertEqual(self.killed_pids(), [], "启动前不允许静默结束别人的实例")

    def test_launch_asserts_exactly_one_instance_and_owns_it(self) -> None:
        pid = self.harness.launch_app(self.APP_NAME, Path("/tmp/WorldOfMysteries.app"), self.executable)

        self.assertEqual(pid, 101)
        self.assertEqual(self.harness.OWNED_PIDS, {101})

    def test_launch_refuses_a_second_instance(self) -> None:
        self.table = {101: str(self.executable), 202: self.foreign_copy}

        with self.assertRaises(RuntimeError) as caught:
            self.harness.launch_app(self.APP_NAME, Path("/tmp/WorldOfMysteries.app"), self.executable)

        self.assertIn("恰好一个", str(caught.exception))
        self.assertEqual(self.harness.OWNED_PIDS, set(), "没确认归属的 pid 不进清理名单")

    def test_launch_refuses_a_process_from_another_bundle(self) -> None:
        self.table = {101: self.foreign_copy}

        with self.assertRaises(RuntimeError) as caught:
            self.harness.launch_app(self.APP_NAME, Path("/tmp/WorldOfMysteries.app"), self.executable)

        self.assertIn("不是本次要采集的包", str(caught.exception))
        self.assertEqual(self.harness.OWNED_PIDS, set())

    def test_cleanup_only_terminates_owned_pids_of_the_capture_bundle(self) -> None:
        self.table = {101: str(self.executable), 202: self.foreign_copy}
        self.harness.OWNED_PIDS.update({101, 202})

        self.harness.terminate_owned_instances(self.APP_NAME, self.executable, timeout=1.0)

        self.assertEqual(self.killed_pids(), ["101"], "只 TERM 自己启动、且仍指向采集包的 pid")
        self.assertEqual(self.harness.OWNED_PIDS, set())

    def test_quit_fails_loudly_when_an_instance_survives(self) -> None:
        self.harness.OWNED_PIDS.add(101)
        self.table = {202: self.foreign_copy}

        with self.assertRaises(RuntimeError) as caught:
            self.harness.quit_app(
                "devplaceholder.LK682GAS.WorldOfMysteries",
                self.APP_NAME,
                self.executable,
                timeout=0.4,
            )

        self.assertIn("残留", str(caught.exception))

    def test_residue_assertion_reports_the_remaining_pids(self) -> None:
        self.table = {202: self.foreign_copy}

        with self.assertRaises(RuntimeError) as caught:
            self.harness.assert_no_residue(self.APP_NAME, self.executable)

        self.assertIn("202", str(caught.exception))

    def test_wait_for_exit_returns_once_the_last_instance_is_gone(self) -> None:
        self.table = {101: str(self.executable)}

        def disappear() -> None:
            self.table.clear()

        threading.Timer(0.1, disappear).start()
        self.harness.wait_for_exit(self.APP_NAME, self.executable, timeout=5.0)

        self.assertEqual(self.table, {})

    def test_cleanup_runs_on_exit_and_on_signals(self) -> None:
        registered = []
        original_atexit = self.harness.atexit.register
        original_signal = self.harness.signal.signal
        self.harness.atexit.register = lambda *args: registered.append(args)
        self.harness.signal.signal = lambda number, handler: registered.append((number, handler))
        self.addCleanup(setattr, self.harness.atexit, "register", original_atexit)
        self.addCleanup(setattr, self.harness.signal, "signal", original_signal)

        self.harness.install_cleanup_handlers(self.APP_NAME, self.executable)

        self.assertEqual(registered[0][0], self.harness.terminate_owned_instances)
        handled = {entry[0] for entry in registered[1:]}
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            self.assertIn(getattr(self.harness.signal, name), handled)

    def test_pipeline_cleanup_is_wired_into_finally_and_the_window_lookup(self) -> None:
        source = TOOL_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        def function(name: str) -> ast.FunctionDef:
            return next(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name
            )

        collect = function("collect_captures")
        finalizers = [
            node for node in ast.walk(collect) if isinstance(node, ast.Try) and node.finalbody
        ]
        self.assertTrue(finalizers, "collect_captures 必须有 finally 收尾")
        cleaned = {
            child.func.id
            for finalizer in finalizers
            for child in ast.walk(ast.Module(body=finalizer.finalbody, type_ignores=[]))
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        for required in (
            "quit_app",
            "terminate_owned_instances",
            "assert_no_residue",
            "clear_preferences",
        ):
            self.assertIn(required, cleaned)

        main_calls = [
            node.func.id
            for node in ast.walk(function("main"))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertLess(
            main_calls.index("ensure_no_instance"),
            main_calls.index("collect_captures"),
            "启动前必须先断开单实例前提",
        )

        window_lookup = function("window_number_for_size")
        self.assertIn(
            "pid",
            {argument.arg for argument in window_lookup.args.kwonlyargs},
            "窗口查找必须按 pid 收窄",
        )
        self.assertIn(
            "pid",
            {
                keyword.arg
                for node in ast.walk(collect)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "window_number_for_size"
                for keyword in node.keywords
            },
            "抓窗口必须锚定本次启动的 pid",
        )


if __name__ == "__main__":
    unittest.main()
