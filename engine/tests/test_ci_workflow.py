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
