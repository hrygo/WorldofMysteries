"""Approved source intake revision 2: integrity, distinct roles and no shipping claims."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("intake_update", HERE / "intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
MANIFEST = json.loads((HERE / "approved_sources.json").read_text())


class SceneApprovalUpdateTests(unittest.TestCase):
    def setUp(self):
        self.m = copy.deepcopy(MANIFEST)

    def test_nine_independent_user_approved_sources(self):
        self.assertEqual(self.m["approved_source_count"], 9)
        self.assertEqual(len(self.m["sources"]), 9)
        self.assertEqual(len({s["sha256"] for s in self.m["sources"]}), 9)
        intake.validate_manifest(self.m)

    def test_original_six_not_replaced(self):
        self.assertEqual([s["source_id"] for s in self.m["sources"][:6]], [
            "S01_WORLD_HERO", "S02_STREET", "S03_CODEX_LIBRARY",
            "S04_RITUAL_TEMPLE", "S05_HARBOR", "S06_ALLEY"])
        self.assertEqual(self.m["sources"][0]["sha256"],
                         "331d165b12f90bced6526e0f2dba36afb80c437100a10d88d194aa1653920ddd")

    def test_new_sources_fill_exact_remaining_slots(self):
        assigned = {w["task_id"]: w["source_id"] for w in self.m["world_targets"]}
        self.assertEqual([assigned[k] for k in ("W2", "W5", "W6")],
                         ["S07_GRAY_FOG", "S08_FATE_WORLDLINE", "S09_ARTIFACT_VAULT"])

    def test_supplemental_stays_supplemental(self):
        self.assertEqual(self.m["supplemental_sources"], ["S02_STREET", "S05_HARBOR", "S06_ALLEY"])

    def test_source_count_drift_fails(self):
        for count in (6, 8, 10, 25, True):
            with self.subTest(count=count), self.assertRaises(ValueError):
                m = copy.deepcopy(self.m); m["approved_source_count"] = count
                intake.validate_manifest(m)

    def test_missing_visual_approval_fails(self):
        self.m["sources"][6]["visual_approval"] = "PENDING"
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_swapped_semantic_bindings_fail(self):
        w = self.m["world_targets"]
        w[1]["source_id"], w[4]["source_id"] = w[4]["source_id"], w[1]["source_id"]
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_partition_correct_but_wrong_role_still_fails(self):
        self.m["world_targets"][1]["source_id"] = "S02_STREET"
        self.m["supplemental_sources"][0] = "S07_GRAY_FOG"
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_new_art_approval_is_not_canon_or_shipping(self):
        for s in self.m["sources"][6:]:
            self.assertFalse(s["canon_approval"])
            self.assertFalse(s["shipping_approved"])
            self.assertTrue((HERE / s["approval_record"]).is_file())

    def test_legacy_six_source_manifest_remains_valid(self):
        self.m.pop("approved_source_count")
        self.m["sources"] = self.m["sources"][:6]
        for w in self.m["world_targets"]:
            if w["task_id"] in ("W2", "W5", "W6"): w["source_id"] = None
        intake.validate_manifest(self.m)

    def test_new_crop_geometry_and_source_hash_binding(self):
        crops = json.loads((HERE / "additional_scene_crops.json").read_text())["records"]
        self.assertEqual([r["task_id"] for r in crops], ["W2", "W5", "W6"])
        sources = {s["source_id"]: s for s in self.m["sources"]}
        for row in crops:
            self.assertEqual(row["source_sha256"], sources[row["source_id"]]["sha256"])
            self.assertEqual(row["source_crop_size"], [1584, 990])
            l, t, r, b = row["source_preview_crop_exclusive"]
            self.assertEqual((r-l)*3, (b-t)*8)
            self.assertTrue(0 <= l < r <= 1584 and 0 <= t < b <= 990)
            self.assertFalse(row["production_master_exists"])
            self.assertFalse(row["g5_runtime_approved"])

    def test_artifact_objects_not_faked_by_scene_sources(self):
        self.assertEqual(len(self.m["artifact_targets"]), 15)
        self.assertTrue(all(a["source_id"] is None for a in self.m["artifact_targets"]))
        self.m["artifact_targets"][0]["source_id"] = "S02_STREET"
        self.m["supplemental_sources"].remove("S02_STREET")
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_approved_direction_is_explicit_not_literal_canon(self):
        text = (HERE / "World_Scene_Approval_Update_2026-09-18.md").read_text()
        self.assertIn("not a literal Canon reconstruction", text)
        self.assertIn("source-level", text)
        self.assertIn("#41", text)


if __name__ == "__main__":
    unittest.main()
