#!/usr/bin/env python3
"""把 .hacf/required-checks.json 同步到 GitHub 分支保护规则集（受保护分支治理）。

设计意图：必需检查名是公开接口，必须与代码里的 workflow 保持单一事实源。
默认 **dry-run**：只打印漂移，不改线上状态；加 `--apply` 才写回规则集。

写回时只替换 `required_status_checks` 一条规则的参数，其余规则（deletion /
non_fast_forward / required_linear_history / pull_request）与 bypass 配置原样保留，
避免脚本成为"一键削弱保护"的后门。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / ".hacf" / "required-checks.json"


def gh_api(args: List[str], payload: Any | None = None) -> Any:
    cmd = ["gh", "api", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    res = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh api {' '.join(args)} 失败: {res.stderr.strip()}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def default_repo() -> str:
    res = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    url = res.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com" in url:
        return url.split("github.com", 1)[1].lstrip(":/")
    raise RuntimeError("无法从 origin 推断仓库，请用 --repo 指定 owner/name")


def desired_contexts(contract: Dict[str, Any]) -> List[str]:
    return [
        entry["context"]
        for entry in contract.get("checks", [])
        if entry.get("required", True) and entry.get("context")
    ]


def find_ruleset(repo: str, name: str) -> Dict[str, Any]:
    rulesets = gh_api([f"/repos/{repo}/rulesets"])
    for ruleset in rulesets:
        if ruleset.get("name") == name:
            return gh_api([f"/repos/{repo}/rulesets/{ruleset['id']}"])
    raise RuntimeError(f"未找到名为 '{name}' 的规则集：{repo}")


def current_contexts(ruleset: Dict[str, Any]) -> List[str]:
    for rule in ruleset.get("rules", []):
        if rule.get("type") == "required_status_checks":
            params = rule.get("parameters", {}) or {}
            return [entry.get("context", "") for entry in params.get("required_status_checks", [])]
    return []


def build_ruleset_payload(ruleset: Dict[str, Any], contexts: List[str]) -> Dict[str, Any]:
    rules: List[Dict[str, Any]] = []
    replaced = False
    for rule in ruleset.get("rules", []):
        if rule.get("type") == "required_status_checks":
            params = dict(rule.get("parameters", {}) or {})
            params["required_status_checks"] = [{"context": c} for c in contexts]
            rules.append({"type": "required_status_checks", "parameters": params})
            replaced = True
        else:
            rules.append({"type": rule["type"], "parameters": rule.get("parameters")})
    if not replaced:
        rules.append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [{"context": c} for c in contexts],
                },
            }
        )
    return {
        "name": ruleset["name"],
        "target": ruleset["target"],
        "enforcement": ruleset["enforcement"],
        "conditions": ruleset.get("conditions", {}),
        "rules": rules,
        "bypass_actors": ruleset.get("bypass_actors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同步必需检查契约到分支保护规则集")
    parser.add_argument("--repo", help="owner/name；默认从 origin 推断")
    parser.add_argument("--apply", action="store_true", help="写回线上规则集（默认 dry-run）")
    args = parser.parse_args()

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    repo = args.repo or default_repo()
    ruleset_name = contract.get("ruleset", "main-protection")
    want = desired_contexts(contract)

    ruleset = find_ruleset(repo, ruleset_name)
    have = current_contexts(ruleset)
    print(f"仓库      : {repo}")
    print(f"规则集    : {ruleset_name} (#{ruleset['id']})")
    print(f"线上必需  : {have}")
    print(f"契约要求  : {want}")

    if sorted(have) == sorted(want):
        print("\n🎉 已一致，无需变更。")
        return 0

    missing = [c for c in want if c not in have]
    extra = [c for c in have if c not in want]
    if missing:
        print(f"  待新增: {missing}")
    if extra:
        print(f"  待移除: {extra}（若这些检查仍在 workflow 中存在，请确认契约文件是否漏登记）")

    if not args.apply:
        print(
            "\n⚠️  dry-run：未修改线上配置。确认后执行 "
            "'python3 scripts/sync_branch_protection.py --apply'。"
        )
        return 1

    payload = build_ruleset_payload(ruleset, want)
    gh_api(["-X", "PUT", f"/repos/{repo}/rulesets/{ruleset['id']}"], payload)
    updated = gh_api([f"/repos/{repo}/rulesets/{ruleset['id']}"])
    print(f"\n✅ 已同步，当前线上必需检查: {current_contexts(updated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
