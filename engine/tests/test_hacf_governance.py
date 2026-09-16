"""HACF 2.1 协同治理门禁测试 (T-GOV-001)。

覆盖三项协同层「主权」断言：
1. 受保护门禁档案与 registry 摘要一致（门禁不可被任务自行改写）；
2. 胶囊契约不携带验收命令、不承载凭证（契约与凭证分离）；
3. 范围裁决对高风险面强制扩权（SCOPE_ESCALATION_REQUIRED）。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
ENGINEERING_DIR = REPO_ROOT / "contracts" / "engineering"

sys.path.insert(0, str(SCRIPTS_DIR))

import gate_profile  # noqa: E402
import hacf_policy  # noqa: E402


def test_gate_registry_digests_match_protected_profiles():
    """门禁档案摘要链：registry 记录值 == 实际文件摘要。"""
    registry = gate_profile.load_registry()
    assert registry["profiles"], "registry 不应为空"
    for profile_id in registry["profiles"]:
        profile, _, digest = gate_profile.resolve_profile(profile_id)
        assert digest == registry["profiles"][profile_id]["sha256"]
        assert profile["stages"], f"{profile_id} 缺少 stage 定义"


def test_gate_profile_tampering_is_rejected(tmp_path):
    """覆盖受保护档案而不更新 registry 必须被拒绝执行。"""
    tampered = tmp_path / "tampered.json"
    source = REPO_ROOT / ".hacf" / "gates" / "full_p0.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["stages"] = [
        {"stage": 1, "name": "noop", "cwd": ".", "command": ["true"]}
    ]
    tampered.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    registry_copy = tmp_path / "registry.json"
    registry = gate_profile.load_registry()
    registry["profiles"]["FULL_P0"]["file"] = str(tampered)
    registry_copy.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    with pytest.raises(gate_profile.GateProfileError, match="digest mismatch"):
        gate_profile.resolve_profile("FULL_P0", registry_path=registry_copy)


def test_capsule_carries_no_executable_gate_commands():
    """契约不得携带 verification_commands，也不得承载 attestation（凭证分离）。"""
    schema = json.loads(
        (ENGINEERING_DIR / "task_capsule.schema.json").read_text(encoding="utf-8")
    )
    properties = schema["properties"]
    assert "verification_commands" not in properties
    assert "attestation" not in properties
    assert schema["additionalProperties"] is False
    assert "gates" in schema["required"]

    receipt_schema = json.loads(
        (ENGINEERING_DIR / "work_receipt.schema.json").read_text(encoding="utf-8")
    )
    assert "capsule_digest" in receipt_schema["required"]
    assert "merge_authorizing" in receipt_schema["required"]
    Draft202012Validator.check_schema(receipt_schema)


def test_privileged_surface_requires_explicit_grant():
    """非 ARB 角色触碰 contracts/ 等高风险面时必须走扩权，不能静默通过。"""
    capsule = {
        "assigned_role": "AGT-DOM",
        "scope": {
            "read": ["contracts/"],
            "write": ["engine/domain/"],
            "forbidden": ["macos-app/**"],
            "privileged_grants": [],
        },
    }
    audit = hacf_policy.audit_scope(capsule, ["contracts/schemas/world_event.schema.json"])
    assert audit["escalations"], "高风险面未被判定为需要扩权"
    assert not audit["violations"]

    granted = json.loads(json.dumps(capsule))
    granted["scope"]["privileged_grants"] = ["contracts/schemas/world_event.schema.json"]
    audit_granted = hacf_policy.audit_scope(
        granted, ["contracts/schemas/world_event.schema.json"]
    )
    assert not audit_granted["escalations"]
    assert audit_granted["privileged_uses"] == ["contracts/schemas/world_event.schema.json"]


def test_forbidden_scope_is_enforced():
    """forbidden 必须真正拦截（HACF 2.0 中该字段是死字段）。"""
    capsule = {
        "assigned_role": "AGT-DOM",
        "scope": {"read": [], "write": ["engine/domain/"], "forbidden": ["macos-app/**"]},
    }
    audit = hacf_policy.audit_scope(capsule, ["macos-app/WorldOfMysteries/App.swift"])
    assert audit["violations"][0]["reason"].startswith("命中 forbidden")


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("contracts/schemas/world_event.schema.json", "contracts/", True),
        ("engine/infrastructure/migrations/001_init.sql", "engine/**/migrations/", True),
        ("engine/domain/world_engine.py", "engine/**/migrations/", False),
        ("macos-app/WorldOfMysteries/App.swift", "macos-app/**", True),
        ("engine/uv.lock", "engine/uv.lock", True),
    ],
)
def test_path_pattern_semantics(path, pattern, expected):
    """边界模式语义必须可复算：目录前缀、递归通配与精确路径。"""
    assert hacf_policy.matches_any(path, [pattern]) is expected


def test_gate_runner_has_no_embedded_commands():
    """门禁启动器必须是薄封装：命令只存在于受保护档案中。"""
    runner = (REPO_ROOT / "scripts" / "gate_runner.sh").read_text(encoding="utf-8")
    assert "gate_profile.py" in runner
    for embedded in ("check_architecture_fitness.py", "uv run", "swift test"):
        assert embedded not in runner, f"门禁启动器内嵌了命令: {embedded}"


def test_pack_produces_decoupled_capsule(tmp_path):
    """pack 产出的胶囊只引用 gate profile，且切片按焦点而非目录顺序。"""
    out = tmp_path / "capsule.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "agent_capsule.py"),
            "pack",
            "--role",
            "AGT-MAC",
            "--task-id",
            "T-GOV-TEST",
            "--title",
            "IPC client smoke",
            "--output",
            str(out),
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    capsule = json.loads(out.read_text(encoding="utf-8"))
    assert capsule["gates"]["profile"] == "MACOS_APP_P0"
    assert capsule["gates"]["profile_digest"].startswith("sha256:")
    assert "verification_commands" not in capsule
    assert "attestation" not in capsule
    assert capsule["base"]["context_snapshot"].startswith("sha256:")
    Draft202012Validator(
        json.loads((ENGINEERING_DIR / "task_capsule.schema.json").read_text(encoding="utf-8"))
    ).validate(capsule)
