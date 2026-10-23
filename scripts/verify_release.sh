#!/usr/bin/env bash
# One-command verification of procurecheck v1.0.0. No live model is required.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON="${PYTHON:-python3}"
else
  PYTHON="${PYTHON:-python}"
fi

echo "Python: $($PYTHON --version)"

VERSION="$($PYTHON -c "import procurecheck; print(procurecheck.__version__)")"
echo "Package: procurecheck ${VERSION}"
if [ "$VERSION" != "1.0.0" ]; then
  echo "error: expected procurecheck 1.0.0, got ${VERSION}" >&2
  exit 1
fi

echo
echo "== pytest (unit, approval gate, memory, workflow, and the rest of the suite) =="
$PYTHON -m pytest -q
echo
echo "== scripted memory demonstration (completeness audit, memory delta, used_by_planner=false) =="
$PYTHON tests/evaluation/run_memory_demonstration.py --scripted
echo
echo "== fail-closed approval gate is covered by tests/test_approval.py (already in pytest) =="
echo "== python run.py verify --quick (deterministic, no model) =="
$PYTHON run.py verify --quick

echo
echo "Release verification passed for procurecheck ${VERSION}."
