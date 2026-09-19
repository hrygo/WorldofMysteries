import sys
from io import StringIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from ci_changed_scope import (
    ScopeDecision,
    classify_paths,
    decision_from_nul_bytes,
    write_github_output,
    write_summary,
)


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["docs/design.md", ".agents/receipts/T1/abc.json"], (False, False, "meta")),
        (["engine/domain/world.py"], (True, False, "python")),
        (["macos-app/WorldofMysteries/AppState.swift"], (False, True, "swift")),
        (["contracts/schemas/story.schema.json"], (True, True, "full")),
        (["scripts/check_architecture_fitness.py"], (True, True, "full")),
        (["engine/uv.lock"], (True, True, "full")),
        (["engine/pyproject.toml"], (True, True, "full")),
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


def test_summary_escapes_untrusted_reason_text():
    output = StringIO()
    write_summary(
        ScopeDecision.full("未知路径: `evil`\n## forged <tag>"),
        output,
    )
    assert "<code>未知路径: `evil` ## forged &lt;tag&gt;</code>" in output.getvalue()
