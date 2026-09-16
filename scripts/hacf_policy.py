#!/usr/bin/env python3
"""
HACF 2.1 Policy & Receipt Kernel

职责（深模块，只暴露少量稳定接缝）：
1. Capsule 读取与摘要：capsule_digest = sha256(胶囊文件原始字节)，胶囊本身不可被回写。
2. 范围裁决：write / read / forbidden / privileged 四类边界判定，越权需显式 grant。
3. Receipt 生成：Work Receipt 与 Integration Receipt 共用同一结构，绑定摘要链与原始日志摘要。

注意（诚实性原则）：sha256 是摘要而非密码学签名。本模块不声称"防伪签名"，
只保证"可校验、可追溯、可复算"。需要抗伪造的合入授权由受保护分支 + CODEOWNERS 评审承担。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import getpass
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

RECEIPTS_DIR = ".agents/receipts"

# 高风险面：任何角色触碰都必须在胶囊中留下显式 grant，并触发人工（CODEOWNERS）评审。
PRIVILEGED_SURFACES: List[str] = [
    "contracts/",
    ".hacf/",
    ".github/",
    "scripts/",
    ".agents/skills/",
    ".agents/prompts/",
    "docs/01_总体架构/",
    "engine/uv.lock",
    "engine/pyproject.toml",
    "macos-app/Package.swift",
    "macos-app/WorldOfMysteries.xcodeproj/project.pbxproj",
    "engine/**/migrations/",
]

# 根目录治理与仓库元文件：不属于任何业务角色，纳入 AGT-ARB 治理通道。
# 非特权角色触碰需显式 privileged grant，避免"无人认领路径"成为审核盲区。
ROOT_GOVERNANCE_SURFACES: List[str] = [
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "NOTICE.md",
    "CODE_OF_CONDUCT.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
]

PRIVILEGED_SURFACES.extend(ROOT_GOVERNANCE_SURFACES)

# 范围审计豁免：这些路径属于协同元数据或本地证据，不构成业务越界。
SCOPE_EXEMPT_PREFIXES = (
    ".agents/capsules/",
    ".agents/receipts/",
    ".hacf/tmp/",
    ".hacf/spm-scratch/",
    ".hacf/testdb/",
    ".hacf/run/",
    ".hacf/logs/",
)
SCOPE_EXEMPT_SUFFIXES = (".tmp",)
# 精确豁免：工作区资源租约由流水线生成，不是任务提交的业务变更
# （注意：`.hacf/gates/**` 仍属受保护面，不在豁免之列）
SCOPE_EXEMPT_EXACT = (".hacf/workspace.json",)

# 仅可仲裁扩权的高风险面：即使落在角色 write scope 内，非 AGT-ARB 角色仍需显式 grant。
ESCALATION_ONLY_SURFACES: List[str] = [
    "contracts/",
    ".hacf/",
    ".github/",
    "engine/**/migrations/",
]

# 拥有独立治理权、无需为上述高风险面逐次申请 grant 的角色。
PRIVILEGED_LANE_ROLES = ("AGT-ARB",)


class PolicyError(RuntimeError):
    """胶囊缺失、结构非法或摘要不可复算。"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_digest(payload: Any) -> str:
    """对结构化内容做确定性摘要（键排序、紧凑分隔、UTF-8）。"""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(blob.encode("utf-8"))


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    """路径匹配：支持目录前缀（`contracts/`）、递归通配（`engine/**/migrations/`）与文件名通配。"""
    posix = PurePosixPath(path)
    for pattern in patterns or []:
        if not pattern:
            continue
        if path == pattern:
            return True
        if pattern.endswith("/"):
            if path.startswith(pattern) or posix.match(pattern.rstrip("/")):
                return True
            # 目录型通配（如 engine/**/migrations/）：fnmatch 不区分层级，恰好符合目录语义
            if any(
                fnmatch.fnmatch(path, candidate)
                for candidate in (pattern, pattern + "*", pattern + "**")
            ):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
        if "**" in pattern and posix.match(pattern):
            return True
        if fnmatch.fnmatch(posix.name, pattern):
            return True
    return False


