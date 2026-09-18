"""Transport/mapping tests only; never substitutes for image or macOS runtime QA."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("intake", HERE / "intake.py")
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
MANIFEST = json.loads((HERE / "approved_sources.json").read_text())


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def png():
    return (intake.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = copy.deepcopy(MANIFEST)

    def test_valid_manifest(self):
        intake.validate_manifest(self.manifest)

    def test_real_registry(self):
        root = HERE.parents[3]
        registry = root / self.manifest["registry_path"]
        intake.validate_manifest(self.manifest, registry.read_text())

    def test_world_gaps_remain_explicit(self):
        self.assertEqual([w["task_id"] for w in self.manifest["world_targets"] if w["source_id"] is None], ["W2", "W5", "W6"])

    def test_approval_is_not_shipping(self):
        self.manifest["sources"][0]["shipping_approved"] = True
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_target_shipping_cannot_be_inferred(self):
        self.manifest["world_targets"][0]["shipping_approved"] = True
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_duplicate_source_rejected(self):
        self.manifest["sources"][1]["source_id"] = self.manifest["sources"][0]["source_id"]
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_duplicate_bytes_rejected(self):
        self.manifest["sources"][1]["sha256"] = self.manifest["sources"][0]["sha256"]
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_source_cannot_fill_multiple_identities(self):
        self.manifest["world_targets"][1]["source_id"] = "S01_WORLD_HERO"
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_supplemental_cannot_fill_gray_fog(self):
        self.manifest["world_targets"][1]["source_id"] = "S02_STREET"
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_relabeling_supplemental_still_rejected(self):
        self.manifest["world_targets"][1]["source_id"] = "S02_STREET"
        self.manifest["supplemental_sources"].remove("S02_STREET")
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_p0_p1_order(self):
        self.manifest["artifact_targets"][0]["phase"] = "P1"
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_w1_top_anchor(self):
        self.manifest["world_targets"][0]["wide_anchor"] = "center"
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_registry_drift(self):
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest, 'case wrong = "wom.art.world.wrong"')

    def test_unsafe_paths(self):
        for name in ("../escape.png", "/escape.png", "C:\\escape.png", "a/../../escape.png"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                intake.safe_path(Path.cwd(), name)

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "real").mkdir()
            (root / "link").symlink_to(root / "real", target_is_directory=True)
            with self.assertRaises(ValueError):
                intake.safe_path(root, "link/source.png")

    def test_png_header_and_crcs(self):
        self.assertEqual(intake.png_container_size(png()), (1, 1))

    def test_corrupted_png(self):
        data = bytearray(png()); data[20] ^= 1
        with self.assertRaises(ValueError):
            intake.png_container_size(bytes(data))

    def test_truncated_and_trailing_png(self):
        for data in (png()[:-1], png() + b"garbage", b"not a png"):
            with self.subTest(data=data[-10:]), self.assertRaises(ValueError):
                intake.png_container_size(data)

    def test_missing_sources(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            intake.verify_sources(self.manifest, Path(tmp))

    def test_wrong_source_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / self.manifest["sources"][0]["filename"]
            first.parent.mkdir(parents=True); first.write_bytes(png())
            with self.assertRaises(ValueError):
                intake.verify_sources(self.manifest, root)

    def fixture_bundle(self, root):
        for index, source in enumerate(self.manifest["sources"]):
            data = (intake.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(bytes([0, index, 0, 0]))) + chunk(b"IEND", b""))
            source.update(width=1, height=1, byte_size=len(data), sha256=hashlib.sha256(data).hexdigest())
            path = root / source["filename"]
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)

    def test_stage_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; dest = root / "staged"
            self.fixture_bundle(source)
            intake.stage_sources(self.manifest, source, dest)
            self.assertTrue((dest / "INTAKE_COMPLETE.json").exists())
            self.assertEqual(len(intake.verify_sources(self.manifest, dest)), 6)
            with self.assertRaises(ValueError):
                intake.stage_sources(self.manifest, source, dest)
            self.assertTrue((dest / "INTAKE_COMPLETE.json").exists())

    def test_asset_catalog_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"
            self.fixture_bundle(source)
            with self.assertRaises(ValueError):
                intake.stage_sources(self.manifest, source, root / "Assets.xcassets" / "art")
            self.assertFalse((root / "Assets.xcassets").exists())

    def test_wrong_hash_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture_bundle(root)
            self.manifest["sources"][0]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                intake.verify_sources(self.manifest, root)


if __name__ == "__main__":
    unittest.main()
