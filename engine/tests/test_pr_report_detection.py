"""PR 证据卡片检测链路回归测试 (T-GOV-002)。

背景：`pr-gate-reporter.yml` 曾使用默认浅克隆（`fetch-depth: 1`），
`git diff origin/<base>...HEAD` 因缺少共同祖先返回 exit 128 与空 stdout；
报告脚本未检查退出码，把「判定失败」静默降级为「本 PR 未附带胶囊」，
导致证据卡片永久显示「未检测到内容」。

覆盖断言：
1. 浅克隆下判定必须显式失败，禁止返回「无变更」；
2. 完整历史下变更面与凭单能被正确解析（检测与胶囊解耦）。
"""

import subprocess
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

import generate_pr_report as reporter  # noqa: E402

# git 钩子（pre-commit 走 gate_runner.sh）会向测试进程注入 GIT_DIR / GIT_INDEX_FILE /
# GIT_WORK_TREE。夹具里的临时仓库必须忽略这些变量，否则测试内的 `git add .` 会
# 改写真实仓库的索引（曾实际损坏隔离工作区索引）。
_GIT_ENV_POLLUTANTS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


def _clean_git_env() -> dict:
    env = dict(os.environ)
    for key in _GIT_ENV_POLLUTANTS:
        env.pop(key, None)
    return env


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_clean_git_env(),
    )


def _init_repo_with_branches(tmp_path: Path, shallow_clone: bool) -> Path:
    """构造带 `origin/main` 与一个引入胶囊/凭单的功能分支的工作区。

    `shallow_clone=True` 时返回 depth=1 的克隆（复刻 actions/checkout 默认行为）。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin = tmp_path / "origin"
    origin.mkdir(parents=True, exist_ok=True)
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.com")
    _git(origin, "config", "user.name", "tester")
    (origin / "README.md").write_text("base\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "base")

    _git(origin, "checkout", "-q", "-b", "feature")
    capsule_dir = origin / ".agents" / "capsules"
    capsule_dir.mkdir(parents=True)
    (capsule_dir / "TASK-1.json").write_text('{"task_id": "TASK-1"}\n', encoding="utf-8")
    receipt_dir = origin / ".agents" / "receipts" / "TASK-1"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "abc123.json").write_text(
        '{"task_id": "TASK-1", "receipt_type": "work", "verdict": "passed",'
        ' "head_commit": "abcdef1234567890", "coverage_gaps": []}\n',
        encoding="utf-8",
    )
    (origin / "app.txt").write_text("feature\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "feature work")

    # 让 `main` 与分支尖端都前进若干提交：这样 merge base 落在浅克隆窗口之外，
    # 与线上「PR 多提交 + base 已前进」的真实形态一致。
    (origin / "app.txt").write_text("feature work 2\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "feature work 2")
    _git(origin, "checkout", "-q", "main")
    (origin / "README.md").write_text("base\nmain march\n", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "main march")

    clone = (tmp_path / "work") if shallow_clone else (tmp_path / "full")
    # ⚠️ 必须用 file:// URL：本地路径克隆会让 git 忽略 `--depth`，浅克隆特征随之消失。
    source = f"file://{origin}" if shallow_clone else str(origin)
    clone_args = ["clone", "-q", "--no-tags"]
    if shallow_clone:
        # 复刻 actions/checkout 的默认行为：depth=1 且 base 分支同样被浅取，
        # 于是 origin/main 与 HEAD 之间不存在共同祖先。
        clone_args += ["--depth", "1", "--no-single-branch"]
    clone_args += [source, str(clone)]
    _git(tmp_path, *clone_args)
    _git(clone, "checkout", "-q", "feature")
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "tester")
    return clone


def test_shallow_clone_detection_fails_loudly(tmp_path: Path, monkeypatch):
    """浅克隆实测：`git diff origin/main...HEAD` 必然失败，且失败必须出现在卡片上。"""
    shallow = _init_repo_with_branches(tmp_path, shallow_clone=True)
    monkeypatch.setattr(reporter, "REPO_ROOT", shallow)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    probe = _git(shallow, "diff", "--name-only", "origin/main...HEAD")
    assert probe.returncode != 0, "浅克隆应无法解析三点 diff，否则本测试失去意义"

    changed, failures = reporter.detect_changed_files()
    assert changed == []
    assert failures, "判定失败时必须给出诊断说明，禁止静默返回空变更面"
    assert any("merge base" in item or "merge-base" in item for item in failures)

    report = reporter.generate_report()
    assert "变更面判定失败" in report
    assert "未附带业务胶囊" not in report, "判定失败不得伪报为「本 PR 未引入胶囊变更」"


def test_injected_git_failure_is_reported(monkeypatch):
    """复刻线上故障现场：浅克隆下 `git diff origin/main...HEAD` 返回 exit 128。

    `actions/checkout` 的 depth=1 工作区没有共同祖先，git 直接失败且 stdout 为空；
    旧实现对 `check=False` 的结果不做区分，把空 stdout 当成「本 PR 没有胶囊」。
    这里把该失败精确注入，断言判定失败必须显式暴露。
    """
    stderr = "fatal: origin/main...HEAD: no merge base\n"
    git_calls: list[list[str]] = []

    def fake_git(args: list[str]) -> subprocess.CompletedProcess[str]:
        git_calls.append(list(args))
        if args[:1] == ["diff"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", stderr)
        if args[:1] == ["merge-base"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: Not a valid object name")
        raise AssertionError(f"未预期的 git 调用：{args}")

    monkeypatch.setattr(reporter, "_run_git", fake_git)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed, failures = reporter.detect_changed_files()
    assert changed == []
    assert failures, "判定失败时必须给出诊断说明，禁止静默返回空变更面"
    assert failures[0].startswith("三点 diff") and "128" in failures[0]
    assert any("fetch-depth: 0" in item for item in failures)

    report = reporter.generate_report()
    assert "变更面判定失败" in report
    assert "检测诊断 (Detection Diagnostics)" in report
    assert "fetch-depth: 0" in report
    assert "未附带业务胶囊" not in report, "判定失败不得伪报为「本 PR 未引入胶囊变更」"
    assert git_calls, "检测链路必须真正调用 git 解析变更面"


def test_full_history_detection_resolves_capsule_and_receipt(tmp_path: Path, monkeypatch):
    """完整历史：变更面、胶囊与凭单必须被正确解析（凭单检测与胶囊解耦）。"""
    full = _init_repo_with_branches(tmp_path, shallow_clone=False)
    monkeypatch.setattr(reporter, "REPO_ROOT", full)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed, failures = reporter.detect_changed_files()
    assert failures == []
    assert ".agents/capsules/TASK-1.json" in changed
    assert ".agents/receipts/TASK-1/abc123.json" in changed

    capsules = reporter.load_capsules(changed)
    assert [c["task_id"] for c in capsules] == ["TASK-1"]

    receipts = reporter.load_changed_receipts(changed)
    assert [r["receipt_type"] for r in receipts] == ["work"]


def test_receipts_are_reported_without_capsule(tmp_path: Path, monkeypatch):
    """无胶囊 PR：携带的凭单仍必须出现在卡片上，不得判为「无证据」。"""
    full = _init_repo_with_branches(tmp_path, shallow_clone=False)
    monkeypatch.setattr(reporter, "REPO_ROOT", full)
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    changed = ["macos-app/WorldOfMysteries/AppState.swift", ".agents/receipts/TASK-1/abc123.json"]
    assert reporter.load_capsules(changed) == []
    receipts = reporter.load_changed_receipts(changed)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == "passed"
