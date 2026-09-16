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

    if all_violations:
        print(f"\n💥 Total {len(all_violations)} architecture fitness violation(s) detected!")
        return 1

    print("\n🎉 All architecture fitness functions PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
