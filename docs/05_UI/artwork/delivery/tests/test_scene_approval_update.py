"""Approved source intake revision 3: integrity, distinct roles and no shipping claims."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("intake_update", HERE / "intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
MANIFEST = json.loads((HERE / "approved_sources.json").read_text())
ARTIFACT_BUNDLE = HERE.parent / "sources/artifacts-r1"
ARTIFACT_SOURCE_IDS = [
    "A01_ARRODES_MIRROR", "A02_ALZUHOD_QUILL", "A03_TRUNSOEST_BRASS_BOOK",
    "A04_MAGIC_WISHING_LAMP", "A05_CREEPING_HUNGER", "A06_SEA_GOD_SCEPTER",
    "A07_PROBABILITY_DIE", "A08_LEYMANO_TRAVELS", "A09_GROSELLE_TRAVELS",
    "A10_AZIK_COPPER_WHISTLE", "A11_CARDS_OF_BLASPHEMY", "A12_STAFF_OF_STARS",
    "A13_BOX_OF_GREAT_OLD_ONES", "A14_DEATH_KNELL", "A15_UNSHADOWED_CRUCIFIX",
]


class SceneApprovalUpdateTests(unittest.TestCase):
    def setUp(self):
        self.m = copy.deepcopy(MANIFEST)

    def test_twenty_four_independent_user_approved_sources(self):
        self.assertEqual(self.m["source_manifest_revision"], 3)
        self.assertEqual(self.m["approved_source_count"], 24)
        self.assertEqual(len(self.m["sources"]), 24)
        self.assertEqual(len({s["sha256"] for s in self.m["sources"]}), 24)
        self.assertEqual([s["source_id"] for s in self.m["sources"][9:]], ARTIFACT_SOURCE_IDS)
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
        for count in (6, 8, 9, 23, 25, True):
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
        for a in self.m["artifact_targets"]:
            a["source_id"] = None
            a["status"] = "CANON_BRIEF_AND_GENERATION_PENDING"
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
        self.m["artifact_targets"][0]["source_id"] = "S02_STREET"
        self.m["supplemental_sources"].remove("S02_STREET")
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_artifact_source_cannot_fill_a_scene_target(self):
        self.m["world_targets"][1]["source_id"] = "A01_ARRODES_MIRROR"
        with self.assertRaises(ValueError): intake.validate_manifest(self.m)

    def test_every_artifact_object_binds_its_own_approved_source(self):
        self.assertEqual(len(self.m["artifact_targets"]), 15)
        self.assertEqual([a["source_id"] for a in self.m["artifact_targets"]], ARTIFACT_SOURCE_IDS)
        for target in self.m["artifact_targets"]:
            self.assertEqual(target["status"], "SOURCE_LOCKED_FINISHING_PENDING")
            self.assertFalse(target["shipping_approved"])
            self.assertTrue((HERE / target["approval_record"]).is_file())

    def test_staged_artifact_bundle_matches_the_manifest(self):
        self.assertTrue(ARTIFACT_BUNDLE.is_dir(), "the artifact source bundle must be committed")
        receipt = json.loads((ARTIFACT_BUNDLE / "INTAKE_COMPLETE.json").read_text(encoding="utf-8"))
        self.assertIs(receipt["shipping_approved"], False)
        self.assertTrue(receipt["partial_bundle"])
        self.assertEqual(receipt["staged_source_ids"], ARTIFACT_SOURCE_IDS)
        by_id = {s["source_id"]: s for s in self.m["sources"]}
        for source_id in ARTIFACT_SOURCE_IDS:
            data = (ARTIFACT_BUNDLE / "sources" / source_id / "source.png").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), by_id[source_id]["sha256"])
            self.assertEqual(len(data), by_id[source_id]["byte_size"])

    def test_approved_direction_is_explicit_not_literal_canon(self):
        text = (HERE / "World_Scene_Approval_Update_2026-09-18.md").read_text()
        self.assertIn("not a literal Canon reconstruction", text)
        self.assertIn("source-level", text)
        self.assertIn("#41", text)


if __name__ == "__main__":
    unittest.main()