def run_git(args: List[str], cwd: Path = REPO_ROOT) -> str:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        raise PolicyError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def run_git_bytes(args: List[str], cwd: Path = REPO_ROOT) -> bytes:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if res.returncode != 0:
        raise PolicyError(f"git {' '.join(args)} failed: {res.stderr.decode('utf-8', 'replace').strip()}")
    return res.stdout


def split_nul(blob: bytes) -> List[str]:
    """解析 git -z 输出。

    必须使用 -z：默认 `core.quotePath=true` 会把非 ASCII（本仓库大量中文文件名）
    转义成 `"docs/01_\\346\\200..."` 形式，导致范围裁决对中文路径全部误判。
    """
    return [item.decode("utf-8", "surrogateescape") for item in blob.split(b"\0") if item]


def changed_files(cwd: Path = REPO_ROOT, base_commit: Optional[str] = None) -> List[str]:
    """工作区相对 base 的变更文件（含未跟踪文件）。"""
    base = base_commit or "HEAD"
    tracked = split_nul(run_git_bytes(["diff", "--name-only", "-z", base], cwd=cwd))
    untracked = split_nul(
        run_git_bytes(["ls-files", "--others", "--exclude-standard", "-z"], cwd=cwd)
    )
    files = set(tracked) | set(untracked)
    return sorted(
        f
        for f in files
        if f not in SCOPE_EXEMPT_EXACT
        and not f.startswith(SCOPE_EXEMPT_PREFIXES)
        and not f.endswith(SCOPE_EXEMPT_SUFFIXES)
    )


def capsule_digest(capsule_path: Path) -> str:
    return sha256_file(capsule_path)


