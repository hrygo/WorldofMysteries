# CI 变更面感知与效率优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让核心 GitHub Actions CI 按变更面跳过无关的 Python/Swift runner，同时保持 required checks、门禁安全性和未知路径的 fail-closed 行为。

**Architecture:** 在 `.github/workflows/ci.yml` 中增加轻量 `change-scope` job，使用完整历史计算变更路径，并调用标准库脚本输出 `run_python` / `run_swift`。架构静态检查始终运行；两个平台 job 使用 job-level `if` 选择性创建；`All Quality Gates Passed` 保留原名并显式接受被分类器判定为不需要的 skipped job。同步移除无效 SPM cache、重复的 `uv lock --check` 和 PR Reporter 的 `edited` 触发。

**Tech Stack:** GitHub Actions YAML、Python 3.14 标准库、pytest、uv、Swift 6 / Xcode 27、macOS 26+。

**Spec:** `docs/superpowers/specs/2026-09-19-ci-efficiency-design.md`

## Global Constraints

- `All Quality Gates Passed` 与 `Capsule Gate` 是 branch protection 公开检查名，禁止重命名或改动其 required-check 契约。
- `architecture-and-contracts` 始终运行；只有变更面明确不需要时才跳过 Python/Swift job。
- 变更面为空、未知或解析异常时选择 full：`run_python=true` 且 `run_swift=true`。
- 不使用核心 CI 的 workflow-level `paths` 过滤；使用 job-level `if`，避免 required workflow 进入 Pending。
- `ci_changed_scope.py` 只使用 Python 标准库，不新增产品依赖或修改 `engine/uv.lock`。
- 保留 `actions/checkout@v7`、`actions/setup-python@v7`、`astral-sh/setup-uv@v10.1.0`、`macos-latest` 与现有 timeout/concurrency 配置。
- 删除 SPM `.build` cache；Swift 测试继续使用 `${RUNNER_TEMP}/wom-spm-scratch`。
- 文档中的命令使用可移植原生命令，不写本机 `rtk` 前缀；临时输出只写入 `.hacf/tmp/`。
- 不修改当前主工作区中已有的未提交文件，不触碰领域代码、Schema、门禁 profile 或分支保护配置。

## Review Focus

1. **纯元数据输入：** `docs/**`、`.agents/**`、Markdown 变更只保留架构 job；测试 `classify_paths()` 返回 `meta/false/false`，并验证 aggregate 对两个 skipped 平台 job 仍判定合法。
2. **跨语言协议输入：** `contracts/**` 必须同时运行 Python 与 Swift；测试 `classify_paths(["contracts/..."])` 返回 `full/true/true`。
3. **平台单栈输入：** `engine/**` 只启用 Python，`macos-app/**` 只启用 Swift；分别测试两个方向，另加 `macos-app/Packaging/**` 的 full 保护例外。
4. **不可信/异常输入：** 未知路径、空 NUL 流和非法 UTF-8 均进入 full；测试分类器的 bytes 解码与 CLI 输出。
5. **required-check 拓扑：** workflow 必须保留两个公开 job name、`all-gates-passed` 的 `always()` 和 job-level 条件；静态测试锁定这些字符串与禁止出现的 SPM cache/重复 lock check。

### Task 1: Implement and test the change-scope classifier

**Files:**
- Create: `scripts/ci_changed_scope.py`
- Test: `engine/tests/test_ci_changed_scope.py`

**Interfaces:**
- Produces `ScopeDecision(run_python: bool, run_swift: bool, scope: str, reason: str)`.
- Produces `classify_paths(paths: Iterable[str]) -> ScopeDecision`.
- Produces `decision_from_nul_bytes(raw: bytes) -> ScopeDecision`.
- Produces `write_github_output(decision: ScopeDecision, stream: TextIO) -> None`.
- Produces `write_summary(decision: ScopeDecision, stream: TextIO) -> None`.
- Produces `main(argv: Sequence[str] | None = None) -> int` with `--github-output`, `--summary`, and `--force-full` options.

- [ ] **Step 1: Write the failing classifier tests**

