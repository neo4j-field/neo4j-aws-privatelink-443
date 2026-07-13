#!/usr/bin/env bash
# Runs the Postman collection via Newman against both environments back-to-back
# and prints the two "average response time" lines side by side.
#
# Usage:
#   ./run-comparison.sh [iterations]
#
# Requires: npm install -g newman

set -euo pipefail
cd "$(dirname "$0")"

ITERATIONS="${1:-50}"
COLLECTION="Neo4j-HAProxy-vs-Direct.postman_collection.json"

if ! command -v newman >/dev/null 2>&1; then
  echo "newman not found. Install it with: npm install -g newman" >&2
  exit 1
fi

echo "=== Direct baseline (HAProxy bypassed) — ${ITERATIONS} iterations ==="
newman run "$COLLECTION" -e direct-baseline.postman_environment.json -n "$ITERATIONS" \
  --reporters cli | tee /tmp/newman-direct-baseline.log | grep -A1 "average response time" || true

echo
echo "=== Via HAProxy (port 443) — ${ITERATIONS} iterations ==="
newman run "$COLLECTION" -e via-haproxy.postman_environment.json -n "$ITERATIONS" \
  --reporters cli | tee /tmp/newman-via-haproxy.log | grep -A1 "average response time" || true

echo
echo "Full logs: /tmp/newman-direct-baseline.log and /tmp/newman-via-haproxy.log"
