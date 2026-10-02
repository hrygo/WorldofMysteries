#!/usr/bin/env python3
"""Architecture Fitness Function Checker for World of Mysteries.

Enforces strict architectural boundaries and invariants:
1. engine/domain/ must NOT import sqlite3, aiosqlite, agentscope, or cloud SDKs.
2. macos-app/ must NOT directly reference SQLite or Python runtime internals.
3. contracts/schemas/ must remain valid JSON Schemas.
"""

import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN_DIR = REPO_ROOT / "engine" / "domain"
CONTRACTS_SCHEMAS_DIR = REPO_ROOT / "contracts" / "schemas"
MACOS_APP_DIR = REPO_ROOT / "macos-app" / "WorldOfMysteries"

FORBIDDEN_DOMAIN_MODULES = {
    "sqlite3",
    "aiosqlite",
    "agentscope",
    "openai",
    "requests",
    "httpx",
    "urllib",
}


def check_domain_dependencies() -> list[str]:
    """Scan engine/domain/ to enforce zero external SDK/DB dependencies."""
    violations = []
    py_files = list(DOMAIN_DIR.glob("*.py"))

    for py_file in py_files:
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
        except Exception as e:
            violations.append(f"Syntax error parsing {py_file.name}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in FORBIDDEN_DOMAIN_MODULES:
                        violations.append(
                            f"[Invariant Violation] {py_file.relative_to(REPO_ROOT)}:{node.lineno} "
                            f"imports forbidden module '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in FORBIDDEN_DOMAIN_MODULES:
                        violations.append(
                            f"[Invariant Violation] {py_file.relative_to(REPO_ROOT)}:{node.lineno} "
                            f"imports from forbidden module '{node.module}'"
                        )
    return violations


def check_contracts_schemas() -> list[str]:
    """Verify that all JSON schemas in contracts/schemas/ are valid JSON."""
    violations = []
    schemas = list(CONTRACTS_SCHEMAS_DIR.glob("*.schema.json"))
    if not schemas:
        violations.append("No schema files found in contracts/schemas/")

    for s_file in schemas:
        try:
            with open(s_file, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            violations.append(f"Invalid JSON schema {s_file.name}: {e}")
    return violations


def check_macos_app_independence() -> list[str]:
    """Verify that macos-app/ does not directly import SQLite or access SQLite C APIs (Invariant 12)."""
    violations = []
    swift_files = list(MACOS_APP_DIR.glob("**/*.swift"))
    forbidden_tokens = ["import SQLite3", "import SQLite", "sqlite3_open", "sqlite3_exec"]

    for s_file in swift_files:
        try:
            with open(s_file, "r", encoding="utf-8") as f:
                content = f.read()
            for token in forbidden_tokens:
                if token in content:
                    violations.append(
                        f"[Invariant 12 Violation] {s_file.relative_to(REPO_ROOT)} contains forbidden DB direct access: '{token}'"
                    )
        except Exception as e:
            violations.append(f"Error reading {s_file.name}: {e}")
    return violations


def check_ai_layer_safety() -> list[str]:
    """Verify engine/ai/ does not perform direct database write operations (Invariant 5)."""
    violations = []
    ai_dir = REPO_ROOT / "engine" / "ai"
    if not ai_dir.exists():
        return violations

    forbidden_write_patterns = ["INSERT INTO", "UPDATE ", "DELETE FROM", "DROP TABLE"]
    for py_file in ai_dir.glob("**/*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read().upper()
            for pattern in forbidden_write_patterns:
                if pattern in content:
                    violations.append(
                        f"[Invariant 5 Violation] {py_file.relative_to(REPO_ROOT)} contains raw SQL write pattern: '{pattern}'"
                    )
        except Exception as e:
            violations.append(f"Error reading {py_file.name}: {e}")
    return violations


STORYBOOK_READING_MODULES = (
    "engine/application/storybook_projection.py",
    "engine/application/storybook_service.py",
)

#: Importing any of these into the reading logic would put a model or a network
#: hop between a committed Narrative Block and the page the reader sees.
MODEL_CAPABLE_MODULES = {
    "agentscope",
    "ai",
    "openai",
    "anthropic",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
}


def _forbidden_imports_in(py_file: Path, forbidden: set[str]) -> list[str]:
    """Report every import in ``py_file`` whose root module is forbidden."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except (OSError, SyntaxError, ValueError) as exc:
        return [f"Error reading {py_file.name}: {exc}"]

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden:
                    violations.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                violations.append((node.lineno, node.module))
    return [
        f"{py_file}:{lineno} imports '{module}'"
        for lineno, module in violations
    ]


def check_storybook_reading_path_is_model_free() -> list[str]:
    """PRD §20.1 / Invariant 9: reading the Story Book must never rewrite it.

    §20.1 allows a necessary transition or a closing paragraph but forbids
    letting the model republish an "approximately the same" novel once the
    Episode has been committed. The only structural way to keep that promise is
    for the modules that assemble the book to contain no model and no network
    hop at all.

    The scope is deliberately the projection and the service — the two modules
    that actually read committed state and shape the page. ``story_runtime`` is
    the composition root and must wire the model for the rest of the engine, so
    including it would flag the entire runtime rather than the reading path.
    """
    violations = []
    for relative in STORYBOOK_READING_MODULES:
        target = REPO_ROOT / relative
        if not target.is_file():
            violations.append(f"[Invariant 9 Violation] {relative} is missing")
            continue
        violations.extend(
            f"[Invariant 9 Violation] {line}"
            for line in _forbidden_imports_in(target, MODEL_CAPABLE_MODULES)
        )
    return violations


ALLOWED_ROOT_FILES = {
    "LICENSE",
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "NOTICE.md",
    "CODE_OF_CONDUCT.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".gitmessage",
    # git worktree 检出会把 `.git` 落成指针文件（非目录）；它是仓库机制而非根目录垃圾，
    # 误判会让 HACF 隔离工作区在 Stage 1 无条件失败。
    ".git",
    ".DS_Store",
}


def check_repository_root_cleanliness() -> list[str]:
    """Verify that no unexpected temporary files or reports are placed in REPO_ROOT."""
    violations = []
    for item in REPO_ROOT.iterdir():
        if item.is_file():
            name = item.name
            if name in ALLOWED_ROOT_FILES or name == ".env" or name.startswith(".env."):
                continue
            violations.append(
                f"[Root Cleanliness Violation] Unexpected file at repository root: '{name}'. "
                "Temporary reports, logs, and artifacts must be placed in .hacf/tmp/, logs/, or scratch/."
            )
    return violations


def main() -> int:
    print("🔍 [Architecture Fitness] Running architectural boundary checks...")
    all_violations = []

    # 1. Domain independence (Invariant 5 & 12)
    domain_violations = check_domain_dependencies()
    if domain_violations:
        all_violations.extend(domain_violations)
        for v in domain_violations:
            print(f"❌ {v}")
    else:
        print("✅ engine/domain/ has ZERO forbidden database/AI/cloud dependencies.")

    # 2. macOS App isolation (Invariant 12: App does not directly access database)
    app_violations = check_macos_app_independence()
    if app_violations:
        all_violations.extend(app_violations)
        for v in app_violations:
            print(f"❌ {v}")
    else:
        print("✅ macos-app/ strictly respects UDS IPC boundary (ZERO direct SQLite access).")

    # 3. AI layer safety (Invariant 5: AI outputs typed proposals only)
    ai_violations = check_ai_layer_safety()
    if ai_violations:
        all_violations.extend(ai_violations)
        for v in ai_violations:
            print(f"❌ {v}")
    else:
        print("✅ engine/ai/ strictly respects Proposal boundary (ZERO direct DB write operations).")

    # 4. Schema integrity
    schema_violations = check_contracts_schemas()
    if schema_violations:
        all_violations.extend(schema_violations)
        for v in schema_violations:
            print(f"❌ {v}")
    else:
        print("✅ contracts/schemas/ all schemas are syntactically valid JSON.")

    # 5. Repository root cleanliness (Root Cleanliness Principle)
    root_violations = check_repository_root_cleanliness()
    if root_violations:
        all_violations.extend(root_violations)
        for v in root_violations:
            print(f"❌ {v}")
    else:
        print("✅ REPO_ROOT is clean (ZERO unexpected reports/dumps/temporary files).")

    # 6. Story Book reading path stays model-free (Invariant 9 / PRD §20.1)
    reading_violations = check_storybook_reading_path_is_model_free()
    if reading_violations:
        all_violations.extend(reading_violations)
        for v in reading_violations:
            print(f"❌ {v}")
    else:
        print(
            "✅ Story Book reading path is model-free "
            "(ZERO model/network imports on the §20.1 read path)."
        )

    if all_violations:
        print(f"\n💥 Total {len(all_violations)} architecture fitness violation(s) detected!")
        return 1

    print("\n🎉 All architecture fitness functions PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
