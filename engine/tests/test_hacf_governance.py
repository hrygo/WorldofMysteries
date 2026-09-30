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
import collab_pipeline  # noqa: E402
import gate_profile  # noqa: E402
import hacf_policy  # noqa: E402
import project_status  # noqa: E402


def test_agt_mac_scope_allows_only_the_app_engine_driver_manifest_in_engine_tests():
    """App source additions and their real-source driver manifest share one writer."""
    role = agent_capsule.ROLE_DEFAULTS["AGT-MAC"]
    capsule = {
        "assigned_role": "AGT-MAC",
        "scope": {
            "write": role["write"],
            "forbidden": role["forbidden"],
            "privileged_grants": [],
        },
    }

    assert hacf_policy.path_verdict(
        capsule, "engine/tests/test_app_engine_session.py"
    )["verdict"] == "authorized"
    assert "engine/tests/" in role["read"]

    for path in (
        "engine/domain/world_engine.py",
        "engine/infrastructure/database/store.py",
        "engine/ai/model_router.py",
        "engine/application/session_orchestrator.py",
    ):
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "forbidden"

    assert hacf_policy.path_verdict(
        capsule, "engine/tests/test_contracts_schema.py"
    )["verdict"] == "out_of_scope"


def test_agt_mac_owns_the_cross_process_app_driver_it_must_keep_alive():
    """The Swift driver that launches the real Engine is App harness, not QA assertion.

    ``engine/tests/fixtures/app_engine_driver.swift`` compiles the production
    App sources and drives them against a real child Engine. When the App's
    launch or session contract changes, only the App owner can keep that driver
    in step; leaving it under a role that may not touch App sources makes the
    FULL_P0 acceptance suite impossible to keep green, which is how a real
    behaviour change gets silently reverted instead of accepted.
    """
    role = agent_capsule.ROLE_DEFAULTS["AGT-MAC"]
    capsule = {
        "assigned_role": "AGT-MAC",
        "scope": {
            "write": role["write"],
            "forbidden": role["forbidden"],
            "privileged_grants": [],
        },
    }

    for path in (
        "engine/tests/fixtures/app_engine_driver.swift",
        "engine/tests/fixtures/voice_turn_e2e_driver.swift",
        "engine/tests/test_app_engine_session.py",
        "engine/tests/test_voice_turn_e2e.py",
    ):
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "authorized", path

    # Narrowing must not leak: the rest of engine/tests/ stays out of reach.
    assert hacf_policy.path_verdict(
        capsule, "engine/tests/test_outbox.py"
    )["verdict"] == "out_of_scope"


