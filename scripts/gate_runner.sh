#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=================================================================="
echo "🛡️  [World of Mysteries] Multi-Agent / Human Quality Gate Runner"
echo "=================================================================="

# 1. Architecture Fitness Gate
echo -e "\n--- [Stage 1: Architecture Fitness & Boundaries] ---"
python3 "${REPO_ROOT}/scripts/check_architecture_fitness.py"

# 2. Python Engine & Contract Gate
echo -e "\n--- [Stage 2: Python Engine & Contract Tests (pytest)] ---"
(
    cd "${REPO_ROOT}/engine"
    uv run --extra dev pytest -q
)

# 3. Swift 6 macOS App Gate
echo -e "\n--- [Stage 3: Swift 6 App & Protocol Tests (swift test)] ---"
(
    cd "${REPO_ROOT}/macos-app"
    swift test
)

echo -e "\n=================================================================="
echo "🎉 ALL LOCAL PRE-COMMIT GATES PASSED! READY FOR REVIEW & MERGE."
echo "=================================================================="
