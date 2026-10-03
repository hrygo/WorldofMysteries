#!/usr/bin/env python3
"""
project_status.py - 《诡秘世界》工程态势罗盘与调度导航 CLI

提供三大核心能力：
  1. status   - 宏观状态与进展报告（质量门禁、已达成里程碑、当前阶段）
  2. next     - 下一步推进方向与战略依赖原因（关键路径、交付成果、风险）
  3. dispatch - 明确人物指派、任务胶囊命令与工作区隔离指令
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT_DIR / "docs" / "PROJECT_STATE.json"
SCRIPTS_DIR = Path(__file__).resolve().parent

#: The pre-commit hook injects these, and a ``git`` call that inherits them is
#: hijacked back to the real repository even when cwd is an isolated worktree.
_GIT_ENV_POLLUTANTS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
)


def _git_env() -> dict:
    env = dict(os.environ)
    for key in _GIT_ENV_POLLUTANTS:
        env.pop(key, None)
    return env


def repository_tip(root: Path = ROOT_DIR) -> dict | None:
    """Date and short SHA of the newest commit the repository actually has."""
    for ref in ("origin/main", "HEAD"):
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cI %h", ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=_git_env(),
        )
        if res.returncode != 0 or not res.stdout.strip():
            continue
        committed, _, short = res.stdout.strip().partition(" ")
        try:
            return {"date": date.fromisoformat(committed[:10]), "sha": short}
        except ValueError:
            return None
    return None


def staleness(state: dict, root: Path = ROOT_DIR) -> dict | None:
    """How far this narrative sits behind the repository, or ``None`` if it does not.

    ``docs/PROJECT_STATE.json`` is prose, written once and then replayed verbatim
    by every ``status`` / ``next`` / ``dispatch`` call. The wom-navigator skill
    points at it as the 事实源, so a reader has no way to tell that the baseline
    it names is hundreds of commits old. A fact source that is quietly stale is
    worse than none, because it still gets trusted.
    """
    try:
        recorded = date.fromisoformat(str(state["last_updated"])[:10])
    except (KeyError, ValueError):
        return None
    tip = repository_tip(root)
    if tip is None or tip["date"] <= recorded:
        return None
    return {
        "recorded": recorded.isoformat(),
        "tip_date": tip["date"].isoformat(),
        "tip_sha": tip["sha"],
        "days_behind": (tip["date"] - recorded).days,
    }


def _warn_if_stale(state: dict, root: Path = ROOT_DIR) -> None:
    gap = staleness(state, root)
    if gap is None:
        return
    print(
        f"⚠️  本报告的事实源落后于仓库 {gap['days_behind']} 天："
        f"叙述描述的是 {gap['recorded']} 的状态，"
        f"而仓库最新提交是 {gap['tip_date']} {gap['tip_sha']}。",
        file=sys.stderr,
    )
    print(
        "   以下里程碑与门禁结论属于历史记录，不代表当前仓库状态；以 git log 与 CI 为准。",
        file=sys.stderr,
    )


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"❌ 错误: 未找到工程状态事实源文件: {STATE_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def role_scope(role: str) -> dict:
    """Read a role's authoritative scope out of ``agent_capsule.ROLE_DEFAULTS``.

    ``docs/PROJECT_STATE.json`` used to restate each dispatch card's authorized
    scope and forbidden patterns in prose, and the restatements drifted: a card
    could name a directory the capsule would later adjudicate as out of scope,
    while omitting one the role really holds. The card is handed to the next
    agent verbatim, so a drifted restatement is worse than no statement — it is
    a confident wrong answer. Scope has exactly one source, and this reads it.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from agent_capsule import ROLE_DEFAULTS

    defaults = ROLE_DEFAULTS.get(role)
    if defaults is None:
        return {}
    return defaults


