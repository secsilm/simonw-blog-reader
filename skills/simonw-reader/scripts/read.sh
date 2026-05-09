#!/usr/bin/env bash
# Thin wrapper around the simonw_reader fetch-only CLI.
# Usage: read.sh <url> [extra args ...]
#
# Emits JSON on stdout. The agent calling the skill is expected to do the
# analysis itself — this script never calls any LLM.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [--max-refs N] [--ref-chars N]" >&2
  exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Prefer an installed entry point (works in any env where the package
# was installed with `pip install -e .` or `uv pip install -e .`).
if command -v simonw-fetch >/dev/null 2>&1; then
  exec simonw-fetch "$@"
fi

# Otherwise prefer `uv run` from the repo root: it auto-syncs deps from
# uv.lock into a local .venv and runs the entry point.
if command -v uv >/dev/null 2>&1 && [[ -f "$REPO_ROOT/uv.lock" ]]; then
  exec uv run --project "$REPO_ROOT" simonw-fetch "$@"
fi

# Last resort: run from source against the ambient Python.
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m simonw_reader.fetch_cli "$@"
