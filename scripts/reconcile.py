"""
Parallel run from the command line: load the full dataset through the API,
close the quarter, reconcile every payout with the Excel oracle and (on
PostgreSQL) run the SQL invariants. Writes a report folder.

Against a running server:
    python scripts/reconcile.py --base-url http://localhost:8000 \
        --database-url postgresql+psycopg://qa@localhost:5432/comp --label rc2

In-process (starts the app on the given database):
    python scripts/reconcile.py --database-url sqlite:///recon.db --in-process --label local

--mode single posts transactions one by one (workaround when imports fail).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qa_tools import loader, reconcile, sql_checks  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url")
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--mode", choices=["import", "single"], default="import")
    ap.add_argument("--label", default="local")
    args = ap.parse_args()

    out = ROOT / "reports" / args.label / "reconciliation"
    started = time.time()

    if args.in_process:
        from fastapi.testclient import TestClient
        from sqlmodel import SQLModel, create_engine

        from app.main import create_app

        if args.database_url.startswith("postgresql"):
            engine = create_engine(args.database_url)
            SQLModel.metadata.drop_all(engine)
            engine.dispose()
        app = create_app(args.database_url)
        client_cm = TestClient(app, raise_server_exceptions=False)
    else:
        import httpx

        client_cm = httpx.Client(base_url=args.base_url, timeout=300)

    with client_cm as client:
        version = client.get("/health").json().get("version")
        try:
            result = loader.load(client, mode=args.mode)
        except loader.LoadError as exc:
            out.mkdir(parents=True, exist_ok=True)
            blocked = {"version": version, "mode": args.mode, "status": "BLOCKED", "step": exc.step,
                       "http_status": exc.status, "response": exc.body}
            (out / "summary.json").write_text(json.dumps(blocked, indent=2, default=str) + "\n")
            print(json.dumps(blocked, indent=2, default=str))
            return 2
        payouts = {}
        for p in loader.PERIODS:
            for row in client.get(f"/periods/{p}/payouts").json():
                payouts[(p, row["seller_id"])] = row

    mismatches = reconcile.compare_payouts(payouts, reconcile.read_oracle())
    totals = reconcile.compare_totals(result["closes"])
    meta = {"version": version, "mode": args.mode, "status": "COMPLETED", "rows_compared": len(payouts),
            "transactions_loaded": result["transactions"], "seconds": round(time.time() - started, 1),
            "close_responses": result["closes"]}
    summary = reconcile.write_report(out, mismatches, totals, meta)

    if args.database_url.startswith("postgresql"):
        checks = sql_checks.run(args.database_url)
        report = {name: {"rows": len(rows), "sample": rows[:5]} for name, rows in checks.items()}
        (out / "sql-checks.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        summary["sql_checks_failing"] = [n for n, r in report.items() if r["rows"]]

    print(json.dumps({k: v for k, v in summary.items() if k != "close_responses"}, indent=2, default=str))
    ok = not mismatches and not totals and not summary.get("sql_checks_failing")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
