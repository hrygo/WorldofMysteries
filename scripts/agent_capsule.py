#!/usr/bin/env python3
"""
AgentCapsule CLI - Deep Module for Human-Agent Collaborative Development
Enforces zero context dilution, precise AST graph slicing, and machine-attested handoffs.
"""

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

ROLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "AGT-DOM": {
        "directories": ["engine/domain/", "engine/tests/"],
        "forbidden_patterns": ["macos-app/*", "contracts/schemas/*", "*aiosqlite*", "*sqlite3*"],
        "invariants": [1, 2, 4, 5, 6, 8, 9],
        "instructions": "恪守纯领域零外部依赖原则。禁止直接引用数据库或 AI SDK。保持状态提交确定性。",
        "verification_commands": [
            "rtk python3 scripts/check_architecture_fitness.py",
            "rtk uv run --directory engine pytest tests/ -k 'domain or resolver or contract'"
        ]
    },
    "AGT-DATA": {
        "directories": ["engine/infrastructure/database_manager.py", "engine/infrastructure/outbox.py", "engine/tests/"],
        "forbidden_patterns": ["macos-app/*", "engine/domain/*"],
        "invariants": [3, 10, 11],
        "instructions": "落实四库隔离物理架构。严格保证 canon.db 只读，world.db 强事务，retrieval.db 异步投影可重建。",
        "verification_commands": [
            "rtk python3 scripts/check_architecture_fitness.py",
            "rtk uv run --directory engine pytest tests/ -k 'database or outbox'"
        ]
    },
    "AGT-AI": {
        "directories": ["engine/ai/", "engine/application/", "engine/tests/"],
        "forbidden_patterns": ["engine/infrastructure/database_manager.py", "macos-app/*"],
        "invariants": [5, 6, 7, 8],
        "instructions": "落实 AgentScope 2.0.8 适配与网关。AI 仅产生类型化 Proposal，严禁直接执行写库事务。语义授权先行。",
        "verification_commands": [
            "rtk python3 scripts/check_architecture_fitness.py",
            "rtk uv run --directory engine pytest tests/ -k 'ai or gateway or context'"
        ]
    },
    "AGT-VOICE": {
        "directories": ["engine/domain/audio_voice.py", "engine/infrastructure/audio/", "engine/tests/test_audio_adapter.py"],
        "forbidden_patterns": ["macos-app/*", "engine/ai/*"],
        "invariants": [9],
        "instructions": "维护 OpenAI Audio API 规范对接与 SpeechRail 热拔插。落实 sha256 内容寻址缓存与静音降级。",
        "verification_commands": [
            "rtk python3 scripts/check_architecture_fitness.py",
            "rtk uv run --directory engine pytest tests/test_audio_adapter.py"
        ]
    },
    "AGT-MAC": {
        "directories": ["macos-app/WorldOfMysteries/", "macos-app/WorldOfMysteriesTests/"],
        "forbidden_patterns": ["engine/*", "*sqlite3*"],
        "invariants": [12],
        "instructions": "遵循 Swift 6 严格并发与 SwiftUI @Observable 规范。严格通过 UDS IPC 驱动，零直接数据库访问。",
        "verification_commands": [
            "rtk python3 scripts/check_architecture_fitness.py",
            "rtk swift test --package-path macos-app"
        ]
    },
    "AGT-QA": {
        "directories": ["engine/tests/", "macos-app/WorldOfMysteriesTests/", "fixtures/golden_001/"],
        "forbidden_patterns": [],
        "invariants": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "instructions": "作为裁决者与质检门禁。负责全量回归断言、端到端契约校验与三阶段门禁自动化审计。",
        "verification_commands": [
            "bash scripts/gate_runner.sh"
        ]
    },
    "AGT-ARB": {
        "directories": ["docs/", "contracts/schemas/", "scripts/"],
        "forbidden_patterns": [],
        "invariants": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "instructions": "主架构师与调度仲裁者。负责需求分解、任务胶囊派发、架构适应度评估与冲突仲裁。",
        "verification_commands": [
            "bash scripts/gate_runner.sh"
        ]
    }
}


