#!/usr/bin/env bash
# ============================================================
# Auto-AI-WebPost — one-command local health check.
# Mirrors what CI runs: syntax, dependencies, tests, 100% coverage.
#
#   bash scripts/check.sh               # full: compileall + deps + YAML + tests + coverage
#   bash scripts/check.sh --fast        # fast: everything except tests/coverage
#
# Safe by default: if dependencies are missing it tells you how to
# set up the venv instead of installing into the system interpreter.
# ============================================================
set -euo pipefail

RUN_TESTS=1
case "${1:-}" in
    "" ) ;;
    --fast ) RUN_TESTS=0 ;;
    * )
        echo "Usage: bash scripts/check.sh [--fast]" >&2
        exit 2
        ;;
esac

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

PY=""
for candidate in .venv/bin/python3 .venv/bin/python; do
    if [ -x "$candidate" ]; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
    done
fi
if [ -z "$PY" ]; then
    echo "No Python interpreter found. Install Python 3.9+, then re-run scripts/mac-setup.sh." >&2
    exit 1
fi

if ! "$PY" -c "import yaml, requests, pytest" >/dev/null 2>&1; then
    echo "Dependencies missing for $PY." >&2
    echo "" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  source .venv/bin/activate" >&2
    echo "  pip install -r requirements-dev.txt" >&2
    echo "" >&2
    echo "Or just re-run: bash scripts/mac-setup.sh" >&2
    exit 1
fi

echo "==> Python byte-compile check"
"$PY" -m compileall -q autowebpost tests

echo "==> Python 3.9 syntax compatibility"
"$PY" - <<'PY'
import ast, pathlib, sys
bad = []
for root in ("autowebpost", "tests"):
    for p in pathlib.Path(root).rglob("*.py"):
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p), feature_version=(3, 9))
        except SyntaxError as exc:
            bad.append(f"{p}:{exc.lineno}: {exc.msg}")
if bad:
    print("\n".join(bad), file=sys.stderr)
    raise SystemExit(1)
print("  ok")
PY

echo "==> Dependency consistency"
"$PY" -m pip check

echo "==> CLI import"
"$PY" -m autowebpost.cli --version >/dev/null

echo "==> YAML syntax"
"$PY" - <<'PY'
import pathlib, yaml
paths = [pathlib.Path(".github/workflow-templates/autopost.yml"),
         pathlib.Path(".github/workflows/tests.yml"),
         pathlib.Path("data/sites.yaml"),
         pathlib.Path("data/config.example.yaml"),
         pathlib.Path("data/persona.example.yaml")]
for p in paths:
    if p.exists():
        yaml.safe_load(p.read_text(encoding="utf-8"))
        print("  ok", p)
PY

echo "==> Shell syntax"
bash -n scripts/*.sh bin/autowebpost

if [ "$RUN_TESTS" = "1" ]; then
    echo "==> Tests + coverage (CI gate: 100%, warnings are errors)"
    "$PY" -m pytest -W error --cov=autowebpost --cov-report=term-missing --cov-fail-under=100
    echo ""
    echo "All checks passed."
else
    echo ""
    echo "Fast checks passed (tests/coverage skipped)."
fi
