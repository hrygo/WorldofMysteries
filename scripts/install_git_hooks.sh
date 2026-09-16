#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DEST="${REPO_ROOT}/.git/hooks/pre-commit"

echo "🔧 Installing Git pre-commit hook..."

cat << 'EOF' > "${HOOK_DEST}"
#!/usr/bin/env bash
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
echo "🚀 [Git Hook] Running World of Mysteries Quality Gate before commit..."
"${REPO_ROOT}/scripts/gate_runner.sh"
EOF

chmod +x "${HOOK_DEST}"
echo "✅ Git pre-commit hook installed successfully at ${HOOK_DEST}"
