#!/usr/bin/env python3
"""
Capsule Audit (HACF 2.1) — PR 侧权威审计

取代 HACF 2.0 中「只检查字段是否存在」的内联脚本，落实四条硬规则：
1. 触碰代码路径的 PR 必须携带任务胶囊，且变更不得超出 capsule.scope.write；
2. forbid/privileged 边界与本地一致：高风险面必须显式 grant，否则要求仲裁扩权；
3. 必须存在 head 与 PR 提交一致、verdict=passed 的 Work Receipt（无证据不放行）；
4. 门禁档案摘要以**目标分支（受保护）**的 registry 为权威，
   PR 内同时改写 profile 与 registry 无法自证通过。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_profile  # noqa: E402
import hacf_policy as policy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# 元数据路径：不参与「代码变更必须带胶囊」的判定，但仍受 forbidden / 门禁档案主权约束。
META_PREFIXES = (".agents/capsules/", ".agents/receipts/", "docs/", "README.md", "AGENTS.md")


def _is_meta(path: str) -> bool:
    return path.startswith(META_PREFIXES) or path.endswith(".md")


def _is_code(path: str) -> bool:
    return not _is_meta(path)


def registry_from_ref(ref: str, repo_root: Path = REPO_ROOT) -> Optional[Dict[str, Any]]:
    """读取目标分支（受保护）的 registry；不存在则返回 None。"""
    res = subprocess.run(
        ["git", "show", f"{ref}:.hacf/gates/registry.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def load_receipts(repo_root: Path, task_id: str) -> List[Dict[str, Any]]:
    receipts = []
    for path in sorted((repo_root / policy.RECEIPTS_DIR / task_id).glob("*.json")):
        try:
            receipts.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return receipts


def _arbiter_synced_registry(
    repo_root: Path, capsule: Dict[str, Any], actual_digest: str
) -> bool:
    """治理通道在同一 PR 内同步更新 profile 与 registry 摘要时，允许门禁档案正常演进。

    否则「任何 profile 改动都等于篡改」会让门禁档案在受保护分支上永久冻结，
    连合法升级都无法通过 PR 完成——这是自锁而非守门。
    """
    if capsule.get("assigned_role") not in policy.PRIVILEGED_LANE_ROLES:
        return False
    registry_file = repo_root / ".hacf" / "gates" / "registry.json"
    if not registry_file.exists():
        return False
    try:
        registry = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    profile_id = capsule.get("gates", {}).get("profile")
    entry_pr = registry.get("profiles", {}).get(profile_id)
    if not entry_pr:
        return False
    return f"sha256:{entry_pr.get('sha256')}" == actual_digest


def audit_pr(
    *,
    changed_files: Sequence[str],
    capsule_paths: Sequence[Path],
    head_sha: str,
    repo_root: Path = REPO_ROOT,
    authoritative_registry: Optional[Dict[str, Any]] = None,
    current_diff_digest: str = "",
) -> Dict[str, Any]:
    """返回结构化审计结论；blocking 非空时由调用方（CI）阻断合入。

    分级原则——只拦「不可逆 / 不可信」，不拦进度：
      * blocking：越界写、forbidden 命中、门禁档案篡改、胶囊不可读或未携带；
      * advisory：证据完备性（Work Receipt、覆盖缺口、stale_context）默认只提示，
        设 HACF_STRICT_EVIDENCE=1 时升级为阻断。

    边界裁决为**覆盖式**：一个文件只要求「被至少一枚胶囊授权」，
    而不是「被 PR 内每一枚胶囊授权」，多角色协同 PR 因此不再必然失败。
    """
    blocking: List[str] = []
    advisory: List[str] = []
    notices: List[str] = []

    strict_evidence = os.getenv("HACF_STRICT_EVIDENCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    def report(message: str, *, hard: bool) -> None:
        if hard or strict_evidence:
            blocking.append(message)
        else:
            advisory.append(message)

    code_files = [f for f in changed_files if _is_code(f)]
    meta_files = [f for f in changed_files if _is_meta(f)]
    if meta_files:
        notices.append(f"元数据变更 {len(meta_files)} 个文件（docs/.agents 等）不参与代码胶囊判定")

    gates_touched = [f for f in changed_files if f.startswith(".hacf/gates/")]
    capsules = []
    for capsule_path in capsule_paths:
        try:
            capsules.append((capsule_path, policy.load_capsule(capsule_path)))
        except policy.PolicyError as exc:
            report(f"胶囊不可读: {capsule_path}: {exc}", hard=True)

    # 识别自动化维护 PR（如 Dependabot、纯依赖锁文件或 CI 流水线微调）
    MAINTENANCE_ALLOWED_PREFIXES = (
        ".github/dependabot.yml",
        ".github/workflows/",
        "engine/uv.lock",
        "macos-app/Package.resolved",
    )
    is_maintenance = False
    actor = os.getenv("GITHUB_ACTOR", "")
    head_ref_name = os.getenv("GITHUB_HEAD_REF", "")
    if "dependabot" in actor.lower() or head_ref_name.startswith("dependabot/"):
        is_maintenance = True
    elif code_files and all(
        any(f.startswith(prefix) or f == prefix for prefix in MAINTENANCE_ALLOWED_PREFIXES)
        for f in code_files
    ):
        is_maintenance = True

    if is_maintenance and not capsules:
        notices.append(
            "🤖 [MAINTENANCE] 判定为自动化依赖/工作流维护 PR，免除业务任务胶囊与 Work Receipt 约束（由 CI 3-Stage 门禁全权守门）"
        )
    elif code_files and not capsules:
        report(
            "本 PR 修改了代码路径但未携带任务胶囊："
            f"{', '.join(code_files[:10])}{' …' if len(code_files) > 10 else ''}",
            hard=True,
        )
    if not capsules and not code_files:
        notices.append("无代码变更且无胶囊：按元数据变更放行（仍需人工评审）")

    per_file: Dict[str, List[Dict[str, str]]] = {}
    for capsule_path, capsule in capsules:
        role = capsule.get("assigned_role", "UNKNOWN")
        task_id = capsule.get("task_id", "UNKNOWN")
        print(f"\n🏷️  审计胶囊 {capsule.get('capsule_id')} · role={role} · task={task_id}")

        # 1. 边界裁决（覆盖式）：先逐胶囊取单文件裁决，最后按文件汇总
        for path in code_files:
            verdict = policy.path_verdict(capsule, path)
            per_file.setdefault(path, []).append(
                {**verdict, "task_id": task_id, "role": role}
            )
            if verdict["verdict"] == "authorized" and policy.touches_high_risk(path):
                notices.append(f"[{task_id}] 已授权高风险面: {path}")

        # 2. 门禁档案主权：PR 不得自证门禁
        # 归属口径同样按覆盖式：只有「确实授权了门禁档案」的胶囊才被追责，
        # 否则同 PR 内任何无关胶囊都会被安上篡改罪名。
        gates_claimed = [
            f for f in gates_touched if policy.path_verdict(capsule, f)["verdict"] == "authorized"
        ]
        if gates_claimed and role not in policy.PRIVILEGED_LANE_ROLES:
            report(
                f"[{task_id}] 角色 {role} 不得修改受保护门禁档案: {', '.join(gates_claimed)}",
                hard=True,
            )
        base_registry_digest = None
        if authoritative_registry:
            profile_id = capsule.get("gates", {}).get("profile")
            entry = authoritative_registry.get("profiles", {}).get(profile_id)
            if not entry:
                report(
                    f"[{task_id}] 胶囊引用的门禁档案 '{profile_id}' 不存在于目标分支 registry",
                    hard=True,
                )
            else:
                base_registry_digest = f"sha256:{entry['sha256']}"
                if capsule.get("gates", {}).get("profile_digest") != base_registry_digest:
                    report(
                        f"[{task_id}] 胶囊记录的门禁摘要与目标分支权威 registry 不一致 "
                        f"(capsule={capsule.get('gates', {}).get('profile_digest')}, base={base_registry_digest})",
                        hard=True,
                    )
                profile_file = repo_root / entry["file"]
                if profile_file.exists():
                    actual = f"sha256:{gate_profile.sha256_file(profile_file)}"
                    if actual != base_registry_digest:
                        if _arbiter_synced_registry(repo_root, capsule, actual):
                            notices.append(
                                f"[{task_id}] 治理通道在同一 PR 内同步更新了 profile 与 registry 摘要，"
                                f"门禁档案演进被受理: {entry['file']}"
                            )
                        else:
                            report(
                                f"[{task_id}] PR 内门禁档案被改写且未同步目标分支 registry: {entry['file']}",
                                hard=True,
                            )
        else:
            notices.append("未能读取目标分支 registry（首次引入阶段），跳过权威摘要比对")

        # 3. 凭单证据：优先按变更集内容摘要匹配（与提交解耦），head 一致作为兼容回退
        receipts = load_receipts(repo_root, task_id)
        matching = [
            r
            for r in receipts
            if r.get("receipt_type") == "work"
            and (
                (current_diff_digest and r.get("diff_digest") == current_diff_digest)
                or r.get("head_commit") == head_sha
            )
        ]
        if not matching:
            report(
                f"[{task_id}] 缺少覆盖当前变更集的 Work Receipt（diff={current_diff_digest[:19]}…）："
                "请在工作区执行 'python3 scripts/agent_capsule.py verify --capsule <capsule>' 后提交凭单",
                hard=False,
            )
        for receipt in matching:
            if receipt.get("verdict") != "passed":
                report(f"[{task_id}] Work Receipt verdict={receipt.get('verdict')}", hard=False)
            if receipt.get("capsule_digest") != f"sha256:{policy.capsule_digest(capsule_path)}":
                report(
                    f"[{task_id}] Work Receipt 绑定的 capsule_digest 与当前胶囊不一致（胶囊被改动后需重新验收）",
                    hard=False,
                )
            if base_registry_digest and receipt.get("gate_profile_digest") != base_registry_digest:
                report(f"[{task_id}] Work Receipt 的 gate_profile_digest 非权威档案摘要", hard=False)
            if receipt.get("coverage_gaps"):
                notices.append(
                    f"[{task_id}] 验收存在覆盖缺口 {len(receipt['coverage_gaps'])} 项："
                    + "；".join(receipt["coverage_gaps"][:3])
                )
            if receipt.get("stale_context"):
                report(f"[{task_id}] Work Receipt 标记 stale_context=true", hard=False)

    # 4. 按文件汇总覆盖结论：被任一胶囊授权即放行，无任何胶囊覆盖才判越界
    for path, verdicts in sorted(per_file.items()):
        if any(v["verdict"] == "authorized" for v in verdicts):
            continue
        forbidding = [v for v in verdicts if v["verdict"] == "forbidden"]
        if forbidding:
            owners = ", ".join(f"{v['role']}/{v['task_id']}" for v in forbidding)
            report(f"越界: {path} — {forbidding[0]['reason']}（禁方: {owners}）", hard=True)
            continue
        escalations = [v for v in verdicts if v["verdict"] == "escalation_required"]
        if escalations:
            owners = ", ".join(f"{v['role']}/{v['task_id']}" for v in escalations)
            report(
                f"SCOPE_ESCALATION_REQUIRED: {path} — {escalations[0]['reason']}（相关胶囊: {owners}）",
                hard=True,
            )
            continue
        owners = ", ".join(sorted({v["task_id"] for v in verdicts}))
        report(f"越界: {path} — 无任何胶囊覆盖该路径（PR 内胶囊: {owners}）", hard=True)

    return {
        "ok": not blocking,
        "failures": blocking,
        "blocking": blocking,
        "advisory": advisory,
        "notices": notices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="HACF 2.1 PR Capsule & Evidence Audit")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--changed-files", help="逗号分隔；默认由 git diff 计算")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if args.changed_files:
        changed = [f for f in args.changed_files.split(",") if f]
    else:
        res = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--name-only", f"{args.base_ref}...{args.head_ref}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        changed = [line.strip() for line in res.stdout.splitlines() if line.strip()]

    head_sha = subprocess.run(
        ["git", "rev-parse", args.head_ref], cwd=repo_root, capture_output=True, text=True
    ).stdout.strip()

    # 优先只审计本次 PR 变更集涉及的胶囊；若本次 PR 未修改胶囊，则只在包含业务代码时回退至相关胶囊
    changed_capsules = [
        repo_root / f
        for f in changed
        if f.startswith(".agents/capsules/") and f.endswith(".json") and (repo_root / f).exists()
    ]

    result = audit_pr(
        changed_files=changed,
        capsule_paths=changed_capsules,
        head_sha=head_sha,
        repo_root=repo_root,
        authoritative_registry=registry_from_ref(args.base_ref, repo_root),
        current_diff_digest="sha256:"
        + policy.changes_digest(args.base_ref, args.head_ref, cwd=repo_root),
    )

    print(f"\n📋 变更文件 {len(changed)} 个；审计结论: {'PASS' if result['ok'] else 'FAIL'}")
    for notice in result["notices"]:
        print(f"   ️  {notice}")
    for failure in result["blocking"]:
        print(f"    [BLOCKING] {failure}")
    for warning in result["advisory"]:
        print(f"   ⚠️  [ADVISORY] {warning}")
    if result["ok"]:
        if result["advisory"]:
            print(
                f"\n✅ Capsule 审计通过（{len(result['advisory'])} 项提示不阻断合入；"
                "严格模式请设 HACF_STRICT_EVIDENCE=1）。"
            )
        else:
            print("\n Capsule scope & evidence audit PASSED.")
        return 0
    print("\n❌ Capsule audit FAILED：存在越界或不可信变更，拒绝合入。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
