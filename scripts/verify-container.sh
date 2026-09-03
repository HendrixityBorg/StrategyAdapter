#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" == "0" ]]; then
  echo "严格验证拒绝以 root 用户运行。" >&2
  exit 1
fi

evidence_dir="${1:-/psrc/reports}"
temporary_root="$(mktemp -d /tmp/psrc-verify.XXXXXX)"
trap 'rm -rf -- "$temporary_root"' EXIT
export UV_CACHE_DIR="$temporary_root/uv-cache"
export COVERAGE_FILE="$temporary_root/.coverage"
export HYPOTHESIS_STORAGE_DIRECTORY="$temporary_root/hypothesis"

cd /app
mkdir -p "$evidence_dir"

uv run --frozen ruff check . --cache-dir="$temporary_root/ruff-cache"
uv run --frozen mypy src tests --cache-dir="$temporary_root/mypy-cache"

uv run --frozen psrc schema export --output "$temporary_root/schemas"
diff -ru /app/schemas/generated "$temporary_root/schemas"

uv run --frozen psrc package export --output "$temporary_root/strategies"
diff -ru /app/strategies "$temporary_root/strategies"

uv run --frozen pytest -q -p no:cacheprovider \
  --junitxml="$evidence_dir/junit.xml" \
  --cov=psrc \
  --cov-report="json:$evidence_dir/coverage.json" \
  --cov-fail-under=90

uv run --frozen psrc demo all --output "$evidence_dir/runs/all" --require-strict
uv run --frozen psrc demo failures --output "$evidence_dir/runs/failures"
uv run --frozen psrc demo adapters --output "$evidence_dir/runs/adapters"
uv run --frozen psrc demo compatibility --output "$evidence_dir/runs/compatibility"
uv run --frozen psrc verify \
  --matrix /app/ACCEPTANCE_MATRIX.yaml \
  --evidence-root "$evidence_dir" \
  --output "$evidence_dir/acceptance-report.json" \
  --require-strict