def cmd_status(state: dict, as_json: bool = False):
    if as_json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    _warn_if_stale(state)
    curr = state["current_phase"]
    gates = state["gates_health"]
    completed = state["completed_phases"]

    print("=" * 72)
    print(f"🧭 《{state['project_name']}》工程宏观态势与进展报告 (v{state['version']})")
    print(f"📅 最新对齐基准: {state['last_updated']} | 当前运行阶段: {curr['phase_id']} {curr['phase_name']}")
    print("=" * 72)

    print("\n【1. 当前阶段态势】")
    print(f"  • 阶段标识: {curr['phase_id']}")
    print(f"  • 当前状态: {curr['status']}")
    print(f"  • 态势简报: {curr['progress_summary']}")

    print("\n【2. 本地与云端质量门禁现状】")
    for gate_name, gate_val in gates.items():
        print(f"  • {gate_name.upper():<20}: {gate_val}")

    print("\n【3. 已完成里程碑阶段 (Completed Deliverables)】")
    for cp in completed:
        print(f"  ✅ {cp['phase_id']}: {cp['phase_name']} (验收时间: {cp['completed_at']})")
        for d in cp["key_deliverables"]:
            print(f"     - {d}")

    print("\n【4. 全局里程碑推进全景】")
    for m in state["milestones"]:
        status = m["status"]
        status_badge = {
            "COMPLETED": "✅",
            "READY": "🟢",
            "IN_PROGRESS": "🟡",
            "BLOCKED": "⚪",
        }.get(status, "❓")
        deps = f" (前置依赖: {', '.join(m['depends_on'])})" if "depends_on" in m else ""
        print(f"  {status_badge} [{m['id']}] {m['name']} [{m['lead_role']}] [{status}]{deps}")

    pending = state.get("pending_decisions") or []
    if pending:
        print("\n【5. 待人类裁决 (Pending Decisions)】")
        print("   以下各项均需产品语义或架构裁决才能推进；未裁决前不得当作可执行任务派发。")
        for item in pending:
            print(f"\n   ⏸ {item['id']}")
            print(f"      问题: {item['question']}")
            print(f"      出处: {item.get('evidence') or '（尚无权威文档，需先补提案）'}")
            print(f"      卡住原因: {item['why_blocking']}")
            print(f"      裁决后解锁: {item['unblocks']}")

    unwired = state.get("verified_unwired") or []
    if unwired:
        print("\n【6. 已证实但未接线的子系统 (Verified Unwired)】")
        print("   以下各项不是待裁决缺陷，而是机制已建好、却没有任何生产调用方。")
        for item in unwired:
            print(f"\n   🔌 {item['id']}")
            print(f"      结论: {item['claim']}")
            print(f"      后果: {item['consequence']}")
            print(f"      仍需裁决: {item['remaining_decision']}")
            print(f"      撤回: {item['retracts']}")

    gaps = state.get("verified_gaps") or []
    if gaps:
        print("\n【7. 已证实的规格缺口 (Verified Gaps)】")
        print("   以下各项不是待裁决缺陷，而是规格明列、代码未实现；不受 gated_by 门控。")
        for item in gaps:
            print(f"\n   🕳 {item['id']}")
            print(f"      结论: {item['claim']}")
            print(f"      为什么是缺口: {item['why_it_is_a_gap']}")
            if item.get("readiness"):
                print(f"      可推进性: {item['readiness']}")
            print(f"      需参与角色: {'、'.join(item['roles_required'])}")
            print(f"      边界: {item['not_decided_here']}")

    print("\n💡 提示: 运行 `python3 scripts/project_status.py next` 查看下一步科学推进方向。")
    print("=" * 72)


def cmd_next(state: dict, as_json: bool = False):
    cp = state["critical_path"]
    if as_json:
        print(json.dumps(cp, indent=2, ensure_ascii=False))
        return

    _warn_if_stale(state)
    print("=" * 72)
    print("🎯 《诡秘世界》关键路径推进决策导航 (Next Strategic Direction)")
    print("=" * 72)

    print(f"\n【核心推进目标】: [{cp['next_milestone_id']}] {cp['next_milestone_name']}")

    print("\n【为什么是这个方向 (科学依赖论证)】:")
    print(f"  {cp['strategic_rationale']}")

    print("\n【本阶段硬性交付成果 (Target Deliverables)】:")
    for i, item in enumerate(cp["target_deliverables"], 1):
        print(f"  {i}. {item}")

    print("\n【协同专精角色】:")
    dp = cp["dispatch"]
    print(f"  • 责任人: {dp['assigned_role']} ({dp['role_title']})")
    print(f"  • 任务代号: {dp['task_id']}")

    print("\n💡 提示: 运行 `python3 scripts/project_status.py dispatch` 获取即刻派发指令。")
    print("=" * 72)