```python
# engine/tests/test_ci_changed_scope.py
from io import StringIO
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from ci_changed_scope import (  # noqa: E402
    classify_paths,
    decision_from_nul_bytes,
    write_github_output,
)


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["docs/design.md", ".agents/receipts/T1/abc.json"], (False, False, "meta")),
        (["engine/domain/world.py"], (True, False, "python")),
        (["macos-app/WorldOfMysteries/AppState.swift"], (False, True, "swift")),
        (["contracts/schemas/story.schema.json"], (True, True, "full")),
        (["scripts/check_architecture_fitness.py"], (True, True, "full")),
        (["macos-app/Packaging/python-runtime.lock.json"], (True, True, "full")),
        (["unknown-root-config.toml"], (True, True, "full")),
        ([], (True, True, "full")),
    ],
)
def test_classify_paths(paths, expected):
    decision = classify_paths(paths)
    assert (decision.run_python, decision.run_swift, decision.scope) == expected


def test_invalid_utf8_bytes_fail_closed_to_full():
    decision = decision_from_nul_bytes(b"docs/readme.md\x00\xff\x00")
    assert (decision.run_python, decision.run_swift, decision.scope) == (True, True, "full")


def test_github_output_contains_only_safe_scalar_outputs():
    output = StringIO()
    write_github_output(classify_paths(["engine/domain/world.py"]), output)
    assert output.getvalue().splitlines() == [
        "run_python=true",
        "run_swift=false",
        "scope=python",
    ]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run --directory engine --extra dev pytest tests/test_ci_changed_scope.py -q`

Expected: FAIL because `scripts/ci_changed_scope.py` does not exist yet.

- [ ] **Step 3: Implement the minimal standard-library classifier**

Implement the following decision order in `scripts/ci_changed_scope.py`:

```python
FULL_PREFIXES = ("scripts/", ".hacf/", ".github/")
PYTHON_PREFIXES = ("engine/", "contracts/", "fixtures/")
SWIFT_PREFIXES = ("macos-app/",)
META_PREFIXES = ("docs/", ".agents/")
META_FILES = {"README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", ".gitignore"}


def classify_paths(paths: Iterable[str]) -> ScopeDecision:
    normalized = [path.lstrip("./") for path in paths if path]
    if not normalized:
        return ScopeDecision.full("变更面为空，按 full 运行")

    run_python = False
    run_swift = False
    saw_code = False
    for path in normalized:
        if path.startswith(FULL_PREFIXES):
            return ScopeDecision.full(f"命中治理路径: {path}")
        if path.startswith("macos-app/Packaging/"):
            return ScopeDecision.full(f"命中打包路径: {path}")
        if path.startswith(PYTHON_PREFIXES):
            run_python = True
            saw_code = True
            continue
        if path.startswith(SWIFT_PREFIXES):
            run_swift = True
            saw_code = True
            continue
        if path.startswith(META_PREFIXES) or path in META_FILES or path.endswith(".md"):
            continue
        return ScopeDecision.full(f"未知路径: {path}")

    if not saw_code:
        return ScopeDecision(False, False, "meta", "仅元数据变更")
    if run_python and run_swift:
        return ScopeDecision.full("命中 Python 与 Swift 变更面")
    if run_python:
        return ScopeDecision(True, False, "python", "仅 Python/Engine 变更")
    return ScopeDecision(False, True, "swift", "仅 macOS App 变更")
```

`decision_from_nul_bytes` 必须用 strict UTF-8 解码；任何 `UnicodeDecodeError`、`--force-full` 或输出文件写入失败都不能产生“跳过平台”的成功结果。对非法路径字节，函数返回 full；对输出文件 I/O 失败，`main` 返回非零。`write_github_output` 只写三个布尔/枚举 scalar，不把完整路径或多行 reason 写入 `$GITHUB_OUTPUT`；`write_summary` 才写 scope、reason 和文件计数。

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `uv run --directory engine --extra dev pytest tests/test_ci_changed_scope.py -q`

Expected: all classifier cases pass, including meta-only, single-platform, cross-language, unknown, empty and invalid-byte inputs.

- [ ] **Step 5: Commit the classifier slice**

```bash
git add scripts/ci_changed_scope.py engine/tests/test_ci_changed_scope.py
git commit -m "feat(ci): add fail-closed change scope classifier"
```

### Task 2: Add job-level CI selection while preserving required checks

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `engine/tests/test_ci_workflow.py`