def run_cmd(cmd: str, check: bool = True) -> str:
    """Run shell command and return stdout."""
    res = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {cmd}\nStderr: {res.stderr}")
    return res.stdout.strip()


def extract_ast_symbols(target_dirs: List[str]) -> List[str]:
    """Scan authorized directories and extract class/function symbols via AST."""
    symbols = []
    for d in target_dirs:
        dir_path = REPO_ROOT / d
        if dir_path.is_file() and dir_path.suffix == ".py":
            files = [dir_path]
        elif dir_path.is_dir():
            files = list(dir_path.glob("**/*.py"))
        else:
            continue

        for f in files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        rel_file = f.relative_to(REPO_ROOT)
                        symbols.append(f"{node.name} ({rel_file}:{node.lineno})")
            except Exception:
                continue
    return sorted(symbols[:30])  # Cap to prevent token inflation


def pack_capsule(role: str, task_id: str, title: str, output_file: Optional[str] = None) -> Path:
    """Create a self-contained Task Capsule with AST graph slicing."""
    if role not in ROLE_DEFAULTS:
        raise ValueError(f"Unknown role '{role}'. Choose from {list(ROLE_DEFAULTS.keys())}")

    defaults = ROLE_DEFAULTS[role]
    current_branch = run_cmd("git rev-parse --abbrev-ref HEAD")
    base_commit = run_cmd("git rev-parse --short HEAD")

    symbols = extract_ast_symbols(defaults["directories"])
    now_str = datetime.now(timezone.utc).isoformat()
    capsule_id = f"CAP-{datetime.now().strftime('%Y%m%d')}-{task_id}"

    capsule_data = {
        "$schema": "contracts/schemas/task_capsule.schema.json",
        "capsule_id": capsule_id,
        "task_id": task_id,
        "title": title,
        "assigned_role": role,
        "status": "CREATED",
        "created_at": now_str,
        "git_context": {
            "base_commit": base_commit,
            "target_branch": current_branch,
            "worktree_path": str(REPO_ROOT)
        },
        "authorized_scope": {
            "directories": defaults["directories"],
            "forbidden_patterns": defaults["forbidden_patterns"]
        },
        "graph_slice": {
            "target_symbols": symbols,
            "related_schemas": ["world_snapshot.schema.json", "state_delta.schema.json", "engine_ipc.schema.json"]
        },
        "constraints": {
            "invariants": defaults["invariants"],
            "instructions": defaults["instructions"]
        },
        "verification_commands": defaults["verification_commands"]
    }

    if not output_file:
        out_dir = REPO_ROOT / ".agents" / "capsules"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}.json"
    else:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(json.dumps(capsule_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"📦 [AgentCapsule] Successfully packed capsule for {role} -> {out_path}")
    print(f"   Task: [{task_id}] {title}")
    print(f"   AST Symbols Sliced: {len(symbols)} items")
    print(f"   Scope: {defaults['directories']}")
    return out_path


def verify_capsule(capsule_path: Path) -> bool:
    """Verify changes against capsule scope and run verification commands."""
    if not capsule_path.exists():
        print(f"❌ Capsule file not found: {capsule_path}")
        return False

    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    print(f"🔍 [AgentCapsule] Verifying Task: [{capsule['task_id']}] {capsule['title']}")
    print(f"   Assigned Role: {capsule['assigned_role']}")

    # 1. Check Git Modified Files Scope
    diff_files_raw = run_cmd("git diff --name-only HEAD", check=False)
    untracked_raw = run_cmd("git ls-files --others --exclude-standard", check=False)
    changed_files = [f for f in (diff_files_raw + "\n" + untracked_raw).splitlines() if f.strip()]

    auth_dirs = capsule["authorized_scope"]["directories"]
    violations = []
    for f in changed_files:
        # Ignore temporary cache and capsule files
        if f.startswith(".agents/capsules/") or f.endswith(".tmp") or ".pytest_cache" in f:
            continue
        matched = any(f.startswith(d.rstrip("*")) for d in auth_dirs)
        if not matched:
            violations.append(f)

    if violations:
        print("⚠️ [Scope Warning] The following files are modified outside authorized scope:")
        for v in violations:
            print(f"   - {v}")
        print("   Please review if these changes are intentional.")

    # 2. Run Verification Commands
    print("\n🚀 Executing verification commands...")
    for cmd in capsule["verification_commands"]:
        # Strip 'rtk ' if rtk is not on PATH or directly running python
        exec_cmd = cmd.replace("rtk ", "")
        print(f"   ▶ {cmd}")
        res = subprocess.run(exec_cmd, shell=True, cwd=REPO_ROOT)
        if res.returncode != 0:
            print(f"❌ Command failed with code {res.returncode}: {cmd}")
            return False

    # 3. Machine-attested Signing
    now_str = datetime.now(timezone.utc).isoformat()
    checksum = hashlib.sha256(f"{capsule['task_id']}:{now_str}".encode()).hexdigest()[:16]
    capsule["status"] = "VERIFIED"
    capsule["attestation"] = {
        "verified_at": now_str,
        "gate_checksum": f"sha256:{checksum}",
        "verified_by": "AgentCapsuleGateKeeper_v1.0"
    }
    capsule_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n🎉 [AgentCapsule] Verification PASSED! Attested signature: sha256:{checksum}")
    return True


def show_capsule(capsule_path: Path):
    """Print readable summary of the task capsule."""
    if not capsule_path.exists():
        print(f"❌ Capsule not found: {capsule_path}")
        return

    capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    print("\n========================================================")
    print(f"🏷️  Task Capsule: {capsule['capsule_id']}")
    print(f"📋 Title: {capsule['title']}")
    print(f"👤 Assigned Role: {capsule['assigned_role']} | Status: {capsule.get('status', 'CREATED')}")
    print("========================================================")
    print(f"📁 Authorized Scope: {', '.join(capsule['authorized_scope']['directories'])}")
    print(f"🛡️  Invariants Bound: {capsule['constraints']['invariants']}")
    print(f"💡 Instructions: {capsule['constraints']['instructions']}")
    print("\n🔬 Extracted AST Symbols (Sample):")
    for s in capsule.get("graph_slice", {}).get("target_symbols", [])[:8]:
        print(f"   • {s}")
    print("\n🚦 Verification Gate Commands:")
    for cmd in capsule["verification_commands"]:
        print(f"   $ {cmd}")
    if "attestation" in capsule:
        print(f"\n✅ Signed Attestation: {capsule['attestation']['gate_checksum']} ({capsule['attestation']['verified_at']})")
    print("========================================================\n")


def main():
    parser = argparse.ArgumentParser(description="AgentCapsule CLI - Collaborative Engineering Deep Seam")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pack command
    pack_parser = subparsers.add_parser("pack", help="Pack task capsule for a role")
    pack_parser.add_argument("--role", required=True, choices=list(ROLE_DEFAULTS.keys()), help="Agent role identifier")
    pack_parser.add_argument("--task-id", required=True, help="Unique task identifier, e.g. M2-DATA-KERNEL")
    pack_parser.add_argument("--title", required=True, help="Short human-readable task description")
    pack_parser.add_argument("--output", help="Optional custom output path for JSON capsule")

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify task against scope & run gates")
    verify_parser.add_argument("--capsule", required=True, help="Path to capsule JSON file")

    # show command
    show_parser = subparsers.add_parser("show", help="Display capsule summary")
    show_parser.add_argument("--capsule", required=True, help="Path to capsule JSON file")

    args = parser.parse_args()

    if args.command == "pack":
        pack_capsule(args.role, args.task_id, args.title, args.output)
    elif args.command == "verify":
        success = verify_capsule(Path(args.capsule))
        sys.exit(0 if success else 1)
    elif args.command == "show":
        show_capsule(Path(args.capsule))


if __name__ == "__main__":
    main()