def changes_digest(base_ref: str, head_ref: str, cwd: Path = REPO_ROOT) -> str:
    """变更集内容摘要：文件清单 + 每个文件在 head 的对象摘要。

    凭单以此摘要绑定"验收过的内容"，而不是绑定某个 commit：
    rebase、合入最新 main、或纯提交信息变更都不改变摘要，凭单继续有效；
    只有实际改动（含文件增删改）或胶囊变化才要求重跑门禁。

    证据文件（`.agents/capsules/`、`.agents/receipts/`）不计入摘要，否则
    "签发凭单 → 提交凭单"会改变摘要并让凭单立刻失效（自指死循环）。
    胶囊内容另由凭单的 `capsule_digest` 字段独立绑定。
    """
    names = split_nul(
        run_git_bytes(["diff", "--name-only", "-z", f"{base_ref}...{head_ref}"], cwd=cwd)
    )
    entries: List[str] = []
    substantive = [
        n for n in names if n and not n.startswith((".agents/capsules/", ".agents/receipts/"))
    ]
    for name in sorted(substantive):
        res = subprocess.run(
            ["git", "ls-tree", head_ref, "--", name],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        fields = res.stdout.split()
        object_id = fields[2] if len(fields) >= 3 else "DELETED"
        entries.append(f"{name}\0{object_id}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def load_capsule(capsule_path: Path) -> Dict[str, Any]:
    if not capsule_path.exists():
        raise PolicyError(f"capsule not found: {capsule_path}")
    try:
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"capsule is not valid JSON: {exc}") from exc
    if "scope" not in capsule or "gates" not in capsule:
        raise PolicyError(
            "capsule is not HACF 2.1 shaped (missing 'scope'/'gates'). "
            "请用 'python3 scripts/agent_capsule.py pack' 重新生成。"
        )
    return capsule


def path_verdict(capsule: Dict[str, Any], path: str) -> Dict[str, str]:
    """单文件裁决原语。

    返回 `{"path", "verdict", "reason"}`，verdict 取值：
      - `authorized`：该胶囊足以授权此路径
      - `escalation_required`：可行，但需仲裁扩权（高风险面缺 grant）
      - `forbidden`：命中该胶囊的 forbidden 禁区
      - `out_of_scope`：超出该胶囊 write scope 且非高风险面

    覆盖式归属（多胶囊 PR）以此原语逐胶囊判定后取并集，
    避免"每枚胶囊都必须覆盖 PR 里每个文件"的并集语义把正常协同判成越权。
    """
    scope = capsule.get("scope", {}) or {}
    write_scope = scope.get("write", []) or []
    forbidden = scope.get("forbidden", []) or []
    grants = scope.get("privileged_grants", []) or []
    role = capsule.get("assigned_role", "")
    in_privileged_lane = role in PRIVILEGED_LANE_ROLES

    if matches_any(path, forbidden):
        return {"path": path, "verdict": "forbidden", "reason": "命中 forbidden 禁区"}
    if not in_privileged_lane and matches_any(path, ESCALATION_ONLY_SURFACES):
        if matches_any(path, grants):
            return {"path": path, "verdict": "authorized", "reason": "已授予 privileged grant"}
        return {
            "path": path,
            "verdict": "escalation_required",
            "reason": "命中高风险面，需仲裁扩权（SCOPE_ESCALATION_REQUIRED）",
        }
    if matches_any(path, write_scope):
        return {"path": path, "verdict": "authorized", "reason": "命中 write scope"}
    if matches_any(path, PRIVILEGED_SURFACES):
        if matches_any(path, grants):
            return {"path": path, "verdict": "authorized", "reason": "已授予 privileged grant"}
        return {
            "path": path,
            "verdict": "escalation_required",
            "reason": "命中高风险面但未授予 privileged grant",
        }
    return {"path": path, "verdict": "out_of_scope", "reason": "超出 write scope"}


def touches_high_risk(path: str) -> bool:
    """该路径是否落在高风险面（privileged / escalation-only）上。"""
    return bool(matches_any(path, PRIVILEGED_SURFACES) or matches_any(path, ESCALATION_ONLY_SURFACES))


def audit_scope(capsule: Dict[str, Any], files: List[str]) -> Dict[str, Any]:
    """四类边界裁决。返回 violations / escalations / granted 三类结论。"""
    violations: List[Dict[str, str]] = []
    escalations: List[Dict[str, str]] = []
    granted_uses: List[str] = []

    for path in files:
        verdict = path_verdict(capsule, path)
        kind = verdict["verdict"]
        if kind == "forbidden":
            violations.append({"path": path, "reason": verdict["reason"]})
        elif kind == "escalation_required":
            escalations.append({"path": path, "reason": verdict["reason"]})
        elif kind == "out_of_scope":
            violations.append({"path": path, "reason": verdict["reason"]})
        elif touches_high_risk(path):
            granted_uses.append(path)

    return {
        "changed_files": files,
        "violations": violations,
        "escalations": escalations,
        "privileged_uses": granted_uses,
    }


def runner_identity(role: str) -> Dict[str, str]:
    return {
        "host": platform.node(),
        "user": getpass.getuser(),
        "role": role,
        "cwd": os.getcwd(),
    }


def build_receipt(
    *,
    receipt_type: str,
    capsule: Dict[str, Any],
    capsule_digest_value: str,
    gate_result: Dict[str, Any],
    scope_audit: Dict[str, Any],
    base_commit: str,
    head_commit: str,
    diff_digest_value: str = "",
    target_ref: str,
    target_sha: str,
    stale_context: bool,
    toolchain: Dict[str, str],
    started_at: str,
    verdict: str,
    merge_authorizing: bool = False,
    merge: Optional[Dict[str, Any]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    task_id = capsule.get("task_id", "UNKNOWN")
    head_short = head_commit[:12] if head_commit else "uncommitted"
    return {
        "receipt_id": f"RCP-{receipt_type.upper()}-{task_id}-{head_short}",
        "receipt_type": receipt_type,
        "task_id": task_id,
        "capsule_id": capsule.get("capsule_id"),
        "capsule_revision": capsule.get("capsule_revision", 1),
        "capsule_digest": f"sha256:{capsule_digest_value}",
        # 内容绑定：CI 以 diff_digest 判定凭单是否仍对应当前变更集（head_commit 仅作信息记录）
        "diff_digest": f"sha256:{diff_digest_value}" if diff_digest_value else "",
        "assigned_role": capsule.get("assigned_role"),
        "risk_class": capsule.get("risk_class", "medium"),
        "base_commit": base_commit,
        "head_commit": head_commit,
        "target_ref": target_ref,
        "target_sha": target_sha,
        "stale_context": stale_context,
        "gate_profile_id": gate_result.get("gate_profile_id"),
        "gate_profile_digest": gate_result.get("gate_profile_digest"),
        "gate_result": gate_result.get("result"),
        "gate_stages": gate_result.get("stages", []),
        "coverage_gaps": gate_result.get("coverage_gaps", []),
        "scope_audit": scope_audit,
        "toolchain": toolchain,
        "runner": runner_identity(str(capsule.get("assigned_role", "UNKNOWN"))),
        "started_at": started_at,
        "finished_at": now_iso(),
        "verdict": verdict,
        "merge_authorizing": merge_authorizing,
        "merge": merge or {},
        "notes": notes or [],
        "integrity": {
            "digest_algorithm": "sha256",
            "statement": (
                "本凭单为可复算摘要记录（digest-recorded receipt），不是密码学签名；"
                "其可信度由受保护分支策略、CODEOWNERS 评审与 CI 复算共同保证。"
            ),
        },
    }


def write_receipt(repo_root: Path, receipt: Dict[str, Any], head_commit: str) -> Path:
    out_dir = repo_root / RECEIPTS_DIR / str(receipt["task_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    head_short = head_commit[:12] if head_commit else "uncommitted"
    suffix = "" if receipt["receipt_type"] == "work" else "-integration"
    out_path = out_dir / f"{head_short}{suffix}.json"
    out_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out_path


def log_dir_for(repo_root: Path, task_id: str, head_commit: str) -> Path:
    head_short = head_commit[:12] if head_commit else "uncommitted"
    return repo_root / RECEIPTS_DIR / task_id / head_short


def load_workspace_lease(repo_root: Path) -> Dict[str, Any]:
    """读取 worktree 资源命名空间租约（由 collab_pipeline start 生成）。"""
    lease_path = repo_root / ".hacf" / "workspace.json"
    if not lease_path.exists():
        return {}
    try:
        return json.loads(lease_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def env_overrides_from_lease(lease: Dict[str, Any]) -> Dict[str, str]:
    if not lease:
        return {}
    return {
        "TMPDIR": lease.get("tmpdir", ""),
        "WOM_SPM_SCRATCH": lease.get("spm_scratch", ""),
        "WOM_TEST_DB_DIR": lease.get("test_db_dir", ""),
        "WOM_IPC_SOCKET": lease.get("ipc_socket", ""),
        "WOM_PORT_RANGE": lease.get("port_range", ""),
        "WOM_LOG_DIR": lease.get("log_dir", ""),
    }


def print_receipt_summary(receipt: Dict[str, Any], path: Optional[Path] = None) -> None:
    icon = {"passed": "✅", "failed": "❌"}.get(receipt["verdict"], "•")
    print(f"{icon} {receipt['receipt_type']} receipt · {receipt['task_id']} · verdict={receipt['verdict']}")
    print(f"   capsule_digest : {receipt['capsule_digest']}")
    print(f"   gate profile   : {receipt['gate_profile_id']} ({receipt['gate_profile_digest']})")
    print(f"   head_commit    : {receipt['head_commit'] or '(uncommitted worktree state)'}")
    if receipt["coverage_gaps"]:
        for gap in receipt["coverage_gaps"]:
            print(f"   ️  {gap}")
    if path:
        print(f"   receipt        : {path}")
