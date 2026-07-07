#!/usr/bin/env bash
# Run the raven_framework test suite.
# Must be run from anywhere inside the repo; it always operates relative to the
# raven_framework package root so pytest picks up pyproject.toml settings.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> raven_framework tests"
echo "    package root : $PKG_ROOT"
echo "    python       : $(python --version 2>&1)"
echo ""

# Install/upgrade the package in editable mode if it isn't already importable.
if ! python -c "import raven_framework" 2>/dev/null; then
    echo "==> Installing raven_framework (editable) ..."
    pip install -e "$PKG_ROOT[dev]" -q
fi

cd "$PKG_ROOT"
python -m pytest tests/ "$@"
