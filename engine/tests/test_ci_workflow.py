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


def test_pull_request_scope_uses_trusted_base_classifier():
    assert 'git cat-file -e "$PR_BASE_SHA:scripts/ci_changed_scope.py"' in CI
    assert 'git show "$PR_BASE_SHA:scripts/ci_changed_scope.py"' in CI
    assert '"$RUNNER_TEMP/ci_changed_scope.py"' in CI
    assert "base branch has no trusted classifier" in CI


def test_aggregate_validates_scope_and_keeps_outputs_out_of_shell_source():
    assert 'CI_SCOPE: ${{ needs.change-scope.outputs.scope }}' in CI
    assert 'RUN_PYTHON: ${{ needs.change-scope.outputs.run_python }}' in CI
    assert 'RUN_SWIFT: ${{ needs.change-scope.outputs.run_swift }}' in CI
    assert 'case "$CI_SCOPE" in' in CI
    assert "Inconsistent CI scope outputs" in CI
    assert '[ "${{ needs.change-scope.outputs.run_python }}"' not in CI
    assert '[ "${{ needs.change-scope.outputs.run_swift }}"' not in CI


def test_ci_does_not_keep_unusable_or_duplicate_checks():
    assert "actions/cache@v6" not in CI
    assert "uv lock --check" not in CI


def test_capsule_audit_does_not_interpolate_branch_input_into_shell_source():
    capsule_audit = (ROOT / ".github/workflows/capsule-audit.yml").read_text(encoding="utf-8")
    assert "BASE_REF: ${{ github.base_ref }}" in capsule_audit
    assert '--base-ref "origin/$BASE_REF"' in capsule_audit
    assert '--base-ref "origin/${{ github.base_ref }}"' not in capsule_audit


def test_workflows_do_not_persist_checkout_credentials():
    workflow_paths = (
        ".github/workflows/ci.yml",
        ".github/workflows/capsule-audit.yml",
        ".github/workflows/pr-gate-reporter.yml",
        ".github/workflows/bundled-engine.yml",
        ".github/workflows/component-gallery-runtime-visual-qa.yml",
        ".github/workflows/nightly-golden-audit.yml",
    )
    for relative_path in workflow_paths:
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")
        assert workflow.count("uses: actions/checkout@v7") == workflow.count(
            "persist-credentials: false"
        ), relative_path
