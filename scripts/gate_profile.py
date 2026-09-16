#!/usr/bin/env python3
"""
GateProfile - Protected Gate Policy Resolver & Executor (HACF 2.1)

门禁主权原则：任务胶囊只引用 gate_profile_id 与 profile_digest，
真实验收命令由受保护的 .hacf/gates/*.json 定义，并由 registry.json 记录摘要。

摘要链（任一环不匹配即拒绝执行）：
    capsule.gates.profile_digest  ==  registry.profiles[id].sha256  ==  sha256(profile file)

本地执行使用工作区内的 registry；CI 权威校验使用目标分支（受保护 main）的 registry，
因此 PR 内同时篡改 profile 与 registry 无法自证通过。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
GATES_DIR = REPO_ROOT / ".hacf" / "gates"
REGISTRY_PATH = GATES_DIR / "registry.json"

# pytest 在「未收集到任何测试」时的退出码
PYTEST_NO_TESTS_EXIT_CODE = 5

_PLACEHOLDER = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


class GateProfileError(RuntimeError):
    """门禁档案缺失、摘要不匹配或结构非法。"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    if not registry_path.exists():
        raise GateProfileError(f"gate registry not found: {registry_path}")
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateProfileError(f"gate registry is not valid JSON: {exc}") from exc
    if not isinstance(registry.get("profiles"), dict):
        raise GateProfileError("gate registry is missing the 'profiles' object")
    return registry


def resolve_profile(
    profile_id: str,
    registry_path: Optional[Path] = None,
    repo_root: Path = REPO_ROOT,
) -> Tuple[Dict[str, Any], Path, str]:
    """解析 profile，并校验「registry 记录摘要 == 实际文件摘要」。"""
    registry = load_registry(registry_path)
    entry = registry["profiles"].get(profile_id)
    if not entry:
        known = ", ".join(sorted(registry["profiles"]))
        raise GateProfileError(f"unknown gate profile '{profile_id}'. Known profiles: {known}")

    profile_path = repo_root / entry["file"]
    if not profile_path.exists():
        raise GateProfileError(f"gate profile file missing: {profile_path}")

    actual_digest = sha256_file(profile_path)
    recorded_digest = entry.get("sha256", "")
    if actual_digest != recorded_digest:
        raise GateProfileError(
            "gate profile digest mismatch (profile file has been modified without registry update)\n"
            f"  profile : {profile_path}\n"
            f"  expected: sha256:{recorded_digest}\n"
            f"  actual  : sha256:{actual_digest}\n"
            "  → 若确为受权变更，请由 AGT-ARB 执行 "
            "'python3 scripts/gate_profile.py refresh-registry' 并走架构评审。"
        )

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("gate_profile_id") != profile_id:
        raise GateProfileError(
            f"profile id mismatch: registry key '{profile_id}' vs file id "
            f"'{profile.get('gate_profile_id')}'"
        )
    if not isinstance(profile.get("stages"), list) or not profile["stages"]:
        raise GateProfileError(f"gate profile '{profile_id}' has no stages")
    return profile, profile_path, actual_digest


