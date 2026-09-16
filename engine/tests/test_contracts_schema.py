"""Test suite for Contract JSON Schemas and Fixtures Validation (T-CON-001)."""

import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMAS_DIR = REPO_ROOT / "contracts" / "schemas"
PROTOCOL_DIR = REPO_ROOT / "contracts" / "protocol"
ENGINEERING_DIR = REPO_ROOT / "contracts" / "engineering"
FIXTURES_DIR = REPO_ROOT / "fixtures" / "golden_001"


def test_all_schemas_are_valid_json_schema():
    """Verify that every schema file in contracts/ is valid JSON Schema Draft 2020-12."""
    schema_files = list(SCHEMAS_DIR.glob("*.schema.json")) + list(
        PROTOCOL_DIR.glob("*.schema.json")
    )
    assert len(schema_files) >= 28, f"Expected at least 28 schemas, found {len(schema_files)}"

    for schema_file in schema_files:
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_data = json.load(f)
        # Check syntax with Draft202012Validator
        Draft202012Validator.check_schema(schema_data)


def test_engineering_contracts_are_separated_from_product_contracts():
    """产品领域契约与研发编排契约必须分属不同 namespace（HACF 2.1 / ADR-004）。"""
    product_schemas = list(SCHEMAS_DIR.glob("*.schema.json"))
    engineering_schemas = list(ENGINEERING_DIR.glob("*.schema.json"))

    assert len(product_schemas) >= 27, f"产品领域 Schema 少于预期: {len(product_schemas)}"
    engineering_names = {p.name for p in engineering_schemas}
    assert {
        "task_capsule.schema.json",
        "work_receipt.schema.json",
        "gate_profile.schema.json",
    } <= engineering_names, f"研发编排 Schema 缺失: {engineering_names}"

    # 研发编排 Schema 不得混入产品领域 namespace
    assert not (SCHEMAS_DIR / "task_capsule.schema.json").exists()
    assert not (SCHEMAS_DIR / "work_receipt.schema.json").exists()

    for schema_file in engineering_schemas:
        with open(schema_file, "r", encoding="utf-8") as f:
            Draft202012Validator.check_schema(json.load(f))


def load_schema(schema_name: str) -> dict:
    path = SCHEMAS_DIR / schema_name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_golden_001_character_matches_schema():
    schema = load_schema("character.schema.json")
    validator = Draft202012Validator(schema)
    with open(FIXTURES_DIR / "character.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    validator.validate(data)


def test_golden_001_world_matches_schema():
    schema = load_schema("world_snapshot.schema.json")
    validator = Draft202012Validator(schema)
    with open(FIXTURES_DIR / "world.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    validator.validate(data)


def test_golden_001_seed_matches_schema():
    schema = load_schema("story_seed.schema.json")
    validator = Draft202012Validator(schema)
    with open(FIXTURES_DIR / "seed.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    validator.validate(data)


def test_golden_001_expected_episode_matches_schema():
    schema = load_schema("episode.schema.json")
    validator = Draft202012Validator(schema)
    with open(FIXTURES_DIR / "expected_episode.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    validator.validate(data)


def test_golden_001_knowledge_matches_schema():
    schema = load_schema("character_knowledge.schema.json")
    validator = Draft202012Validator(schema)
    knowledge_dir = FIXTURES_DIR / "knowledge"
    knowledge_files = list(knowledge_dir.glob("*.json"))
    assert len(knowledge_files) > 0

    for k_file in knowledge_files:
        with open(k_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        validator.validate(data)


def test_golden_001_turns_advice_matches_schema():
    schema = load_schema("player_advice.schema.json")
    validator = Draft202012Validator(schema)
    advice_files = list((FIXTURES_DIR / "turns").glob("*_advice.json"))
    assert len(advice_files) == 5

    for a_file in advice_files:
        with open(a_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        validator.validate(data)
