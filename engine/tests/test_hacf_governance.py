"""HACF 2.1 协同治理门禁测试 (T-GOV-001)。

覆盖三项协同层「主权」断言：
1. 受保护门禁档案与 registry 摘要一致（门禁不可被任务自行改写）；
2. 胶囊契约不携带验收命令、不承载凭证（契约与凭证分离）；
3. 范围裁决对高风险面强制扩权（SCOPE_ESCALATION_REQUIRED）。

另含 T-GOV-002（PR 证据卡片检测链路）：
4. 变更面判定失败必须显式呈现，禁止静默降级为「本 PR 未附带胶囊」；
5. 完整历史下凭单解析与胶囊解耦（无胶囊 PR 也要复述其凭单）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
ENGINEERING_DIR = REPO_ROOT / "contracts" / "engineering"

sys.path.insert(0, str(SCRIPTS_DIR))

import generate_pr_report as reporter  # noqa: E402
import agent_capsule  # noqa: E402
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


# ==============================================================================
# T-GOV-002：PR 证据卡片检测链路
#
# 背景：`pr-gate-reporter.yml` 曾用默认浅克隆（fetch-depth: 1），
# `git diff origin/<base>...HEAD` 因缺少共同祖先返回 exit 128 与空 stdout；
# 报告脚本未检查退出码，把「判定失败」静默降级为「本 PR 未附带胶囊」，
# 证据卡片因此永久显示「未检测到内容」。
# ==============================================================================

# git 钩子（pre-commit 走 gate_runner.sh）会向测试进程注入 GIT_DIR / GIT_INDEX_FILE /
# GIT_WORK_TREE。夹具里的临时仓库必须忽略这些变量，否则夹具内的 `git add .` 会
# 改写真实仓库的索引（曾实际损坏隔离工作区索引）。
_GIT_ENV_POLLUTANTS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
)


def _clean_git_env() -> dict:
    env = dict(os.environ)
    for key in _GIT_ENV_POLLUTANTS:
        env.pop(key, None)
    return env


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_clean_git_env(),
    )


def _init_repo_with_branches(tmp_path: Path, shallow_clone: bool) -> Path:
    """构造带 `origin/main` 与一个引入胶囊/凭单的功能分支的工作区。

    `shallow_clone=True` 时返回 depth=1 的克隆（复刻 actions/checkout 默认行为）。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin"
    origin.mkdir(parents=True, exist_ok=True)
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.com")
    _git(origin, "config", "user.name", "tester")
    (origin / "README.md").write_text("base\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "base")

    _git(origin, "checkout", "-q", "-b", "feature")
    capsule_dir = origin / ".agents" / "capsules"
    capsule_dir.mkdir(parents=True)
    (capsule_dir / "TASK-1.json").write_text('{"task_id": "TASK-1"}\n', encoding="utf-8")
    receipt_dir = origin / ".agents" / "receipts" / "TASK-1"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "abc123.json").write_text(
        '{"task_id": "TASK-1", "receipt_type": "work", "verdict": "passed",'
        ' "head_commit": "abcdef1234567890", "coverage_gaps": []}\n',
        encoding="utf-8",
    )
    (origin / "app.txt").write_text("feature\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "feature work")

    # 让 `main` 与分支尖端都前进若干提交：这样 merge base 落在浅克隆窗口之外，
    # 与线上「PR 多提交 + base 已前进」的真实形态一致。
    (origin / "app.txt").write_text("feature work 2\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "feature work 2")
    _git(origin, "checkout", "-q", "main")
    (origin / "README.md").write_text("base\nmain march\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "main march")

    clone = (tmp_path / "work") if shallow_clone else (tmp_path / "full")
    # ⚠️ 必须用 file:// URL：本地路径克隆会让 git 忽略 `--depth`，浅克隆特征随之消失。
    source = f"file://{origin}" if shallow_clone else str(origin)
    clone_args = ["clone", "-q", "--no-tags"]
    if shallow_clone:
        # 复刻 actions/checkout 的默认行为：depth=1 且 base 分支同样被浅取，
        # 于是 origin/main 与 HEAD 之间不存在共同祖先。
        clone_args += ["--depth", "1", "--no-single-branch"]
    clone_args += [source, str(clone)]
    _git(tmp_path, *clone_args)
    _git(clone, "checkout", "-q", "feature")
    return clone


def test_shallow_clone_detection_fails_loudly(tmp_path: Path, monkeypatch):
    """浅克隆实测：`git diff origin/main...HEAD` 必然失败，且失败必须出现在卡片上。"""
    shallow = _init_repo_with_branches(tmp_path, shallow_clone=True)
    monkeypatch.setattr(reporter, "REPO_ROOT", shallow)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    probe = _git(shallow, "diff", "--name-only", "origin/main...HEAD")
    assert probe.returncode != 0, "浅克隆应无法解析三点 diff，否则本测试失去意义"

    changed, failures = reporter.detect_changed_files()
    assert changed == []
    assert failures, "判定失败时必须给出诊断说明，禁止静默返回空变更面"
    assert any("merge base" in item or "merge-base" in item for item in failures)
    assert any("fetch-depth: 0" in item for item in failures)

    report = reporter.generate_report()
    assert "变更面判定失败" in report
    assert "检测诊断 (Detection Diagnostics)" in report
    assert "未附带业务胶囊" not in report, "判定失败不得伪报为「本 PR 未引入胶囊变更」"


def test_injected_git_failure_is_reported(monkeypatch):
    """注入 exit 128：诊断必须包含退出码与 stderr，并给出修复指引。"""
    stderr = "fatal: origin/main...HEAD: no merge base\n"

    def fake_git(args: list) -> subprocess.CompletedProcess:
        if args[:1] == ["diff"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", stderr)
        if args[:1] == ["merge-base"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: Not a valid object name")
        raise AssertionError(f"未预期的 git 调用：{args}")

    monkeypatch.setattr(reporter, "_run_git", fake_git)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed, failures = reporter.detect_changed_files()
    assert changed == []
    assert failures and failures[0].startswith("三点 diff") and "128" in failures[0]

    report = reporter.generate_report()
    assert "变更面判定失败" in report
    assert "fetch-depth: 0" in report


def test_full_history_detection_resolves_capsule_and_receipt(tmp_path: Path, monkeypatch):
    """完整历史：变更面、胶囊与凭单必须被正确解析。"""
    full = _init_repo_with_branches(tmp_path, shallow_clone=False)
    monkeypatch.setattr(reporter, "REPO_ROOT", full)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed, failures = reporter.detect_changed_files()
    assert failures == []
    assert ".agents/capsules/TASK-1.json" in changed
    assert ".agents/receipts/TASK-1/abc123.json" in changed
    assert [c["task_id"] for c in reporter.load_capsules(changed)] == ["TASK-1"]
    assert [r["receipt_type"] for r in reporter.load_changed_receipts(changed)] == ["work"]


def test_receipts_are_reported_without_capsule(tmp_path: Path, monkeypatch):
    """无胶囊 PR：携带的凭单仍必须出现在卡片上，不得判为「无证据」。"""
    full = _init_repo_with_branches(tmp_path, shallow_clone=False)
    monkeypatch.setattr(reporter, "REPO_ROOT", full)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed = ["macos-app/WorldOfMysteries/AppState.swift", ".agents/receipts/TASK-1/abc123.json"]
    assert reporter.load_capsules(changed) == []
    receipts = reporter.load_changed_receipts(changed)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == "passed"


# ==============================================================================
# T-GOV-003：门禁档案演进的受理规则（本地 verify 与 CI 审计共用一份实现）
#
# 背景：ADR-004 D2 要求三环摘要完全相等
# （`capsule.profile_digest` == 目标分支 registry == profile 文件字节）。
# 但「本变更集自身就在改写引用的 profile」时三环无法同时成立：胶囊必须按改造前打包
# （否则 CI 判其篡改），而文件字节已是新值。`capsule_audit` 早已为受权治理通道留出口，
# 本地 `verify` 却没有，于是 AGT-ARB 无法为合法门禁升级签出绿色凭单 ——
# 门禁档案在受保护分支上被永久冻结（HACF-2.5 实际撞上该自锁）。
# 本组测试锁定共用规则：只有「受权通道 + registry 同变更集同步」才受理演进。
# ==============================================================================

BASE_PROFILE_DIGEST = "sha256:" + "a" * 64
EVOLVED_PROFILE_DIGEST = "sha256:" + "b" * 64


def _gate_evolution_capsule(role: str = "AGT-ARB") -> dict:
    return {
        "capsule_id": "CAP-T-GOV-EVOLUTION",
        "capsule_revision": 1,
        "task_id": "T-GOV-EVOLUTION",
        "title": "门禁档案演进受理",
        "assigned_role": role,
        "risk_class": "privileged",
        "scope": {
            "read": ["."],
            "write": [".hacf/", "app.txt"],
            "forbidden": [],
            "privileged_grants": [],
        },
        "gates": {
            "profile": "FULL_P0",
            "profile_digest": BASE_PROFILE_DIGEST,
            "profile_file": ".hacf/gates/full_p0.json",
            "risk_class": "high",
        },
    }


def _write_evolution_registry(path: Path, digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": {
                    "FULL_P0": {
                        "file": ".hacf/gates/full_p0.json",
                        "sha256": digest.removeprefix("sha256:"),
                        "risk_class": "high",
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_gate_evolution_accepted_for_privileged_lane_with_synced_registry(tmp_path):
    """AGT-ARB + registry 已同步 → 演进受理（这是门禁档案唯一合法的改写通道）。"""
    registry = tmp_path / "registry.json"
    _write_evolution_registry(registry, EVOLVED_PROFILE_DIGEST)

    info = hacf_policy.gate_profile_evolution(
        _gate_evolution_capsule("AGT-ARB"),
        actual_digest=EVOLVED_PROFILE_DIGEST,
        registry_path=registry,
    )

    assert info["accepted"] is True
    assert info["registry_synced"] is True
    assert info["profile_id"] == "FULL_P0"


def test_gate_evolution_rejected_for_non_privileged_role(tmp_path):
    """非受权通道角色：即使 registry 已同步，也一律判篡改。"""
    registry = tmp_path / "registry.json"
    _write_evolution_registry(registry, EVOLVED_PROFILE_DIGEST)

    info = hacf_policy.gate_profile_evolution(
        _gate_evolution_capsule("AGT-MAC"),
        actual_digest=EVOLVED_PROFILE_DIGEST,
        registry_path=registry,
    )

    assert info["accepted"] is False
    assert "AGT-MAC" in info["reason"]


def test_gate_evolution_rejected_when_registry_not_synced(tmp_path):
    """registry 仍记录旧摘要 → 未同步，判篡改（自证式改写必须被拒）。"""
    registry = tmp_path / "registry.json"
    _write_evolution_registry(registry, BASE_PROFILE_DIGEST)

    info = hacf_policy.gate_profile_evolution(
        _gate_evolution_capsule("AGT-ARB"),
        actual_digest=EVOLVED_PROFILE_DIGEST,
        registry_path=registry,
    )

    assert info["accepted"] is False
    assert "未随本变更集同步" in info["reason"]


def test_gate_evolution_rejected_when_registry_missing(tmp_path):
    """缺 registry → 无从证明同步，判篡改。"""
    info = hacf_policy.gate_profile_evolution(
        _gate_evolution_capsule("AGT-ARB"),
        actual_digest=EVOLVED_PROFILE_DIGEST,
        registry_path=tmp_path / "absent.json",
    )

    assert info["accepted"] is False
    assert "未找到 gate registry" in info["reason"]


def _gate_evolution_workspace(tmp_path: Path, *, registry_digest: str) -> tuple[Path, Path, str]:
    """构造一个「自身改写了所引用 profile」的最小工作区，返回 (工作区, 胶囊路径, HEAD)。"""
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    _git(workspace, "init", "-q", "-b", "main")
    _git(workspace, "config", "user.email", "t@example.com")
    _git(workspace, "config", "user.name", "tester")

    gates = workspace / ".hacf" / "gates"
    gates.mkdir(parents=True)
    (gates / "full_p0.json").write_text(
        json.dumps(
            {
                "gate_profile_id": "FULL_P0",
                "description": "fixture",
                "risk_class": "high",
                "stages": [{"stage": 1, "name": "noop", "cwd": ".", "command": ["true"]}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_evolution_registry(gates / "registry.json", registry_digest)
    (workspace / "app.txt").write_text("gate evolution\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-q", "-m", "base with gates")
    base_sha = _git(workspace, "rev-parse", "HEAD").stdout.strip()

    # 第二个提交提供非空变更集：凭单的 diff_digest 契约要求 sha256:<64hex>，
    # 空变更集会写出空摘要而无法通过 schema 校验。
    (workspace / "app.txt").write_text("gate evolution v2\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-q", "-m", "evolve gates")
    head = _git(workspace, "rev-parse", "HEAD").stdout.strip()

    capsule = _gate_evolution_capsule("AGT-ARB")
    capsule["base"] = {
        "target_ref": "main",
        "base_sha": base_sha,
        "target_sha": head,
        "context_snapshot": "sha256:" + "c" * 64,
    }
    capsule_path = workspace / ".agents" / "capsules" / "T-GOV-EVOLUTION.json"
    capsule_path.parent.mkdir(parents=True)
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")
    return workspace, capsule_path, head


def _fake_gate_run(actual_digest: str):
    def _run(profile_id, cwd=None, log_dir=None, **kwargs):  # noqa: ANN001, ANN003
        return {
            "gate_profile_id": profile_id,
            "gate_profile_digest": actual_digest,
            "result": "passed",
            "stages": [],
            "coverage_gaps": [],
        }

    return _run


def _isolate_in_process_git_env(monkeypatch) -> None:
    """清掉钩子注入的 GIT_* 变量。

    `verify_capsule` 在以进程内方式调用 git（`hacf_policy.run_git`），其子进程继承 `os.environ`。
    pre-commit 钩子会向测试进程注入 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE`，此时夹具内的
    裁决与 `changed_files` 会落到**真实仓库**上（曾实际损坏隔离工作区索引）。夹具里的
    `_git()` 已自带 `_clean_git_env`，这里补齐进程内调用的同一道防线。
    """
    for key in _GIT_ENV_POLLUTANTS:
        monkeypatch.delenv(key, raising=False)


def test_verify_signs_green_receipt_for_accepted_gate_evolution(tmp_path, monkeypatch):
    """回归：受权通道合法升级门禁档案时，本地 verify 必须能签出绿色凭单。"""
    _isolate_in_process_git_env(monkeypatch)
    workspace, capsule_path, head = _gate_evolution_workspace(
        tmp_path, registry_digest=EVOLVED_PROFILE_DIGEST
    )
    monkeypatch.setattr(gate_profile, "run_profile", _fake_gate_run(EVOLVED_PROFILE_DIGEST))

    assert agent_capsule.verify_capsule(capsule_path, cwd=workspace) is True

    receipt = json.loads(
        (workspace / ".agents" / "receipts" / "T-GOV-EVOLUTION" / f"{head[:12]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["verdict"] == "passed"
    assert receipt["gate_profile_digest"] == EVOLVED_PROFILE_DIGEST
    assert any("演进被受理" in note for note in receipt["notes"])
    assert "gate profile digest mismatch" not in receipt["coverage_gaps"]
    Draft202012Validator(
        json.loads((ENGINEERING_DIR / "work_receipt.schema.json").read_text(encoding="utf-8"))
    ).validate(receipt)


def test_verify_rejects_gate_evolution_without_registry_sync(tmp_path, monkeypatch):
    """反向回归：registry 未同步的档案改写仍必须被判失败。"""
    _isolate_in_process_git_env(monkeypatch)
    workspace, capsule_path, head = _gate_evolution_workspace(
        tmp_path, registry_digest=BASE_PROFILE_DIGEST
    )
    monkeypatch.setattr(gate_profile, "run_profile", _fake_gate_run(EVOLVED_PROFILE_DIGEST))

    assert agent_capsule.verify_capsule(capsule_path, cwd=workspace) is False

    receipt = json.loads(
        (workspace / ".agents" / "receipts" / "T-GOV-EVOLUTION" / f"{head[:12]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["verdict"] == "failed"
    assert "gate profile digest mismatch" in receipt["coverage_gaps"]
