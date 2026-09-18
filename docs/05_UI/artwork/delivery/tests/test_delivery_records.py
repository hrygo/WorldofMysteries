"""Check delivery metadata consistency, not artistic correctness or shipping readiness."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "approved_sources.json").read_text())
SOURCES = {row["source_id"]: row for row in MANIFEST["sources"]}


class DeliveryRecordsTests(unittest.TestCase):
    def test_crop_source_binding(self):
        rows = json.loads((ROOT / "crop_review.json").read_text())["records"]
        self.assertEqual([r["task_id"] for r in rows], ["W1", "W3", "W4"])
        for row in rows:
            source = SOURCES[row["source_id"]]
            self.assertEqual(row["source_sha256"], source["sha256"])
            self.assertRegex(row["source_crop_sha256"], r"^[0-9a-f]{64}$")
            left, top, right, bottom = row["source_crop_exclusive"]
            self.assertEqual([left, top, right, bottom], [1, 1, source["width"] - 1, source["height"] - 1])
            self.assertEqual(row["source_crop_size"], [right-left, bottom-top])
            self.assertEqual((right-left)*10, (bottom-top)*16)

    def test_wide_crop_geometry(self):
        for row in json.loads((ROOT / "crop_review.json").read_text())["records"]:
            for field, size in (("source_preview_crop_exclusive", row["source_crop_size"]),
                                ("master_crop_exclusive", [4096, 2560])):
                left, top, right, bottom = row[field]
                self.assertTrue(0 <= left < right <= size[0])
                self.assertTrue(0 <= top < bottom <= size[1])
                self.assertEqual((right-left)*3, (bottom-top)*8)
                anchor = row["proposed_wide_anchor"]
                self.assertEqual(top, {"top":0, "center":(size[1]-(bottom-top))//2,
                                       "bottom":size[1]-(bottom-top)}[anchor])

    def test_crop_is_not_shipping(self):
        for row in json.loads((ROOT / "crop_review.json").read_text())["records"]:
            self.assertEqual(row["review_status"], "CROP_PROPOSAL_NOT_RUNTIME_APPROVAL")
            self.assertFalse(row["production_master_exists"])
            self.assertFalse(row["g5_runtime_approved"])

    def test_attempts_cannot_become_approved_sources(self):
        attempts = json.loads((ROOT / "generation_attempts.json").read_text())
        self.assertFalse(attempts["shipping_approved"])
        accepted = {row["sha256"] for row in SOURCES.values()}
        for row in attempts["attempts"]:
            self.assertNotIn(row["sha256"], accepted)
            self.assertEqual(row["result"], "REJECTED_TARGET_MISMATCH")
            self.assertIsNone(row["assigned_runtime_asset"])
            self.assertIsNone(row["user_approval"])
            self.assertFalse(row["binary_committed"])

    def test_primary_evidence_has_explicit_limits(self):
        evidence = json.loads((ROOT / "canon_evidence.json").read_text())
        self.assertFalse(evidence["full_p0_canon_review_complete"])
        # Revision 3 approves 15 Artifact source images. That count must track the manifest
        # bindings, and the record must still say out loud that a visual approval is not a Canon
        # verification of the object's form.
        bound = [row for row in MANIFEST["artifact_targets"] if row["source_id"]]
        self.assertEqual(evidence["artifact_source_images_approved"], len(bound))
        self.assertIn("not Canon verification", evidence["artifact_source_images_approved_note"])
        verified = {row["artifact_id"] for row in evidence["claims"]}
        limits = {row["artifact_id"] for row in evidence["coverage_limits"]}
        p0_ids = {row["artifact_id"] for row in MANIFEST["artifact_targets"] if row["phase"] == "P0"}
        self.assertTrue(verified < p0_ids, "not every P0 object may claim verified primary form")
        self.assertTrue(verified.isdisjoint(limits))
        self.assertTrue(verified | limits <= p0_ids)
        for row in evidence["claims"]:
            self.assertIn(row["artifact_id"], p0_ids)
            self.assertIn("lord-of-mysteries_11022733006234505", row["url"])
            self.assertTrue(row["not_verified"])

    def test_scene_prompts_are_individual(self):
        expected = {"W2_GRAY_FOG.txt", "W5_FATE_WORLDLINE.txt", "W6_ARTIFACT_VAULT.txt"}
        self.assertEqual({p.name for p in (ROOT / "scene_prompts").glob("*.txt")}, expected)
        self.assertEqual(len({hashlib.sha256((ROOT/"scene_prompts"/n).read_bytes()).hexdigest() for n in expected}), 3)
        for name in expected:
            text = (ROOT/"scene_prompts"/name).read_text()
            self.assertIn("16:10", text)
            self.assertIn("8:3", text)

    def test_no_local_absolute_paths_in_delivery_markdown(self):
        for path in ROOT.glob("*.md"):
            text = path.read_text()
            self.assertIsNone(re.search(r"file:///|/mnt/data/|/Users/|/home/|[A-Z]:\\\\", text))


if __name__ == "__main__":
    unittest.main()