**Interfaces:**
- `change-scope` exposes `run_python`, `run_swift`, and `scope` job outputs.
- `python-engine` consumes `needs.change-scope.outputs.run_python`.
- `swift-macos-app` consumes `needs.change-scope.outputs.run_swift`.
- `all-gates-passed` consumes all job results and the two scope outputs while retaining its existing public name.

- [ ] **Step 1: Write failing workflow contract tests**

```python
# engine/tests/test_ci_workflow.py
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_required_check_name_and_aggregate_contract_are_stable():
    assert 'name: "All Quality Gates Passed"' in CI
    assert "all-gates-passed:" in CI
    assert "if: always()" in CI
    assert 'name: "Capsule Gate"' in (
        ROOT / ".github/workflows/capsule-audit.yml"
    ).read_text(encoding="utf-8")


def test_ci_uses_job_level_scope_selection():
    assert "change-scope:" in CI
    assert "needs: [change-scope, architecture-and-contracts]" in CI
    assert "needs.change-scope.outputs.run_python" in CI
    assert "needs.change-scope.outputs.run_swift" in CI
    assert "\n    paths:" not in CI


def test_ci_does_not_keep_unusable_or_duplicate_checks():
    assert "actions/cache@v6" not in CI
    assert "uv lock --check" not in CI
```

- [ ] **Step 2: Run the workflow contract tests and verify they fail**

Run: `uv run --directory engine --extra dev pytest tests/test_ci_workflow.py -q`

Expected: FAIL because `ci.yml` has no `change-scope` job and still contains the SPM cache and explicit `uv lock --check`.

- [ ] **Step 3: Add the `change-scope` job and outputs**

Insert the job before `architecture-and-contracts` in `.github/workflows/ci.yml`:

```yaml
  change-scope:
    name: "Determine CI Scope"
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      run_python: ${{ steps.scope.outputs.run_python }}
      run_swift: ${{ steps.scope.outputs.run_swift }}
      scope: ${{ steps.scope.outputs.scope }}
    steps:
      - name: Checkout Code with History
        uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.14"

      - name: Classify changed paths
        id: scope
        env:
          EVENT_NAME: ${{ github.event_name }}
          PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}
          PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          PUSH_BEFORE_SHA: ${{ github.event.before }}
          PUSH_HEAD_SHA: ${{ github.sha }}
        run: |
          set -euo pipefail
          if [[ "$EVENT_NAME" == "pull_request" ]]; then
            git diff --name-only -z "$PR_BASE_SHA...$PR_HEAD_SHA" \
              | python3 scripts/ci_changed_scope.py \
                  --github-output "$GITHUB_OUTPUT" \
                  --summary "$GITHUB_STEP_SUMMARY"
          elif [[ "$EVENT_NAME" == "push" && ! "$PUSH_BEFORE_SHA" =~ ^0+$ ]]; then
            git diff --name-only -z "$PUSH_BEFORE_SHA" "$PUSH_HEAD_SHA" \
              | python3 scripts/ci_changed_scope.py \
                  --github-output "$GITHUB_OUTPUT" \
                  --summary "$GITHUB_STEP_SUMMARY"
          elif [[ "$EVENT_NAME" == "push" ]]; then
            git ls-files -z \
              | python3 scripts/ci_changed_scope.py \
                  --github-output "$GITHUB_OUTPUT" \
                  --summary "$GITHUB_STEP_SUMMARY"
          else
            python3 scripts/ci_changed_scope.py \
              --force-full \
              --github-output "$GITHUB_OUTPUT" \
              --summary "$GITHUB_STEP_SUMMARY"
          fi
```

The full-history checkout is required for the PR three-dot diff; using a workflow-level path filter is explicitly out of scope because skipped required workflows remain Pending. The `set -o pipefail` behavior must make a missing ref fail the job rather than silently emit an empty scope.

- [ ] **Step 4: Gate only the expensive jobs and make the aggregate skip-aware**

Change `python-engine` and `swift-macos-app` as follows, without changing their `name` fields or test commands except for the redundant lock check:

```yaml
  python-engine:
    needs: [change-scope, architecture-and-contracts]
    if: ${{ needs.change-scope.outputs.run_python == 'true' }}
```

```yaml
  swift-macos-app:
    needs: [change-scope, architecture-and-contracts]
    if: ${{ needs.change-scope.outputs.run_swift == 'true' }}
```