def test_agt_ai_scope_allows_only_story_composition_root_files_in_infrastructure():
    """AI may update the narrow composition roots and the AO-04 scenario adapters.

    ``ROLE_DEFAULTS`` 把 ``engine/infrastructure/scenarios/`` 作为**目录**授予
    AGT-AI（见 AO-04-AI-GOV2），因此本断言不再维护一份会与授权漂移的三文件
    白名单，而是直接断言两条不变量：

    1. infrastructure 下的**源码**文件要么落在 AGT-AI 的授权面内，要么被判为
       ``forbidden`` / ``out_of_scope``——绝不出现 ``escalation_required`` 这类
       等待仲裁的中间态；
    2. 授权面内不允许出现持久化与迁移资产（database* / outbox* / migrations/），
       目录级授权不得成为绕过 forbidden 的暗道。

    遍历只覆盖 ``*.py`` 源码：``__pycache__/*.pyc`` 是被 gitignore 的编译产物，
    Stage 2 在本机与 CI 上都会生成，把编译输出纳入所有权断言只会制造与代码无关的
    门禁脆弱点。
    """
    role = agent_capsule.ROLE_DEFAULTS["AGT-AI"]
    capsule = {
        "assigned_role": "AGT-AI",
        "scope": {
            "write": role["write"],
            "forbidden": role["forbidden"],
            "privileged_grants": [],
        },
    }

    for path in (
        "engine/infrastructure/story_runtime.py",
        "engine/infrastructure/episode_settlement.py",
        "engine/infrastructure/scenarios/golden_policy.py",
    ):
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "authorized"

    for path in (
        "engine/infrastructure/database_manager.py",
        "engine/infrastructure/database_migrations.py",
        "engine/infrastructure/migrations/0001_add_story_state.sql",
    ):
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "forbidden"

    assert hacf_policy.path_verdict(
        capsule, "engine/infrastructure/story_runtime_helpers.py"
    )["verdict"] == "out_of_scope"
    for path in (
        "engine/infrastructure/voice_delivery.py",
        "engine/infrastructure/audio/voice_delivery.py",
        "engine/infrastructure/story_control.py",
    ):
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "out_of_scope"

    composition_roots = {
        "engine/infrastructure/story_runtime.py",
        "engine/infrastructure/episode_settlement.py",
        "engine/infrastructure/scenarios/golden_policy.py",
    }
    for path in composition_roots:
        assert hacf_policy.path_verdict(capsule, path)["verdict"] == "authorized"

    persistence_patterns = [
        pattern
        for pattern in role["forbidden"]
        if pattern.startswith("engine/infrastructure/")
    ]
    assert persistence_patterns, "AGT-AI 必须显式声明 infrastructure 的持久化禁区"

    authorized: list[str] = []
    for candidate in (REPO_ROOT / "engine/infrastructure").rglob("*"):
        if not candidate.is_file() or candidate.suffix != ".py":
            continue
        path = candidate.relative_to(REPO_ROOT).as_posix()
        verdict = hacf_policy.path_verdict(capsule, path)["verdict"]
        assert verdict in {"authorized", "forbidden", "out_of_scope"}, path
        if verdict == "authorized":
            authorized.append(path)

    # 反向对照：目录级授权不得成为影子路径的暗道。`scenarios/` 被授予 write，
    # 但 `scenarios/database_manager.py` 仍必须落在 forbidden 里——否则
    # AGT-AI 可以把持久化代码藏进已授权目录，forbidden 的顶层锚定形同虚设。
    for shadowed in (
        "engine/infrastructure/scenarios/database_manager.py",
        "engine/infrastructure/scenarios/outbox_worker.py",
        "engine/infrastructure/scenarios/migrations/0002_seed.sql",
    ):
        assert hacf_policy.path_verdict(capsule, shadowed)["verdict"] == "forbidden", (
            f"目录授权被影子路径绕过：{shadowed}"
        )

    # 目录级授权必须仍然是「窄」的：授权面只能落在两个组合根或 scenarios/ 适配器
    # 目录内，infrastructure 下不得出现第三个授权入口。
    unexpected = [
        path
        for path in authorized
        if path not in composition_roots
        and not path.startswith("engine/infrastructure/scenarios/")
    ]
    assert not unexpected, f"infrastructure 出现未预期的授权面：{unexpected}"


EXCLUSIVE_WRITE_OWNERS = {
    "engine/domain/character_engine.py": "AGT-DOM",
    "engine/ai/gateway.py": "AGT-AI",
    "engine/application/scenario_policy.py": "AGT-AI",
    "engine/infrastructure/database_manager.py": "AGT-DATA",
    "engine/infrastructure/story_session_repository.py": "AGT-DATA",
    "engine/infrastructure/story_runtime.py": "AGT-AI",
    "engine/infrastructure/episode_settlement.py": "AGT-AI",
    "engine/infrastructure/scenarios/golden_policy.py": "AGT-AI",
    "engine/infrastructure/audio/voice_delivery.py": "AGT-VOICE",
    "macos-app/WorldOfMysteries/StorySessionModel.swift": "AGT-MAC",
    "scripts/agent_capsule.py": "AGT-ARB",
    "contracts/protocol/engine_ipc.schema.json": "AGT-ARB",
    "engine/contracts/models.py": "AGT-ARB",
}


def test_every_delivery_surface_has_exactly_one_authorized_writer():
    """每条投递链路上有且只有一个角色被授权写入该文件。

    ``AGT-DATA`` 对 ``engine/infrastructure/`` 是整目录授权，``AGT-AI`` 持有
    AO-04 的组合根与场景适配器，``AGT-VOICE`` 持有 ``audio/``——三者叠加后，
    同一文件会同时对多个角色 ``authorized``，范围审计会全部放行，"每个文件
    只设一个写入者" 就只剩人工纪律而没有机器约束。本断言把独占性钉死。
    """
    authorized_by: dict[str, list[str]] = {}
    for path in EXCLUSIVE_WRITE_OWNERS:
        owners = []
        for role, defaults in agent_capsule.ROLE_DEFAULTS.items():
            capsule = {
                "assigned_role": role,
                "scope": {
                    "write": defaults["write"],
                    "forbidden": defaults["forbidden"],
                    "privileged_grants": [],
                },
            }
            if hacf_policy.path_verdict(capsule, path)["verdict"] == "authorized":
                owners.append(role)
        authorized_by[path] = owners

    overlapping = {path: owners for path, owners in authorized_by.items() if len(owners) != 1}
    assert not overlapping, f"存在多角色写权重叠或零授权：{overlapping}"

    wrong_owner = {
        path: authorized_by[path][0]
        for path, expected in EXCLUSIVE_WRITE_OWNERS.items()
        if authorized_by[path][0] != expected
    }
    assert not wrong_owner, f"授权归属与治理矩阵不符：{wrong_owner}"

    missing = [
        path for path in EXCLUSIVE_WRITE_OWNERS if not (REPO_ROOT / path).is_file()
    ]
    assert not missing, f"治理矩阵引用了不存在的文件：{missing}"


