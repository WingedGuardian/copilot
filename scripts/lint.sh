#!/bin/bash
# Full ruff lint + format check for manual use.
# Pre-commit hook only runs E,F (correctness). This runs all configured rules.
set -e

cd "$(git rev-parse --show-toplevel)"

echo "=== ruff check (E,F,I,N,W) ==="
ruff check nanobot/ scripts/ --select E,F,I,N,W "$@"

echo ""
echo "=== ruff format --check ==="
ruff format --check nanobot/ scripts/ "$@"

echo ""
echo "All clean."
