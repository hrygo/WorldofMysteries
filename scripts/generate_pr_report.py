#!/usr/bin/env python3
"""
PR 质量卡片生成器 (HACF 2.1)

诚实性约束：本卡片只复述**本地凭单中真实记录的事实**，不宣称任何测试通过状态。
门禁权威结论只能来自 CI required checks（ci.yml / capsule-audit.yml）。
HACF 2.0 曾在此处硬编码「✅ PASSED」，本版本移除该行为。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hacf_policy as policy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_capsules() -> List[Dict[str, Any]]:
    # 优先检测当前分支相对于 base 分支的 diff 中是否存在胶囊变更
    import os
    import subprocess
    base_ref = os.getenv("GITHUB_BASE_REF", "main")
    res = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    changed = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    changed_capsules = [
        REPO_ROOT / f for f in changed if f.startswith(".agents/capsules/") and f.endswith(".json")
    ]
    candidate_paths = changed_capsules if changed_capsules else []

    capsules: List[Dict[str, Any]] = []
    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_path"] = str(path.relative_to(REPO_ROOT))
        try:
            payload["_digest"] = policy.capsule_digest(path)
        except OSError:
            payload["_digest"] = ""
        capsules.append(payload)
    return capsules


def load_receipts(task_id: str) -> List[Dict[str, Any]]:
    receipts: List[Dict[str, Any]] = []
    directory = REPO_ROOT / policy.RECEIPTS_DIR / task_id
    if not directory.exists():
        return receipts
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_path"] = str(path.relative_to(REPO_ROOT))
        receipts.append(payload)
    return receipts


def _verdict_badge(verdict: str) -> str:
    return {"passed": "✅ passed", "failed": "❌ failed"}.get(verdict, f"⚠️ {verdict}")


def generate_report() -> str:
    import os
    actor = os.getenv("GITHUB_ACTOR", "")
    head_ref = os.getenv("GITHUB_HEAD_REF", "")
    is_maintenance = "dependabot" in actor.lower() or head_ref.startswith("dependabot/")

    capsules = load_capsules()

    if capsules:
        capsule = capsules[0]
        receipts = load_receipts(str(capsule.get("task_id")))
        capsule_rows = [
            f"| **任务胶囊 (Capsule)** | `{capsule.get('capsule_id')}` rev{capsule.get('capsule_revision', 1)} | {capsule.get('title')} |",
            f"| **契约位置 (Path)** | `{capsule.get('_path')}` | 不可变契约，verify 不回写 |",
            f"| **执行角色 (Role)** | `{capsule.get('assigned_role')}` | risk_class=`{capsule.get('risk_class')}` |",
            f"| **胶囊摘要 (Digest)** | `sha256:{str(capsule.get('_digest'))[:16]}…` | 变更后需重新验收 |",
            f"| **基线 (Base)** | `{str(capsule.get('base', {}).get('target_sha'))[:12]}` | target=`{capsule.get('base', {}).get('target_ref')}` |",
            f"| **门禁档案 (Gate Profile)** | `{capsule.get('gates', {}).get('profile')}` | `{str(capsule.get('gates', {}).get('profile_digest'))[:20]}…` |",
        ]
        capsule_block = "\n".join(capsule_rows)
    elif is_maintenance:
        capsule_block = "| **PR 类型** | 🤖 自动化维护 / 依赖升级 PR (Dependabot / Maintenance) | 本 PR 免除业务任务胶囊，由 CI 3-Stage 门禁独立质检 |"
        receipts = []
    else:
        capsule_block = "| **任务胶囊 (Capsule)** | ℹ️ 未附带业务胶囊 | 本 PR 未引入 `.agents/capsules/*.json` 变更 |"
        receipts = []

    if receipts:
        receipt_rows = [
            "| 类型 | head_commit | verdict | 门禁档案摘要 | 覆盖缺口 |",
            "|:---|:---|:---:|:---|:---:|",
        ]
        for receipt in receipts:
            receipt_rows.append(
                f"| `{receipt.get('receipt_type')}` | `{str(receipt.get('head_commit'))[:12]}` "
                f"| {_verdict_badge(str(receipt.get('verdict')))} "
                f"| `{str(receipt.get('gate_profile_digest'))[:20]}…` "
                f"| {len(receipt.get('coverage_gaps', []))} |"
            )
        receipt_block = "\n".join(receipt_rows)
        gap_lines: List[str] = []
        for receipt in receipts:
            for gap in receipt.get("coverage_gaps", []):
                gap_lines.append(f"- `{receipt.get('head_commit', '')[:12]}` {gap}")
        gap_block = "\n".join(gap_lines) if gap_lines else "无覆盖缺口记录。"
    else:
        receipt_block = "| ⚠️ 未找到凭单 | — | — | — | — |"
        gap_block = "尚未生成 `Work Receipt`：请在工作区执行 `python3 scripts/agent_capsule.py verify --capsule <capsule>`。"

    return f"""## 🛡️ 《诡秘世界》协同证据摘要 (Evidence Summary)

| 项目 | 值 | 说明 |
|:---|:---|:---|
{capsule_block}

### 本 PR 携带的凭单 (Receipts)

{receipt_block}

### 覆盖缺口 (Coverage Gaps)

{gap_block}

> 本卡片只复述仓库内凭单的真实记录，**不代表测试通过**。
> 门禁权威结论以 CI required checks（`ci.yml` 三阶段 + `capsule-audit.yml` 证据审计）为准；
> 摘要为 sha256 内容摘要，不是密码学签名，抗伪造由受保护分支与 CODEOWNERS 评审承担。
"""


if __name__ == "__main__":
    report_text = generate_report()
    out_file = REPO_ROOT / "pr_report.md"
    out_file.write_text(report_text, encoding="utf-8")
    print(report_text)