def _owners_of(path: str) -> list[str]:
    owners = []
    for role, defaults in agent_capsule.ROLE_DEFAULTS.items():
        capsule = {
            "assigned_role": role,
            "scope": {
                "write": defaults["write"],
                "forbidden": defaults["forbidden"],
                "privileged_grants": [],
            },
        }
        if hacf_policy.path_verdict(capsule, path)["verdict"] == "authorized":
            owners.append(role)
    return owners


def test_the_contract_schema_source_and_its_python_mirror_have_the_same_owner():
    """契约源与 Python 镜像必须同主，否则字段只能改一半。

    ``contracts/schemas/*.json`` 是跨语言协议的源，``engine/contracts/models.py``
    是它的 Pydantic 镜像。两侧必须由同一角色持有：契约无主不是「无人可改」的
    常态，而是治理空洞：曾经有一段时间两侧都没有写者，加字段的人只能去改一个，
    而没有任何门禁会指出另一个被漏掉，漂移要等到运行时才暴露。

    本断言把「同主」钉死，不指定具体是谁：换人裁决即可，但不允许一侧有主、
    另一侧无主。
    """
    schema_owner = _owners_of("contracts/schemas/story_state.schema.json")
    mirror_owner = _owners_of("engine/contracts/models.py")

    assert schema_owner, "契约源无授权写入者"
    assert mirror_owner, "契约镜像无授权写入者：加字段只能改一半"
    assert schema_owner == mirror_owner, (
        f"契约源与镜像归属不一致：源={schema_owner} 镜像={mirror_owner}"
    )


def test_project_status_renders_completed_milestones_clearly(capsys):
    """Completed milestones must not share the in-progress badge in the status report."""
    state = {
        "project_name": "World of Mysteries",
        "version": "0.1.0",
        "last_updated": "2026-09-27",
        "current_phase": {
            "phase_id": "Phase 1",
            "phase_name": "Persistent World Alpha",
            "status": "IN_PROGRESS",
            "progress_summary": "",
        },
        "gates_health": {},
        "completed_phases": [],
        "milestones": [
            {
                "id": "M5-PREP",
                "name": "Golden assertions",
                "status": "COMPLETED",
                "lead_role": "AGT-QA",
            },
            {
                "id": "M3",
                "name": "Outcome resolver",
                "status": "BLOCKED",
                "lead_role": "AGT-DOM",
            },
        ],
    }

    project_status.cmd_status(state)

    report = capsys.readouterr().out
    completed_line = next(line for line in report.splitlines() if "[M5-PREP]" in line)
    blocked_line = next(line for line in report.splitlines() if "[M3]" in line)
    assert "✅ [M5-PREP]" in completed_line
    assert "[COMPLETED]" in completed_line
    assert "⚪ [M3]" in blocked_line
    assert "[BLOCKED]" in blocked_line


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


def test_packaging_entitlement_requires_explicit_mac_grant():
    """签名/沙箱 entitlement 是高风险面；AGT-MAC 只能在显式 grant 后修改。"""
    capsule = {
        "assigned_role": "AGT-MAC",
        "scope": {
            "read": ["macos-app/"],
            "write": ["macos-app/WorldOfMysteries/", "macos-app/WorldOfMysteriesTests/"],
            "forbidden": ["engine/**", ".hacf/**", ".github/**"],
            "privileged_grants": [],
        },
    }
    path = "macos-app/Packaging/App.entitlements"
    denied = hacf_policy.audit_scope(capsule, [path])
    assert denied["escalations"]
    assert not denied["violations"]

    capsule["scope"]["privileged_grants"] = [path]
    granted = hacf_policy.audit_scope(capsule, [path])
    assert not granted["escalations"]
    assert not granted["violations"]
    assert granted["privileged_uses"] == [path]


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


