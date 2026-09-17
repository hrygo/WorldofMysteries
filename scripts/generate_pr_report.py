#!/usr/bin/env python3
"""
PR 质量卡片生成器 (HACF 2.1)

诚实性约束：本卡片只复述**本地凭单中真实记录的事实**，不宣称任何测试通过状态。
门禁权威结论只能来自 CI required checks（ci.yml / capsule-audit.yml）。
HACF 2.0 曾在此处硬编码「✅ PASSED」，本版本移除该行为。

检测约束：必须区分「确实没有变更」与「变更面判定本身失败」。
浅克隆（`actions/checkout` 默认 `fetch-depth: 1`）会让 `git diff base...HEAD`
因缺少 merge base 直接失败（exit 128 / 空 stdout）；此处禁止把执行失败
静默降级为「本 PR 未附带胶囊」，失败必须呈现到卡片上。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hacf_policy as policy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_env() -> Dict[str, str]:
    """剔除可能残留的 git 定位变量，强制以 `cwd` 解析仓库。

    git 钩子与部分 CI 包装器会注入 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE`；
    若继承这些变量，`git -C <workdir>` 语义会被静默改写，变更面判定将指向错误的仓库。
    """
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    return env


def _run_git(args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )


def detect_changed_files() -> Tuple[List[str], List[str]]:
    """返回 (相对 base 的变更文件, 判定过程中的失败说明)。

    浅克隆（`actions/checkout` 默认 `fetch-depth: 1`）下 `A...B` 会因缺少
    merge base 直接失败（exit 128 / 空 stdout）。此处逐级降级并保留失败证据，
    禁止把「判定失败」静默降级为「本 PR 没有变更」。
    """
    base_ref = os.getenv("GITHUB_BASE_REF", "main")
    failures: List[str] = []

    def _merge_base(left: str) -> str:
        res = _run_git(["merge-base", left, "HEAD"])
        if res.returncode != 0:
            raise RuntimeError((res.stderr or "缺少共同祖先").strip()[:160])
        return res.stdout.strip()

    three_dot = _run_git(["diff", "--name-only", f"origin/{base_ref}...HEAD"])
    if three_dot.returncode == 0:
        return [line.strip() for line in three_dot.stdout.splitlines() if line.strip()], failures
    failures.append(
        f"三点 diff（基准 origin/{base_ref}）失败：退出码 {three_dot.returncode}"
        f"（{(three_dot.stderr or '').strip()[:160]}）"
    )

    for label in (f"origin/{base_ref}", base_ref):
        try:
            base_commit = _merge_base(label)
        except RuntimeError as exc:
            failures.append(f"两点 diff（基准 {label}）失败：{exc}")
            continue
        res = _run_git(["diff", "--name-only", base_commit, "HEAD"])
        if res.returncode != 0:
            failures.append(
                f"两点 diff（基准 {label}）失败：退出码 {res.returncode}"
                f"（{(res.stderr or '').strip()[:160]}）"
            )
            continue
        return [line.strip() for line in res.stdout.splitlines() if line.strip()], failures

    failures.append(
        "所有变更面判定策略均失败：当前工作区很可能是浅克隆，"
        "请在 checkout 步骤设置 `fetch-depth: 0`（参考 capsule-audit.yml 的既有做法）。"
    )
    return [], failures


def load_capsules(changed: List[str]) -> List[Dict[str, Any]]:
    """只认本 PR 变更面中的胶囊（仓库既有胶囊不属于本 PR 的契约证据）。"""
    changed_capsules = [
        REPO_ROOT / f for f in changed if f.startswith(".agents/capsules/") and f.endswith(".json")
    ]

    capsules: List[Dict[str, Any]] = []
    for path in changed_capsules:
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


def load_changed_receipts(changed: List[str]) -> List[Dict[str, Any]]:
    """复述本 PR 变更面携带的全部凭单，与是否附带胶囊解耦。

    没有业务胶囊的 PR 依然可能携带已验收的 `Work Receipt`；把「无胶囊」
    等同于「无证据」会让证据卡片漏报。
    """
    receipts: List[Dict[str, Any]] = []
    prefix = f"{policy.RECEIPTS_DIR}/"
    for rel in sorted(changed):
        if not rel.startswith(prefix) or not rel.endswith(".json"):
            continue
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_path"] = rel
        receipts.append(payload)
    return receipts


def load_task_receipts(task_id: str) -> List[Dict[str, Any]]:
    """读取某任务在仓库内已落盘的全部凭单（含先前提交的历史凭单）。"""
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


def _merge_receipts(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按凭单路径去重合并（同一凭单同时出现在变更面与任务目录时只留一份）。"""
    merged: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for receipt in group:
            merged.setdefault(str(receipt.get("_path")), receipt)
    return [merged[key] for key in sorted(merged)]


def _verdict_badge(verdict: str) -> str:
    return {"passed": "✅ passed", "failed": "❌ failed"}.get(verdict, f"⚠️ {verdict}")


def generate_report() -> str:
    actor = os.getenv("GITHUB_ACTOR", "")
    head_ref = os.getenv("GITHUB_HEAD_REF", "")
    is_maintenance = "dependabot" in actor.lower() or head_ref.startswith("dependabot/")

    changed, detection_failures = detect_changed_files()
    capsules = load_capsules(changed)

    if capsules:
        capsule = capsules[0]
        receipts = _merge_receipts(
            load_changed_receipts(changed),
            load_task_receipts(str(capsule.get("task_id"))),
        )
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
        receipts = load_changed_receipts(changed)
    elif detection_failures:
        capsule_block = (
            "| **任务胶囊 (Capsule)** | 变更面判定失败，无法判定 | "
            "`git diff` 未能在当前工作区解析出本 PR 变更面（见「检测诊断」） |"
        )
        receipts = load_changed_receipts(changed)
    else:
        capsule_block = "| **任务胶囊 (Capsule)** | ℹ️ 未附带业务胶囊 | 本 PR 未引入 `.agents/capsules/*.json` 变更 |"
        receipts = load_changed_receipts(changed)

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
        gap_block = (
            "变更面判定失败，无法确认本 PR 是否携带凭单；请先修复检测链路。"
            if detection_failures
            else "尚未生成 `Work Receipt`：请在工作区执行 `python3 scripts/agent_capsule.py verify --capsule <capsule>`。"
        )

    base_ref_label = os.getenv("GITHUB_BASE_REF", "main")
    if detection_failures:
        diagnosis_block = "\n".join(f"- {item}" for item in detection_failures)
    else:
        diagnosis_block = (
            f"变更面判定正常：相对 `origin/{base_ref_label}` 解析到 {len(changed)} 个变更文件。"
        )

    return f"""## 🛡️ 《诡秘世界》协同证据摘要 (Evidence Summary)

| 项目 | 值 | 说明 |
|:---|:---|:---|
{capsule_block}

### 本 PR 携带的凭单 (Receipts)

{receipt_block}

### 覆盖缺口 (Coverage Gaps)

{gap_block}

### 检测诊断 (Detection Diagnostics)

{diagnosis_block}

> 本卡片只复述仓库内凭单的真实记录，**不代表测试通过**。
> 门禁权威结论以 CI required checks（`ci.yml` 三阶段 + `capsule-audit.yml` 证据审计）为准；
> 摘要为 sha256 内容摘要，不是密码学签名，抗伪造由受保护分支与 CODEOWNERS 评审承担。
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PR 质量卡片生成器 (HACF 2.1)")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=REPO_ROOT / ".hacf" / "tmp" / "pr_report.md",
        help="报告输出文件路径（默认：.hacf/tmp/pr_report.md）",
    )
    args = parser.parse_args()

    report_text = generate_report()
    out_file = args.output.resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    print(report_text)