def expand_token(token: str, env: Dict[str, str]) -> str:
    """展开 ${VAR} / ${VAR:-default} 占位符，避免在受保护档案中固化本机绝对路径。"""

    def _replace(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        if name in env and env[name]:
            return env[name]
        if default is not None:
            return default
        raise GateProfileError(f"environment variable '{name}' is required by a gate stage")

    return _PLACEHOLDER.sub(_replace, token)


def load_workspace_lease_defaults(cwd: Path) -> Dict[str, str]:
    """从 <cwd>/.hacf/workspace.json 读取资源命名空间（不存在则返回空）。"""
    lease_path = cwd / ".hacf" / "workspace.json"
    if not lease_path.exists():
        return {}
    try:
        lease = json.loads(lease_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        "TMPDIR": lease.get("tmpdir", ""),
        "WOM_SPM_SCRATCH": lease.get("spm_scratch", ""),
        "WOM_TEST_DB_DIR": lease.get("test_db_dir", ""),
        "WOM_IPC_SOCKET": lease.get("ipc_socket", ""),
        "WOM_PORT_RANGE": lease.get("port_range", ""),
        "WOM_LOG_DIR": lease.get("log_dir", ""),
    }


def collect_toolchain(repo_root: Path = REPO_ROOT) -> Dict[str, str]:
    """记录验收时的工具链身份（用于 receipt，不用于门禁判定）。"""
    toolchain: Dict[str, str] = {"python": sys.version.split()[0]}
    for name, argv in (("uv", ["uv", "--version"]), ("swift", ["swift", "--version"])):
        if not shutil.which(argv[0]):
            continue
        try:
            res = subprocess.run(argv, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                toolchain[name] = res.stdout.strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            continue

    lock_file = repo_root / "engine" / "uv.lock"
    if lock_file.exists():
        toolchain["engine_uv_lock_digest"] = f"sha256:{sha256_file(lock_file)}"
    return toolchain


def run_profile(
    profile_id: str,
    cwd: Path,
    log_dir: Optional[Path] = None,
    registry_path: Optional[Path] = None,
    repo_root: Path = REPO_ROOT,
    env_overrides: Optional[Dict[str, str]] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """执行受保护门禁档案，返回可写入 receipt 的结构化结果。"""
    profile, profile_path, profile_digest = resolve_profile(
        profile_id, registry_path=registry_path, repo_root=repo_root
    )
    env = dict(os.environ)
    if env_overrides:
        env.update({k: v for k, v in env_overrides.items() if v})

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    started_at = _now()
    stage_results: List[Dict[str, Any]] = []
    gaps: List[str] = []

    for index, stage in enumerate(profile["stages"], start=1):
        stage_name = stage.get("name") or f"stage {index}"
        stage_cwd = (cwd / stage.get("cwd", ".")).resolve()
        argv = [expand_token(token, env) for token in stage["command"]]
        policy = stage.get("empty_selection_policy", "fail")

        # 覆盖资产判定以「被测工作区」为准，策略档案则以受保护根为准（门禁主权原则）
        missing = [
            expected
            for expected in stage.get("expects", [])
            if not (cwd / expected).exists() and not (repo_root / expected).exists()
        ]
        if missing:
            gaps.append(f"[{profile_id}/stage{index}] 期望资产缺失: {', '.join(missing)}")

        if not quiet:
            print(f"\n▶ [{profile_id}] Stage {index}: {stage_name}")
            print(f"   cwd: {stage_cwd}")
            print(f"   cmd: {' '.join(argv)}")
        if missing and not quiet:
            print(f"   ⚠️  覆盖缺口: {', '.join(missing)}")

        stage_started = _now()
        if not stage_cwd.exists():
            stage_results.append(
                {
                    "stage": index,
                    "name": stage_name,
                    "command": argv,
                    "cwd": str(stage_cwd),
                    "exit_code": None,
                    "status": "failed",
                    "started_at": stage_started,
                    "finished_at": _now(),
                    "note": f"工作目录不存在: {stage_cwd}",
                }
            )
            continue

        res = subprocess.run(argv, cwd=stage_cwd, capture_output=True, text=True, env=env)
        raw_output = f"$ {' '.join(argv)}\n[exit_code={res.returncode}]\n--- stdout ---\n{res.stdout}\n--- stderr ---\n{res.stderr}"

        status = "passed"
        note = ""
        if res.returncode == PYTEST_NO_TESTS_EXIT_CODE and "pytest" in argv[0:3]:
            if policy == "warn":
                status = "passed_with_gap"
                note = "未收集到任何测试：该用例面尚未落地，缺口已计入 receipt。"
            else:
                status = "failed"
                note = "未收集到任何测试，且该门禁不允许空选择。"
        elif res.returncode != 0:
            status = "failed"

        if status == "failed":
            gaps.append(f"[{profile_id}/stage{index}] {stage_name} 未通过 (exit={res.returncode})")
        elif status == "passed_with_gap":
            gaps.append(f"[{profile_id}/stage{index}] {note}")

        log_digest = None
        if log_dir:
            log_file = log_dir / f"stage{index}-{profile_id.lower()}.log"
            log_file.write_text(raw_output, encoding="utf-8")
            log_digest = f"sha256:{sha256_bytes(raw_output.encode('utf-8'))}"

        if not quiet:
            icon = {"passed": "✅", "passed_with_gap": "⚠️ ", "failed": "❌"}[status]
            print(f"   {icon} {status} (exit={res.returncode})")
            if note:
                print(f"   note: {note}")
            if status == "failed":
                tail = (res.stdout + res.stderr).strip().splitlines()[-25:]
                for line in tail:
                    print(f"   │ {line}")

        stage_results.append(
            {
                "stage": index,
                "name": stage_name,
                "command": argv,
                "cwd": str(stage_cwd),
                "exit_code": res.returncode,
                "status": status,
                "started_at": stage_started,
                "finished_at": _now(),
                "raw_log_digest": log_digest,
                "note": note,
            }
        )

    overall = "passed" if all(s["status"] != "failed" for s in stage_results) else "failed"
    return {
        "gate_profile_id": profile_id,
        "gate_profile_file": str(profile_path.relative_to(repo_root)),
        "gate_profile_digest": f"sha256:{profile_digest}",
        "risk_class": profile.get("risk_class", "medium"),
        "started_at": started_at,
        "finished_at": _now(),
        "result": overall,
        "workspace_root": str(cwd),
        "stages": stage_results,
        "coverage_gaps": gaps,
    }


def refresh_registry(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """按当前 .hacf/gates/*.json 重算 registry 摘要（仅 AGT-ARB 受权执行）。"""
    gates_dir = repo_root / ".hacf" / "gates"
    profiles: Dict[str, Any] = {}
    for profile_file in sorted(gates_dir.glob("*.json")):
        if profile_file.name == "registry.json":
            continue
        data = json.loads(profile_file.read_text(encoding="utf-8"))
        profile_id = data["gate_profile_id"]
        profiles[profile_id] = {
            "file": str(profile_file.relative_to(repo_root)),
            "sha256": sha256_file(profile_file),
            "risk_class": data.get("risk_class", "medium"),
            "description": data.get("description", ""),
        }
    registry = {
        "$comment": (
            "受保护门禁档案摘要表。本文件定义于受保护 main 分支；"
            "CI 以目标分支版本为权威校验 PR 内的 profile 文件。"
        ),
        "registry_version": 1,
        "generated_at": _now(),
        "profiles": profiles,
    }
    (gates_dir / "registry.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return registry


def verify_registry(repo_root: Path = REPO_ROOT) -> bool:
    registry = load_registry(repo_root / ".hacf" / "gates" / "registry.json")
    ok = True
    for profile_id in sorted(registry["profiles"]):
        try:
            resolve_profile(profile_id, repo_root=repo_root)
            print(f"✅ {profile_id}")
        except GateProfileError as exc:
            ok = False
            print(f"❌ {profile_id}: {exc}")
    return ok


# 变更集 → 门禁档案路由：命中单一角色域则只跑该域门禁，跨域或未知则回退全量。
# 目的：让协同流程按改动面付时间成本，而不是每轮都跑全量三阶段。
PROFILE_ROUTING: List[Tuple[str, str]] = [
    ("macos-app/", "MACOS_APP_P0"),
    ("engine/ai/", "AI_GATEWAY_P0"),
    ("engine/infrastructure/", "DATA_KERNEL_P0"),
    ("engine/domain/", "DOMAIN_P0"),
    ("engine/tests/", "DOMAIN_P0"),
    ("contracts/", "DOMAIN_P0"),
]
FALLBACK_PROFILE = "FULL_P0"

# 治理与工具链路径：改动面小但影响全局，一律走全量门禁，不接受"看起来只碰了一个文件"的降档。
GOVERNANCE_PREFIXES: Tuple[str, ...] = (
    "scripts/",
    ".github/",
    ".hacf/",
    "contracts/",
    "engine/uv.lock",
    "engine/pyproject.toml",
    "macos-app/Package.swift",
)


def _is_meta_path(path: str) -> bool:
    """元数据路径：不触发领域测试。受保护门禁档案（.hacf/gates/**）不算元数据。"""
    if path in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", ".gitignore"):
        return True
    if path.endswith(".md") or path.startswith(("docs/", ".agents/")):
        return True
    return path == ".hacf/required-checks.json"


def _stage_count(profile_id: str) -> int:
    try:
        entry = load_registry()["profiles"][profile_id]
        profile = json.loads((REPO_ROOT / entry["file"]).read_text(encoding="utf-8"))
        return len(profile.get("stages", []))
    except Exception:  # noqa: BLE001 - 路由尽力而为，异常即视为最重
        return 99


def route_profile(files: List[str]) -> Tuple[str, str]:
    """返回 (profile_id, 选档理由)。只做路由建议，不执行门禁。"""
    known = load_registry()["profiles"]
    code_files = [f for f in files if not _is_meta_path(f)]

    if not code_files:
        lightest = min(known, key=_stage_count)
        return (
            lightest,
            f"纯元数据变更（{len(files)} 个文件）：选用阶段最少的档案"
            f"（{_stage_count(lightest)} 阶段，仅做架构适应度级校验）",
        )

    if any(f.startswith(GOVERNANCE_PREFIXES) for f in code_files):
        return FALLBACK_PROFILE, "触及治理/工具链路径：一律全量门禁"

    hits = set()
    for path in code_files:
        for prefix, profile_id in PROFILE_ROUTING:
            if path.startswith(prefix):
                hits.add(profile_id)
                break

    if len(hits) == 1:
        candidate = next(iter(hits))
        if candidate in known:
            return candidate, f"命中单一角色域：{', '.join(sorted(code_files)[:3])} …"
        return FALLBACK_PROFILE, f"路由目标 '{candidate}' 不在 registry：回退全量门禁"
    if not hits:
        return FALLBACK_PROFILE, "未命中任何路由规则：回退全量门禁（宁可多跑不可漏跑）"
    return (
        FALLBACK_PROFILE,
        f"跨 {len(hits)} 个角色域（{', '.join(sorted(hits))}）：回退全量门禁",
    )


def cmd_resolve(args: argparse.Namespace) -> int:
    if args.changed_files:
        files = [f.strip() for f in args.changed_files.split(",") if f.strip()]
    else:
        res = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "diff",
                "--name-only",
                f"{args.base_ref}...{args.head_ref}",
            ],
            cwd=Path(args.cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        files = [line.strip() for line in res.stdout.splitlines() if line.strip()]

    profile_id, reason = route_profile(files)
    print(f"📋 变更文件 {len(files)} 个")
    print(f" 建议门禁档案: {profile_id}")
    print(f"   理由: {reason}")
    print(f"\n   执行: python3 scripts/gate_profile.py run --profile {profile_id}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {"profile": profile_id, "reason": reason, "changed_files": files},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd).resolve()
    env_overrides: Dict[str, str] = {}
    if args.use_workspace_lease:
        env_overrides.update(load_workspace_lease_defaults(cwd))
    if args.spm_scratch:
        env_overrides["WOM_SPM_SCRATCH"] = args.spm_scratch
    if args.tmpdir:
        env_overrides["TMPDIR"] = args.tmpdir

    result = run_profile(
        args.profile,
        cwd=cwd,
        log_dir=Path(args.log_dir).resolve() if args.log_dir else None,
        env_overrides=env_overrides,
    )
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print("\n" + "=" * 66)
    if result["result"] == "passed":
        print(f"🎉 [{args.profile}] GATES PASSED")
    else:
        print(f"❌ [{args.profile}] GATES FAILED")
    for gap in result["coverage_gaps"]:
        print(f"   ⚠️  {gap}")
    print("=" * 66)
    return 0 if result["result"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="HACF 2.1 Gate Profile resolver & executor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行受保护门禁档案")
    run_parser.add_argument("--profile", required=True, help="gate_profile_id，如 FULL_P0")
    run_parser.add_argument("--cwd", default=str(REPO_ROOT), help="执行工作区根目录")
    run_parser.add_argument("--log-dir", help="原始日志落盘目录（仅本地留存，不入库）")
    run_parser.add_argument("--json-out", help="可选：结构化结果输出路径")
    run_parser.add_argument("--spm-scratch", help="覆盖 SPM scratch path（资源命名空间）")
    run_parser.add_argument("--tmpdir", help="覆盖 TMPDIR（资源命名空间）")
    run_parser.add_argument(
        "--use-workspace-lease",
        action="store_true",
        help="读取 <cwd>/.hacf/workspace.json 作为资源命名空间（worktree 场景）",
    )

    show_parser = subparsers.add_parser("show", help="展示门禁档案与摘要")
    show_parser.add_argument("--profile", required=True)

    resolve_parser = subparsers.add_parser(
        "resolve", help="按变更集路由到最省时的门禁档案（不改状态）"
    )
    resolve_parser.add_argument("--base-ref", default="origin/main")
    resolve_parser.add_argument("--head-ref", default="HEAD")
    resolve_parser.add_argument("--changed-files", help="逗号分隔；默认由 git diff 计算")
    resolve_parser.add_argument("--cwd", default=str(REPO_ROOT))
    resolve_parser.add_argument("--json-out", help="可选：结构化结果输出路径")

    subparsers.add_parser("check", help="校验 registry 与 profile 文件摘要一致性")
    subparsers.add_parser("refresh-registry", help="重算 registry 摘要（受权变更专用）")

    args = parser.parse_args()

    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "resolve":
            return cmd_resolve(args)
        if args.command == "show":
            profile, path, digest = resolve_profile(args.profile)
            print(f"🏷️  {profile['gate_profile_id']}  (risk_class: {profile.get('risk_class')})")
            print(f"   {profile.get('description', '')}")
            print(f"   file: {path.relative_to(REPO_ROOT)}")
            print(f"   digest: sha256:{digest}")
            for stage in profile["stages"]:
                print(f"   • Stage {stage['stage']}: {stage['name']} [{stage.get('cwd', '.')}]")
                print(f"     $ {' '.join(stage['command'])}")
            return 0
        if args.command == "check":
            return 0 if verify_registry() else 1
        if args.command == "refresh-registry":
            registry = refresh_registry()
            print(f"🔐 registry refreshed with {len(registry['profiles'])} profiles.")
            return 0
    except GateProfileError as exc:
        print(f"❌ {exc}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
