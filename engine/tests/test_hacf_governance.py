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
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
ENGINEERING_DIR = REPO_ROOT / "contracts" / "engineering"

sys.path.insert(0, str(SCRIPTS_DIR))

import generate_pr_report as reporter  # noqa: E402
import agent_capsule  # noqa: E402
import check_architecture_fitness as fitness  # noqa: E402
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


def test_the_staleness_probe_measures_the_gap_between_narrative_and_repository():
    """事实源是散文，会静默过期；探针必须能说出它落后了多少。"""
    tip = project_status.repository_tip()
    assert tip is not None, "探测不到仓库最新提交，探针本身失效"

    state = {"last_updated": "2026-09-28"}
    gap = project_status.staleness(state)

    assert gap is not None
    assert gap["recorded"] == "2026-09-28"
    assert gap["tip_sha"] == tip["sha"]
    assert gap["days_behind"] == (tip["date"] - date(2026, 9, 28)).days


def test_a_narrative_that_is_not_behind_reports_no_gap():
    """不得因为「总是告警」而变成噪声 —— 没落后就不该响。"""
    tip = project_status.repository_tip()
    assert tip is not None

    assert project_status.staleness({"last_updated": tip["date"].isoformat()}) is None
    assert project_status.staleness({"last_updated": "2099-01-01"}) is None


def test_a_narrative_without_a_readable_date_is_not_guessed_at():
    assert project_status.staleness({}) is None
    assert project_status.staleness({"last_updated": "not-a-date"}) is None


def test_the_stale_banner_warns_on_stderr_so_stdout_stays_pipeable(capsys):
    """stdout 是给人读的表格，告警走 stderr，`> report.txt` 不会把它弄脏。"""
    state = {
        "project_name": "World of Mysteries",
        "version": "0.1.0",
        "last_updated": "2026-09-28",
        "current_phase": {
            "phase_id": "Phase 1",
            "phase_name": "x",
            "status": "IN_PROGRESS",
            "progress_summary": "",
        },
        "gates_health": {},
        "completed_phases": [],
        "milestones": [],
    }

    project_status.cmd_status(state)

    captured = capsys.readouterr()
    assert "⚠️" in captured.err
    assert "落后于仓库" in captured.err
    assert "⚠️" not in captured.out


def test_the_git_probe_survives_hook_injected_repository_variables(monkeypatch, tmp_path):
    """钩子注入的 GIT_* 会把 git 劫持回真仓库；探针必须在这种环境里仍读到本仓库。

    这不是假想：pre-commit 钩子会注入这五个变量，而脚本与测试里调用 git 若不清
    掉它们，裁决会落到真仓库上——本仓库的夹具曾因此损坏隔离工作区索引。
    """
    real = project_status.repository_tip()
    assert real is not None

    for key in project_status._GIT_ENV_POLLUTANTS:
        monkeypatch.setenv(key, str(tmp_path / "hijacked"))

    assert "GIT_DIR" not in project_status._git_env()
    assert project_status.repository_tip() == real


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


def _real_stage_results(profile_id: str) -> list:
    """按 ``run_profile`` 的形状还原真实档案的阶段，供覆盖核算使用。"""
    profile, _, _ = gate_profile.resolve_profile(profile_id)
    return [
        {
            "stage": index,
            "name": stage.get("name", ""),
            "command": [
                gate_profile.expand_token(token, {}) for token in stage["command"]
            ],
            "cwd": str((REPO_ROOT / stage.get("cwd", ".")).resolve()),
        }
        for index, stage in enumerate(profile["stages"], start=1)
    ]


def test_a_role_profile_that_skips_the_changed_tests_is_reported_as_a_gap():
    """SB-16 实测到的病态：档案全绿，却一条都没跑到本次改动的测试。

    ``empty_selection_policy`` 抓的是「整个 ``-k`` 过滤一条都没收集到」（pytest
    exit 5）。这里要抓的是另一回事：过滤收集到了 plenty 条，但没有一条来自本次
    改动的文件 —— 门禁全绿，而这次改动一行都没被验证过。
    """
    gaps = gate_profile._uncovered_changed_tests(
        "AI_GATEWAY_P0",
        _real_stage_results("AI_GATEWAY_P0"),
        ["engine/tests/test_storybook_contract_parity.py"],
        REPO_ROOT,
        dict(os.environ),
    )

    assert len(gaps) == 1
    assert "test_storybook_contract_parity.py" in gaps[0]


def test_the_tests_a_profile_actually_selects_are_not_reported_as_uncovered():
    """不得把真跑到的测试误报成缺口 —— 否则这条告警会被当成噪声忽略。"""
    gaps = gate_profile._uncovered_changed_tests(
        "AI_GATEWAY_P0",
        _real_stage_results("AI_GATEWAY_P0"),
        ["engine/tests/test_context_compiler.py"],
        REPO_ROOT,
        dict(os.environ),
    )

    assert gaps == []


def test_a_profile_without_a_keyword_filter_covers_what_it_runs():
    """FULL_P0 跑全量套件，没有 ``-k`` 可言，因而不该报缺口。"""
    gaps = gate_profile._uncovered_changed_tests(
        "FULL_P0",
        _real_stage_results("FULL_P0"),
        ["engine/tests/test_storybook_contract_parity.py"],
        REPO_ROOT,
        dict(os.environ),
    )

    assert gaps == []


