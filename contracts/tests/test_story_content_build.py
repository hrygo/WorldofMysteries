"""Trusted Golden 001 content artifact build contract.

The build script is the only producer of the packaged ``scenario_bundles``
artifact. These tests pin its provenance, its fail-closed behaviour and the
read-only shape the Local Engine consumes.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "engine"))

import build_story_content as builder  # noqa: E402
from application.story_initialization import (  # noqa: E402
    GOLDEN_CONTENT_VERSION,
    GOLDEN_POLICY_VERSION,
    GOLDEN_SCENARIO_ID,
    TrustedScenarioBundle,
)

ALLOWED_SOURCES = {
    ROOT / "fixtures/golden_001/seed.json",
    ROOT / "fixtures/golden_001/world.json",
    ROOT / "fixtures/golden_001/character.json",
    ROOT / "fixtures/golden_001/turns/01_advice.json",
    ROOT / "docs/07_工程启动/golden_001_runtime/mock/01_action_intent.json",
}
KNOWLEDGE = {
    ROOT / "fixtures/golden_001/knowledge" / name
    for name in (
        "01_character_knowledge.json",
        "02_character_knowledge.json",
        "03_character_knowledge.json",
        "04_character_knowledge.json",
    )
}


def test_build_payload_is_pinned_and_deterministic():
    first = builder.build_payload()
    second = builder.build_payload()

    assert first == second, "内容包构建必须可复算"
    assert first["scenario_id"] == GOLDEN_SCENARIO_ID
    assert first["content_version"] == GOLDEN_CONTENT_VERSION
    assert first["policy_version"] == GOLDEN_POLICY_VERSION
    assert len(first["content_digest"]) == 64
    assert first["content_digest"] == builder.canonical_digest(first)
    bundle = TrustedScenarioBundle.model_validate(first)
    assert bundle.content_digest == first["content_digest"]
    assert bundle.advice_template.raw_input == "先别问医生病人的事，我想看看他的反应。"
    assert bundle.advice_template.input_mode.value == "text"


def test_build_reads_only_allowlisted_sources(monkeypatch):
    read: list[Path] = []
    original = builder.read_json

    def recording(path: Path) -> dict:
        read.append(Path(path))
        return original(path)

    monkeypatch.setattr(builder, "read_json", recording)
    builder.build_payload()

    assert read, "构建必须真的读取受信来源"
    for path in read:
        if path.parent.name == "schemas":
            continue
        assert path in ALLOWED_SOURCES | KNOWLEDGE, f"越界来源: {path}"
    assert not any("expected" in path.name for path in read), "期望结果不得进入内容包"


def test_poisoned_fixture_fails_closed(tmp_path, monkeypatch):
    poisoned = tmp_path / "golden_001"
    source = ROOT / "fixtures/golden_001"
    for path in source.rglob("*.json"):
        target = poisoned / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    supplied = json.loads((poisoned / "character.json").read_text(encoding="utf-8"))
    supplied["id"] = "char_forged_protagonist"
    (poisoned / "character.json").write_text(
        json.dumps(supplied, ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setattr(builder, "FIXTURE_DIR", poisoned)
    with pytest.raises(builder.StoryContentBuildError) as failure:
        builder.build_payload()
    assert failure.value.code in {
        "protagonist_mismatch",
        "invalid_trusted_bundle",
        "initializer_rejected_bundle",
    }


def test_artifact_is_single_row_and_expected_free(tmp_path):
    payload = builder.build_payload()
    artifact = builder.write_artifact(tmp_path / "canon.db", payload)

    connection = sqlite3.connect(f"file:{artifact}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT scenario_id, content_version, content_digest, payload_json "
            "FROM scenario_bundles"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0][:3] == (
        GOLDEN_SCENARIO_ID,
        GOLDEN_CONTENT_VERSION,
        payload["content_digest"],
    )
    assert json.loads(rows[0][3]) == payload
    assert "expected" not in rows[0][3].lower(), "制品不得携带期望结果"


def test_packaged_artifact_path_is_module_relative():
    assert builder.ENGINE / builder.CONTENT_ARTIFACT_RELATIVE == (
        ROOT / "engine/infrastructure/story_content/canon.db"
    )
    assert builder.CONTENT_ARTIFACT_RELATIVE.as_posix() == "infrastructure/story_content/canon.db"
