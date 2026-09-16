#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    echo "Usage: $0 [create <branch_name> | list | remove <branch_name>]"
    echo "Example: $0 create feat/data-kernel"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

ACTION="$1"

case "$ACTION" in
    create)
        if [ $# -lt 2 ]; then
            echo "❌ Missing branch name!"
            usage
        fi
        BRANCH="$2"
        TARGET_DIR="${REPO_ROOT}/../wom-worktrees/${BRANCH//\//-}"
        mkdir -p "$(dirname "$TARGET_DIR")"
        echo "🌿 Creating Git Worktree for branch '${BRANCH}' at: ${TARGET_DIR}"
        git worktree add -b "$BRANCH" "$TARGET_DIR" main
        echo "✅ Worktree ready! Navigate to: cd ${TARGET_DIR}"
        ;;
    list)
        echo "📋 Current active Git Worktrees:"
        git worktree list
        ;;
    remove)
        if [ $# -lt 2 ]; then
            echo "❌ Missing branch name to remove!"
            usage
        fi
        BRANCH="$2"
        TARGET_DIR="${REPO_ROOT}/../wom-worktrees/${BRANCH//\//-}"
        echo "🧹 Removing Git Worktree at: ${TARGET_DIR}"
        git worktree remove "$TARGET_DIR"
        echo "✅ Worktree removed."
        ;;
    *)
        usage
        ;;
esac
