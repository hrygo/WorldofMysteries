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

import html
import json
import re
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


def _failure(failures: List[str] | None, path: str, reason: str) -> None:
    if failures is not None:
        failures.append(f"证据读取失败：{path}（{reason}）")


def _safe_path(rel: str) -> Path:
    """Evidence is repository-local data, never a symlink or a traversable task ID."""
    parts = Path(rel).parts
    if not parts or Path(rel).is_absolute() or ".." in parts:
        raise ValueError("非法证据路径")
    path = REPO_ROOT
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("不读取符号链接证据")
    return path


def _task_id(value: Any) -> bool:
    return (isinstance(value, str) and bool(value.strip()) and value not in (".", "..")
            and not any(c in value for c in "/\\")
            and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def _unique_object(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重复 JSON 字段")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("非有限 JSON 常量")


def _check_record(record: Any, kind: str) -> None:
    """Check readable shape, NOT authenticity or the authoritative gate verdict.

    Older records may omit optional display fields. Render them as unknown, not
    zero/success. The full engineering-schema/digest audit remains Capsule Gate's
    responsibility; this stdlib-only reporter must not become a second gate.
    """
    if not isinstance(record, dict) or not _task_id(record.get("task_id")):
        raise ValueError("需要对象及安全的 task_id")
    if kind == "capsule":
        for key in ("base", "gates"):
            if key in record and not isinstance(record[key], dict):
                raise ValueError(f"{key} 不是对象")
        for key in ("capsule_id", "title", "assigned_role", "risk_class"):
            if key in record and not isinstance(record[key], str):
                raise ValueError(f"{key} 不是字符串")
        revision = record.get("capsule_revision", 1)
        if type(revision) is not int or revision < 1:
            raise ValueError("非法 capsule_revision")
    else:
        if record.get("receipt_type") not in ("work", "integration"):
            raise ValueError("非法 receipt_type")
        if record.get("verdict") not in ("passed", "failed"):
            raise ValueError("非法 verdict")
        if not isinstance(record.get("head_commit"), str) or not record["head_commit"]:
            raise ValueError("缺少 head_commit")
        if "coverage_gaps" in record:
            gaps = record["coverage_gaps"]
            if not isinstance(gaps, list) or not all(isinstance(gap, str) for gap in gaps):
                raise ValueError("coverage_gaps 不是字符串列表")
        digest = record.get("gate_profile_digest")
        if digest is not None and not isinstance(digest, str):
            raise ValueError("非法 gate_profile_digest")


def _load_record(rel: str, kind: str, failures: List[str] | None) -> Dict[str, Any] | None:
    try:
        path = _safe_path(rel)
        if not os.path.lexists(path):
            return None  # A deleted evidence file is not current evidence.
        payload = json.loads(path.read_text(encoding="utf-8"),
                             object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        _check_record(payload, kind)
        if kind == "receipt" and path.parent.name != payload["task_id"]:
            raise ValueError("凭单 task_id 与任务目录不一致")
        payload["_path"] = rel
        if kind == "capsule":
            payload["_digest"] = policy.capsule_digest(path)
        return payload
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        # Do not echo exception messages: parsers/OS errors can contain payloads
        # or absolute host paths. The relative source and error class suffice.
        _failure(failures, rel, type(exc).__name__)
        return None


def load_capsules(changed: List[str], failures: List[str] | None = None) -> List[Dict[str, Any]]:
    """Load ALL changed capsules; malformed evidence is explicit in the report."""
    return [record for rel in sorted(set(changed))
            if rel.startswith(".agents/capsules/") and rel.endswith(".json")
            if (record := _load_record(rel, "capsule", failures)) is not None]


def load_changed_receipts(changed: List[str], failures: List[str] | None = None) -> List[Dict[str, Any]]:
    """Receipt-only PRs remain visible, independent of capsule presence."""
    return [record for rel in sorted(set(changed))
            if rel.startswith(f"{policy.RECEIPTS_DIR}/") and rel.endswith(".json")
            if (record := _load_record(rel, "receipt", failures)) is not None]


def load_task_receipts(task_id: str, failures: List[str] | None = None) -> List[Dict[str, Any]]:
    """Include task history, without presenting it as current-head verification."""
    rel = f"{policy.RECEIPTS_DIR}/{task_id}"
    try:
        if not _task_id(task_id):
            raise ValueError("非法任务 ID")
        directory = _safe_path(rel)
        if not os.path.lexists(directory):
            return []
        paths = sorted(directory.iterdir())
    except (OSError, ValueError) as exc:
        _failure(failures, rel, type(exc).__name__)
        return []
    return [record for path in paths if path.suffix == ".json"
            if (record := _load_record(str(path.relative_to(REPO_ROOT)), "receipt", failures)) is not None]


def _merge_receipts(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for group in groups:
        for receipt in group:
            merged.setdefault(receipt["_path"], receipt)
    return [merged[key] for key in sorted(merged)]


def _cell(value: Any) -> str:
    """Encode data, never interpolate data as Markdown/table/HTML syntax."""
    text = "未记录" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c if (ord(c) >= 32 or c in "\n\t") and not 0xD800 <= ord(c) <= 0xDFFF
                   else "\ufffd" for c in text)
    text = html.escape(text, quote=True)
    for c in "\\|`*_[]":
        text = text.replace(c, f"&#{ord(c)};")
    return text.replace("\n", "<br>").replace("\t", "    ")


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    """One constructor owns headers/delimiters for every nonempty/empty/error state."""
    if not rows or any(len(row) != len(headers) for row in rows):
        raise ValueError("Report table rows must match the header width")
    return "\n".join([
        "| " + " | ".join(_cell(h) for h in headers) + " |",
        "|" + ":---|" * len(headers),
        *("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows),
    ])


def _short(value: Any, width: int = 20) -> str:
    if value is None or value == "":
        return "未记录"
    text = str(value)
    return text if len(text) <= width else text[:width] + "…"


REPORT_MARKER = "<!-- wom-evidence-summary:v1 -->"
REPORT_TITLE = "## 🛡️ 《诡秘世界》协同证据摘要 (Evidence Summary)"
RECEIPT_HEADING = "### 本 PR 携带的凭单 (Receipts)"
RECEIPT_HEADERS = ["任务 / 类型", "凭单位置", "head_commit", "记录的 verdict", "门禁档案摘要", "覆盖缺口"]


def generate_report() -> str:
    actor = os.getenv("GITHUB_ACTOR", "")
    head_ref = os.getenv("GITHUB_HEAD_REF", "")
    is_maintenance = "dependabot" in actor.lower() or head_ref.startswith("dependabot/")
    changed, detection_failures = detect_changed_files()
    capsule_failures: List[str] = []
    receipt_failures: List[str] = []
    capsules = load_capsules(changed, capsule_failures)
    receipts = _merge_receipts(load_changed_receipts(changed, receipt_failures), *(
        load_task_receipts(task, receipt_failures)
        for task in sorted({capsule["task_id"] for capsule in capsules})
    ))
    head = os.getenv("WOM_REPORT_HEAD_SHA", "")
    base = os.getenv("WOM_REPORT_BASE_SHA", "")
    for value in (head, base):
        if value and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("Invalid report revision metadata")
    lines = [REPORT_MARKER]
    if head:
        lines.append(f"<!-- wom-evidence-head:{head} -->")
    lines.extend([REPORT_TITLE, "", "### 报告快照与验证边界", "", _table(
        ["项目", "值", "说明"], [
            ["PR head", head or "未提供（本地生成）", "来自 PR 事件，不使用胶囊旧基线冒充当前提交"],
            ["目标分支 SHA", base or "未提供（本地生成）", "本次报告生成时的 PR base"],
            ["CI required checks", "本卡片不查询、不推断", "以 GitHub Checks 为准；报告发布成功不等于测试通过"],
            ["产品验收", "本卡片不判定", "工程 CI、Work Receipt、用户体验验收是独立证据"],
        ]), "", "### 本 PR 携带的任务胶囊 (Capsules)", ""])
    if capsules:
        for capsule in capsules:
            lines.extend([_table(["项目", "值", "说明"], [
                ["任务胶囊 (Capsule)", f"{capsule.get('capsule_id', '未记录')} rev{capsule.get('capsule_revision', '未记录')}", capsule.get("title")],
                ["契约位置 (Path)", capsule["_path"], "不可变契约，verify 不回写"],
                ["执行角色 (Role)", capsule.get("assigned_role"), capsule.get("risk_class")],
                ["胶囊摘要 (Digest)", _short("sha256:" + capsule["_digest"], 23), "变更后需重新验收"],
                ["胶囊基线 (Base)", _short(capsule.get("base", {}).get("target_sha"), 12), capsule.get("base", {}).get("target_ref")],
                ["门禁档案 (Gate Profile)", capsule.get("gates", {}).get("profile"), _short(capsule.get("gates", {}).get("profile_digest"))],
            ]), ""])
    else:
        if detection_failures:
            status = "变更面判定失败，无法判定"
        elif capsule_failures:
            status = "胶囊读取失败，无法完整判定"
        elif is_maintenance:
            status = "自动化维护 PR（未附带业务胶囊）"
        else:
            status = "未附带业务胶囊"
        lines.extend([_table(["项目", "值", "说明"], [["任务胶囊", status, "见检测诊断；不推断凭单或 CI 结果"]]), ""])

    rows: List[List[Any]] = []
    for receipt in receipts:
        rows.append([
            f"{receipt['task_id']} / {receipt['receipt_type']}", receipt["_path"],
            _short(receipt["head_commit"], 12), receipt["verdict"],
            _short(receipt.get("gate_profile_digest")),
            len(receipt["coverage_gaps"]) if "coverage_gaps" in receipt else "未记录",
        ])
    if not rows:
        status = "读取失败 / 无法确认" if receipt_failures or capsule_failures or detection_failures else "未找到凭单"
        rows = [[status, "—", "—", "未判定", "未记录", "未知"]]
    lines.extend([RECEIPT_HEADING, "", _table(RECEIPT_HEADERS, rows), "",
                  "verdict 是凭单原始记录，未在本卡片中复核。任务历史凭单不自动覆盖当前 PR head；",
                  "摘要绑定、变更集覆盖与当前门禁结果由 Capsule Gate / GitHub Checks 判定。", "",
                  "### 覆盖缺口 (Coverage Gaps)", ""])
    gaps: List[str] = []
    if detection_failures or capsule_failures or receipt_failures:
        gaps.append("证据读取或检测不完整，无法确认完整覆盖；不得将未知当作零缺口。")
    if not receipts:
        gaps.append("本次仓库快照未找到可读取凭单，不等于未执行测试，也不等于 CI 失败。")
    for task in sorted({capsule["task_id"] for capsule in capsules}):
        if not any(r["task_id"] == task and r["receipt_type"] == "work" for r in receipts):
            gaps.append(f"{task}：未找到可读取的 Work Receipt；若检测/读取失败，应先修复诊断项。")
    for receipt in receipts:
        if receipt["verdict"] == "failed":
            gaps.append(f"{receipt['_path']}：凭单记录 verdict=failed，不因覆盖缺口列表为空而视为通过。")
        if "coverage_gaps" not in receipt:
            gaps.append(f"{receipt['_path']}：coverage_gaps 未记录，数量未知。")
        for gap in receipt.get("coverage_gaps", []):
            gaps.append(f"{receipt['_path']}：{gap}")
    if gaps:
        lines.extend("- " + _cell(gap) for gap in gaps)
    else:
        lines.append("所列凭单的 coverage_gaps 均为空；不代表当前 PR 无缺口。")
    if capsules and not receipts and not (detection_failures or capsule_failures or receipt_failures):
        lines.extend(["", "凭单需由实际验证生成并提交；不能将 CI 状态手工填写成 Work Receipt。"])

    lines.extend(["", "### 检测诊断 (Detection Diagnostics)", ""])
    diagnostics = detection_failures + capsule_failures + receipt_failures
    if diagnostics:
        lines.extend("- " + _cell(item) for item in dict.fromkeys(diagnostics))
    else:
        base_ref = _cell(os.getenv("GITHUB_BASE_REF", "main"))
        lines.append(f"变更面判定正常：相对 origin/{base_ref} 解析到 {len(changed)} 个变更文件；证据读取无错误。")
    lines.extend(["", "> 本卡片只复述仓库内凭单的真实记录，**不代表测试通过**。",
                  "> 门禁权威结论以 CI required checks 为准；sha256 是内容摘要，不是密码学签名。", ""])
    return "\n".join(lines)


def validate_report_markdown(text: str) -> None:
    """Fail before publishing a structurally broken report (stdlib-only guard).

    Real Markdown-to-HTML rendering assertions live in the existing Python test
    suite. This guard checks the restricted table format our constructor emits.
    """
    if not text.startswith(REPORT_MARKER + "\n") or REPORT_TITLE not in text:
        raise ValueError("Missing report identity")
    if text.count(RECEIPT_HEADING) != 1:
        raise ValueError("Missing or duplicate receipt section")
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    for block in blocks:
        width = block[0].count("|") - 1
        if (len(block) < 3 or width < 1
                or not re.fullmatch(r"\|(?::---\|)+", block[1])
                or any(line.count("|") - 1 != width for line in block)):
            raise ValueError("Invalid report table header/delimiter/row width")
    section = text.split(RECEIPT_HEADING, 1)[1].split("\n### ", 1)[0]
    expected_header = "| " + " | ".join(_cell(h) for h in RECEIPT_HEADERS) + " |"
    if expected_header not in section or len(blocks) < 3:
        raise ValueError("Receipt table missing or incomplete")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PR 质量卡片生成器 (HACF 2.1)")
    parser.add_argument("--output", "-o", type=Path,
                        default=REPO_ROOT / ".hacf" / "tmp" / "pr_report.md")
    args = parser.parse_args()
    report_text = generate_report()
    validate_report_markdown(report_text)
    out_file = args.output.resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report_text, encoding="utf-8")
    print(report_text)
