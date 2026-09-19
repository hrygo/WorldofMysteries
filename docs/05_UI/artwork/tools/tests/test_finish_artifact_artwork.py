"""Artifact finishing regressions: byte stability, contract sizes and fail-closed records.

The super-resolution stage needs torch and the Real-ESRGAN weights, so the miniature chain used
here stubs that one stage with a deterministic Lanczos upscale and exercises every other stage for
real. The stub is still written as a normal stage report, so `record` verifies the whole chain.
"""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

try:
    import numpy  # noqa: F401
    from PIL import Image
except ImportError as error:  # pragma: no cover - depends on the local interpreter
    raise unittest.SkipTest(
        f"the Artifact finishing tests need numpy and Pillow ({error}); run them with an "
        "environment that has them"
    ) from error

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
spec = importlib.util.spec_from_file_location(
    "finish_artifact_artwork", TOOLS / "finish_artifact_artwork.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TASK = "A01"
ARTIFACT_ID = "arrodesMirror"
ASSET = "wom.art.artifact.arrodes"
DETAIL = f"{ASSET}.detail"
THUMBNAIL = f"{ASSET}.thumbnail"
PROFILE_DATE_BYTES = struct.pack(">6H", *tool.FIXED_PROFILE_DATE)


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = tool.main(argv)
    return code, json.loads(buffer.getvalue() or "{}")


def gradient(size, seed):
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = (
                (x * 7 + seed) % 256,
                (y * 5 + seed * 3) % 256,
                (x * 3 + y * 2 + seed) % 256,
            )
    return image


class ArtifactToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.work = cls.root / "work"
        cls.work.mkdir()
        cls.catalog = cls.root / "Assets.xcassets"
        cls.catalog.mkdir()

        cls.source = cls.root / "source.png"
        gradient((40, 52), 11).save(cls.source, format="PNG")

        cls.manifest = cls.root / "manifest.json"
        targets = [
            {
                "order": 1,
                "phase": "P0",
                "artifact_id": ARTIFACT_ID,
                "display_name": "A01",
                "asset_name": ASSET,
                "source_id": "A01_ARRODES_MIRROR",
                "status": "SOURCE_LOCKED_FINISHING_PENDING",
                "shipping_approved": False,
            }
        ]
        # The manifest contract covers all 15 Artifact slots; only A01 has a chain on disk here.
        targets.extend(
            {
                "order": order,
                "phase": "P0" if order <= 7 else "P1",
                "artifact_id": f"testArtifact{order}",
                "display_name": f"A{order:02d}",
                "asset_name": f"wom.art.artifact.test-{order}",
                "source_id": f"A{order:02d}_TEST_SOURCE",
                "status": "SOURCE_LOCKED_FINISHING_PENDING",
                "shipping_approved": False,
            }
            for order in range(2, 16)
        )
        write_json(
            cls.manifest,
            {"artifact_targets": targets},
        )

        cls.inspection = cls.root / "inspection.json"
        write_json(
            cls.inspection,
            {
                "protocol": {"method": "miniature chain", "scales_percent": [25, 100, 200]},
                "artifacts": {
                    TASK: {
                        "scales_percent": [25, 100, 200],
                        "defects_found": [],
                        "primary_read": "a small test object",
                        "typography_detected": False,
                        "crop_safety_note": "the subject is centred",
                    }
                },
            },
        )
        cls.build_chain()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def build_chain(cls, work=None):
        work = Path(work or cls.work)
        work.mkdir(parents=True, exist_ok=True)

        crop_path = work / f"{TASK}_01_square.png"
        with Image.open(cls.source) as opened:
            tool.save_png(opened.crop((0, 6, 40, 46)), crop_path)
        write_json(
            work / f"{TASK}_report_square_crop.json",
            {
                "operation": "deterministic_centred_square_safety_crop",
                "generative": False,
                "upscale": False,
                "rect_pixels": [0, 6, 40, 46],
                "removed_pixels": {"left": 0, "top": 6, "right": 0, "bottom": 6},
                "input": {"path": cls.source.name, "width": 40, "height": 52,
                          "sha256": digest(cls.source)},
                "output": {"path": crop_path.name, "width": 40, "height": 40,
                           "sha256": digest(crop_path)},
            },
        )

        # Stub of the learned pass: a deterministic Lanczos upscale recorded as a normal stage,
        # so `record` still proves the chain is intact end to end.
        sr_path = work / f"{TASK}_02_sr.png"
        with Image.open(crop_path) as opened:
            tool.save_png(opened.resize((2048, 2048), Image.LANCZOS), sr_path)
        write_json(
            work / f"{TASK}_report_sr.json",
            {
                "operation": "macos_primary_super_resolution",
                "method": "stub (unit test)",
                "device": "cpu",
                "weights": "stub.pth",
                "weights_sha256": "0" * 64,
                "tile": 512,
                "overlap": 32,
                "scale": 4,
                "downstream_downsample": "2048x2048",
                "passes": 1,
                "input": {"path": crop_path.name, "width": 40, "height": 40,
                          "sha256": digest(crop_path)},
                "output": {"path": sr_path.name, "width": 2048, "height": 2048,
                           "sha256": digest(sr_path)},
            },
        )

        # The CLI prints its stage report; the workbench redirects that into `<task>_report_*.json`
        # and `record` reads those files back, so the miniature chain writes them the same way.
        grade_path = work / f"{TASK}_03_grade.png"
        master_path = work / f"{TASK}_MASTER_2048x2048.png"
        stages = (
            ("grade", ["grade", "--input", str(sr_path), "--output", str(grade_path)]),
            ("master", ["master", "--input", str(grade_path), "--output", str(master_path)]),
            ("derive", ["derive", "--master", str(master_path),
                        "--detail-asset", DETAIL, "--detail-output", str(work / f"{DETAIL}.png"),
                        "--thumbnail-asset", THUMBNAIL,
                        "--thumbnail-output", str(work / f"{THUMBNAIL}.png")]),
            ("fidelity", ["fidelity", "--reference", str(crop_path),
                          "--candidate", str(master_path)]),
        )
        for stage, argv in stages:
            _, payload = run(argv)
            write_json(work / f"{TASK}_report_{stage}.json", payload)
        return work

    def record_argv(self, work=None, **overrides):
        work = Path(work or self.work)
        decision = overrides.pop("text_decision", self.root / "no-text-decision.json")
        argv = [
            "record", "--task", TASK, "--work-dir", str(work),
            "--manifest", str(self.manifest),
            "--inspection", str(self.inspection),
            "--catalog-root", str(self.catalog),
            "--reviewed-at", "2026-01-01",
            "--text-decision", str(decision),
            "--qa", str(work / f"{TASK}.qa.json"),
            "--provenance", str(work / f"{TASK}.provenance.json"),
        ]
        for key, value in overrides.items():
            flag = f"--{key.replace('_', '-')}"
            if value is True:
                argv.append(flag)
            else:
                argv.extend([flag, str(value)])
        return argv

    def text_inspection(self, defects=("baked_readable_text",), name="text-inspection.json"):
        document = json.loads(self.inspection.read_text())
        entry = document["artifacts"][TASK]
        entry["typography_detected"] = True
        entry["defects_found"] = list(defects)
        entry["baked_text_findings"] = [
            {"location": "spine", "text": "THE FOOL", "legibility": "LEGIBLE_AT_100_PERCENT"}
        ]
        path = self.root / name
        write_json(path, document)
        return path

    def text_decision_file(
        self, artwork_id=f"{TASK}_ARRODES_MIRROR", defects=("baked_readable_text",),
        name="text-decision.json",
    ):
        path = self.root / name
        write_json(
            path,
            {
                "schema_version": 1,
                "decision": "ACCEPT_DECORATIVE_INSCRIPTIONAL_TEXT",
                "decided_at": "2026-09-19",
                "decided_by": "user",
                "artifacts": {
                    artwork_id: {"text_approved": True, "accepted_defects": list(defects)}
                },
            },
        )
        return path

    def apply_argv(self, decision, qa=None, provenance=None):
        work = Path(self.work)
        return [
            "apply-text-decision",
            "--qa", str(qa or work / f"{TASK}.qa.json"),
            "--provenance", str(provenance or work / f"{TASK}.provenance.json"),
            "--decision", str(decision),
            "--applied-at", "2026-09-19",
        ]

    def catalog_for(self, name):
        imageset = self.catalog / f"{name}.imageset"
        if not imageset.is_dir():
            run(["publish-catalog", "--task", TASK, "--work-dir", str(self.work),
                 "--catalog-root", str(self.catalog)])
        return imageset

    # -- geometry ---------------------------------------------------------------------

    def test_square_crop_rule(self):
        self.assertEqual(tool.square_crop_rect(1254, 1254), (0, 0, 1254, 1254))
        self.assertEqual(tool.square_crop_rect(1222, 1287), (0, 32, 1222, 1254))
        self.assertEqual(tool.square_crop_rect(1371, 1148), (111, 0, 1259, 1148))
        self.assertEqual(tool.square_crop_rect(100, 100, 64), (18, 18, 82, 82))

    def test_square_crop_refuses_to_invent_pixels(self):
        for size in (1372, 2048):
            with self.subTest(size=size), self.assertRaises(ValueError):
                tool.square_crop_rect(1371, 1148, size)

    def test_square_crop_never_stretches(self):
        output = self.root / "crop.png"
        _, report = run(["square-crop", "--input", str(self.source), "--output", str(output)])
        self.assertFalse(report["upscale"])
        self.assertEqual(report["rect_pixels"], [0, 6, 40, 46])
        self.assertEqual(
            report["removed_pixels"], {"left": 0, "top": 6, "right": 0, "bottom": 6}
        )
        with Image.open(output) as produced:
            self.assertEqual(produced.size, (40, 40))
            self.assertTrue(produced.info.get("icc_profile"))

    # -- colour management ------------------------------------------------------------

    def test_icc_profile_is_a_normalised_srgb_profile(self):
        profile = tool.srgb_profile_bytes()
        self.assertEqual(profile[36:40], b"acsp")
        self.assertEqual(profile[24:36], PROFILE_DATE_BYTES)
        self.assertNotEqual(profile[:24], b"\x00" * 24)
        self.assertEqual(profile, tool.srgb_profile_bytes())

    def test_outputs_are_byte_stable_across_runs(self):
        first, second = self.root / "stable_a.png", self.root / "stable_b.png"
        for target in (first, second):
            run(["square-crop", "--input", str(self.source), "--output", str(target)])
        self.assertEqual(digest(first), digest(second))
        self.assertEqual(tool.pixel_sha256(first), tool.pixel_sha256(second))

    # -- master and derivatives -------------------------------------------------------

    def test_master_refuses_to_upscale(self):
        with self.assertRaises(SystemExit):
            run(["master", "--input", str(Path(self.work) / f"{TASK}_01_square.png"),
                 "--output", str(self.root / "never.png")])
        self.assertFalse((self.root / "never.png").exists())

    def test_derive_requires_the_contract_master(self):
        with self.assertRaises(SystemExit):
            run(["derive", "--master", str(self.source),
                 "--detail-asset", DETAIL, "--detail-output", str(self.root / "d.png"),
                 "--thumbnail-asset", THUMBNAIL, "--thumbnail-output", str(self.root / "t.png")])

    def test_derive_sizes_and_stability(self):
        report = json.loads((Path(self.work) / f"{TASK}_report_derive.json").read_text())
        self.assertFalse(report["independent_regeneration"])
        self.assertFalse(report["generative"])
        self.assertEqual((report["detail"]["width"], report["detail"]["height"]), (1024, 1024))
        self.assertEqual(
            (report["thumbnail"]["width"], report["thumbnail"]["height"]), (512, 512)
        )
        again = self.root / "again"
        self.build_chain(again)
        repeat = json.loads((again / f"{TASK}_report_derive.json").read_text())
        self.assertEqual(report["detail"]["sha256"], repeat["detail"]["sha256"])
        self.assertEqual(report["thumbnail"]["sha256"], repeat["thumbnail"]["sha256"])

    # -- catalog publication ----------------------------------------------------------

    def test_publish_catalog_payload_matches_the_derivative(self):
        imageset = self.catalog_for(DETAIL)
        contents = json.loads((imageset / "Contents.json").read_text())
        payloads = [entry["filename"] for entry in contents["images"] if entry.get("filename")]
        self.assertEqual(payloads, [f"{DETAIL}.png"])
        derive = json.loads((Path(self.work) / f"{TASK}_report_derive.json").read_text())
        self.assertEqual(digest(imageset / payloads[0]), derive["detail"]["sha256"])

    def test_publish_catalog_refuses_to_overwrite(self):
        self.catalog_for(DETAIL)
        with self.assertRaises(SystemExit):
            run(["publish-catalog", "--task", TASK, "--work-dir", str(self.work),
                 "--catalog-root", str(self.catalog)])

    # -- fail-closed record -----------------------------------------------------------

    def test_record_writes_honest_gates(self):
        self.catalog_for(DETAIL)
        code, payload = run(self.record_argv())
        self.assertEqual(code, 0)
        self.assertEqual(payload["final_verdict"], "PRODUCTION_EVIDENCE_PENDING")
        self.assertEqual(payload["pending_gates"], ["G1_canon_atmosphere", "G5_runtime"])

        qa = json.loads((Path(self.work) / f"{TASK}.qa.json").read_text())
        self.assertEqual(qa["gates"]["G4_production"]["status"], "PASSED")
        self.assertTrue(qa["gates"]["G4_production"]["catalog"]["matches_derivatives"])
        self.assertEqual(qa["gates"]["G5_runtime"]["status"], "PENDING_RUNTIME_QA")
        self.assertEqual(
            qa["gates"]["G4_production"]["master_dimensions"], {"width": 2048, "height": 2048}
        )
        self.assertIs(qa["production_evidence"]["independent_derivative_generation"], False)

        provenance = json.loads((Path(self.work) / f"{TASK}.provenance.json").read_text())
        self.assertIs(provenance["shipping_approved"], False)
        self.assertIs(provenance["master"]["runtime_loadable"], False)
        stages = [stage["stage"] for stage in provenance["postprocess"]]
        self.assertIn("oversample_downsample_to_2048x2048_artifact_master", stages)
        derivatives = provenance["derivatives"]
        self.assertEqual([entry["asset_name"] for entry in derivatives], [DETAIL, THUMBNAIL])
        self.assertTrue(all(entry["catalog_payload_verified"] for entry in derivatives))

    def test_record_requires_complete_returns_non_zero(self):
        self.catalog_for(DETAIL)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = tool.main(self.record_argv(require_complete=True))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(buffer.getvalue())["result"], "INCOMPLETE")

    def test_record_refuses_a_missing_stage(self):
        for stage in ("square_crop", "sr", "grade", "master"):
            with self.subTest(stage=stage):
                work = self.root / f"missing-{stage}"
                shutil.copytree(self.work, work)
                (work / f"{TASK}_report_{stage}.json").unlink()
                with self.assertRaises(SystemExit):
                    run(self.record_argv(work))

    def test_record_refuses_tampered_stage_output(self):
        work = self.root / "tampered"
        shutil.copytree(self.work, work)
        tool.save_png(gradient((2048, 2048), 3), work / f"{TASK}_MASTER_2048x2048.png")
        with self.assertRaises(SystemExit):
            run(self.record_argv(work))

    def test_record_refuses_a_broken_stage_chain(self):
        work = self.root / "broken-chain"
        shutil.copytree(self.work, work)
        report = json.loads((work / f"{TASK}_report_grade.json").read_text())
        report["input"]["sha256"] = "0" * 64
        write_json(work / f"{TASK}_report_grade.json", report)
        with self.assertRaises(SystemExit):
            run(self.record_argv(work))

    def test_record_refuses_failed_fidelity(self):
        work = self.root / "bad-fidelity"
        shutil.copytree(self.work, work)
        report = json.loads((work / f"{TASK}_report_fidelity.json").read_text())
        report["verdict"] = "failed"
        write_json(work / f"{TASK}_report_fidelity.json", report)
        with self.assertRaises(SystemExit):
            run(self.record_argv(work))

    def test_record_refuses_derivatives_from_another_master(self):
        work = self.root / "wrong-master"
        shutil.copytree(self.work, work)
        report = json.loads((work / f"{TASK}_report_derive.json").read_text())
        report["input"]["sha256"] = "1" * 64
        write_json(work / f"{TASK}_report_derive.json", report)
        with self.assertRaises(SystemExit):
            run(self.record_argv(work))

    def test_record_refuses_a_catalog_payload_that_is_not_the_derivative(self):
        self.catalog_for(DETAIL)
        work = self.root / "catalog-drift"
        shutil.copytree(self.work, work)
        payload = self.catalog / f"{DETAIL}.imageset" / f"{DETAIL}.png"
        original = payload.read_bytes()
        try:
            tool.save_png(gradient((1024, 1024), 5), payload)
            with self.assertRaises(SystemExit):
                run(self.record_argv(work))
        finally:
            payload.write_bytes(original)

    def test_record_keeps_g0_and_g3_open_for_baked_text(self):
        document = json.loads(self.inspection.read_text())
        entry = document["artifacts"][TASK]
        entry["typography_detected"] = True
        entry["defects_found"] = ["baked_readable_text"]
        entry["baked_text_findings"] = [
            {"location": "spine", "text": "THE FOOL", "legibility": "LEGIBLE_AT_100_PERCENT"}
        ]
        inspection = self.root / "text-inspection.json"
        write_json(inspection, document)
        self.catalog_for(DETAIL)
        code, payload = run(self.record_argv(inspection=inspection))
        self.assertEqual(code, 0)
        self.assertEqual(
            sorted(payload["pending_gates"]),
            ["G0_semantic", "G1_canon_atmosphere", "G3_structure", "G5_runtime"],
        )
        qa = json.loads((Path(self.work) / f"{TASK}.qa.json").read_text())
        self.assertEqual(qa["gates"]["G0_semantic"]["status"], "PENDING_MACOS_FINISHING")
        self.assertEqual(qa["gates"]["G3_structure"]["status"], "PENDING_MACOS_FINISHING")
        self.assertEqual(qa["gates"]["G3_structure"]["defects_found"], ["baked_readable_text"])

    def test_record_applies_a_recorded_text_decision(self):
        inspection = self.text_inspection()
        decision = self.text_decision_file()
        self.catalog_for(DETAIL)
        code, payload = run(self.record_argv(inspection=inspection, text_decision=decision))
        self.assertEqual(code, 0)
        self.assertEqual(sorted(payload["pending_gates"]), ["G1_canon_atmosphere", "G5_runtime"])

        qa = json.loads((Path(self.work) / f"{TASK}.qa.json").read_text())
        self.assertEqual(qa["gates"]["G0_semantic"]["status"], "PASSED")
        self.assertEqual(
            qa["gates"]["G0_semantic"]["status_basis"],
            "ART_DIRECTION_ACCEPTED_DECORATIVE_INSCRIPTION",
        )
        self.assertEqual(qa["gates"]["G3_structure"]["status"], "PASSED")
        self.assertEqual(qa["gates"]["G3_structure"]["accepted_defects"], ["baked_readable_text"])
        self.assertEqual(qa["gates"]["G3_structure"]["blocking_defects"], [])
        self.assertIn("art_direction_text_decision", qa["reviewers"])
        self.assertEqual(len(qa["text_policy_decision"]["sha256"]), 64)
        self.assertEqual(qa["text_policy_decision"]["decided_by"], "user")

        provenance = json.loads((Path(self.work) / f"{TASK}.provenance.json").read_text())
        self.assertEqual(provenance["gates"]["G0_semantic"], "PASSED")
        self.assertEqual(provenance["gates"]["G3_structure"], "PASSED")
        self.assertEqual(
            provenance["text_policy_decision"]["applied_to"], ["G0_semantic", "G3_structure"]
        )

    def test_apply_text_decision_revises_an_existing_record(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        qa_path = Path(self.work) / f"{TASK}.qa.json"
        provenance_path = Path(self.work) / f"{TASK}.provenance.json"
        before = digest(qa_path)

        code, payload = run(self.apply_argv(self.text_decision_file()))
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "REVISED")
        self.assertEqual(payload["revised_gates"], ["G0_semantic", "G3_structure"])

        qa = json.loads(qa_path.read_text())
        self.assertEqual(sorted(qa["pending_gates"]), ["G1_canon_atmosphere", "G5_runtime"])
        self.assertEqual(qa["final_verdict"], "PRODUCTION_EVIDENCE_PENDING")
        self.assertEqual(qa["text_policy_decision"]["revised_from_record_sha256"], before)
        self.assertEqual(
            qa["gates"]["G0_semantic"]["status_basis"],
            "ART_DIRECTION_ACCEPTED_DECORATIVE_INSCRIPTION",
        )

        provenance = json.loads(provenance_path.read_text())
        self.assertEqual(
            provenance["gates"],
            {
                "G0_semantic": "PASSED",
                "G1_canon_atmosphere": "PENDING_CANON_REVIEW",
                "G2_composition": "PASSED",
                "G3_structure": "PASSED",
                "G4_production": "PASSED",
                "G5_runtime": "PENDING_RUNTIME_QA",
            },
        )
        self.assertEqual(qa["status"], "MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING")
        self.assertEqual(provenance["status"], tool.PROVENANCE_PENDING_STATUS)

    def test_apply_text_decision_is_idempotent(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        decision = self.text_decision_file()
        run(self.apply_argv(decision))
        code, payload = run(self.apply_argv(decision))
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "NO_CHANGE")

    def test_apply_text_decision_leaves_an_uncovered_artwork_alone(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        decision = self.text_decision_file(artwork_id="A09_GROSELLE_TRAVELS")
        code, payload = run(self.apply_argv(decision))
        self.assertEqual(code, 0)
        self.assertEqual(payload["result"], "NO_CHANGE")
        qa = json.loads((Path(self.work) / f"{TASK}.qa.json").read_text())
        self.assertEqual(qa["gates"]["G0_semantic"]["status"], "PENDING_MACOS_FINISHING")
        self.assertNotIn("text_policy_decision", qa)

    def test_text_decision_refuses_a_defect_outside_the_lettering_vocabulary(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        decision = self.text_decision_file(defects=("architecture_errors",))
        with self.assertRaises(SystemExit):
            run(self.apply_argv(decision))

    def test_text_decision_refuses_a_defect_the_inspection_did_not_record(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        decision = self.text_decision_file(defects=("baked_readable_text_on_brass_cover",))
        with self.assertRaises(SystemExit):
            run(self.apply_argv(decision))

    def test_apply_text_decision_refuses_disagreeing_records(self):
        self.catalog_for(DETAIL)
        run(self.record_argv(inspection=self.text_inspection()))
        provenance_path = Path(self.work) / f"{TASK}.provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance["gates"]["G0_semantic"] = "PASSED"
        write_json(provenance_path, provenance)
        with self.assertRaises(SystemExit):
            run(self.apply_argv(self.text_decision_file()))

    def test_text_decision_file_must_be_readable(self):
        broken = self.root / "broken-decision.json"
        broken.write_text("{not json", encoding="utf-8")
        self.catalog_for(DETAIL)
        with self.assertRaises(SystemExit):
            run(self.record_argv(inspection=self.text_inspection(), text_decision=broken))


class ArtifactManifestBindingTests(unittest.TestCase):
    def test_manifest_binding_uses_the_approved_targets(self):
        targets = tool.artifact_targets()
        self.assertEqual(list(targets), [f"A{index:02d}" for index in range(1, 16)])
        self.assertEqual(targets["A01"]["asset_name"], ASSET)
        self.assertEqual(targets["A01"]["source_id"], "A01_ARRODES_MIRROR")
        self.assertEqual(
            sorted(targets["A15"]),
            ["approval_record", "artifact_id", "asset_name", "display_name", "order", "phase",
             "shipping_approved", "source_id", "status", "visual_verb"],
        )

    def test_unbound_source_is_refused(self):
        manifest = copy.deepcopy(tool.load_json(tool.DEFAULT_MANIFEST))
        manifest["artifact_targets"][0]["source_id"] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            write_json(path, manifest)
            with self.assertRaises(SystemExit):
                tool.artifact_targets(path)

    def test_drifted_order_is_refused(self):
        manifest = copy.deepcopy(tool.load_json(tool.DEFAULT_MANIFEST))
        manifest["artifact_targets"][2]["order"] = 4
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            write_json(path, manifest)
            with self.assertRaises(SystemExit):
                tool.artifact_targets(path)


if __name__ == "__main__":
    unittest.main()
