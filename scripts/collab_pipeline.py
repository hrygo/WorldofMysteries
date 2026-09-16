#!/usr/bin/env python3
"""
CollabPipeline CLI - Transactional Git Worktree Pipeline for Parallel Agent Collaboration.
Automates branch isolation, shared virtualenv symlinking, 3-stage pre-merge gating, and atomic fast-forward integration.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKTREE_BASE = REPO_ROOT.parent / "wom-worktrees"


def run_cmd(cmd: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess:
    """Run shell command with clear output."""
    res = subprocess.run(cmd, shell=True, cwd=cwd, text=True, capture_output=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed [{res.returncode}]: {cmd}\nStderr: {res.stderr}\nStdout: {res.stdout}")
    return res


def get_worktree_dir(branch: str) -> Path:
    sanitized = branch.replace("/", "-").replace(":", "-")
    return WORKTREE_BASE / sanitized


def start_pipeline(branch: str, role: str = None, task_id: str = None, title: str = None):
    """Start an isolated parallel development transaction."""
    target_dir = get_worktree_dir(branch)
    if target_dir.exists():
        print(f"❌ Worktree directory already exists: {target_dir}")
        print("   Use 'integrate' to merge, or 'abort' to discard.")
        sys.exit(1)

    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
    print(f"🌿 [CollabPipeline] Creating isolated worktree for '{branch}' at: {target_dir}")

    # Check if branch exists
    res = run_cmd(f"git rev-parse --verify {branch}", check=False)
    if res.returncode == 0:
        run_cmd(f"git worktree add \"{target_dir}\" \"{branch}\"")
    else:
        run_cmd(f"git worktree add -b \"{branch}\" \"{target_dir}\" main")

    # Symlink Python .venv to save disk & setup time
    main_venv = REPO_ROOT / "engine" / ".venv"
    target_venv = target_dir / "engine" / ".venv"
    if main_venv.exists() and not target_venv.exists():
        target_venv.symlink_to(main_venv)
        print("⚡ Symlinked engine/.venv for instant zero-overhead Python runtime.")

    # Optional: auto-pack task capsule
    if role and task_id:
        title_str = title or f"Implement {task_id}"
        capsule_cmd = f"python3 scripts/agent_capsule.py pack --role {role} --task-id {task_id} --title \"{title_str}\""
        run_cmd(capsule_cmd, cwd=target_dir)
        print(f"📦 Auto-packed initial Task Capsule in worktree for role: {role}")

    print(f"\n🎉 Parallel workspace ready!\n👉 Navigate to: cd {target_dir}")


def integrate_pipeline(branch: str, auto_clean: bool = False):
    """Verify gates, rebase, merge fast-forward into main, and self-heal clean."""
    target_dir = get_worktree_dir(branch)
    if not target_dir.exists():
        print(f"❌ Worktree not found at: {target_dir}")
        sys.exit(1)

    print(f"🛡️  [CollabPipeline] Initiating pre-merge integration verification for '{branch}'...")

    # 1. Check for uncommitted changes in worktree
    status_res = run_cmd("git status --porcelain", cwd=target_dir)
    if status_res.stdout.strip():
        print("❌ Uncommitted changes detected in worktree. Please commit or stash first:")
        print(status_res.stdout)
        sys.exit(1)

    # 2. Run 3-stage gate runner inside the worktree
    print("\n--- [Stage Gate Verification in Worktree] ---")
    gate_res = subprocess.run("bash scripts/gate_runner.sh", shell=True, cwd=target_dir)
    if gate_res.returncode != 0:
        print("\n❌ 3-Stage Gate verification FAILED! Aborting merge to protect main branch.")
        sys.exit(1)

    print("\n✅ All gates PASSED in worktree environment!")

    # 3. Fast-forward merge into main
    print(f"🔀 Merging '{branch}' into main (Fast-Forward only)...")
    run_cmd("git checkout main", cwd=REPO_ROOT)
    merge_res = run_cmd(f"git merge --ff-only {branch}", cwd=REPO_ROOT, check=False)
    if merge_res.returncode != 0:
        print("⚠️ Fast-forward merge failed. Rebase required:")
        print(f"   In worktree ({target_dir}): git fetch origin && git rebase main")
        sys.exit(1)

    print(f"🎉 Successfully merged '{branch}' into main!")

    # 4. Cleanup if requested
    if auto_clean:
        print(f"🧹 [Auto-Clean] Removing worktree at: {target_dir}")
        run_cmd(f"git worktree remove \"{target_dir}\"", cwd=REPO_ROOT)
        run_cmd(f"git branch -d {branch}", cwd=REPO_ROOT, check=False)
        print("✅ Worktree and branch cleaned up.")


def abort_pipeline(branch: str):
    """Force remove a worktree and discard branch."""
    target_dir = get_worktree_dir(branch)
    if not target_dir.exists():
        print(f"Worktree not found: {target_dir}")
        return

    print(f"🧹 Removing worktree at: {target_dir}")
    run_cmd(f"git worktree remove --force \"{target_dir}\"", cwd=REPO_ROOT)
    run_cmd(f"git branch -D {branch}", cwd=REPO_ROOT, check=False)
    print(f"✅ Aborted and cleaned worktree for branch '{branch}'.")


def list_worktrees():
    """List current active worktrees."""
    print("📋 Current active worktrees:")
    run_cmd("git worktree list", cwd=REPO_ROOT)


def main():
    parser = argparse.ArgumentParser(description="CollabPipeline - Transactional Parallel Worktrees")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = subparsers.add_parser("start", help="Start isolated parallel branch worktree")
    p_start.add_argument("--branch", required=True, help="Git branch name, e.g. feat/m2-data-kernel")
    p_start.add_argument("--role", help="Optional role to auto-pack capsule (e.g. AGT-DOM)")
    p_start.add_argument("--task-id", help="Optional task id for capsule")
    p_start.add_argument("--title", help="Optional task title")

    # integrate
    p_integrate = subparsers.add_parser("integrate", help="Verify gates and merge into main")
    p_integrate.add_argument("--branch", required=True, help="Git branch name to integrate")
    p_integrate.add_argument("--auto-clean", action="store_true", help="Remove worktree after successful merge")

    # abort
    p_abort = subparsers.add_parser("abort", help="Discard worktree and branch")
    p_abort.add_argument("--branch", required=True, help="Git branch name to discard")

    # status
    subparsers.add_parser("status", help="List active worktrees")

    args = parser.parse_args()

    if args.command == "start":
        start_pipeline(args.branch, args.role, args.task_id, args.title)
    elif args.command == "integrate":
        integrate_pipeline(args.branch, args.auto_clean)
    elif args.command == "abort":
        abort_pipeline(args.branch)
    elif args.command == "status":
        list_worktrees()


if __name__ == "__main__":
    main()
