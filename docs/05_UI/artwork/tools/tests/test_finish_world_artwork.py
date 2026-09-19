"""Tests for the macOS finishing pipeline, focused on the evidence chain.

The tool's value is that it refuses to bless unverifiable bytes, so these tests mostly assert
refusals: a modified stage output, a wrong wide anchor, a catalog payload that no longer matches
the derivative, and runtime evidence that asserts a pass without verifiable captures.

Run::

    python3 -m unittest discover -s docs/05_UI/artwork/tools/tests -v

The tests need ``numpy`` and ``Pillow`` (the tool imports them); they skip cleanly without them.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parent.parent / "finish_world_artwork.py"

try:  # pragma: no cover - environment guard
    import numpy as np
    from PIL import Image, ImageDraw

    DEPENDENCIES_AVAILABLE = True
except ImportError:  # pragma: no cover - environment guard
    DEPENDENCIES_AVAILABLE = False


def load_tool():
    spec = importlib.util.spec_from_file_location("finish_world_artwork", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "numpy and Pillow are required for the finishing tool")
class EvidenceChainTests(unittest.TestCase):
    """Exercises ``record`` against a miniature but byte-consistent finishing chain."""

    def setUp(self) -> None:
        self.tool = load_tool()
        self.task = "W1"
        self.scene = self.tool.SCENES[self.task]
        self.asset_name = self.scene["asset_name"]
        self.wide_name = f"{self.asset_name}.wide"
        self.temp = Path(tempfile.mkdtemp(prefix="wom-finishing-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.work = self.temp / "work"
        self.work.mkdir()
        self.catalog = self.temp / "Assets.xcassets"
        self.qa = self.temp / "qa.json"
        self.provenance = self.temp / "provenance.json"
        self.source = self.temp / "source.png"
        self._build_chain()

    # -- fixture -------------------------------------------------------------------------

    def _write_png(
        self, name: str, size: tuple[int, int], colour, patch_colour=(180, 40, 40)
    ) -> Path:
        path = self.work / name
        image = Image.new("RGB", size, colour)
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, size[0] // 4, size[1] // 4], fill=patch_colour)
        image.save(path, format="PNG")
        return path

    def _describe(self, path: Path) -> dict:
        with Image.open(path) as image:
            width, height = image.size
        return {
            "path": path.name,
            "width": width,
            "height": height,
            "sha256": sha256_of(path),
        }

    def _build_chain(self, patch_colour=(180, 40, 40)) -> None:
        crop = self._write_png(f"{self.task}_01_crop.png", (1584, 990), (30, 34, 44), patch_colour)
        self.source.write_bytes(crop.read_bytes())
        sr = self._write_png(f"{self.task}_02_sr.png", (1584, 990), (32, 36, 46), patch_colour)
        grade = self._write_png(f"{self.task}_03_grade.png", (1584, 990), (34, 38, 48), patch_colour)
        master = self._write_png(f"{self.task}_MASTER.png", (4096, 2560), (40, 44, 54), patch_colour)
        runtime = self._write_png(f"{self.asset_name}.png", (2560, 1600), (40, 44, 54), patch_colour)
        wide = self._write_png(f"{self.wide_name}.png", (2400, 900), (40, 44, 54), patch_colour)

        reports = {
            "crop": {
                "rect_pixels": [1, 1, 1585, 991],
                "input": self._describe(self.source),
                "output": self._describe(crop),
            },
            "sr": {
                "method": "Real-ESRGAN RRDBNet x4 (single pass)",
                "device": "test",
                "weights": "test.pth",
                "weights_sha256": "0" * 64,
                "tile": 512,
                "overlap": 32,
                "scale": 4,
                "downstream_downsample": "6144x3840",
                "input": self._describe(crop),
                "output": self._describe(sr),
            },
            "grade": {
                "profile": "subtle-illustration-v1",
                "parameters": {"midtone_contrast": 0.06},
                "generative": False,
                "input": self._describe(sr),
                "output": self._describe(grade),
            },
            "master": {
                "operation": "controlled_downsample_to_production_master",
                "resample": "Lanczos",
                "input": self._describe(grade),
                "output": self._describe(master),
            },
            "derivatives": {
                "input": self._describe(master),
                "wideAnchor": self.scene["wide_anchor"],
                "runtime": {**self._describe(runtime), "size": {"width": 2560, "height": 1600}},
                "wide": {**self._describe(wide), "size": {"width": 2400, "height": 900}},
            },
        }
        reports["fidelity"] = {
            "reference": self._describe(crop),
            "candidate": self._describe(master),
            "mean_absolute_difference_0_255": 3.0,
            "luminance_correlation": 0.99,
            "edge_structure_correlation": 0.95,
            "verdict": "passed",
        }
        for stage, payload in reports.items():
            (self.work / f"{self.task}_report_{stage}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

        for asset in (self.asset_name, self.wide_name):
            imageset = self.catalog / f"{asset}.imageset"
            imageset.mkdir(parents=True, exist_ok=True)
            (imageset / "Contents.json").write_text(
                json.dumps({"images": [{"filename": f"{asset}.png", "idiom": "universal", "scale": "1x"}]}),
                encoding="utf-8",
            )
            shutil.copy(self.work / f"{asset}.png", imageset / f"{asset}.png")

        self.inspection = self.temp / "inspection.json"
        self.inspection.write_text(
            json.dumps(
                {
                    "scales_percent": [25, 100, 200],
                    "method": "fixture inspection",
                    "defects_found": [],
                }
            ),
            encoding="utf-8",
        )

    def _record(self, *, runtime_evidence: Path | None = None, require_complete: bool = False) -> int:
        argv = [
            "record",
            "--task", self.task,
            "--work-dir", str(self.work),
            "--source", str(self.source),
            "--catalog-root", str(self.catalog),
            "--inspection", str(self.inspection),
            "--qa", str(self.qa),
            "--provenance", str(self.provenance),
        ]
        if runtime_evidence is not None:
            argv += ["--runtime-evidence", str(runtime_evidence)]
        if require_complete:
            argv.append("--require-complete")
        with contextlib.redirect_stdout(io.StringIO()):
            return self.tool.main(argv)

    def _qa(self) -> dict:
        return json.loads(self.qa.read_text(encoding="utf-8"))

    # -- tests ---------------------------------------------------------------------------

    def test_byte_verified_chain_records_gates_but_stays_pending_without_runtime_evidence(self) -> None:
        self.assertEqual(self._record(), 0)
        qa = self._qa()
        gates = qa["gates"]
        self.assertEqual(gates["G3_structure"]["status"], "PASSED")
        self.assertEqual(gates["G4_production"]["status"], "PASSED")
        self.assertTrue(gates["G4_production"]["catalog"]["matches_derivatives"])
        self.assertEqual(gates["G5_runtime"]["status"], "PENDING_RUNTIME_QA")
        self.assertEqual(gates["G2_composition"]["status"], "PENDING_RUNTIME_QA")
        self.assertNotEqual(qa["final_verdict"], "PASSED")
        provenance = json.loads(self.provenance.read_text(encoding="utf-8"))
        self.assertNotEqual(provenance["status"], "APPROVED")
        self.assertIsNone(provenance["approved_at"])

    def test_require_complete_fails_while_a_gate_is_open(self) -> None:
        self.assertEqual(self._record(require_complete=True), 1)
        self.assertNotEqual(self._qa()["final_verdict"], "PASSED")

    def test_modified_stage_output_is_refused(self) -> None:
        master = self.work / f"{self.task}_MASTER.png"
        Image.new("RGB", (4096, 2560), (1, 2, 3)).save(master, format="PNG")
        with self.assertRaises(SystemExit) as context:
            self._record()
        self.assertIn("master", str(context.exception))

    def test_wrong_wide_anchor_is_refused(self) -> None:
        report = json.loads((self.work / f"{self.task}_report_derivatives.json").read_text())
        report["wideAnchor"] = "bottom" if self.scene["wide_anchor"] != "bottom" else "top"
        (self.work / f"{self.task}_report_derivatives.json").write_text(json.dumps(report))
        with self.assertRaises(SystemExit) as context:
            self._record()
        self.assertIn("wide anchor", str(context.exception))

    def test_catalog_payload_that_differs_from_the_derivative_is_refused(self) -> None:
        payload = self.catalog / f"{self.wide_name}.imageset" / f"{self.wide_name}.png"
        Image.new("RGB", (2400, 900), (9, 9, 9)).save(payload, format="PNG")
        with self.assertRaises(SystemExit) as context:
            self._record()
        self.assertIn("byte-identical", str(context.exception))

    def test_declared_runtime_claims_without_captures_cannot_pass_g5(self) -> None:
        evidence = self.temp / "runtime_evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "captured_at": "2026-09-18",
                    "window_checks": {
                        size: {"text_legible": True, "identity_visible": True}
                        for size in ("960x640", "1180x760", "2560x1600", "2400x900")
                    },
                    "accessibility_checks": {
                        state: {"text_legible": True, "artwork_readable": True}
                        for state in ("Increased Contrast", "Reduce Transparency")
                    },
                    "contrast": {
                        "text_primary_contrast_min": 21.0,
                        "important_copy_contrast_min": 21.0,
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self._record(runtime_evidence=evidence), 0)
        gate = self._qa()["gates"]["G5_runtime"]
        self.assertEqual(gate["status"], "PENDING_RUNTIME_QA")
        self.assertTrue(gate["unmet_requirements"])
        self.assertIsNone(gate["contrast"]["text_primary_contrast_min"])

    def _passing_runtime_evidence(self) -> tuple[Path, str]:
        """One verified capture whose black backing and white block recompute to a 21:1 ratio."""

        capture = self.temp / "capture_default.png"
        image = Image.new("RGB", (800, 500), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle([20, 20, 380, 220], fill=(255, 255, 255))
        image.save(capture, format="PNG")
        digest = sha256_of(capture)
        region = [10, 10, 400, 240]

        evidence = self.temp / "runtime_evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "captured_at": "2026-09-18",
                    "captures": [{"file": capture.name, "sha256": digest}],
                    "window_checks": {
                        size: {
                            "capture": capture.name,
                            "text_legible": True,
                            "identity_visible": True,
                        }
                        for size in ("960x640", "1180x760", "2560x1600", "2400x900")
                    },
                    "accessibility_checks": {
                        state: {
                            "capture": capture.name,
                            "text_legible": True,
                            "artwork_readable": True,
                        }
                        for state in ("Increased Contrast", "Reduce Transparency")
                    },
                    "contrast": {
                        # A deliberately wrong declared ratio: the tool must recompute instead.
                        "text_primary_contrast_min": 99.0,
                        "important_copy_contrast_min": 99.0,
                        "measurements": [
                            {"capture": capture.name, "region": region, "kind": "text_primary"},
                            {"capture": capture.name, "region": region, "kind": "important_copy"},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        return evidence, digest

    def test_runtime_evidence_with_verified_captures_passes_and_ignores_declared_ratios(self) -> None:
        evidence, digest = self._passing_runtime_evidence()
        self.assertEqual(self._record(runtime_evidence=evidence), 0)
        gate = self._qa()["gates"]["G5_runtime"]
        self.assertEqual(gate["status"], "PASSED")
        self.assertEqual(gate["window_checks"]["960x640"]["capture_sha256"], digest)
        self.assertAlmostEqual(gate["contrast"]["text_primary_contrast_min"], 21.0, delta=0.5)
        self.assertEqual(self._qa()["final_verdict"], "PASSED")
        self.assertEqual(json.loads(self.provenance.read_text())["status"], "APPROVED")

    def test_scene_that_lost_its_identity_motif_cannot_be_approved(self) -> None:
        # Rebuild the same chain without any identity-bearing pixels, then hand it evidence that
        # satisfies G5: the verdict must still refuse, because G2 did not pass.
        self._build_chain(patch_colour=(40, 44, 54))
        evidence, _ = self._passing_runtime_evidence()
        self.assertEqual(self._record(runtime_evidence=evidence, require_complete=False), 0)
        qa = self._qa()
        self.assertEqual(qa["gates"]["G2_composition"]["status"], "PENDING_RUNTIME_QA")
        self.assertEqual(qa["gates"]["G5_runtime"]["status"], "PASSED")
        self.assertNotEqual(qa["final_verdict"], "PASSED")
        self.assertNotEqual(json.loads(self.provenance.read_text())["status"], "APPROVED")

    def test_tampered_capture_digest_blocks_g5(self) -> None:
        capture = self.temp / "capture_changed.png"
        Image.new("RGB", (400, 300), (10, 10, 10)).save(capture, format="PNG")
        evidence = self.temp / "runtime_evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "captures": [{"file": capture.name, "sha256": "f" * 64}],
                    "window_checks": {
                        size: {"capture": capture.name, "text_legible": True, "identity_visible": True}
                        for size in ("960x640", "1180x760", "2560x1600", "2400x900")
                    },
                    "accessibility_checks": {
                        state: {
                            "capture": capture.name,
                            "text_legible": True,
                            "artwork_readable": True,
                        }
                        for state in ("Increased Contrast", "Reduce Transparency")
                    },
                    "contrast": {
                        "measurements": [
                            {"capture": capture.name, "region": [0, 0, 100, 100], "kind": "text_primary"},
                            {"capture": capture.name, "region": [0, 0, 100, 100], "kind": "important_copy"},
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        self._record(runtime_evidence=evidence)
        gate = self._qa()["gates"]["G5_runtime"]
        self.assertEqual(gate["status"], "PENDING_RUNTIME_QA")
        self.assertTrue(any("sha256" in item for item in gate["unmet_requirements"]))


@unittest.skipUnless(DEPENDENCIES_AVAILABLE, "numpy is required for the surface matcher")
class SurfaceMatcherTests(unittest.TestCase):
    def test_normalised_correlation_matches_brute_force(self) -> None:
        tool = load_tool()
        rng = np.random.default_rng(7)
        for _ in range(3):
            capture = (rng.random((90, 120)).astype(np.float32) * 180 + 20)
            template = (rng.random((24, 32)).astype(np.float32) * 180 + 20)
            origin = (int(rng.integers(0, 88)), int(rng.integers(0, 66)))
            capture[origin[1]:origin[1] + 24, origin[0]:origin[0] + 32] = template

            score, (x, y) = tool._max_normalised_correlation(capture, template)

            best = (-2.0, (0, 0))
            for candidate_y in range(capture.shape[0] - 24 + 1):
                for candidate_x in range(capture.shape[1] - 32 + 1):
                    window = capture[candidate_y:candidate_y + 24, candidate_x:candidate_x + 32]
                    window = window.astype(np.float64)
                    a = window - window.mean()
                    b = template.astype(np.float64) - template.astype(np.float64).mean()
                    value = (a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum())
                    if value > best[0]:
                        best = (value, (candidate_x, candidate_y))

            self.assertAlmostEqual(score, best[0], places=6)
            self.assertEqual((x, y), best[1])
            # float32 inputs through a float64 FFT land a hair above 1.0.
            self.assertLessEqual(score, 1.0 + 1e-5)


class RecordHygieneTests(unittest.TestCase):
    """Tracked records are read on other machines, so they must stay path-portable."""

    def test_tracked_records_contain_no_absolute_paths(self) -> None:
        artwork_root = Path(__file__).resolve().parents[2]
        pattern = re.compile(r"file:///|/Users/|/home/|[A-Z]:\\|/var/folders/")
        offenders = []
        for folder in ("qa", "provenance"):
            for path in sorted((artwork_root / folder).glob("*.json")):
                if pattern.search(path.read_text(encoding="utf-8")):
                    offenders.append(f"{folder}/{path.name}")
        self.assertEqual(offenders, [], f"absolute paths leaked into {offenders}")


if __name__ == "__main__":
    unittest.main()
