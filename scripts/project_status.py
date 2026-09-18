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
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT_DIR / "docs" / "PROJECT_STATE.json"


def load_state() -> dict:
    if not STATE_FILE.exists():
        print(f"❌ 错误: 未找到工程状态事实源文件: {STATE_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_status(state: dict, as_json: bool = False):
    if as_json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

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
        status_badge = "🟢" if m["status"] == "READY" else ("⚪" if m["status"] == "BLOCKED" else "🟡")
        deps = f" (前置依赖: {', '.join(m['depends_on'])})" if "depends_on" in m else ""
        print(f"  {status_badge} [{m['id']}] {m['name']} [{m['lead_role']}]{deps}")

    print("\n💡 提示: 运行 `python3 scripts/project_status.py next` 查看下一步科学推进方向。")
    print("=" * 72)


def cmd_next(state: dict, as_json: bool = False):
    cp = state["critical_path"]
    if as_json:
        print(json.dumps(cp, indent=2, ensure_ascii=False))
        return

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


def cmd_dispatch(state: dict, as_json: bool = False):
    dp = state["critical_path"]["dispatch"]
    if as_json:
        print(json.dumps(dp, indent=2, ensure_ascii=False))
        return

    print("=" * 72)
    print("🚀 《诡秘世界》自动化任务派发卡片 (Task Dispatch Voucher)")
    print("=" * 72)

    print(f"\n【指派专精角色】: {dp['assigned_role']} - {dp['role_title']}")
    print(f"【拟定任务标识】: {dp['task_id']}")
    print(f"【任务标准标题】: {dp['task_title']}")

    print("\n【授权工作目录范围 (Authorized Scope)】:")
    for scope in dp["authorized_scope"]:
        print(f"  - {scope}")

    print("\n【严格禁触红线 (Forbidden Patterns)】:")
    for fbd in dp["forbidden_patterns"]:
        print(f"  ⛔ {fbd}")

    print("\n【步骤 1: 生成强类型任务胶囊 (Pack Capsule)】")
    print(f"  {dp['pack_command']}")

    print("\n【步骤 2: 启动事务型隔离工作区 (Start Worktree)】")
    print(f"  {dp['worktree_command']}")

    print("\n【步骤 3: 专精角色编码完成后的验签合流指令】")
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

    args = parser.parse_args()

    state = load_state()

    if args.command == "status" or args.command is None:
        cmd_status(state, getattr(args, "json", False))
    elif args.command == "next":
        cmd_next(state, getattr(args, "json", False))
    elif args.command == "dispatch":
        cmd_dispatch(state, getattr(args, "json", False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
