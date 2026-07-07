#!/usr/bin/env bash
# Run raven_framework unit tests locally.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
pip install -e ".[dev]" -q
python -m pytest -v tests "$@"
