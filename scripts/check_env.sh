#!/usr/bin/env bash
set -euo pipefail

echo "=== [World of Mysteries] Environment Verification ==="

# 1. Check Python
PYTHON_BIN="$(which python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ python3 not found!"
    exit 1
fi
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "✅ Python executable: $PYTHON_BIN (version: $PYTHON_VERSION)"

# Verify Python >= 3.14.0
$PYTHON_BIN -c 'import sys; assert sys.version_info >= (3, 14), f"Python >= 3.14 required, got {sys.version}"'
echo "✅ Python version >= 3.14 requirement satisfied"

# Verify GIL build
IS_FREE_THREADED="$($PYTHON_BIN -c 'import sysconfig; print(bool(sysconfig.get_config_var("Py_GIL_DISABLED")))')"
if [ "$IS_FREE_THREADED" = "False" ]; then
    echo "✅ CPython standard GIL build confirmed"
else
    echo "⚠️ Warning: Python is free-threaded build!"
fi

# 2. Check uv
UV_BIN="$(which uv || true)"
if [ -z "$UV_BIN" ]; then
    echo "❌ uv package manager not found!"
    exit 1
fi
echo "✅ uv found: $($UV_BIN --version)"

# 3. Check Swift & Xcode
SWIFT_BIN="$(which swift || true)"
if [ -z "$SWIFT_BIN" ]; then
    echo "❌ swift compiler not found!"
    exit 1
fi
echo "✅ Swift compiler: $($SWIFT_BIN --version | head -n 1)"

echo "=== All environment baseline prerequisites passed ==="