In `all-gates-passed`, add `change-scope` to `needs` and retain `if: always()`. Its shell check must enforce `change-scope` and architecture success first, then only require a platform result when its corresponding output is `true`:

```bash
if [ "${{ needs.change-scope.result }}" != "success" ] || \
   [ "${{ needs.architecture-and-contracts.result }}" != "success" ]; then
  echo "❌ Scope or architecture gate failed."
  exit 1
fi
if [ "${{ needs.change-scope.outputs.run_python }}" = "true" ] && \
   [ "${{ needs.python-engine.result }}" != "success" ]; then
  echo "❌ Python gate was required but did not succeed."
  exit 1
fi
if [ "${{ needs.change-scope.outputs.run_swift }}" = "true" ] && \
   [ "${{ needs.swift-macos-app.result }}" != "success" ]; then
  echo "❌ Swift gate was required but did not succeed."
  exit 1
fi
echo "🎉 All selected CI gates passed; skipped platform jobs were out of scope."
```

- [ ] **Step 5: Remove only the proven waste**

Delete the `Cache SPM Dependencies` step and its `actions/cache@v6` block. Keep `swift test --scratch-path "${RUNNER_TEMP}/wom-spm-scratch"`. In the Python command, remove only `uv lock --check`; keep `uv run --locked --extra dev pytest -v`.

- [ ] **Step 6: Run workflow contract and governance tests**

Run: `uv run --directory engine --extra dev pytest tests/test_ci_changed_scope.py tests/test_ci_workflow.py tests/test_hacf_governance.py -q`

Expected: all focused classifier, workflow topology, and HACF governance tests pass; skipped-job acceptance is encoded by the aggregate shell branch rather than by changing required check names.

- [ ] **Step 7: Commit the core CI slice**

```bash
git add .github/workflows/ci.yml engine/tests/test_ci_workflow.py
git commit -m "perf(ci): skip unrelated platform gates by change scope"
```

### Task 3: Reduce redundant PR reporting and update the CI baseline documentation

**Files:**
- Modify: `.github/workflows/pr-gate-reporter.yml`
- Modify: `engine/tests/test_pr_report_publication.py`
- Modify: `docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md`

**Interfaces:**
- The reporter continues to publish the same evidence marker and uses the same permissions, checkout depth, and `github-script` publisher.
- Documentation describes the new `change-scope` behavior and no longer promises an unsupported SPM cache hit or a universal `<1.5 minute` full-run time.

- [ ] **Step 1: Add the reporter trigger regression assertion**

Append to `engine/tests/test_pr_report_publication.py`:

```python
def test_reporter_does_not_run_for_description_only_edits():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/pr-gate-reporter.yml").read_text(encoding="utf-8")
    assert "edited" not in workflow
    assert "synchronize" in workflow
    assert "ready_for_review" in workflow
```

- [ ] **Step 2: Run the regression test and verify it fails**

Run: `uv run --directory engine --extra dev pytest tests/test_pr_report_publication.py::test_reporter_does_not_run_for_description_only_edits -q`

Expected: FAIL because `pull_request.types` currently includes `edited`.

- [ ] **Step 3: Remove only the `edited` event**

Change the reporter event list from:

```yaml
types: [opened, synchronize, reopened, ready_for_review, converted_to_draft, edited]
```

to:

```yaml
types: [opened, synchronize, reopened, ready_for_review, converted_to_draft]
```

Keep `pull-requests: write`, `issues: write`, `fetch-depth: 0`, snapshot SHA environment variables, and the stale-report guard unchanged.

- [ ] **Step 4: Update the durable CI baseline document**

In `docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md`:

1. Add `change-scope` to the core workflow specification and state that `architecture-and-contracts` always runs while Python/Swift jobs are job-conditionally selected.
2. Replace the SPM cache row with the fact that `Package.swift` has no external dependencies and the CI test uses a runner-temporary scratch path; do not describe `.build` as an effective CI cache.
3. Replace the universal “整体 CI 流水线端到端耗时控制在 1.5 分钟以内” assertion with a measurement policy: report separate meta-only, Python-only, Swift-only and full-run durations from GitHub Actions; the current observed full run remains a baseline, not a guarantee.
4. Preserve the existing required-check names and explain why workflow-level `paths` is not used.