def cmd_dispatch(state: dict, as_json: bool = False, governed: bool = False):
    dp = state["critical_path"]["dispatch"]
    scope = role_scope(dp["assigned_role"])
    write_scope = scope.get("write", [])
    read_scope = scope.get("read", [])
    forbidden = scope.get("forbidden", [])
    if as_json:
        merged = dict(dp)
        merged.pop("authorized_scope", None)
        merged.pop("forbidden_patterns", None)
        merged["workflow_mode"] = "governed" if governed else "lightweight"
        if not governed:
            merged.pop("pack_command", None)
            merged.pop("worktree_command", None)
        merged["role_scope_source"] = f"scripts/agent_capsule.py::ROLE_DEFAULTS[{dp['assigned_role']}]"
        merged["write"] = write_scope
        merged["read"] = read_scope
        merged["forbidden"] = forbidden
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        return

    _warn_if_stale(state)
    print("=" * 72)
    print("🚀 《诡秘世界》任务建议")
    print("=" * 72)

    print(f"\n【指派专精角色】: {dp['assigned_role']} - {dp['role_title']}")
    print(f"【拟定任务标识】: {dp['task_id']}")
    print(f"【任务标准标题】: {dp['task_title']}")

    print("\n【可选治理角色范围 — 单一事实源: agent_capsule.ROLE_DEFAULTS】:")
    print("  角色范围仅供显式治理模式使用；日常任务以用户授权和产品模块边界为准。")
    if not scope:
        print(f"  ❌ 角色 {dp['assigned_role']} 不在 ROLE_DEFAULTS 枚举内，无法给出授权范围。")
    else:
        print("  ✍️  可写 (write):")
        for item in write_scope:
            print(f"     - {item}")
        print("  👁️  可读 (read):")
        for item in read_scope:
            print(f"     - {item}")

    print("\n【可选治理角色禁区 (Forbidden Patterns) — 同一事实源】:")
    for fbd in forbidden:
        print(f"  ⛔ {fbd}")
    if scope:
        print(f"  门禁档案: {scope.get('gate_profile')} · 风险等级: {scope.get('risk_class')}")
        if scope.get("invariants"):
            print(f"  关联不变量: {', '.join(str(i) for i in scope['invariants'])}")

    if not governed:
        print("\n【默认轻量流程】")
        print("  功能分支开发 → 按改动面验证 → PR → CI 与评审。")
        print("  无需胶囊、凭单或按角色拆分；并行写入或工作区不干净时按需隔离。")
        print("  旧治理步骤仅在 dispatch --governed 中显示。")
    else:
        print("\n【可选治理步骤 1: 生成任务胶囊 (Pack Capsule)】")
        print(f"  {dp['pack_command']}")

        print("\n【可选治理步骤 2: 启动隔离工作区 (Start Worktree)】")
        print(f"  {dp['worktree_command']}")

        print("\n【可选治理步骤 3: 验证与本地集成预演】")
        print(f"  python3 scripts/agent_capsule.py verify --capsule .agents/capsules/{dp['task_id']}.json")
        print(f"  python3 scripts/collab_pipeline.py integrate --branch feat/{dp['task_id'].lower()} --auto-clean")
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="《诡秘世界》工程态势罗盘与调度导航 CLI")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    p_status = subparsers.add_parser("status", help="输出当前工程宏观状态与进展")
    p_status.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_next = subparsers.add_parser("next", help="输出下一步清晰科学的推进方向与战略依赖")
    p_next.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_dispatch = subparsers.add_parser("dispatch", help="输出明确的被派发人物与可执行派发命令")
    p_dispatch.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    p_dispatch.add_argument("--governed", action="store_true", help="显式显示旧胶囊治理步骤")

    args = parser.parse_args()

    state = load_state()

    if args.command == "status" or args.command is None:
        cmd_status(state, getattr(args, "json", False))
    elif args.command == "next":
        cmd_next(state, getattr(args, "json", False))
    elif args.command == "dispatch":
        cmd_dispatch(state, getattr(args, "json", False), args.governed)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