def test_swift_test_runs_the_whole_package_so_changed_swift_tests_are_covered():
    gaps = gate_profile._uncovered_changed_tests(
        "MACOS_APP_P0",
        _real_stage_results("MACOS_APP_P0"),
        ["macos-app/WorldOfMysteriesTests/StoryBookTests.swift"],
        REPO_ROOT,
        dict(os.environ),
    )

    assert gaps == []


def test_changing_production_code_alone_is_not_a_coverage_gap():
    """只有「改了测试文件却没跑到」才是缺口；改生产代码无从判断覆盖。"""
    gaps = gate_profile._uncovered_changed_tests(
        "AI_GATEWAY_P0",
        _real_stage_results("AI_GATEWAY_P0"),
        ["engine/ai/gateway.py", "engine/infrastructure/story_runtime.py"],
        REPO_ROOT,
        dict(os.environ),
    )

    assert gaps == []


def test_run_profile_records_the_gap_in_coverage_gaps(tmp_path):
    """凭单里那条 ``coverage_gaps`` 必须真被填上，而不只是字段存在。

    ``coverage_gaps`` 从receipt schema 到 ``capsule_audit`` 到 PR 证据卡都是现成的，
    唯独没人给「档案没跑到本次改动」这个情况赋值。这条断言盯的就是那条接线。
    """
    staging = REPO_ROOT / ".hacf" / "tmp" / f"cheap_p0_{tmp_path.name}"
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / "cheap_p0.json"
    staged.write_text(
        json.dumps(
            {
                "gate_profile_id": "CHEAP_P0",
                "risk_class": "low",
                "stages": [
                    {"stage": 1, "name": "noop", "cwd": ".", "command": ["true"]}
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    registry = gate_profile.load_registry()
    registry["profiles"]["CHEAP_P0"] = {
        "file": str(staged),
        "sha256": gate_profile.sha256_file(staged),
    }
    registry_copy = tmp_path / "registry.json"
    registry_copy.write_text(json.dumps(registry), encoding="utf-8")

    result = gate_profile.run_profile(
        "CHEAP_P0",
        cwd=REPO_ROOT,
        registry_path=registry_copy,
        repo_root=REPO_ROOT,
        quiet=True,
        changed_files=["engine/tests/test_context_compiler.py"],
    )

    assert result["result"] == "passed"
    assert any(
        "test_context_compiler.py" in gap for gap in result["coverage_gaps"]
    )


def _run_empty_selection_profile(tmp_path, policy: str):
    """跑一个 ``-k`` 注定收集不到任何东西的 pytest 阶段。

    真实档案的 pytest 命令形如 ``uv run --locked --extra dev pytest``，pytest 落在
    index 6 —— 这正是那个前缀匹配从未生效、``empty_selection_policy`` 形同虚设的
    原因，所以这里必须用真实 argv 而不能图省事写个短命令。
    """
    staging = REPO_ROOT / ".hacf" / "tmp" / f"empty_sel_{tmp_path.name}_{policy}"
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / "empty_p0.json"
    staged.write_text(
        json.dumps(
            {
                "gate_profile_id": "EMPTY_P0",
                "risk_class": "low",
                "stages": [
                    {
                        "stage": 1,
                        "name": "selects nothing",
                        "cwd": "engine",
                        "command": [
                            "uv", "run", "--locked", "--extra", "dev",
                            "pytest", "-q", "-k",
                            "zzz_no_such_test_selector_zzz",
                        ],
                        "empty_selection_policy": policy,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    registry = gate_profile.load_registry()
    registry["profiles"]["EMPTY_P0"] = {
        "file": str(staged),
        "sha256": gate_profile.sha256_file(staged),
    }
    registry_copy = tmp_path / f"registry_{policy}.json"
    registry_copy.write_text(json.dumps(registry), encoding="utf-8")
    return gate_profile.run_profile(
        "EMPTY_P0",
        cwd=REPO_ROOT,
        registry_path=registry_copy,
        repo_root=REPO_ROOT,
        quiet=True,
    )


def test_a_profile_that_declares_warn_records_the_gap_instead_of_failing(tmp_path):
    """``.hacf/gates/ai_gateway_p0.json`` 写着「缺口将被显式记录」，那就得真的记录。

    该档案声明 ``empty_selection_policy: "warn"``：命令选择不到任何用例时应当
    记为 ``passed_with_gap`` 并把缺口写进 receipt，而不是直接判failed。
    """
    result = _run_empty_selection_profile(tmp_path, "warn")

    assert result["stages"][0]["status"] == "passed_with_gap"
    assert result["result"] == "passed"
    assert any("未收集到任何测试" in gap for gap in result["coverage_gaps"])


def test_a_profile_that_forbids_empty_selection_still_fails_closed(tmp_path):
    """反向：没声明 warn 的档案不得因为选择器空转而放行。"""
    result = _run_empty_selection_profile(tmp_path, "fail")

    assert result["stages"][0]["status"] == "failed"
    assert result["result"] == "failed"


# ---- PRD §20.1: reading the Story Book must never rewrite it --------------


def test_the_reading_path_carries_no_model_capable_import():
    """不变量 9 / §20.1 的结构面：装配故事书的两个模块不得触达模型或网络。"""
    assert fitness.check_storybook_reading_path_is_model_free() == []


@pytest.mark.parametrize(
    "source",
    [
        "import agentscope\n",
        "from agentscope import Msg\n",
        "import openai\n",
        "import httpx\n",
        "from urllib import request\n",
        "from ai import ModelRouter\n",
        "import ai.model_router\n",
    ],
    ids=lambda s: s.strip().replace(" ", "_"),
)
def test_the_fitness_check_catches_a_model_reaching_the_reading_path(tmp_path, source):
    """这条规则本身必须会红，否则它只是一句声明。"""
    offender = tmp_path / "storybook_projection.py"
    offender.write_text(source, encoding="utf-8")

    violations = fitness._forbidden_imports_in(offender, fitness.MODEL_CAPABLE_MODULES)

    assert len(violations) == 1
    assert "imports" in violations[0] and str(offender) in violations[0]


def test_the_fitness_check_names_the_invariant_when_a_real_module_drifts(tmp_path):
    """外层包装必须把违规标成不变量 9，否则 Stage 1 报告读不出严重性。"""
    staged = tmp_path / "engine" / "application"
    staged.mkdir(parents=True)
    (staged / "storybook_projection.py").write_text(
        "from openai import OpenAI\n", encoding="utf-8"
    )
    (staged / "storybook_service.py").write_text("x = 1\n", encoding="utf-8")

    original_root, original_modules = fitness.REPO_ROOT, fitness.STORYBOOK_READING_MODULES
    fitness.REPO_ROOT = tmp_path
    fitness.STORYBOOK_READING_MODULES = (
        "engine/application/storybook_projection.py",
        "engine/application/storybook_service.py",
    )
    try:
        violations = fitness.check_storybook_reading_path_is_model_free()
    finally:
        fitness.REPO_ROOT, fitness.STORYBOOK_READING_MODULES = (
            original_root,
            original_modules,
        )

    assert any("Invariant 9 Violation" in v and "openai" in v for v in violations)


def test_a_missing_reading_module_is_reported_rather_than_skipped():
    """文件不见了必须报缺失，不能当作「没有违规」而静默放行。"""
    original_modules = fitness.STORYBOOK_READING_MODULES
    fitness.STORYBOOK_READING_MODULES = ("engine/application/not_there.py",)
    try:
        violations = fitness.check_storybook_reading_path_is_model_free()
    finally:
        fitness.STORYBOOK_READING_MODULES = original_modules

    assert violations and "missing" in violations[0]


# §20.1 says the book is the Narrative Blocks that actually happened, plus any
# necessary transition — never a novel the model wrote afterwards. Nothing
# pinned that: the projection's own tests asserted speakers and structure, and
# the "no model call" claim lived only in a module docstring.
_VERBATIM_TEXTS = (
    "  雨落在诊所的窗外。  ",
    "第 3 次敲门，无人应答。",
    "「你终于来了。」——他说",
    "她把账本翻到第 12 页，指尖停在空白处。",
)


def _verbatim_book():
    from application.storybook_projection import project_story_book
    from contracts import Episode, NarrativeBlock
    from contracts.models import NarrativeSegment

    segments = [
        NarrativeSegment(type="narration", text=text) for text in _VERBATIM_TEXTS
    ]
    block = NarrativeBlock(
        schema_version="1.0",
        id="b1",
        story_session_id="session-1",
        source_story_revision=1,
        scene_id="consultation_room",
        segments=segments,
    )
    episode = Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode-1",
            "world_id": "world-1",
            "worldline_id": "worldline-1",
            "protagonist_ids": ["char_evelyn"],
            "title": "哈维诊所的停顿",
            "start_world_time": "1349-06-12T21:40:00",
            "ending": {"type": "partial_truth", "main_problem": None},
            "secret_states": {},
            "unresolved_threads": [],
            "narrative_block_ids": ["b1"],
        }
    )
    book = project_story_book(
        episode=episode,
        narrative_blocks={"b1": block},
        character_display_names={},
        proposition_display_names={},
    )
    return book, segments


def test_the_book_reproduces_committed_prose_verbatim():
    """§20.1 的行为面：书里的正文必须就是当时提交的那段原文。

    任何 strip、标点归一、数字改写或「润色」都会在这里现形 —— 而这正是模型
    重写一篇「差不多」的小说在输出上留下的痕迹。
    """
    book, segments = _verbatim_book()

    produced = [segment["text"] for segment in book["chapters"][0]["segments"]]
    assert produced == list(_VERBATIM_TEXTS)
    assert produced == [segment.text for segment in segments]


def test_the_book_neither_adds_nor_drops_a_segment():
    """重写还常表现为合并、拆分或总结；段数与顺序必须原样保留。"""
    book, segments = _verbatim_book()

    assert len(book["chapters"]) == 1
    assert len(book["chapters"][0]["segments"]) == len(segments)


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

    # 第二个提交提供非空变更集。凭单必须绑定实际被门禁验过的那份内容：空变更集曾被
    # schema 放行（sha256("") 也是合法摘要），签出的是一份什么都没认证的绿色凭单，
    # 该路径现由 verify 的空变更范围守卫拒绝。
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


def test_verify_refuses_to_certify_an_empty_change_range(tmp_path, monkeypatch):
    """回归：base_sha 落在改动之后时，不得签发绑定空摘要的绿色凭单。

    事故实例：VF-85A 首次验收时 base_commit == head_commit == 42e30fcd，
    diff_digest=sha256:e3b0c442…（空串的 SHA-256），verdict 仍是 passed。
    成因是在提交代码之后才重打包胶囊，base 指向了代码提交自身。

    一份不绑定任何内容的凭单比没有凭单更危险：它看上去像一次授权。
    """
    _isolate_in_process_git_env(monkeypatch)
    workspace, capsule_path, head = _gate_evolution_workspace(
        tmp_path, registry_digest=EVOLVED_PROFILE_DIGEST
    )
    monkeypatch.setattr(gate_profile, "run_profile", _fake_gate_run(EVOLVED_PROFILE_DIGEST))

    # 把 base 挪到 HEAD，精确复现「提交之后才打包」的顺序错误。
    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    capsule["base"]["base_sha"] = head
    capsule_path.write_text(json.dumps(capsule, indent=2), encoding="utf-8")

    assert agent_capsule.verify_capsule(capsule_path, cwd=workspace) is False

    receipt = json.loads(
        (workspace / ".agents" / "receipts" / "T-GOV-EVOLUTION" / f"{head[:12]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["verdict"] == "failed"
    assert any("空变更范围" in note for note in receipt["notes"])
    assert receipt["gate_result"] == "not_run"


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


def _dispatch_state(role: str) -> dict:
    return {
        "critical_path": {
            "dispatch": {
                "assigned_role": role,
                "role_title": "角色标题",
                "task_id": "SB-23",
                "task_title": "任务标题",
                "pack_command": "python3 scripts/agent_capsule.py pack",
                "worktree_command": "python3 scripts/collab_pipeline.py start",
            }
        }
    }


def test_the_dispatch_card_takes_its_scope_from_the_role_defaults(capsys):
    """派发卡是下一位 Agent 逐字照抄的东西，它说的范围必须是真的那份。"""
    role = "AGT-VOICE"
    scope = project_status.role_scope(role)
    assert scope, f"{role} 应当有角色默认值"

    project_status.cmd_dispatch(_dispatch_state(role))

    out = capsys.readouterr().out
    for item in scope["write"]:
        assert f"- {item}" in out, f"可写范围漏了 {item}"
    for item in scope["read"]:
        assert f"- {item}" in out, f"可读范围漏了 {item}"
    for item in scope["forbidden"]:
        assert item in out, f"禁触红线漏了 {item}"


def test_the_dispatch_card_cannot_restate_a_scope_of_its_own(capsys):
    """卡片一旦把范围抄回自己就会漂移——本用例钉死它不许再抄。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    for holder in ("critical_path", "execution_focus"):
        dispatch = card[holder].get("dispatch", {})
        assert "authorized_scope" not in dispatch, (
            f"{holder}.dispatch 复述了 authorized_scope：它与 ROLE_DEFAULTS 漂移过"
        )
        assert "forbidden_patterns" not in dispatch, (
            f"{holder}.dispatch 复述了 forbidden_patterns：它与 ROLE_DEFAULTS 漂移过"
        )

    project_status.cmd_dispatch(card)
    out = capsys.readouterr().out
    assert "单一事实源" in out


def test_the_dispatch_card_follows_the_defaults_when_they_change(monkeypatch, capsys):
    """反向扰动：改角色默认值，卡片必须跟着变——证明它不是在念自己的草稿。"""
    monkeypatch.setitem(
        agent_capsule.ROLE_DEFAULTS,
        "AGT-VOICE",
        {
            "write": ["engine/tests/test_only_probe.py"],
            "read": ["contracts/"],
            "forbidden": ["scripts/**"],
            "gate_profile": "VOICE_P0",
            "risk_class": "medium",
            "invariants": [9],
        },
    )

    project_status.cmd_dispatch(_dispatch_state("AGT-VOICE"))

    out = capsys.readouterr().out
    assert "engine/tests/test_only_probe.py" in out
    assert "scripts/**" in out
    assert "engine/infrastructure/audio/" not in out, "卡片仍在念写死的旧范围"


def test_an_unknown_role_is_reported_rather_than_granted_an_empty_scope(capsys):
    """查不到角色时必须显式说查不到；空列表会被读成「什么都能写」。"""
    project_status.cmd_dispatch(_dispatch_state("AGT-NOT-A-ROLE"))

    out = capsys.readouterr().out
    assert "AGT-NOT-A-ROLE" in out
    assert "不在 ROLE_DEFAULTS 枚举内" in out


def _pending_decisions() -> list:
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    return card["pending_decisions"]


def test_every_pending_decision_cites_a_section_that_still_resolves():
    """待裁决清单是给人裁的，出处必须点得开——引错文档等于没引。"""
    for item in _pending_decisions():
        evidence = item.get("evidence")
        if evidence is None:
            assert item.get("evidence_gap"), (
                f"{item['id']} 没有证据出处，必须用 evidence_gap 说明为什么没有"
            )
            continue
        rel, _, heading = evidence.partition("#")
        path = project_status.ROOT_DIR / rel
        assert path.exists(), f"{item['id']} 的证据出处不存在：{rel}"
        assert heading, f"{item['id']} 的证据出处缺少章节锚点：{evidence}"
        assert heading in path.read_text(encoding="utf-8"), (
            f"{item['id']} 引用的章节标题在 {rel} 里已经不存在了：{heading}"
        )


def test_a_pending_decision_is_never_dispatched_as_a_task():
    """把待裁决项当任务派下去，等于替人类架构师做了那个决定。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    pending_ids = {item["id"] for item in card["pending_decisions"]}
    for holder in ("critical_path", "execution_focus"):
        task_id = card[holder]["dispatch"]["task_id"]
        assert task_id not in pending_ids, (
            f"{holder}.dispatch 把待裁决项 {task_id} 当成可执行任务派发了"
        )


def test_the_dispatch_card_states_what_it_is_not_allowed_to_do():
    """派发卡必须同时说清禁区，否则接手者只会看到该做什么。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    for holder in ("critical_path", "execution_focus"):
        dispatch = card[holder]["dispatch"]
        assert dispatch.get("forbidden_actions"), f"{holder}.dispatch 没有写禁区"
        assert dispatch.get("preconditions"), f"{holder}.dispatch 没有写前提"


def test_the_status_report_actually_shows_the_pending_decisions(capsys):
    """决策包如果只在 JSON 里而不在报告里，接手者看不到等于没有。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )

    project_status.cmd_status(card)

    report = capsys.readouterr().out
    assert "【5. 待人类裁决" in report
    for item in card["pending_decisions"]:
        assert item["id"] in report, f"{item['id']} 没出现在状态报告里"
        assert item["question"] in report, f"{item['id']} 的问题陈述没出现在状态报告里"
    assert "【6. 已证实但未接线的子系统" in report
    for item in card["verified_unwired"]:
        assert item["id"] in report, f"{item['id']} 没出现在状态报告里"


def test_the_narrative_segment_to_take_binding_is_persisted_not_recomputed():
    """曾被写成「无任何表记录该绑定、回放靠重算 render_key 反推」——两条都是假的，钉死。"""
    root = project_status.ROOT_DIR
    migration = (root / "engine/infrastructure/migrations/007_world_audio_tracks.sql").read_text(
        encoding="utf-8"
    )
    for column in ("turn_id", "narrative_block_id", "segment_index", "story_revision", "take_id"):
        assert column in migration, f"audio_track_units 不再记录 {column}，绑定口径已变"
    assert "REFERENCES turn_transactions(id)" in migration
    assert "REFERENCES narrative_blocks(id)" in migration
    assert "UNIQUE(track_id, narrative_block_id, segment_index)" in migration, (
        "分段唯一约束消失，同一叙事段可能被钉到多个 take"
    )

    replay = (root / "engine/infrastructure/audio_replay.py").read_text(encoding="utf-8")
    assert "unit.take_id" in replay, "回放不再从钉住的 unit 取件"
    assert "render_key" not in replay, (
        "回放路径里出现 render_key：若按内容地址反推取件，重铸音色后会取到从未播放过的音频"
    )


def test_the_unwired_subsystem_records_what_is_actually_verified():
    """已证实的未接线子系统必须逐条给出证据，不能只是一句判断。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    unwired = card.get("verified_unwired") or []
    assert unwired, "未接线子系统清单不应为空：它是被逐条核实过的结论"
    for item in unwired:
        assert item.get("retracts"), f"{item['id']} 没有记录它撤回了什么"
        for key in ("persisted", "replay_reads_pins", "recast_is_designed_for", "but_unwired"):
            assert item["evidence"].get(key), f"{item['id']} 缺证据条目 {key}"


def test_the_take_layer_itself_has_no_production_caller():
    """曾三次误判为「只是 track 层没接线」。take 层同样零调用——钉死这一层。"""
    root = project_status.ROOT_DIR
    source_root = root / "engine"

    #: 这五个模块互相引用是子系统内部结构，不是生产接线：
    #: audio_replay 用 SQLiteAudioTakeStore，并不意味着有任何生产路径能到达 audio_replay。
    subsystem = frozenset({
        "engine/infrastructure/audio_take_store.py",
        "engine/infrastructure/audio_take_coordinator.py",
        "engine/infrastructure/audio_prefetch.py",
        "engine/infrastructure/audio_track_repository.py",
        "engine/infrastructure/audio_replay.py",
    })

    def _production_modules() -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for path in source_root.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if "/tests/" in f"/{rel}" or rel.startswith("engine/tests/"):
                continue
            found.append((rel, path.read_text(encoding="utf-8")))
        return found

    modules = _production_modules()

    # publish_pcm 是写入 audio_takes 的唯一入口；它若无人调用，take 永不产生。
    callers = sorted(
        rel for rel, text in modules
        if "publish_pcm" in text and rel != "engine/infrastructure/audio_take_store.py"
    )
    assert callers == ["engine/infrastructure/audio_take_coordinator.py"], (
        f"publish_pcm 的调用方变了：{callers}；唯一写入口不再只经 coordinator，take 层结论需重核"
    )

    # 子系统之外无人引用这五个类。
    for symbol in (
        "SQLiteAudioTakeStore",
        "SQLiteAudioTrackRepository",
        "AudioTakeRenderCoordinator",
        "AudioTakePrefetchQueue",
        "OfflineStoryBookReplayResolver",
    ):
        outside = sorted(
            rel for rel, text in modules
            if symbol in text and rel not in subsystem
        )
        assert outside == [], (
            f"{symbol} 已被子系统外的生产代码 {outside} 引用，"
            "「take 层零接线」的结论已过期，需重新核实"
        )

    # 子系统本身没有任何导入者：无人从外部进入这套机制。
    module_names = sorted(
        rel.rsplit("/", 1)[-1][: -len(".py")] for rel in subsystem
    )
    importers = sorted(
        rel for rel, text in modules
        if rel not in subsystem
        and any(
            f".{name} import" in text or f"import {name}" in text
            for name in module_names
        )
    )
    assert importers == [], (
        f"持久音频子系统已有生产导入者 {importers}，「零接线」结论已过期，需重新核实"
    )


def test_a_take_cannot_be_teed_off_the_realtime_stream():
    """实时路径是流式的，而 publish_pcm 要求完整 PCM——所以这不是一行 tee。"""
    root = project_status.ROOT_DIR
    store = (root / "engine/infrastructure/audio_take_store.py").read_text(encoding="utf-8")
    assert "PCM take must contain complete signed-16 frames" in store, (
        "publish_pcm 不再要求完整帧：若实时流可整段 tee 落库，接线难度评估需重做"
    )
    bridge = (root / "engine/infrastructure/audio/media_bridge.py").read_text(encoding="utf-8")
    assert "re-chunks it while preserving sample continuity" in bridge, (
        "媒体桥不再是流式 re-chunk：流式落 take 的可行性需重新评估"
    )


def test_the_storybook_contract_carries_no_audio_surface():
    """PRD §20.2 要求「重用已生成音频」；契约里没有音频面，说明从未有过。"""
    schema = json.loads(
        (project_status.ROOT_DIR / "contracts/schemas/storybook.schema.json").read_text(
            encoding="utf-8"
        )
    )
    offenders = [
        key
        for key in schema.get("properties", {})
        if any(token in key.lower() for token in ("audio", "track", "take", "voice"))
    ]
    assert offenders == [], (
        f"storybook.schema.json 出现了音频字段 {offenders}："
        "若契约已承载音频，verified_unwired 的结论需重新核实"
    )


def test_the_unwired_subsystem_names_what_it_retracted_each_time():
    """三次误判同源。条目必须逐步记清每次撤回了什么，而不是只记最后一次。"""
    card = json.loads(
        (project_status.ROOT_DIR / "docs" / "PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    for item in card["verified_unwired"]:
        retracts = item["retracts"]
        assert "SB-24B" in retracts or "SB-24" in retracts, (
            f"{item['id']} 没记录它撤回了前一轮的哪一版判断"
        )
        for key in ("realtime_path_never_persists", "contract_has_no_audio_surface",
                    "not_superseded_dead_code"):
            assert item["evidence"].get(key), f"{item['id']} 缺证据条目 {key}"


def test_only_committed_facts_could_back_a_storybook_section():
    """ADR-008 §2 的判据：投影进故事书的东西必须有提交绑定，否则它不是「已发生」。"""
    root = project_status.ROOT_DIR
    migrations = root / "engine/infrastructure/migrations"
    read = lambda pattern: "".join(
        p.read_text(encoding="utf-8") for p in migrations.glob(pattern)
    )

    # 玩家建议表明确不是领域事实来源——用它投影第五段会违反不变量 4（Advice ≠ Command）。
    advice = read("009*.sql")
    assert "turn_advice_interpretations" in advice
    assert "never advances world_meta or creates Domain events" in advice, (
        "迁移 009 不再声明自己不产生领域事件：ADR-008 §2 的第一条判据需重核"
    )
    assert "committed_world_revision" not in advice, (
        "turn_advice_interpretations 获得了提交绑定：它已成为领域事实，"
        "ADR-008 §2 的候选源清单需重做"
    )

    # 而 Episode 结算的四组事件表确实带 deferred FK 到 domain_commits。
    settlement = read("011*.sql")
    for table in (
        "episode_character_events",
        "episode_relationship_events",
        "episode_knowledge_changes",
        "episode_world_events",
    ):
        start = settlement.find(f"CREATE TABLE {table}")
        assert start != -1, f"{table} 不在迁移 011 里，ADR-008 §2 的候选源清单需重核"
        body = settlement[start : start + 700]
        assert "committed_world_revision" in body and "domain_commits(revision)" in body, (
            f"{table} 不再带 committed_world_revision 外键，"
            "「已提交事实」与「叙事提议」的边界已移动"
        )

    # beat_plans 是编排产物：无提交绑定，故其 npc_intents 是意图不是事实。
    beats = read("012*.sql")
    assert "domain_commits" not in beats, (
        "beat_plans 获得了 domain_commits 绑定：npc_intents 的性质判断需重核"
    )


def test_the_fate_path_section_is_still_undecided():
    """ADR-008 是提案而非裁决：契约里必须还没有第五段。"""
    schema = json.loads(
        (project_status.ROOT_DIR / "contracts/schemas/storybook.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert not any(
        key in schema["properties"]
        for key in ("fate_path", "intervention_path", "destiny", "fate", "interventions")
    ), "第五段已进入契约：ADR-008 §8 的「未裁决前不加字段」已被越过，需核实是谁裁决的"

    card = json.loads(
        (project_status.ROOT_DIR / "docs/PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    fate = next(
        item for item in card["pending_decisions"] if item["id"] == "STORYBOOK-FATE-PATH"
    )
    assert fate["evidence"] == (
        "docs/01_总体架构/ADR-008_命运介入路径的语义与投影.md#8. 决策状态"
    ), "STORYBOOK-FATE-PATH 的出处未指向 ADR-008 §8：读者会找不到该看的提案"


# ADR-008 §4.4 方案 D 的成本此前写的是「未核实裁决器的输出形状」。§1.1 已把它
# 核实成结论，于是这些事实必须被钉住：任一条漂移都意味着 ADR 的成本估算失真，
# 而方案 D 正是待裁决人拿来比价的依据。
ADR008 = (
    project_status.ROOT_DIR
    / "docs/01_总体架构/ADR-008_命运介入路径的语义与投影.md"
)
MIGRATIONS_DIR = project_status.ROOT_DIR / "engine/infrastructure/migrations"


def test_the_action_intent_contract_is_the_shape_plan_d_needs():
    """ActionIntent 恰是 §4.4 描述的「谁、做了什么、依据哪个意图」——逐字段钉死。"""
    schema = json.loads(
        (
            project_status.ROOT_DIR / "contracts/schemas/action_intent.schema.json"
        ).read_text(encoding="utf-8")
    )
    declared = set(schema["required"]) | set(schema["properties"])
    for field in ("character_id", "actions", "intent", "adherence", "evidence_ids"):
        assert field in declared, (
            f"ActionIntent 不再声明 {field}：ADR-008 §1.1(2) 的「结构已在裁决器输入上」"
            "已不成立，方案 D 的成本估算需重核"
        )

    action = schema["properties"]["actions"]["items"]["properties"]
    for field in ("type", "purpose", "target_ids"):
        assert field in action, (
            f"ActionIntent.actions[] 不再带 {field}："
            "§1.1(2) 所述的「做了什么」已无法从裁决器输入复原"
        )


def test_the_resolver_output_carries_no_action_record():
    """StateDelta 里不能出现 actions / adherence：裁决器输出不含行动记录。"""
    schema = json.loads(
        (
            project_status.ROOT_DIR / "contracts/schemas/state_delta.schema.json"
        ).read_text(encoding="utf-8")
    )
    for key in ("actions", "adherence", "action_intent"):
        assert key not in schema["properties"], (
            f"StateDelta 新增了 {key}：ADR-008 §1.1(1)「裁决器输出不含行动条目」"
            "已过期——若是有意的，请先更新 §1.1 再合入"
        )

    resolver = (
        project_status.ROOT_DIR / "engine/domain/resolver.py"
    ).read_text(encoding="utf-8")
    assert "def resolve(" in resolver, "resolver.py 的裁决器入口已改名，§1.1 需重新核实"


def test_the_action_intent_body_is_still_not_persisted():
    """ActionIntent 本体仍未落库：只有 id 字符串，没有表也没有外键。

    这条断言是 ADR-008 §1.1(3) 的可执行形式。它一旦转红，说明方案 D 的第一步
    （落库）已经被人做了——那时必须先更新 §1.1 与 §4.4，而不是让 ADR 继续
    声称「未落库」。
    """
    migration_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )
    assert "action_intents" not in migration_text, (
        "已出现 action_intents 表：ADR-008 §1.1(3) 与 §4.4 的成本行已过期，"
        "方案 D 的落库前置已完成，需回写 ADR"
    )
    assert "action_intent_id TEXT REFERENCES" not in migration_text, (
        "turn_transactions.action_intent_id 已接上外键：§1.1(3) 已过期，需回写 ADR"
    )
    assert "action_intent_id TEXT" in migration_text, (
        "turn_transactions.action_intent_id 已被移除：§1.1(3) 的指针描述已过期，"
        "需回写 ADR"
    )


def test_adr_008_records_the_resolver_verification_it_relied_on():
    """§4.4 不得再把裁决器输出形状写成未核实——那正是待裁决人被误导的地方。"""
    text = ADR008.read_text(encoding="utf-8")
    assert "### 1.1 裁决器输出形状核实" in text, (
        "ADR-008 缺少 §1.1 裁决器输出形状核实：§4.4 声称已完成核实却无出处"
    )
    assert "本 ADR **未**核实裁决器的输出形状" not in text, (
        "ADR-008 §4.4 仍写着「未核实裁决器的输出形状」：与 §1.1 自相矛盾，"
        "读者会以为方案 D 的成本仍未知"
    )
    assert "**待裁决**" in text, "ADR-008 的决策状态已被改动：核实事实不等于裁决"


def test_the_action_intent_still_binds_to_the_protagonist_only():
    """§1.1(5).2：character_id 恒为主角。放宽它属契约破坏性变更，须先裁决。"""
    advice_action = (
        project_status.ROOT_DIR / "engine/application/advice_action.py"
    ).read_text(encoding="utf-8")
    assert '"character_id": scope.protagonist_id' in advice_action, (
        "ActionIntent 不再恒绑主角：ADR-008 §1.1(5).2 与 §4.4 的覆盖面前置已过期"
    )

    initialization = (
        project_status.ROOT_DIR / "engine/application/story_initialization.py"
    ).read_text(encoding="utf-8")
    assert "unsupported_scenario" in initialization, (
        "场景准入已放开：ADR-008 §1.1(5).3「生产可用场景只有 golden_001」已过期"
    )


# SB-25 撤回了「Story Book 回放缺音频只是 track 层没接线」的结论，却没同步到派发卡：
# 同一份 PROJECT_STATE.json 里 verified_unwired 写着「不再是发布时机与 redub 策略」，
# 派发卡仍写着「唯一需人裁的是发布时机与 redub 策略」。下一个接手者照卡派工，就会重蹈
# SB-22——把待裁决项当成可直接推进的任务。
def _dispatch_cards():
    card = json.loads(
        (project_status.ROOT_DIR / "docs/PROJECT_STATE.json").read_text(encoding="utf-8")
    )
    return card, {holder: card[holder]["dispatch"] for holder in ("critical_path", "execution_focus")}


def test_the_dispatch_card_never_contradicts_the_verified_findings():
    """派发卡一旦由待裁决项门控，就不能再声称这件事「不需要裁决」。"""
    card, cards = _dispatch_cards()
    pending_ids = {item["id"] for item in card["pending_decisions"]}
    unwired_ids = {item["id"] for item in card["verified_unwired"]}

    for holder, dispatch in cards.items():
        gated_by = dispatch.get("gated_by")
        assert gated_by, f"{holder}.dispatch 没有写 gated_by：接手者无从知道这件事被什么门控"
        assert set(gated_by), f"{holder}.dispatch 的 gated_by 是空的"

        unknown = sorted(set(gated_by) - pending_ids - unwired_ids)
        assert not unknown, f"{holder}.dispatch 的 gated_by 指向不存在的事项：{unknown}"

        # 宣布撤回的那一句必须能引述它撤回的原话，否则无法说明自己撤回了什么；
        # 但描述现状的句子若仍在断言那个结论，就是把误判留在了事实源里。
        # 判据因此落在句级：带更正/撤回标记的句子豁免，其余句子一律不许出现。
        RETRACTING = ("更正", "撤回", "上一版", "误判", "已被推翻", "自相矛盾")
        sentences = re.split(r"(?<=[。；])", dispatch["rationale"])
        asserted = "".join(
            sentence
            for sentence in sentences
            if not any(mark in sentence for mark in RETRACTING)
        )
        blob = json.dumps(
            {
                "task_title": dispatch["task_title"],
                "preconditions": dispatch["preconditions"],
                "rationale_asserting_sentences": asserted,
            },
            ensure_ascii=False,
        )
        for phrase in ("不需要架构裁决", "唯一需人裁的是发布时机", "可直接推进的接线工作"):
            assert phrase not in blob, (
                f"{holder}.dispatch 仍断言「{phrase}」：它已被 verified_unwired 的结论推翻。"
                "照这张卡派工会把待裁决项当成可直接推进的任务——这正是 SB-22 的失败形态。"
            )


def test_the_two_dispatch_cards_cannot_drift_apart():
    """两张派发卡内容重复过一次，其中一张被更正而另一张没被更正是 SB-28 的成因。"""
    _, cards = _dispatch_cards()
    critical, focus = cards["critical_path"], cards["execution_focus"]
    for field in ("task_id", "task_title", "rationale", "gated_by", "forbidden_actions"):
        assert critical[field] == focus[field], (
            f"两张派发卡的 {field} 不一致：单张被更正会让状态报告自我矛盾，"
            "必须同改两张"
        )


def test_the_take_layer_still_has_no_production_writer():
    """派发卡把这件事降级为裁决，前提是「take 确实没人写」这件事没变。

    一旦有人接上了写侧，`gated_by` 里 PERSISTENT-AUDIO-SUBSYSTEM 的第一问就已有答案，
    派发卡必须随之改写——否则它会继续声称「无从接线」。
    """
    root = project_status.ROOT_DIR
    modules = [
        path
        for path in (root / "engine").rglob("*.py")
        if "/tests/" not in f"/{path.relative_to(root).as_posix()}"
        and not path.relative_to(root).as_posix().startswith("engine/tests/")
    ]
    callers = sorted(
        path.relative_to(root).as_posix()
        for path in modules
        if "publish_pcm" in path.read_text(encoding="utf-8")
        and path.name != "audio_take_store.py"
    )
    assert callers == ["engine/infrastructure/audio_take_coordinator.py"], (
        f"publish_pcm 的调用方变了：{callers}；take 写侧不再只有 coordinator 一条链，"
        "PERSISTENT-AUDIO-SUBSYSTEM 的第一问已有答案，PROJECT_STATE 的派发卡需重写"
    )
