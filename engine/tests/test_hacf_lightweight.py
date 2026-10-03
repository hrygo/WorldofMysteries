"""日常 PR 不依赖任务凭证，质量门禁与显式治理模式仍可用。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import capsule_audit
import gate_profile
import project_status


@pytest.fixture
def repository(tmp_path):
    gates = tmp_path / ".hacf" / "gates"
    gates.mkdir(parents=True)
    profile = gates / "probe.json"
    profile.write_text(
        json.dumps(
            {
                "gate_profile_id": "PROBE",
                "stages": [{"name": "probe", "command": ["python3", "--version"]}],
            }
        ),
        encoding="utf-8",
    )
    (gates / "registry.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "PROBE": {
                        "file": ".hacf/gates/probe.json",
                        "sha256": gate_profile.sha256_file(profile),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def audit(repository, **kwargs):
    return capsule_audit.audit_pr(
        changed_files=[
            "engine/domain/world.py",
            "engine/infrastructure/world_repository.py",
            "contracts/schemas/world.schema.json",
            "macos-app/WorldOfMysteries/AppState.swift",
        ],
        capsule_paths=[],
        head_sha="a" * 40,
        repo_root=repository,
        **kwargs,
    )


def test_default_audit_accepts_one_feature_across_roles_without_paperwork(repository):
    result = audit(repository)
    assert result["ok"], result
    assert not result["blocking"]
    assert any("CI" in notice for notice in result["notices"])


def test_default_audit_does_not_load_old_capsules_or_receipts(repository, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("轻量流程读取了历史任务凭证")

    monkeypatch.setattr(capsule_audit.policy, "load_capsule", forbidden)
    monkeypatch.setattr(capsule_audit, "load_receipts", forbidden)
    result = capsule_audit.audit_pr(
        changed_files=["engine/domain/world.py"],
        capsule_paths=[repository / ".agents/capsules/OLD.json"],
        head_sha="a" * 40,
        repo_root=repository,
    )
    assert result["ok"], result


@pytest.mark.parametrize(
    "damage",
    ["tampered_profile", "missing_profile", "bad_registry", "empty_registry", "wrong_shape"],
)
def test_lightweight_audit_still_rejects_broken_gate_registry(repository, damage):
    gates = repository / ".hacf" / "gates"
    if damage == "tampered_profile":
        (gates / "probe.json").write_text("{}", encoding="utf-8")
    elif damage == "missing_profile":
        (gates / "probe.json").unlink()
    elif damage == "bad_registry":
        (gates / "registry.json").write_text("{", encoding="utf-8")
    elif damage == "empty_registry":
        (gates / "registry.json").write_text('{"profiles": {}}', encoding="utf-8")
    else:
        (gates / "registry.json").write_text("[]", encoding="utf-8")
    result = audit(repository)
    assert not result["ok"]
    assert result["blocking"]


@pytest.mark.parametrize(
    ("actor", "head_ref"),
    [
        ("developer", "feature/world"),
        ("dependabot[bot]", "feature/world"),
        ("developer", "dependabot/uv/engine/pypdf-6.19.0"),
    ],
)
def test_governed_mode_still_requires_an_explicit_task_capsule(
    repository, monkeypatch, actor, head_ref
):
    monkeypatch.setenv("GITHUB_ACTOR", actor)
    monkeypatch.setenv("GITHUB_HEAD_REF", head_ref)
    result = audit(repository, mode="governed")
    assert not result["ok"]
    assert any("未携带任务胶囊" in problem for problem in result["blocking"])


def test_governed_maintenance_exemption_depends_on_changed_paths(repository, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTOR", "developer")
    monkeypatch.setenv("GITHUB_HEAD_REF", "chore/dependencies")
    result = capsule_audit.audit_pr(
        changed_files=["engine/uv.lock"],
        capsule_paths=[],
        head_sha="a" * 40,
        repo_root=repository,
        mode="governed",
    )
    assert result["ok"], result
    assert any("[MAINTENANCE]" in notice for notice in result["notices"])


def test_unknown_mode_is_rejected(repository):
    with pytest.raises(ValueError, match="mode"):
        audit(repository, mode="unknown")


def test_cli_defaults_to_lightweight_and_never_scans_historical_capsules(repository):
    def git(*args):
        subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            env=capsule_audit.policy._git_env(),
        )

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    git("add", ".")
    git("commit", "-m", "base")
    old = repository / ".agents/capsules/OLD.json"
    old.parent.mkdir(parents=True)
    old.write_text("{", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/capsule_audit.py"),
            "--repo-root", str(repository),
            "--base-ref", "HEAD",
            "--changed-files", "engine/domain/world.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "lightweight" in result.stdout


def test_cli_invalid_base_ref_fails_instead_of_claiming_an_empty_change_set(repository):
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/capsule_audit.py"),
            "--repo-root", str(repository),
            "--base-ref", "missing-ref",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "unable to compute" in result.stdout


def test_dispatch_defaults_to_lightweight_in_text_and_json(capsys):
    state = json.loads((REPO_ROOT / "docs/PROJECT_STATE.json").read_text(encoding="utf-8"))
    project_status.cmd_dispatch(state)
    text = capsys.readouterr().out
    assert "默认轻量流程" in text
    assert "scripts/agent_capsule.py pack" not in text
    assert "scripts/collab_pipeline.py integrate" not in text
    project_status.cmd_dispatch(state, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow_mode"] == "lightweight"
    assert "pack_command" not in payload
    assert "worktree_command" not in payload


def test_dispatch_offers_old_commands_only_when_governed_is_explicit(capsys):
    state = json.loads((REPO_ROOT / "docs/PROJECT_STATE.json").read_text(encoding="utf-8"))
    project_status.cmd_dispatch(state, governed=True)
    assert "scripts/agent_capsule.py pack" in capsys.readouterr().out
