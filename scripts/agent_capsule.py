#!/usr/bin/env python3
"""
AgentCapsule CLI (HACF 2.1)

不可变任务契约 · 受保护门禁引用 · 可复算凭单。

与 HACF 2.0 的关键差异：
1. 胶囊只声明「做什么 / 边界在哪 / 用哪套门禁」，不再携带可被任务自行改写的验收命令；
2. verify 不再回写胶囊，而是产出独立 Receipt（契约与凭证分离，rebase 后需重新出单）；
3. 摘要为 sha256 内容摘要，不冒充密码学签名；合入授权由受保护分支与 CODEOWNERS 评审承担。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_profile  # noqa: E402
import hacf_policy as policy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# 每个角色的边界 + 受保护门禁引用。验收命令不在此定义，见 .hacf/gates/*.json
ROLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "AGT-DOM": {
        "write": ["engine/domain/", "engine/tests/"],
        "read": ["engine/domain/", "engine/application/", "engine/tests/", "contracts/"],
        "forbidden": ["macos-app/**", "engine/infrastructure/**", "engine/ai/**", ".hacf/**", ".github/**"],
        "gate_profile": "DOMAIN_P0",
        "risk_class": "medium",
        "invariants": [1, 2, 4, 5, 6, 8, 9],
        "instructions": "恪守纯领域零外部依赖原则。禁止引用数据库或 AI SDK，状态提交保持确定性。",
        "contracts": ["world_snapshot.schema.json", "state_delta.schema.json", "proposal.schema.json"],
    },
    "AGT-DATA": {
        "write": ["engine/infrastructure/", "engine/tests/"],
        "read": ["engine/infrastructure/", "engine/tests/", "contracts/", "docs/03_工程规范/"],
        "forbidden": ["macos-app/**", "engine/domain/**", "engine/ai/**", ".hacf/**", ".github/**"],
        "gate_profile": "DATA_KERNEL_P0",
        "risk_class": "high",
        "invariants": [3, 10, 11],
        "instructions": "落实四库物理隔离：canon.db 只读、world.db 强事务、retrieval.db 幂等可重建。迁移变更需仲裁扩权。",
        "contracts": ["world_snapshot.schema.json", "state_delta.schema.json", "domain_event.schema.json"],
    },
    "AGT-AI": {
        "write": ["engine/ai/", "engine/application/", "engine/tests/"],
        "read": ["engine/ai/", "engine/application/", "engine/tests/", "contracts/"],
        "forbidden": ["macos-app/**", "engine/domain/**", "engine/infrastructure/**", ".hacf/**", ".github/**"],
        "gate_profile": "AI_GATEWAY_P0",
        "risk_class": "high",
        "invariants": [5, 6, 7, 8],
        "instructions": "AI 仅产出类型化 Proposal；语义授权先行，严禁直接执行写库事务。",
        "contracts": ["context_packet.schema.json", "context_request.schema.json", "proposal.schema.json"],
    },
    "AGT-VOICE": {
        "write": ["engine/domain/audio_voice.py", "engine/infrastructure/audio/", "engine/tests/test_audio_adapter.py"],
        "read": ["engine/domain/", "engine/infrastructure/audio/", "engine/tests/", "contracts/"],
        "forbidden": ["macos-app/**", "engine/ai/**", ".hacf/**", ".github/**"],
        "gate_profile": "VOICE_P0",
        "risk_class": "medium",
        "invariants": [9],
        "instructions": "维护 OpenAI Audio API 规范对接与 SpeechRail 热拔插，落实内容寻址缓存与静音降级。",
        "contracts": ["audio_asset_ref.schema.json", "performance_plan.schema.json"],
    },
    "AGT-MAC": {
        "write": ["macos-app/WorldOfMysteries/", "macos-app/WorldOfMysteriesTests/"],
        "read": ["macos-app/", "contracts/", "docs/03_工程规范/"],
        "forbidden": ["engine/**", ".hacf/**", ".github/**"],
        "gate_profile": "MACOS_APP_P0",
        "risk_class": "medium",
        "invariants": [12],
        "instructions": "遵循 Swift 6 严格并发与 SwiftUI @Observable 规范，严格通过 UDS IPC 驱动，零直接数据库访问。",
        "contracts": ["engine_ipc.schema.json", "narrative_block.schema.json"],
    },
    "AGT-QA": {
        "write": ["engine/tests/", "macos-app/WorldOfMysteriesTests/", "fixtures/golden_001/"],
        "read": ["engine/", "macos-app/", "contracts/", "fixtures/", "docs/"],
        "forbidden": [
            "engine/domain/**",
            "engine/application/**",
            "engine/ai/**",
            "engine/infrastructure/**",
            "macos-app/WorldOfMysteries/**",
            ".hacf/**",
            ".github/**",
        ],
        "gate_profile": "FULL_P0",
        "risk_class": "high",
        "invariants": list(range(1, 16)),
        "instructions": "作为裁决者与质检门禁。只读实现、只写断言；严禁为通过测试而放宽黄金断言。",
        "contracts": ["episode.schema.json", "turn_transaction.schema.json", "engine_ipc.schema.json"],
    },
    "AGT-ARB": {
        "write": [
            "docs/",
            "contracts/",
            "scripts/",
            ".hacf/",
            ".github/",
            ".agents/",
            "AGENTS.md",
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".gitignore",
            "engine/tests/test_hacf_governance.py",
            "engine/tests/test_contracts_schema.py",
        ],
        "read": ["."],
        "forbidden": [
            "engine/domain/**",
            "engine/infrastructure/**",
            "engine/ai/**",
            "macos-app/**",
            "fixtures/**",
        ],
        "gate_profile": "FULL_P0",
        "risk_class": "privileged",
        "invariants": list(range(1, 16)),
        "instructions": "主架构师与调度仲裁者。负责需求分解、胶囊派发、架构适应度评估、扩权审批与冲突仲裁。",
        "contracts": ["engine_ipc.schema.json", "task_capsule.schema.json"],
    },
}

CONTEXT_TOKEN_BUDGET = 3000


def extract_symbols(targets: List[str]) -> List[Dict[str, str]]:
    """扫描授权目录，抽取类/函数符号及其定义位置。"""
    symbols: List[Dict[str, str]] = []
    for target in targets:
        path = REPO_ROOT / target
        if path.is_file() and path.suffix == ".py":
            files = [path]
        elif path.is_dir():
            files = sorted(path.glob("**/*.py"))
        else:
            continue
        for file_path in files:
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            rel = file_path.relative_to(REPO_ROOT)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        {"symbol": node.name, "file": str(rel), "line": str(node.lineno)}
                    )
    return symbols


def rank_symbols(
    symbols: List[Dict[str, str]], focus: List[str], limit: int = 30
) -> tuple[List[Dict[str, str]], str]:
    """按任务焦点排序切片：命中焦点词的符号优先，避免「按目录静态取前 N 个」。"""
    if not symbols:
        return [], "empty"
    if not focus:
        return symbols[:limit], "static-scope-order"

    tokens = [t.lower() for t in focus if t]
    focused, rest = [], []
    for item in symbols:
        haystack = f"{item['symbol']} {item['file']}".lower()
        (focused if any(t in haystack for t in tokens) else rest).append(item)
    if not focused:
        return rest[:limit], "focus-unmatched(static-scope-order)"
    return (focused + rest)[:limit], "focus-ranked"


def pack_capsule(
    role: str,
    task_id: str,
    title: str,
    output_file: Optional[str] = None,
    focus: Optional[List[str]] = None,
    grants: Optional[List[str]] = None,
    risk_class: Optional[str] = None,
    depends_on: Optional[List[str]] = None,
    conflicts_with: Optional[List[str]] = None,
    supersedes: Optional[str] = None,
) -> Path:
    """生成自包含任务胶囊（不可变契约）。"""
    if role not in ROLE_DEFAULTS:
        raise ValueError(f"Unknown role '{role}'. Choose from {list(ROLE_DEFAULTS.keys())}")

    defaults = ROLE_DEFAULTS[role]
    target_ref = policy.run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    base_sha = policy.run_git(["rev-parse", "HEAD"])
    target_sha = policy.run_git(["rev-parse", "main"]) if target_ref != "main" else base_sha

    profile, profile_path, profile_digest = gate_profile.resolve_profile(
        defaults["gate_profile"]
    )

    focus_tokens = list(focus or []) + [w for w in task_id.replace("-", " ").split() if len(w) > 2]
    symbols, strategy = rank_symbols(extract_symbols(defaults["write"]), focus_tokens)

    context_snapshot = policy.canonical_json_digest(
        {
            "write_scope": defaults["write"],
            "symbols": symbols,
            "contracts": defaults["contracts"],
            "gate_profile_digest": profile_digest,
            "base_sha": base_sha,
        }
    )
    token_estimate = len(json.dumps(symbols, ensure_ascii=False)) // 4

    capsule = {
        "$schema": "contracts/engineering/task_capsule.schema.json",
        "capsule_id": f"CAP-{task_id}",
        "capsule_revision": 2 if supersedes else 1,
        "task_id": task_id,
        "title": title,
        "assigned_role": role,
        "status": "CREATED",
        "created_at": policy.now_iso(),
        "risk_class": risk_class or defaults["risk_class"],
        "base": {
            "target_ref": target_ref,
            "base_sha": base_sha,
            "target_sha": target_sha,
            "context_snapshot": f"sha256:{context_snapshot}",
        },
        "scope": {
            "read": defaults["read"],
            "write": defaults["write"],
            "forbidden": defaults["forbidden"],
            "privileged_grants": grants or [],
        },
        "context": {
            "core_manifest": [
                f"symbol:{s['symbol']}@{s['file']}:{s['line']}" for s in symbols
            ],
            "related_contracts": defaults["contracts"],
            "slice_strategy": strategy,
            "token_estimate": token_estimate,
            "max_core_tokens": CONTEXT_TOKEN_BUDGET,
            "expansion_policy": "arbiter_approved",
            "note": "上下文为最小充分集而非最小集：不足时可申请扩权/扩上下文并生成胶囊修订版。",
        },
        "impact": {
            "symbols": [s["symbol"] for s in symbols],
            "contracts": defaults["contracts"],
            "tests": [],
        },
        "dependencies": {
            "depends_on": depends_on or [],
            "conflicts_with": conflicts_with or [],
        },
        "gates": {
            "profile": defaults["gate_profile"],
            "profile_digest": f"sha256:{profile_digest}",
            "profile_file": str(profile_path.relative_to(REPO_ROOT)),
            "risk_class": profile.get("risk_class", "medium"),
        },
        "acceptance": {
            "invariants": defaults["invariants"],
            "instructions": defaults["instructions"],
            "assertions": [f"INV-{i:02d}" for i in defaults["invariants"]],
        },
    }
    if supersedes:
        capsule["supersedes"] = supersedes

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = REPO_ROOT / ".agents" / "capsules"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}.json"

    out_path.write_text(
        json.dumps(capsule, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f" [AgentCapsule] packed capsule for {role} -> {out_path}")
    print(f"   Task: [{task_id}] {title}")
    print(f"   Slice strategy: {strategy} · symbols={len(symbols)} (~{token_estimate} tokens)")
    print(f"   Gate profile: {defaults['gate_profile']} · sha256:{profile_digest[:16]}…")
    print(f"   Write scope: {defaults['write']}")
    if grants:
        print(f"   Privileged grants: {grants}")
    return out_path


def verify_capsule(
    capsule_path: Path,
    cwd: Path = REPO_ROOT,
    allow_stale: bool = False,
    log_dir: Optional[Path] = None,
) -> bool:
    """范围裁决 + 受保护门禁执行 + 生成 Work Receipt。绝不回写胶囊。"""
    capsule = policy.load_capsule(capsule_path)
    capsule_digest = policy.capsule_digest(capsule_path)
    started_at = policy.now_iso()

    print(f" [AgentCapsule] verifying task [{capsule['task_id']}] {capsule['title']}")
    print(f"   role={capsule['assigned_role']} · risk={capsule.get('risk_class')} · revision={capsule.get('capsule_revision')}")
    print(f"   capsule_digest=sha256:{capsule_digest[:32]}… (胶囊不被回写)")

    head_commit = policy.run_git(["rev-parse", "HEAD"], cwd=cwd)
    target_ref = capsule["base"]["target_ref"]
    base_commit = capsule["base"]["base_sha"]

    # 1. 上下文陈旧性：目标分支已前进则要求重新出单
    target_sha_now = policy.run_git(["rev-parse", target_ref], cwd=cwd)
    stale_context = target_sha_now != capsule["base"]["target_sha"]
    if stale_context:
        print(
            f"\n⚠️  [STALE CONTEXT] '{target_ref}' 已从 {capsule['base']['target_sha'][:12]} "
            f"前进到 {target_sha_now[:12]}"
        )
        print("   请在最新目标基线上重新 pack（生成胶囊修订版）后再验收。")
        if not allow_stale:
            print("   （仅调试可用 --allow-stale 跳过；凭单会记录 stale_context=true）")
            return _emit_failed_receipt(
                capsule, capsule_digest, started_at, cwd, head_commit, target_ref,
                target_sha_now, stale_context, [], "验证在陈旧上下文上被拒绝执行",
            )

    # 2. 范围裁决
    files = policy.changed_files(cwd=cwd)
    audit = policy.audit_scope(capsule, files)
    print(f"\n️  Scope audit · changed files: {len(files)}")
    for violation in audit["violations"]:
        print(f"   ❌ [SCOPE BREACH] {violation['path']} — {violation['reason']}")
    for escalation in audit["escalations"]:
        print(f"    [SCOPE_ESCALATION_REQUIRED] {escalation['path']} — {escalation['reason']}")
    for granted in audit["privileged_uses"]:
        print(f"   🔐 [privileged] {granted}")
    if not (audit["violations"] or audit["escalations"]):
        print("   ✅ 所有变更均在授权范围内")

    if audit["privileged_uses"] and capsule.get("risk_class") not in ("high", "privileged"):
        print(
            "\n 触碰高风险面要求 risk_class 至少为 high，请重新 pack 并注明扩权理由。"
        )
        audit["escalations"].append(
            {"path": ", ".join(audit["privileged_uses"]), "reason": "risk_class 过低"}
        )

    if audit["violations"] or audit["escalations"]:
        return _emit_failed_receipt(
            capsule, capsule_digest, started_at, cwd, head_commit, target_ref,
            target_sha_now, stale_context, audit, "范围裁决未通过",
        )

    # 3. 受保护门禁执行
    workspace_root = cwd
    lease = policy.load_workspace_lease(workspace_root)
    profile_id = capsule["gates"]["profile"]
    print(f"\n🚦 Executing protected gate profile '{profile_id}' …")
    try:
        gate_result = gate_profile.run_profile(
            profile_id,
            cwd=workspace_root,
            log_dir=log_dir or policy.log_dir_for(workspace_root, capsule["task_id"], head_commit),
            env_overrides=policy.env_overrides_from_lease(lease),
        )
    except gate_profile.GateProfileError as exc:
        print(f" {exc}")
        gate_result = {
            "gate_profile_id": profile_id,
            "gate_profile_digest": capsule["gates"].get("profile_digest"),
            "result": "failed",
            "stages": [],
            "coverage_gaps": [str(exc)],
        }

    # 4. 摘要链校验：胶囊记录的 profile 摘要必须与受保护档案一致
    if gate_result.get("gate_profile_digest") and gate_result["gate_profile_digest"] != capsule["gates"].get("profile_digest"):
        print(
            "❌ 门禁档案摘要与胶囊记录不一致：\n"
            f"   capsule : {capsule['gates'].get('profile_digest')}\n"
            f"   actual  : {gate_result['gate_profile_digest']}"
        )
        gate_result["result"] = "failed"
        gate_result.setdefault("coverage_gaps", []).append("gate profile digest mismatch")

    verdict = "passed" if gate_result.get("result") == "passed" else "failed"
    receipt = policy.build_receipt(
        receipt_type="work",
        capsule=capsule,
        capsule_digest_value=capsule_digest,
        gate_result=gate_result,
        scope_audit=audit,
        base_commit=base_commit,
        head_commit=head_commit,
        diff_digest_value=policy.changes_digest(base_commit, head_commit, cwd=workspace_root),
        target_ref=target_ref,
        target_sha=target_sha_now,
        stale_context=stale_context,
        toolchain=gate_profile.collect_toolchain(REPO_ROOT),
        started_at=started_at,
        verdict=verdict,
    )
    receipt_path = policy.write_receipt(workspace_root, receipt, head_commit)
    print("\n" + "=" * 66)
    if verdict == "passed":
        print("🎉 [AgentCapsule] Work Receipt 已签发（摘要记录，非密码学签名）")
    else:
        print("❌ [AgentCapsule] 验收未通过，Receipt 记录失败证据")
    policy.print_receipt_summary(receipt, receipt_path)
    print("=" * 66)
    return verdict == "passed"


def _emit_failed_receipt(
    capsule: Dict[str, Any],
    capsule_digest: str,
    started_at: str,
    cwd: Path,
    head_commit: str,
    target_ref: str,
    target_sha: str,
    stale_context: bool,
    audit: Dict[str, Any],
    reason: str,
) -> bool:
    receipt = policy.build_receipt(
        receipt_type="work",
        capsule=capsule,
        capsule_digest_value=capsule_digest,
        gate_result={
            "gate_profile_id": capsule["gates"]["profile"],
            "gate_profile_digest": capsule["gates"].get("profile_digest"),
            "result": "not_run",
            "stages": [],
            "coverage_gaps": [reason],
        },
        scope_audit=audit,
        base_commit=capsule["base"]["base_sha"],
        head_commit=head_commit,
        diff_digest_value=policy.changes_digest(
            capsule["base"]["base_sha"], head_commit, cwd=cwd
        ),
        target_ref=target_ref,
        target_sha=target_sha,
        stale_context=stale_context,
        toolchain={},
        started_at=started_at,
        verdict="failed",
        notes=[reason],
    )
    receipt_path = policy.write_receipt(cwd, receipt, head_commit)
    print(f"\n❌ 拒绝签发放行凭单：{reason}")
    policy.print_receipt_summary(receipt, receipt_path)
    return False


def show_capsule(capsule_path: Path) -> None:
    capsule = policy.load_capsule(capsule_path)
    print("\n" + "=" * 60)
    print(f"🏷️  Task Capsule: {capsule['capsule_id']} (revision {capsule.get('capsule_revision', 1)})")
    print(f"📋 Title: {capsule['title']}")
    print(f"👤 Role: {capsule['assigned_role']} | Status: {capsule.get('status')} | Risk: {capsule.get('risk_class')}")
    print("=" * 60)
    print(f"📁 write scope : {', '.join(capsule['scope']['write'])}")
    print(f" forbidden   : {', '.join(capsule['scope']['forbidden'])}")
    if capsule["scope"].get("privileged_grants"):
        print(f"🔐 grants      : {', '.join(capsule['scope']['privileged_grants'])}")
    print(f"🚦 gate profile: {capsule['gates']['profile']} ({capsule['gates']['profile_digest']})")
    print(f"🧾 base        : {capsule['base']['target_ref']}@{capsule['base']['target_sha'][:12]}")
    print(f"🛡️  invariants  : {capsule['acceptance']['invariants']}")
    print(f"🔬 slice       : {capsule['context']['slice_strategy']} · ~{capsule['context']['token_estimate']} tokens")
    for symbol in capsule["context"]["core_manifest"][:8]:
        print(f"   • {symbol}")
    print(f"💡 {capsule['acceptance']['instructions']}")
    print("=" * 60 + "\n")


def list_receipts(task_id: Optional[str] = None) -> None:
    base = REPO_ROOT / policy.RECEIPTS_DIR
    if not base.exists():
        print("ℹ️ 尚未生成任何 receipt。")
        return
    pattern = f"{task_id}/*.json" if task_id else "*/*.json"
    for receipt_file in sorted(base.glob(pattern)):
        try:
            receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        icon = "✅" if receipt.get("verdict") == "passed" else "❌"
        print(
            f"{icon} {receipt.get('receipt_type'):<11} {receipt.get('task_id'):<22} "
            f"head={str(receipt.get('head_commit'))[:12]} "
            f"gates={receipt.get('gate_result')} "
            f"gaps={len(receipt.get('coverage_gaps', []))} -> {receipt_file.relative_to(REPO_ROOT)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentCapsule CLI (HACF 2.1)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack_parser = subparsers.add_parser("pack", help="生成任务胶囊（受保护门禁引用 + 焦点切片）")
    pack_parser.add_argument("--role", required=True, choices=list(ROLE_DEFAULTS.keys()))
    pack_parser.add_argument("--task-id", required=True)
    pack_parser.add_argument("--title", required=True)
    pack_parser.add_argument("--output", help="自定义输出路径")
    pack_parser.add_argument("--focus", help="逗号分隔的焦点符号/关键词，用于排序切片")
    pack_parser.add_argument(
        "--grant-privileged",
        help="仲裁扩权：逗号分隔的高风险面 glob（如 contracts/schemas/world_event.schema.json）",
    )
    pack_parser.add_argument("--risk-class", choices=["low", "medium", "high", "privileged"])
    pack_parser.add_argument("--depends-on", help="逗号分隔的前置任务")
    pack_parser.add_argument("--conflicts-with", help="逗号分隔的互斥任务")
    pack_parser.add_argument("--supersedes", help="被本修订版取代的取消胶囊 id")

    verify_parser = subparsers.add_parser("verify", help="范围裁决 + 门禁执行 + 签发 Work Receipt")
    verify_parser.add_argument("--capsule", required=True)
    verify_parser.add_argument("--cwd", default=str(REPO_ROOT), help="执行工作区（worktree 场景）")
    verify_parser.add_argument("--allow-stale", action="store_true", help="调试用：允许在陈旧上下文上执行")

    show_parser = subparsers.add_parser("show", help="展示胶囊摘要")
    show_parser.add_argument("--capsule", required=True)

    receipts_parser = subparsers.add_parser("receipts", help="列出已签发凭单")
    receipts_parser.add_argument("--task-id")

    args = parser.parse_args()
    try:
        if args.command == "pack":
            pack_capsule(
                args.role,
                args.task_id,
                args.title,
                args.output,
                focus=args.focus.split(",") if args.focus else None,
                grants=args.grant_privileged.split(",") if args.grant_privileged else None,
                risk_class=args.risk_class,
                depends_on=args.depends_on.split(",") if args.depends_on else None,
                conflicts_with=args.conflicts_with.split(",") if args.conflicts_with else None,
                supersedes=args.supersedes,
            )
            return 0
        if args.command == "verify":
            ok = verify_capsule(
                Path(args.capsule), cwd=Path(args.cwd).resolve(), allow_stale=args.allow_stale
            )
            return 0 if ok else 1
        if args.command == "show":
            show_capsule(Path(args.capsule))
            return 0
        if args.command == "receipts":
            list_receipts(args.task_id)
            return 0
    except (ValueError, policy.PolicyError, gate_profile.GateProfileError) as exc:
        print(f"❌ {exc}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
