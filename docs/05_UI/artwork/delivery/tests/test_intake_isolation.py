"""Source staging boundary regressions, including macOS-portable path handling."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_intake as fixtures

intake = fixtures.intake


class IntakeIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "input"
        self.destination = self.root / "output"
        self.manifest = copy.deepcopy(fixtures.MANIFEST)
        fixtures.IntakeTests.fixture_bundle(self, self.source)

    def assert_stage_refused(self, destination):
        with self.assertRaises(ValueError):
            intake.stage_sources(self.manifest, self.source, destination)
        self.assertFalse(destination.exists())

    def test_symlink_parent_cannot_hide_catalog(self):
        catalog = self.root / "Assets.xcassets"
        catalog.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(catalog, target_is_directory=True)
        self.assert_stage_refused(alias / "source-intake")
        self.assertEqual(list(catalog.iterdir()), [])

    def test_relative_destination_inside_catalog(self):
        catalog = self.root / "Assets.xcassets"
        catalog.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(catalog)
            self.assert_stage_refused(Path("source-intake"))
        finally:
            os.chdir(previous)

    def test_case_insensitive_catalog_destination(self):
        for suffix in (".XCASSETS", ".ImageSet"):
            with self.subTest(suffix=suffix):
                parent = self.root / ("art" + suffix)
                self.assert_stage_refused(parent / "new-source")
                self.assertFalse(parent.exists())

    def test_source_cannot_create_nested_catalog(self):
        for suffix in (".xcassets", ".IMAGESET"):
            with self.subTest(suffix=suffix):
                self.manifest["sources"][0]["filename"] = "sources/asset" + suffix + "/source.png"
                with self.assertRaises(ValueError):
                    intake.validate_manifest(self.manifest)

    def test_source_cannot_replace_intake_metadata(self):
        for name in ("approved_sources.json", "INTAKE_COMPLETE.json"):
            with self.subTest(name=name):
                self.manifest["sources"][0]["filename"] = name
                fixtures.IntakeTests.fixture_bundle(self, self.source)
                self.assert_stage_refused(self.root / name.replace(".json", "-output"))

    def test_case_insensitive_source_collision(self):
        self.manifest["sources"][1]["filename"] = self.manifest["sources"][0]["filename"].lower()
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_unicode_normalization_source_collision(self):
        self.manifest["sources"][0]["filename"] = "sources/caf\u00e9/source.png"
        self.manifest["sources"][1]["filename"] = "sources/cafe\u0301/source.png"
        with self.assertRaises(ValueError):
            intake.validate_manifest(self.manifest)

    def test_noncanonical_source_aliases_rejected(self):
        for name in ("sources//S01/source.png", "sources/./S01/source.png", "./sources/S01/source.png"):
            with self.subTest(name=name):
                self.manifest["sources"][0]["filename"] = name
                with self.assertRaises(ValueError):
                    intake.validate_manifest(self.manifest)

    def test_source_payload_must_stay_in_png_namespace(self):
        for name in ("outside/source.png", "sources/source.json", "sources"):
            with self.subTest(name=name):
                self.manifest["sources"][0]["filename"] = name
                with self.assertRaises(ValueError):
                    intake.validate_manifest(self.manifest)

    def test_safe_directory_alias_remains_supported(self):
        # macOS also has legitimate directory aliases; do not ban every parent link.
        normal = self.root / "normal"
        normal.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(normal, target_is_directory=True)
        intake.stage_sources(self.manifest, self.source, alias / "staged")
        self.assertEqual(
            len(intake.verify_sources(self.manifest, normal / "staged")),
            len(self.manifest["sources"]),
        )

    def test_metadata_is_explicit_utf8(self):
        original = Path.write_text

        def write(path, data, *args, **kwargs):
            self.assertEqual(kwargs.get("encoding"), "utf-8")
            return original(path, data, *args, **kwargs)

        with mock.patch.object(Path, "write_text", autospec=True, side_effect=write):
            intake.stage_sources(self.manifest, self.source, self.destination)
        restored = json.loads((self.destination / "approved_sources.json").read_text(encoding="utf-8"))
        self.assertEqual(restored, self.manifest)

    def test_stage_cli_verifies_each_copy_once(self):
        manifest_file = self.root / "input-manifest.json"
        manifest_file.write_text(json.dumps(self.manifest), encoding="utf-8")
        argv = ["intake.py", "stage", "--manifest", str(manifest_file),
                "--source-dir", str(self.source), "--stage-dir", str(self.destination)]
        with mock.patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(intake, "verify_sources", wraps=intake.verify_sources) as verify:
            self.assertEqual(intake.main(), 0)
        self.assertEqual(verify.call_count, 2)

    def test_copy_error_does_not_publish_partial_bundle(self):
        with mock.patch.object(intake.shutil, "copyfile", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                intake.stage_sources(self.manifest, self.source, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".art-intake-*")))
        self.assertFalse(list(self.root.glob("*.intake.lock")))

    def test_copied_bytes_are_verified_before_publication(self):
        original = intake.shutil.copyfile

        def corrupt(source, target):
            original(source, target)
            with Path(target).open("ab") as stream:
                stream.write(b"corrupt")

        with mock.patch.object(intake.shutil, "copyfile", side_effect=corrupt):
            self.assert_stage_refused(self.destination)
        self.assertFalse(list(self.root.glob("*.intake.lock")))

    def test_legacy_six_source_manifest_remains_supported(self):
        self.manifest.pop("approved_source_count")
        self.manifest["sources"] = self.manifest["sources"][:6]
        for target in self.manifest["world_targets"]:
            if target["task_id"] in ("W2", "W5", "W6"):
                target["source_id"] = None
        for target in self.manifest["artifact_targets"]:
            target["source_id"] = None
            target["status"] = "CANON_BRIEF_AND_GENERATION_PENDING"
        intake.validate_manifest(self.manifest)
        intake.stage_sources(self.manifest, self.source, self.destination)
        self.assertEqual(len(intake.verify_sources(self.manifest, self.destination)), 6)

    def test_only_stages_a_declared_subset_as_a_partial_bundle(self):
        subset = ["A01_ARRODES_MIRROR", "A02_ALZUHOD_QUILL"]
        intake.stage_sources(self.manifest, self.source, self.destination, subset)
        selected = intake.select_sources(self.manifest, subset)
        self.assertEqual(
            len(intake.verify_sources(self.manifest, self.destination, selected)), len(subset)
        )
        receipt = json.loads((self.destination / "INTAKE_COMPLETE.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["staged_source_ids"], subset)
        self.assertEqual(receipt["manifest_source_count"], 24)
        self.assertTrue(receipt["partial_bundle"])
        staged = sorted(path.parent.name for path in (self.destination / "sources").glob("*/source.png"))
        self.assertEqual(staged, subset)

    def test_only_refuses_unknown_or_duplicate_source_ids(self):
        for only in (["A99_MISSING"], ["A01_ARRODES_MIRROR", "A01_ARRODES_MIRROR"]):
            with self.subTest(only=only), self.assertRaises(ValueError):
                intake.stage_sources(self.manifest, self.source, self.root / "never", only)
        self.assertFalse((self.root / "never").exists())

    def test_intake_does_not_change_approval_or_originals(self):
        before = copy.deepcopy(self.manifest)
        intake.stage_sources(self.manifest, self.source, self.destination)
        self.assertEqual(self.manifest, before)
        self.assertEqual(
            len(intake.verify_sources(self.manifest, self.source)),
            len(self.manifest["sources"]),
        )
        receipt = json.loads((self.destination / "INTAKE_COMPLETE.json").read_text(encoding="utf-8"))
        self.assertIs(receipt["shipping_approved"], False)


if __name__ == "__main__":
    unittest.main()
