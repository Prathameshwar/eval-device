#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
case "${1:-api}" in
  api) exec uv run pms-api ;;
  worker) exec uv run pms-worker ;;
  retention) exec uv run pms-worker --retention ;;
  *) echo 'Use api, worker, or retention' >&2; exit 2 ;;
esac
