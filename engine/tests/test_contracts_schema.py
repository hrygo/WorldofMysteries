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


def test_the_documented_schema_mirror_is_identical_to_the_contract_source():
    """``docs/03_工程规范/schemas/`` 是 ``contracts/schemas/`` 的人工镜像。

    这份镜像是**部分**的——并非每个契约都有文档副本，所以本断言只做单向
    检查：存在的镜像必须与源逐字相同。反向不成立：「补齐每份镜像」是文档
    工作，不是契约不变量，不该由测试逼迫。

    值得守的是另一半：契约源改动后，镜像会静默停在旧版，而读文档的人据此
    以为字段不存在。差异必须报错，而不是等人来发现。
    """
    mirror_dir = REPO_ROOT / "docs" / "03_工程规范" / "schemas"
    assert mirror_dir.is_dir()
    mirrors = sorted(mirror_dir.glob("*.schema.json"))
    assert mirrors, "文档镜像目录不应为空，否则本断言形同虚设"

    for mirror in mirrors:
        schema_file = SCHEMAS_DIR / mirror.name
        assert schema_file.is_file(), f"文档镜像没有对应契约源：{mirror.name}"
        assert mirror.read_text(encoding="utf-8") == schema_file.read_text(
            encoding="utf-8"
        ), f"契约源与文档镜像已漂移：{mirror.name}"


def test_story_delta_model_and_schema_declare_the_same_story_fields():
    """``StoryDelta`` 的 Python 镜像与 JSON Schema 必须声明同一组字段。

    ``story_delta`` 上 ``additionalProperties`` 是 false，所以 schema 少一个
    字段就是「模型能写、线上被拒」，schema 多一个字段就是「线上能过、
    模型读不到」。两种漂移都不会让任何现有测试变红——夹具不经过这条路径。
    """
    from contracts.models import StoryDelta

    declared = set(
        load_schema("state_delta.schema.json")["properties"]["story_delta"]["properties"]
    )
    modelled = set(StoryDelta.model_fields)

    assert declared == modelled, (
        f"StoryDelta 字段漂移：仅 schema 有 {sorted(declared - modelled)}，"
        f"仅模型有 {sorted(modelled - declared)}"
    )


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


# ---- Story Book additive sections (PRD §20 / §20.4) --------------------


def _story_book(**overrides):
    """The SB-01 core shape, which every later revision must stay compatible with."""
    book = {
        "schema_version": "1.0",
        "episode_id": "episode_session-1",
        "world_id": "world-1",
        "worldline_id": "worldline-1",
        "title": "哈维诊所的停顿",
        "protagonist_ids": ["char_evelyn"],
        "start_world_time": "1349-06-12T21:40:00",
        "end_world_time": "1349-06-12T21:52:00",
        "chapters": [
            {
                "block_id": "b1",
                "scene_id": "consultation_room",
                "segments": [
                    {"type": "narration", "speaker": None, "text": "雨落在诊所的窗外。"}
                ],
            }
        ],
        "ending": {"type": "partial_truth", "main_problem": "Jonathan 去向不明"},
        "unresolved_threads": ["Jonathan 是否还活着"],
    }
    book.update(overrides)
    return book


def _story_book_validator():
    return Draft202012Validator(load_schema("storybook.schema.json"))


def test_story_book_additive_sections_are_optional_and_backward_compatible():
    """SB-01 readers must keep working: the new sections may simply be absent."""
    _story_book_validator().validate(_story_book())


def test_story_book_accepts_the_full_additive_shape():
    _story_book_validator().validate(
        _story_book(
            discovered_secrets=[
                {
                    "proposition": "病人失踪了",
                    "holder": None,
                    "certainty": 1,
                    "status": "confirmed",
                    "acquired_world_time": "1349-06-12T20:30:00",
                }
            ],
            key_characters=[{"label": "莫里斯医生", "change_count": 3}],
            relationship_changes=[
                {
                    "from": "Jonathan",
                    "to": None,
                    "dimensions": {"trust": 0.3, "fear": -0.1},
                }
            ],
            world_impacts=[
                {
                    "event_type": "patient_left_clinic",
                    "world_time": "1349-06-12T21:52:00",
                    "importance": "local",
                    "persistence": "world",
                    "actors": ["莫里斯医生"],
                    "targets": [],
                }
            ],
        )
    )


@pytest.mark.parametrize(
    "section,bad",
    [
        # A canonical proposition_id must have no way into the book: the
        # proposition is required, and an empty label is not a public name.
        ("discovered_secrets", [{"holder": None, "certainty": 1, "status": "confirmed"}]),
        (
            "discovered_secrets",
            [{"proposition": "", "holder": None, "certainty": 1, "status": "confirmed"}],
        ),
        (
            "discovered_secrets",
            [
                {
                    "proposition": "病人失踪了",
                    "holder": None,
                    "certainty": 1.4,
                    "status": "confirmed",
                }
            ],
        ),
        (
            "discovered_secrets",
            [
                {
                    "proposition": "病人失踪了",
                    "holder": None,
                    "certainty": 1,
                    "status": "rumoured",
                }
            ],
        ),
        # The canonical proposition id must have no door into the book at all.
        (
            "discovered_secrets",
            [
                {
                    "proposition": "病人失踪了",
                    "proposition_id": "fact.patient_disappeared",
                    "holder": None,
                    "certainty": 1,
                    "status": "confirmed",
                }
            ],
        ),
        # change_count counts real commits; zero changes is not a key character.
        ("key_characters", [{"label": "莫里斯医生", "change_count": 0}]),
        ("key_characters", [{"label": "", "change_count": 1}]),
        # dimensions is closed: an invented axis is a contract violation.
        (
            "relationship_changes",
            [{"from": None, "to": None, "dimensions": {"luck": 1}}],
        ),
        (
            "relationship_changes",
            [{"from": None, "to": None, "dimensions": {}, "reason": "because"}],
        ),
        # "a relationship changed" with no changed dimension is not a change.
        (
            "relationship_changes",
            [{"from": "Jonathan", "to": "莫里斯医生", "dimensions": {}}],
        ),
        # Neither endpoint has a public name: the reader learns nothing, and a
        # bare pair of anonymous ids is exactly what must never reach the book.
        (
            "relationship_changes",
            [{"from": None, "to": None, "dimensions": {"trust": 0.3}}],
        ),
        # importance/persistence are closed vocabularies from world_event.schema.
        (
            "world_impacts",
            [
                {
                    "event_type": "e",
                    "importance": "cosmic",
                    "persistence": "world",
                    "actors": [],
                    "targets": [],
                }
            ],
        ),
        (
            "world_impacts",
            [
                {
                    "event_type": "e",
                    "importance": "local",
                    "persistence": "forever",
                    "actors": [],
                    "targets": [],
                }
            ],
        ),
    ],
)
def test_story_book_additive_sections_reject_malformed_entries(section, bad):
    with pytest.raises(ValidationError):
        _story_book_validator().validate(_story_book(**{section: bad}))
