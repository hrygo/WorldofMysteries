#!/usr/bin/env python3
"""
CollabPipeline CLI (HACF 2.1) — Transactional Parallel Worktrees

与 HACF 2.0 的关键差异：
1. 每个 Worktree 拥有独立 `engine/.venv`（`uv sync --locked`），只共享 uv 全局缓存；
   不再软链主仓 venv —— 避免 editable `.pth` 被其他工作区重写而互相污染。
2. Worktree 提供「资源命名空间租约」(.hacf/workspace.json)：TMPDIR / SPM scratch /
   测试库目录 / IPC socket / 日志目录 / 端口段，运行时隔离与源码隔离分离。
3. 合入前记录 expected_main_sha，并在真正合入前做 compare-and-swap 复核，
   合入后执行 post-merge smoke，最后签发 Integration Receipt。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_profile  # noqa: E402
import hacf_policy as policy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKTREE_BASE = REPO_ROOT.parent / "wom-worktrees"
INTEGRATION_PROFILE = "FULL_P0"


def run_cmd(cmd: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if check and res.returncode != 0:
        raise RuntimeError(
            f"Command failed [{res.returncode}]: {cmd}\nStderr: {res.stderr}\nStdout: {res.stdout}"
        )
    return res


def get_worktree_dir(branch: str) -> Path:
    return WORKTREE_BASE / branch.replace("/", "-").replace(":", "-")


def _lease_for(branch: str, worktree: Path) -> Dict[str, str]:
    """按分支名确定性分配资源命名空间，避免多工作区抢占同一端口段/临时目录。"""
    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()
    port_base = 51000 + (int(digest[:4], 16) % 400) * 10
    runtime = worktree / ".hacf"
    return {
        "workspace_id": f"WS-{digest[:8]}",
        "branch": branch,
        "worktree_path": str(worktree),
        "tmpdir": str(runtime / "tmp"),
        "spm_scratch": str(runtime / "spm-scratch"),
        "test_db_dir": str(runtime / "testdb"),
        "ipc_socket": str(runtime / "run" / "engine.sock"),
        "log_dir": str(runtime / "logs"),
        "port_range": f"{port_base}-{port_base + 9}",
        "created_at": policy.now_iso(),
        "note": "Git Worktree 提供源码隔离；本租约提供运行时资源隔离，两者缺一不可。",
    }


def _provision_workspace(branch: str, worktree: Path, skip_venv: bool) -> None:
    lease = _lease_for(branch, worktree)
    for key in ("tmpdir", "spm_scratch", "test_db_dir", "log_dir"):
        Path(lease[key]).mkdir(parents=True, exist_ok=True)
    Path(lease["ipc_socket"]).parent.mkdir(parents=True, exist_ok=True)
    lease_path = worktree / ".hacf" / "workspace.json"
    lease_path.write_text(json.dumps(lease, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("🧾 Workspace lease written (资源命名空间隔离):")
    print(f"   TMPDIR      : {lease['tmpdir']}")
    print(f"   SPM scratch : {lease['spm_scratch']}")
    print(f"   test DB dir : {lease['test_db_dir']}")
    print(f"   IPC socket  : {lease['ipc_socket']}")
    print(f"   port range  : {lease['port_range']}")

    if skip_venv:
        print("️  --skip-venv：跳过独立虚拟环境创建（仅限不执行 Python 门禁的场景）。")
        return

    target_venv = worktree / "engine" / ".venv"
    if target_venv.is_symlink():
        # HACF 2.0 遗留：软链主仓 venv 会让 editable .pth 被跨工作区重写。仅删除链接本身。
        target_venv.unlink()
        print("🧹 移除 HACF 2.0 遗留的 engine/.venv 软链接（仅删除链接，不影响主仓环境）。")

    if not shutil.which("uv"):
        print("⚠️  未找到 uv：跳过独立环境创建，门禁阶段可能失败。")
        return

    # 必须同步 dev extra：否则 `uv run pytest` 会回退到全局 uv tool 的 pytest，
    # 绕过项目配置（pythonpath/asyncio_mode）并在收集阶段失败。
    print("️  创建本工作区独立 Python 环境：uv sync --locked --extra dev（共享 uv 全局缓存）")
    res = subprocess.run(
        ["uv", "sync", "--locked", "--extra", "dev"],
        cwd=worktree / "engine",
        text=True,
        capture_output=True,
    )
    if res.returncode != 0:
        print("❌ uv sync --locked 失败：")
        print((res.stdout + res.stderr).strip()[-2000:])
        raise RuntimeError("per-worktree venv provisioning failed")
    print("✅ 独立环境就绪（uv.lock 锁定，跨工作区互不影响）。")


def start_pipeline(
    branch: str,
    role: Optional[str] = None,
    task_id: Optional[str] = None,
    title: Optional[str] = None,
    skip_venv: bool = False,
) -> None:
    target_dir = get_worktree_dir(branch)
    if target_dir.exists():
        print(f" Worktree directory already exists: {target_dir}")
        print("   Use 'integrate' to merge, or 'abort' to discard.")
        sys.exit(1)

    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
    print(f"🌿 [CollabPipeline] Creating isolated worktree for '{branch}' at: {target_dir}")

    res = run_cmd(f"git rev-parse --verify {branch}", check=False)
    if res.returncode == 0:
        run_cmd(f"git worktree add \"{target_dir}\" \"{branch}\"")
    else:
        run_cmd(f"git worktree add -b \"{branch}\" \"{target_dir}\" main")

    _provision_workspace(branch, target_dir, skip_venv)

    if role and task_id:
        title_str = title or f"Implement {task_id}"
        capsule_cmd = (
            f"python3 scripts/agent_capsule.py pack --role {role} "
            f"--task-id {task_id} --title \"{title_str}\""
        )
        run_cmd(capsule_cmd, cwd=target_dir)
        print(f"📦 Auto-packed Task Capsule in worktree for role: {role}")

    print(f"\n🎉 Parallel workspace ready!\n👉 Navigate to: cd {target_dir}")
    print("   ️  门禁执行请使用：bash scripts/gate_runner.sh（在该工作区内运行）")


def _resolve_task_id(worktree: Path, explicit: Optional[str]) -> Optional[str]:
    """凭单归属推断：优先匹配分支名的胶囊；多个候选时拒绝静默猜测。"""
    if explicit:
        return explicit
    capsules = sorted((worktree / ".agents" / "capsules").glob("*.json"))
    if not capsules:
        return None
    if len(capsules) == 1:
        return capsules[0].stem

    branch = policy.run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree).lower()
    normalized = branch.replace("/", "-").replace("_", "-")
    matched = [c for c in capsules if c.stem.lower().replace("_", "-") in normalized]
    if len(matched) == 1:
        return matched[0].stem
    print(
        "⚠️  工作区存在多个任务胶囊且无法唯一归属本次集成："
        f"{[c.stem for c in capsules]}；请在 integrate 时显式指定 --task-id。"
    )
    return None


def _changed_paths(worktree: Path, head_before: str) -> list[str]:
    res = run_cmd(f"git -c core.quotepath=false diff --name-only {head_before} HEAD", cwd=worktree, check=False)
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def integrate_pipeline(
    branch: str,
    auto_clean: bool = False,
    task_id: Optional[str] = None,
    skip_smoke: bool = False,
) -> None:
    """门禁 → CAS 合入 → post-merge smoke → Integration Receipt。"""
    target_dir = get_worktree_dir(branch)
    if not target_dir.exists():
        print(f"❌ Worktree not found at: {target_dir}")
        sys.exit(1)

    print(f"🛡️  [CollabPipeline] pre-merge integration for '{branch}'")

    status_res = run_cmd("git -c core.quotepath=false status --porcelain", cwd=target_dir)
    dirty_lines = [
        line
        for line in status_res.stdout.splitlines()
        if not any(token in line for token in [".agents/capsules/", ".agents/receipts/", ".hacf/"])
    ]
    if dirty_lines:
        print("❌ Uncommitted changes detected in worktree. Please commit or stash first:")
        for line in dirty_lines:
            print(f"   {line}")
        sys.exit(1)

    head_commit = policy.run_git(["rev-parse", "HEAD"], cwd=target_dir)
    expected_main_sha = policy.run_git(["rev-parse", "main"], cwd=REPO_ROOT)
    resolved_task_id = _resolve_task_id(target_dir, task_id) or "UNBOUND-TASK"

    # 1. 受保护门禁（在工作区内对即将合入的树执行）
    print(f"\n--- [Protected Gate Profile: {INTEGRATION_PROFILE}] ---")
    log_dir = policy.log_dir_for(target_dir, resolved_task_id, head_commit)
    lease = policy.load_workspace_lease(target_dir)
    # 门禁主权：策略档案取自受保护 main（REPO_ROOT），命令在被测工作区（target_dir）执行
    gate_result = gate_profile.run_profile(
        INTEGRATION_PROFILE,
        cwd=target_dir,
        log_dir=log_dir,
        repo_root=REPO_ROOT,
        env_overrides=policy.env_overrides_from_lease(lease),
    )
    if gate_result["result"] != "passed":
        print("\n❌ Gate verification FAILED — 拒绝合入，main 未被触碰。")
        sys.exit(1)
    print("\n✅ All protected gates PASSED in the worktree.")

    # 2. Compare-and-swap：合入前复核目标分支未前进
    main_sha_now = policy.run_git(["rev-parse", "main"], cwd=REPO_ROOT)
    if main_sha_now != expected_main_sha:
        print(
            "⚠️  [CAS REJECTED] main 已从 "
            f"{expected_main_sha[:12]} 前进到 {main_sha_now[:12]}；"
            "请在最新 main 上 rebase 后重新 integrate（门禁必须对新组合重跑）。"
        )
        sys.exit(1)

    # 3. 原子合入（仅快进）
    print(f"🔀 Merging '{branch}' into main (fast-forward only)…")
    run_cmd("git checkout main", cwd=REPO_ROOT)
    merge_res = run_cmd(f"git merge --ff-only {branch}", cwd=REPO_ROOT, check=False)
    if merge_res.returncode != 0:
        print("⚠️ Fast-forward merge failed:")
        print(merge_res.stderr.strip())
        sys.exit(1)
    merged_sha = policy.run_git(["rev-parse", "HEAD"], cwd=REPO_ROOT)
    print(f"🎉 main 现已推进到 {merged_sha[:12]}")

    # 4. Post-merge smoke：对合入后的真实 main 重新执行门禁
    smoke_result: Dict[str, Any] = {"result": "skipped", "coverage_gaps": ["post-merge smoke 被显式跳过"]}
    if not skip_smoke:
        print("\n--- [Post-Merge Smoke on main] ---")
        smoke_result = gate_profile.run_profile(
            INTEGRATION_PROFILE,
            cwd=REPO_ROOT,
            log_dir=policy.log_dir_for(REPO_ROOT, resolved_task_id, merged_sha),
            repo_root=REPO_ROOT,
        )
        print(f"post-merge smoke: {smoke_result['result']}")

    # 5. Integration Receipt（唯一可授权合入的凭证）
    capsule_path = target_dir / ".agents" / "capsules" / f"{resolved_task_id}.json"
    capsule: Dict[str, Any] = {}
    capsule_digest_value = ""
    if capsule_path.exists():
        capsule = policy.load_capsule(capsule_path)
        capsule_digest_value = policy.capsule_digest(capsule_path)
    else:
        capsule = {
            "capsule_id": f"CAP-{resolved_task_id}",
            "task_id": resolved_task_id,
            "assigned_role": "UNBOUND",
            "risk_class": "high",
        }

    smoke_ok = smoke_result["result"] in ("passed", "skipped")
    receipt = policy.build_receipt(
        receipt_type="integration",
        capsule=capsule,
        capsule_digest_value=capsule_digest_value or policy.canonical_json_digest(capsule),
        gate_result=gate_result,
        scope_audit={
            "changed_files": _changed_paths(target_dir, expected_main_sha),
            "violations": [],
            "escalations": [],
            "privileged_uses": [],
        },
        base_commit=expected_main_sha,
        head_commit=merged_sha,
        target_ref="main",
        target_sha=merged_sha,
        stale_context=False,
        toolchain=gate_profile.collect_toolchain(REPO_ROOT),
        started_at=gate_result.get("started_at", policy.now_iso()),
        verdict="passed" if smoke_ok else "failed",
        merge_authorizing=smoke_ok,
        merge={
            "strategy": "fast-forward",
            "expected_main_sha": expected_main_sha,
            "merged_sha": merged_sha,
            "cas_verified": True,
            "post_merge_smoke": smoke_result["result"],
        },
        notes=(
            []
            if smoke_ok
            else ["post-merge smoke 未通过：main 已推进，需立即由 AGT-ARB 处置（回滚或前滚修复）。"]
        ),
    )
    if smoke_result["result"] == "passed":
        receipt["coverage_gaps"] = list(receipt["coverage_gaps"]) + smoke_result["coverage_gaps"]
    receipt_path = policy.write_receipt(REPO_ROOT, receipt, merged_sha)
    print()
    policy.print_receipt_summary(receipt, receipt_path)
    if not smoke_ok:
        print("❌ post-merge smoke 失败：请勿继续后续任务，先修复 main。")
        sys.exit(1)

    if auto_clean:
        print(f"\n🧹 [Auto-Clean] Removing worktree at: {target_dir}")
        target_venv = target_dir / "engine" / ".venv"
        if target_venv.is_symlink():
            target_venv.unlink()
        run_cmd(f"git worktree remove --force \"{target_dir}\"", cwd=REPO_ROOT)
        run_cmd(f"git branch -D {branch}", cwd=REPO_ROOT, check=False)
        print("✅ Worktree（含独立 .venv 与资源租约目录）与分支已清理。")


def abort_pipeline(branch: str) -> None:
    target_dir = get_worktree_dir(branch)
    if not target_dir.exists():
        print(f"Worktree not found: {target_dir}")
        return
    print(f" Removing worktree at: {target_dir}")
    run_cmd(f"git worktree remove --force \"{target_dir}\"", cwd=REPO_ROOT)
    run_cmd(f"git branch -D {branch}", cwd=REPO_ROOT, check=False)
    print(f"✅ Aborted and cleaned worktree for branch '{branch}'.")


def list_worktrees() -> None:
    print("📋 Current active worktrees:")
    run_cmd("git worktree list", cwd=REPO_ROOT)
    for candidate in sorted(WORKTREE_BASE.glob("*/")):
        lease_path = candidate / ".hacf" / "workspace.json"
        if lease_path.exists():
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            print(
                f"   • {lease['branch']:<32} ports={lease['port_range']} "
                f"tmpdir={Path(lease['tmpdir']).name}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="CollabPipeline (HACF 2.1)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_start = subparsers.add_parser("start", help="开启隔离工作区事务")
    p_start.add_argument("--branch", required=True)
    p_start.add_argument("--role")
    p_start.add_argument("--task-id")
    p_start.add_argument("--title")
    p_start.add_argument("--skip-venv", action="store_true", help="跳过独立 venv 创建（不推荐）")

    p_integrate = subparsers.add_parser("integrate", help="门禁 + CAS 合入 + 集成凭单")
    p_integrate.add_argument("--branch", required=True)
    p_integrate.add_argument("--task-id", help="凭单归属任务；默认从工作区内胶囊推断")
    p_integrate.add_argument("--auto-clean", action="store_true")
    p_integrate.add_argument("--no-smoke", action="store_true", help="跳过 post-merge smoke（不推荐）")

    p_abort = subparsers.add_parser("abort", help="放弃并清理工作区")
    p_abort.add_argument("--branch", required=True)

    subparsers.add_parser("status", help="列出活跃工作区与资源租约")

    args = parser.parse_args()
    try:
        if args.command == "start":
            start_pipeline(args.branch, args.role, args.task_id, args.title, args.skip_venv)
        elif args.command == "integrate":
            integrate_pipeline(args.branch, args.auto_clean, args.task_id, args.no_smoke)
        elif args.command == "abort":
            abort_pipeline(args.branch)
        elif args.command == "status":
            list_worktrees()
    except (RuntimeError, policy.PolicyError, gate_profile.GateProfileError) as exc:
        print(f"❌ {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