def test_policy_git_calls_scrub_hook_injected_environment(monkeypatch):
    """策略内核的 git 子进程不得继承 hook 注入的仓库定位变量。"""
    captured = {}

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    for key in _GIT_ENV_POLLUTANTS:
        monkeypatch.setenv(key, "/polluted-by-hook")
    monkeypatch.setattr(hacf_policy.subprocess, "run", fake_run)

    hacf_policy.run_git(["status"])

    assert all(key not in captured["env"] for key in _GIT_ENV_POLLUTANTS)


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


def test_workspace_lease_keeps_af_unix_paths_short(tmp_path, monkeypatch):
    """回归：worktree 路径再长，租约里的 TMPDIR 与 socket 也必须满足 macOS AF_UNIX 上限。

    真实故障形态：worktree 位于 `~/Documents/wom-worktrees/<branch>`（60+ 字符），租约把
    TMPDIR 放在 `<worktree>/.hacf/tmp` 下，`test_ipc_server.py` 的 runtime fixture 在其中
    再嵌套 `tempfile.TemporaryDirectory(prefix="wom-ipc-")` 后 bind，直接触发
    `AF_UNIX path too long`，IPC 测试整片红；而 CI 侧没有 `.hacf/workspace.json`（TMPDIR
    保持系统默认）反而恒绿 —— 这种「本地假红」会持续消耗排障时间。
    """
    monkeypatch.delenv("WOM_WORKSPACE_RUNTIME_BASE", raising=False)
    long_worktree = tmp_path / ("deep-worktree-segment-" * 6)
    branch = "fix/a-deliberately-long-branch-name"

    lease = collab_pipeline._lease_for(branch, long_worktree)

    assert str(long_worktree) not in lease["tmpdir"]
    assert str(long_worktree) not in lease["ipc_socket"]

    # sockaddr_un 的 sun_path 上限含结尾 NUL，可用字节数为 103。
    assert len(lease["tmpdir"].encode("utf-8")) <= 103
    assert len(lease["ipc_socket"].encode("utf-8")) <= 103
    # 复刻最坏嵌套：TMPDIR / <临时子目录> / engine.sock
    worst_case = Path(lease["tmpdir"]) / "wom-ipc-abcdefgh" / "engine.sock"
    assert len(str(worst_case).encode("utf-8")) <= 103

    # 同一分支必须稳定复用同一命名空间（start / status / abort 之间不漂移）。
    assert collab_pipeline._lease_for(branch, long_worktree)["tmpdir"] == lease["tmpdir"]
    # 不同分支互不干扰。
    assert collab_pipeline._lease_for("fix/other", long_worktree)["tmpdir"] != lease["tmpdir"]


def test_workspace_lease_rejects_unusably_long_short_base(monkeypatch):
    """短路径根目录被配置得过长时，必须在 start 阶段响亮失败，而不是留到 socket 断言里。"""
    monkeypatch.setenv("WOM_WORKSPACE_RUNTIME_BASE", "/tmp/" + "x" * 120)
    with pytest.raises(RuntimeError, match="AF_UNIX"):
        collab_pipeline._lease_for("fix/whatever", Path("/tmp/any-worktree"))


