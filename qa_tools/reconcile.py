"""
Parallel run: compare what the engine paid with what the Excel oracle says.

Every field is compared as text, exactly as the API returns it (two-decimal
strings), so a one-cent difference is a mismatch. No tolerance is applied.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

ORACLE = Path(__file__).resolve().parent.parent / "oracle"
FIELDS = ("quota", "net_credited", "attainment_pct", "qualified", "payout")


def read_oracle(path: Path = ORACLE / "oracle_payouts.csv") -> dict:
    rows = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        r["qualified"] = r["qualified"] == "True"
        rows[(r["period_id"], r["seller_id"])] = r
    return rows


def compare_payouts(api_rows: dict, oracle: dict) -> list[dict]:
    """api_rows: {(period, seller): row as returned by GET /periods/{p}/payouts}."""
    mismatches = []
    for key in sorted(set(api_rows) | set(oracle)):
        a, o = api_rows.get(key), oracle.get(key)
        if a is None or o is None:
            mismatches.append({"period_id": key[0], "seller_id": key[1], "field": "row",
                               "api": "missing" if a is None else "present",
                               "oracle": "missing" if o is None else "present", "difference": ""})
            continue
        for f in FIELDS:
            if a[f] != o[f]:
                diff = ""
                if f in ("net_credited", "payout", "quota"):
                    diff = str(Decimal(a[f]) - Decimal(o[f]))
                mismatches.append({"period_id": key[0], "seller_id": key[1], "field": f,
                                   "api": a[f], "oracle": o[f], "difference": diff})
    return mismatches


def compare_totals(closes: dict, summary_path: Path = ORACLE / "oracle_summary.json") -> list[dict]:
    expected = json.loads(summary_path.read_text(encoding="utf-8"))["periods"]
    out = []
    for period, exp in expected.items():
        got = closes.get(period, {})
        for api_field, oracle_field in (("sellers", "payout_rows"), ("total_payout", "total_payout")):
            if str(got.get(api_field)) != str(exp[oracle_field]):
                out.append({"period_id": period, "field": api_field,
                            "api": got.get(api_field), "oracle": exp[oracle_field]})
    return out


def write_report(folder: Path, mismatches: list[dict], totals: list[dict], meta: dict) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "mismatches.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["period_id", "seller_id", "field", "api", "oracle", "difference"])
        w.writeheader()
        w.writerows(mismatches)
    rows_with_issue = {(m["period_id"], m["seller_id"]) for m in mismatches}
    by_field: dict[str, int] = {}
    for m in mismatches:
        by_field[m["field"]] = by_field.get(m["field"], 0) + 1
    payout_diff = sum((Decimal(m["difference"]) for m in mismatches if m["field"] == "payout"), Decimal("0"))
    summary = {**meta,
               "rows_compared": meta.get("rows_compared"),
               "rows_matching": meta.get("rows_compared", 0) - len(rows_with_issue),
               "rows_with_mismatch": len(rows_with_issue),
               "mismatches_by_field": by_field,
               "net_payout_difference_api_minus_oracle": f"{payout_diff:.2f}",
               "period_total_mismatches": totals}
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
