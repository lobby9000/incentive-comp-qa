"""
Measure how good the functional suite is at catching faults (mutation testing
with hand-written mutation operators).

Each mutant changes one rule of the engine on purpose (an inclusive bound
made exclusive, a rate, a rounding mode, a removed validation). The suite runs
against every mutant; a mutant is "killed" when at least one test fails. A
surviving mutant points at a rule the tests do not really pin down.

The source files are restored after every mutant, even on errors.

Usage: python scripts/mutation_check.py [--label rc2]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTANTS = [
    ("M01", "app/calc.py", "qualified = attainment >= GATE", "qualified = attainment > GATE",
     "Gate becomes exclusive (50% no longer qualifies)"),
    ("M02", "app/calc.py", "qualified = attainment >= GATE", "qualified = attainment_pct >= GATE * 100",
     "Gate evaluated on the rounded display value (BUG-002 reintroduced)"),
    ("M03", "app/calc.py", "total.quantize(CENT, rounding=ROUND_HALF_UP)", "total.quantize(CENT)",
     "Payout rounding back to banker's rounding (BUG-003 reintroduced)"),
    ("M04", "app/calc.py", '("B", Decimal("0.80"), Decimal("1.00"), Decimal("0.025"))',
     '("B", Decimal("0.80"), Decimal("1.00"), Decimal("0.020"))', "Band B rate 2.5% becomes 2.0%"),
    ("M05", "app/calc.py", '("C", Decimal("1.00"), Decimal("1.50"), Decimal("0.040"))',
     '("C", Decimal("1.00"), Decimal("1.40"), Decimal("0.040"))', "Band C upper limit 150% becomes 140%"),
    ("M06", "app/calc.py", '("D", Decimal("1.50"), Decimal("2.00"), Decimal("0.050"))',
     '("D", Decimal("1.50"), Decimal("9.99"), Decimal("0.050"))', "Cap at 200% removed"),
    ("M07", "app/calc.py", "        if base < 0:\n            base = Decimal(\"0\")",
     "        if base < -10**12:\n            base = Decimal(\"0\")", "Negative band bases no longer clamped to zero"),
    ("M08", "app/calc.py", "(attainment * 100).quantize(CENT, rounding=ROUND_HALF_UP)",
     "(attainment * 100).quantize(CENT)", "Attainment display back to banker's rounding (BUG-006)"),
    ("M09", "app/service.py", "if days <= CLAWBACK_DAYS:", "if days < CLAWBACK_DAYS:",
     "Clawback window excludes day 30 (BUG-004 reintroduced)"),
    ("M10", "app/service.py", "if days <= CLAWBACK_DAYS:", "if days <= CLAWBACK_DAYS + 1:",
     "Clawback window includes day 31"),
    ("M11", "app/service.py", "values = [-v for v in split_cents(amount_cents, splits)]",
     "values = split_cents(-amount_cents, splits)", "Negative amount split with floor (BUG-005 reintroduced)"),
    ("M12", "app/service.py", "second = amount_cents * splits[1] // 100",
     "second = -(-amount_cents * splits[1] // 100)", "Remainder cent goes to the second seller"),
    ("M13", "app/service.py", "if returned + amount_cents > original.amount_cents:",
     "if returned + amount_cents >= original.amount_cents:", "A return of the exact remaining amount is rejected"),
    ("M14", "app/service.py", "if data.transaction_id in pending or session.get(Txn, data.transaction_id) is not None:",
     "if data.transaction_id in pending:", "Duplicate check against stored transactions removed"),
    ("M15", "app/service.py", "if primary.store_id != data.store_id:", "if False:",
     "Primary seller store rule removed"),
    ("M16", "app/service.py", 'select(Period).where(Period.start_date < period.start_date, Period.status == "OPEN")',
     'select(Period).where(Period.start_date > period.start_date, Period.status == "OPEN")',
     "Close-in-order check looks at later periods"),
    ("M17", "app/service.py", "missing = sorted(credited_sellers - with_quota)", "missing = []",
     "Quota-missing check removed from close"),
    ("M18", "app/service.py", 'if seller.status != "ACTIVE":', 'if seller.status == "SUSPENDED":',
     "Inactive sellers can receive credit"),
]


def run_suite() -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True, timeout=900)
    first_fail = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FAILED")), "")
    return proc.returncode != 0, first_fail.replace("FAILED ", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="local")
    args = ap.parse_args()

    baseline_failed, _ = run_suite()
    if baseline_failed:
        print("The suite fails on the unmodified code; fix that first.")
        return 2

    results = []
    for mid, rel, old, new, description in MUTANTS:
        path = ROOT / rel
        original = path.read_text(encoding="utf-8")
        if original.count(old) != 1:
            results.append({"id": mid, "description": description, "status": "INVALID (pattern not found once)"})
            continue
        started = time.time()
        try:
            path.write_text(original.replace(old, new), encoding="utf-8")
            killed, by = run_suite()
        finally:
            path.write_text(original, encoding="utf-8")
        results.append({"id": mid, "file": rel, "description": description,
                        "status": "KILLED" if killed else "SURVIVED", "killed_by": by,
                        "seconds": round(time.time() - started, 1)})
        print(f"{mid} {results[-1]['status']:9} {description}  {by}")

    killed = sum(r["status"] == "KILLED" for r in results)
    summary = {"mutants": len(results), "killed": killed, "survived": len(results) - killed,
               "score": f"{100 * killed / len(results):.0f}%", "results": results}
    out = ROOT / "reports" / args.label / "mutation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nKilled {killed} of {len(results)} mutants ({summary['score']}). Report: {out.relative_to(ROOT)}")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