def test_start_persists_task_id_in_workspace_lease(tmp_path, monkeypatch):
    branch = "feat/arb-collab-lease-task-id"
    task_id = "ARB-COLLAB-LEASE-TASK-ID"
    worktree_base = tmp_path / "worktrees"
    worktree = worktree_base / branch.replace("/", "-")
    runtime_base = Path("/tmp") / f"wom-test-{os.getpid()}-{tmp_path.name[-4:]}"
    monkeypatch.setattr(collab_pipeline, "WORKTREE_BASE", worktree_base)
    monkeypatch.setattr(collab_pipeline, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setenv("WOM_WORKSPACE_RUNTIME_BASE", str(runtime_base))

    def fake_run_cmd(cmd, cwd=collab_pipeline.REPO_ROOT, check=True):
        if cmd.startswith("git rev-parse --verify "):
            return subprocess.CompletedProcess(cmd, 1, "", "")
        if cmd.startswith("git worktree add -b "):
            worktree.mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(collab_pipeline, "run_cmd", fake_run_cmd)

    try:
        collab_pipeline.start_pipeline(
            branch, role="AGT-ARB", task_id=task_id, skip_venv=True
        )

        lease = json.loads(
            (worktree / ".hacf" / "workspace.json").read_text(encoding="utf-8")
        )
        assert lease["task_id"] == task_id
    finally:
        collab_pipeline._cleanup_short_runtime(branch)
        if runtime_base.exists():
            runtime_base.rmdir()


@pytest.mark.parametrize(
    ("branch", "task_id"),
    [
        ("feat/mac-art-runtime-repack-r1", "MAC-ART-RUNTIME-REPACK-R1"),
        ("feat/arb-asset-lesson-r1", "ARB-ASSET-LESSON-R1"),
        (
            "feat/arb-asset-storage-encoding-r1",
            "ARB-ASSET-STORAGE-ENCODING-R1",
        ),
    ],
)
def test_old_workspace_lease_keeps_historical_branch_guess(
    tmp_path, monkeypatch, branch, task_id
):
    workspace = tmp_path / "workspace"
    capsules_dir = workspace / ".agents" / "capsules"
    capsules_dir.mkdir(parents=True)
    (workspace / ".hacf").mkdir()
    (workspace / ".hacf" / "workspace.json").write_text(
        json.dumps({"branch": branch}), encoding="utf-8"
    )
    (capsules_dir / f"{task_id}.json").write_text("{}", encoding="utf-8")
    (capsules_dir / "UNRELATED-TASK.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        hacf_policy,
        "run_git",
        lambda args, cwd=None: branch
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]
        else pytest.fail(f"unexpected git query: {args}"),
    )

    assert collab_pipeline._resolve_task_id(workspace, None) == task_id


