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

if command -v simonw-fetch >/dev/null 2>&1; then
  exec simonw-fetch "$@"
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m simonw_reader.fetch_cli "$@"
