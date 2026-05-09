#!/usr/bin/env bash
# Thin wrapper around the simonw_reader Python module.
# Usage: read.sh <url> [extra args ...]
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [--lang zh|en] [--max-refs N] [--json]" >&2
  exit 64
fi

# Resolve the repo root relative to this script so the skill works regardless
# of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Prefer an installed `simonw-read` entry point if present; otherwise run the
# module from the source tree.
if command -v simonw-read >/dev/null 2>&1; then
  exec simonw-read "$@"
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m simonw_reader "$@"
