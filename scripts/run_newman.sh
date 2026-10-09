#!/usr/bin/env bash
# Start the API on a fresh database, run the Postman collection with Newman and
# write CLI, JUnit, JSON and HTML reports to reports/<label>/.
#
# Usage: scripts/run_newman.sh <label> [database_url]
#   scripts/run_newman.sh local
#   scripts/run_newman.sh rc2 postgresql+psycopg://qa@localhost:5432/comp
set -uo pipefail
LABEL=${1:-local}
DB_URL=${2:-sqlite:///./newman.db}
PORT=${PORT:-8000}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/reports/$LABEL"
mkdir -p "$OUT"
cd "$ROOT" || exit 1

python scripts/reset_db.py "$DB_URL" || exit 1
DATABASE_URL="$DB_URL" python -m uvicorn app.main:app --port "$PORT" --log-level warning \
  > "$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -sf "http://localhost:$PORT/health" > /dev/null && break
  sleep 0.2
done

newman run postman/commission-engine.postman_collection.json \
  --env-var "baseUrl=http://localhost:$PORT" \
  --reporters cli,junit,htmlextra,json \
  --reporter-junit-export "$OUT/newman-junit.xml" \
  --reporter-json-export "$OUT/newman.json" \
  --reporter-htmlextra-export "$OUT/newman-report.html" \
  --reporter-htmlextra-title "Commission Engine QA - $LABEL" \
  --reporter-htmlextra-browserTitle "Newman $LABEL" \
  --color off
STATUS=$?
echo "newman exit code: $STATUS (reports in reports/$LABEL)"
exit $STATUS