- [ ] **Step 5: Run reporter, workflow and documentation checks**

Run: `uv run --directory engine --extra dev pytest tests/test_pr_report_publication.py tests/test_ci_workflow.py -q`

Expected: reporter event regression, required-check topology assertions and existing publisher tests all pass.

- [ ] **Step 6: Commit the reporting/documentation slice**

```bash
git add .github/workflows/pr-gate-reporter.yml engine/tests/test_pr_report_publication.py docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md
git commit -m "docs(ci): document change-aware gate execution"
```

### Task 4: Execute full verification and produce evidence

**Files:**
- Read: `.hacf/gates/full_p0.json`
- Read: `.hacf/required-checks.json`
- Write temporarily: `.hacf/tmp/ci-scope-*.out` and `.hacf/tmp/ci-scope-*.md` (not committed)

**Interfaces:**
- Verifies the implemented outputs against the protected required-check and gate registry contracts.
- Does not add a new production interface or alter any receipt/capsule schema.

- [ ] **Step 1: Run deterministic scope probes**

```bash
mkdir -p .hacf/tmp
printf 'docs/design.md\0.agents/receipts/T1/abc.json\0' \
  | python3 scripts/ci_changed_scope.py \
      --github-output .hacf/tmp/ci-scope-meta.out \
      --summary .hacf/tmp/ci-scope-meta.md
grep -Fx 'run_python=false' .hacf/tmp/ci-scope-meta.out
grep -Fx 'run_swift=false' .hacf/tmp/ci-scope-meta.out
printf 'contracts/schemas/story.schema.json\0' \
  | python3 scripts/ci_changed_scope.py \
      --github-output .hacf/tmp/ci-scope-contracts.out
grep -Fx 'run_python=true' .hacf/tmp/ci-scope-contracts.out
grep -Fx 'run_swift=true' .hacf/tmp/ci-scope-contracts.out
```

Expected: meta-only selects neither platform; contract changes select both.

- [ ] **Step 2: Run protected-contract checks**

```bash
python3 scripts/check_required_checks.py
python3 scripts/gate_profile.py check
git diff --check HEAD~3..HEAD
```

Expected: both required checks are still exposed from their original workflows, every protected gate digest matches, and no whitespace error is reported.

- [ ] **Step 3: Run the focused and full Python suites**

```bash
uv run --directory engine --extra dev pytest \
  tests/test_ci_changed_scope.py \
  tests/test_ci_workflow.py \
  tests/test_pr_report_publication.py \
  tests/test_hacf_governance.py -q
uv run --directory engine --locked --extra dev pytest -q
```

Expected: both commands exit 0; the second command is the full Python/contract gate and must not rely on a pre-existing `.venv` state.

- [ ] **Step 4: Run the protected full gate**

```bash
bash scripts/gate_runner.sh FULL_P0
```

Expected: architecture, Python, Swift and Xcode stages all pass. Preserve the raw output and any receipt evidence under the project’s existing `.agents/receipts/` or `.hacf/logs/` conventions; do not add root-level logs.

- [ ] **Step 5: Verify scope discipline and commit history**

```bash
git status --short
git diff --name-only origin/main...HEAD
git log --oneline --decorate -4
```

Expected: only the classifier, its tests, the two workflows, the workflow tests, and the CI baseline document are present; pre-existing user files in the main worktree remain untouched; commits are split into the three logical slices above.

- [ ] **Step 6: Report local vs cloud evidence**

Report the exact local exit codes and test counts. Explicitly mark GitHub Actions timing and skipped-job behavior as pending cloud verification until a PR run executes the new workflow; do not claim the target latency before that run exists.

## Self-review checklist

- Spec coverage: Tasks 1–4 cover classifier behavior, job topology, cache/lock cleanup, reporter trigger, documentation, required checks, fail-closed behavior and rollback constraints.
- Placeholder scan: no unresolved placeholder steps are used; each code change has concrete test, implementation, verification and commit commands.
- Interface consistency: `ScopeDecision`, `classify_paths`, `decision_from_nul_bytes`, `write_github_output`, and `main` are introduced in Task 1 and consumed by the workflow in Task 2; the output keys match the job outputs in Task 2.
- Review focus coverage: every focus item has a test in Tasks 1–3 or a deterministic probe in Task 4.
