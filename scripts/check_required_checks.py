#!/usr/bin/env python3
"""必需检查契约守卫（HACF 2.1 优化项）。

分支保护按『检查名』匹配。一旦有人在 workflow 里改了 job 的 `name`，
已配置的必需检查就永远等不到结果，PR 会永久卡在 pending —— 这比失败更难排查。

本脚本把必需检查名当成公开接口来守护：解析 `.github/workflows/*.yml` 里每个 job
实际暴露的检查名，断言契约文件里声明的名字都存在。改名会在 CI 立刻变红，
而不是在合并时静默死锁。

只读、无第三方依赖：不引入 PyYAML，按缩进扫描 job 块。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / ".hacf" / "required-checks.json"

JOB_KEY_RE = re.compile(r"^ {2}([A-Za-z0-9_.\-]+):\s*$")
NAME_RE = re.compile(r"^ {4,}name:\s*(.+?)\s*$")


def job_check_names(workflow_path: Path) -> Dict[str, str]:
    """返回 {job_id: 暴露的检查名}。未显式声明 name 时，GitHub 以 job_id 作为检查名。"""
    text = workflow_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:
        return {}

    names: Dict[str, str] = {}
    current_job: str | None = None
    for line in lines[start + 1 :]:
        if line and not line.startswith(" ") and not line.startswith("#"):
            break  # 离开 jobs 块
        job_match = JOB_KEY_RE.match(line)
        if job_match:
            current_job = job_match.group(1)
            names.setdefault(current_job, current_job)
            continue
        if current_job:
            name_match = NAME_RE.match(line)
            if name_match and not names[current_job].strip().startswith("${{"):
                raw = name_match.group(1).strip()
                names[current_job] = raw.strip("\"'")
    return names


def exposed_check_names(repo_root: Path = REPO_ROOT) -> Dict[str, List[str]]:
    exposed: Dict[str, List[str]] = {}
    for workflow in sorted((repo_root / ".github" / "workflows").glob("*.yml")):
        for job_id, check_name in job_check_names(workflow).items():
            exposed.setdefault(check_name, []).append(
                f"{workflow.relative_to(repo_root)}:{job_id}"
            )
    return exposed


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"❌ 缺少必需检查契约文件: {CONTRACT_PATH.relative_to(REPO_ROOT)}")
        return 1
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    checks = contract.get("checks", [])
    exposed = exposed_check_names()

    problems: List[str] = []
    for entry in checks:
        context = entry.get("context", "")
        workflow = entry.get("workflow", "")
        if not context:
            problems.append("契约中存在空的 context")
            continue
        sources = exposed.get(context, [])
        declared = [
            f for f in sources if workflow and f.startswith(workflow + ":")
        ]
        if not declared:
            hint = f"（期望来自 {workflow}）" if workflow else ""
            found = f"，实际存在: {', '.join(sources)}" if sources else "，任何 workflow 都未暴露该检查名"
            problems.append(f"必需检查名失配: '{context}'{hint}{found}")
        else:
            flag = "必需" if entry.get("required", True) else "可选"
            print(f"✅ {flag}检查 '{context}' ← {', '.join(declared)}")

    if problems:
        print("\n❌ 必需检查契约被破坏：")
        for problem in problems:
            print(f"   - {problem}")
        print(
            "\n改名 workflow 的 job `name` 会让已配置的必需检查永久 pending。"
            "若确需改名，请同时更新 .hacf/required-checks.json 并执行 "
            "'python3 scripts/sync_branch_protection.py --apply'。"
        )
        return 1

    print(f"\n🎉 必需检查契约成立（{len(checks)} 项）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