@pytest.mark.parametrize(
    ("explicit_task_id", "expected_task_id"),
    [
        (None, "ARB-COLLAB-LEASE-TASK-ID"),
        ("EXPLICIT-INTEGRATE-TASK", "EXPLICIT-INTEGRATE-TASK"),
    ],
)
def test_integrate_uses_workspace_task_id_unless_explicitly_overridden(
    tmp_path, monkeypatch, explicit_task_id, expected_task_id
):
    branch = "feat/ao-03-retire-store-protocol"
    lease_task_id = "ARB-COLLAB-LEASE-TASK-ID"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    worktree = tmp_path / "worktree"
    capsules_dir = worktree / ".agents" / "capsules"
    capsules_dir.mkdir(parents=True)
    (worktree / ".hacf").mkdir()
    (worktree / ".hacf" / "workspace.json").write_text(
        json.dumps({"task_id": lease_task_id}), encoding="utf-8"
    )
    for task_id in (lease_task_id, "EXPLICIT-INTEGRATE-TASK"):
        (capsules_dir / f"{task_id}.json").write_text(
            json.dumps(
                {
                    "capsule_id": f"CAP-{task_id}",
                    "task_id": task_id,
                    "assigned_role": "AGT-ARB",
                    "risk_class": "privileged",
                    "scope": {},
                    "gates": {},
                }
            ),
            encoding="utf-8",
        )
    (capsules_dir / "UNRELATED-TASK.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(collab_pipeline, "REPO_ROOT", repo_root)
    monkeypatch.setattr(collab_pipeline, "get_worktree_dir", lambda _: worktree)

    def fake_run_git(args, cwd=None):
        if args == ["rev-parse", "HEAD"] and Path(cwd) == worktree:
            return "worktree-head"
        if args == ["rev-parse", "main"]:
            return "main-head"
        if args == ["rev-parse", "HEAD"] and Path(cwd) == repo_root:
            return "merged-head"
        raise AssertionError(f"unexpected git query: {args} cwd={cwd}")

    monkeypatch.setattr(hacf_policy, "run_git", fake_run_git)
    monkeypatch.setattr(
        collab_pipeline,
        "run_cmd",
        lambda cmd, cwd=repo_root, check=True: subprocess.CompletedProcess(
            cmd, 0, "", ""
        ),
    )
    monkeypatch.setattr(
        gate_profile,
        "run_profile",
        lambda *args, **kwargs: {
            "result": "passed",
            "gate_profile_id": "FULL_P0",
            "gate_profile_digest": "test-digest",
            "started_at": "2026-09-28T00:00:00+08:00",
            "coverage_gaps": [],
        },
    )
    monkeypatch.setattr(gate_profile, "collect_toolchain", lambda _: {})
    monkeypatch.setattr(hacf_policy, "changes_digest", lambda *args, **kwargs: "digest")
    captured_receipts = []
    monkeypatch.setattr(
        hacf_policy,
        "write_receipt",
        lambda root, receipt, head: captured_receipts.append(receipt)
        or (tmp_path / "receipt.json"),
    )

    collab_pipeline.integrate_pipeline(
        branch, task_id=explicit_task_id, skip_smoke=True
    )

    assert len(captured_receipts) == 1
    assert captured_receipts[0]["task_id"] == expected_task_id
    assert captured_receipts[0]["capsule_id"] == f"CAP-{expected_task_id}"


def test_capsule_target_ref_prefers_integration_base_branch(tmp_path, monkeypatch):
    """回归：在特性分支工作区里 pack，必须记录合入目标（origin/main）而不是当前分支。

    历史缺陷：`start --role --task-id` 会在新建 worktree 内自动 pack，此时 HEAD 是特性
    分支，胶囊便把特性分支记成 `target_ref` —— 提交自己的改动就触发 `stale_context`，
    verify 永远拒绝签发凭单；而按直觉在提交前验收，`changes_digest(base_sha...HEAD)` 又是
    空 diff（凭单绑定空值）。目标 ref 只应在**受保护的合入目标**前进时才判定上下文陈旧。

    必须清掉钩子注入的 `GIT_*`：pre-commit 会向测试进程注入 `GIT_DIR`，此时进程内
    `hacf_policy.run_git` 即使拿到 `cwd=临时仓库` 也会解析到真实仓库，让本用例假红。
    """
    _isolate_in_process_git_env(monkeypatch)
    workspace = _init_repo_with_branches(tmp_path, shallow_clone=False)
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"

    original_run_git = hacf_policy.run_git

    def run_git_in_workspace(args, cwd=None):
        return original_run_git(args, cwd=workspace)

    monkeypatch.setattr(hacf_policy, "run_git", run_git_in_workspace)

    assert agent_capsule._detect_target_ref() == "origin/main"
    # 显式指定优先（合入目标非默认命名时）。
    assert agent_capsule._detect_target_ref("feature") == "feature"
    # 记录的目标是合入目标的 sha，与当前特性分支尖端不同 —— 两者混淆正是「自发陈旧」的成因。
    assert hacf_policy.run_git(["rev-parse", "origin/main"]) != hacf_policy.run_git(
        ["rev-parse", "HEAD"]
    )


def test_scope_audit_covers_committed_range_not_only_working_tree(tmp_path, monkeypatch):
    """回归：先提交再 verify 时，范围裁决必须覆盖 `base_sha → HEAD` 的**已提交**内容。

    历史缺陷：审计只取工作树（`git diff HEAD`）。验收流程要求「先提交、再 verify」
    （否则 `changes_digest` 是空 diff），此时工作区干净、审计恒为空集 —— 越界改动会静默
    漏过本地门禁，只剩 CI 一道防线。本用例把越界改动**先提交**并保持工作区干净，
    verify 仍必须判 SCOPE BREACH。
    """
    _isolate_in_process_git_env(monkeypatch)
    workspace, capsule_path, _ = _gate_evolution_workspace(
        tmp_path, registry_digest=EVOLVED_PROFILE_DIGEST
    )
    monkeypatch.setattr(gate_profile, "run_profile", _fake_gate_run(EVOLVED_PROFILE_DIGEST))

    out_of_scope = workspace / "macos-app" / "App.swift"
    out_of_scope.parent.mkdir()
    out_of_scope.write_text("// 越界：write scope 只有 .hacf/ 与 app.txt\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-q", "-m", "out of scope work")
    assert _git(workspace, "status", "--porcelain").stdout.strip() == ""

    # 模拟「在该提交上重新 pack」：否则目标 ref 已前进，verify 会先以 STALE CONTEXT 拒绝，
    # 走不到本用例要检验的范围裁决。
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["base"]["target_sha"] = _git(workspace, "rev-parse", "HEAD").stdout.strip()
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")

    assert agent_capsule.verify_capsule(capsule_path, cwd=workspace) is False

    receipts = sorted((workspace / ".agents" / "receipts" / "T-GOV-EVOLUTION").glob("*.json"))
    receipt = json.loads(receipts[-1].read_text(encoding="utf-8"))
    rendered = json.dumps(receipt, ensure_ascii=False)
    assert receipt["verdict"] == "failed"
    assert "范围裁决未通过" in rendered
    assert "macos-app/App.swift" in rendered
