"""
Build the traceability matrix from real results, not by hand.

Reads every JUnit report under reports/<build>/ (pytest on SQLite and
PostgreSQL, the full-volume run, Newman), maps each result to its test case ID
(the ID is part of every test and request name), adds manual results for runs
that could not execute, and links defects from bugs/*.md ("Found by").

Writes:
  docs/03-test-cases.csv   adds result_rc1, result_rc2 and defects columns
  docs/04-traceability.md  requirement -> test cases -> results -> defects

Usage: python scripts/traceability.py
"""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ["rc1", "rc2"]
TC_RE = re.compile(r"TC[-_]([A-Z]{2,3})[-_](\d{3})")
# Failure text -> defect, for failures whose test case is not listed in a bug's "Found by"
SIGNATURES = {
    "ForeignKeyViolation": "BUG-008",
    "'list' object has no attribute": "BUG-001",
    "but got 500": "BUG-008",
}


def tc_of(text: str) -> str | None:
    m = TC_RE.search(text or "")
    return f"TC-{m.group(1)}-{m.group(2)}" if m else None


FAILURE_BUGS: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))


def junit_results(path: Path, build: str = "") -> dict[str, list[bool]]:
    """{tc_id: [passed?, ...]} for one JUnit file (pytest or Newman)."""
    out: dict[str, list[bool]] = defaultdict(list)
    root = ET.parse(path).getroot()
    for suite in root.iter("testsuite"):
        suite_tc = tc_of(suite.get("name", ""))
        for case in suite.iter("testcase"):
            tc = tc_of(case.get("name", "")) or suite_tc
            if tc is None:
                continue
            problem = case.find("failure") if case.find("failure") is not None else case.find("error")
            failed = problem is not None
            skipped = case.find("skipped") is not None
            if failed:
                text = (problem.get("message") or "") + (problem.text or "")
                for sig, bug in SIGNATURES.items():
                    if sig in text:
                        FAILURE_BUGS[build][tc].add(bug)
            if not skipped:
                out[tc].append(not failed)
    return out


PER_SOURCE: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)


def build_results(build: str) -> dict[str, tuple[str, str]]:
    folder = ROOT / "reports" / build
    merged: dict[str, list[bool]] = defaultdict(list)
    sources: dict[str, set] = defaultdict(set)
    for path in sorted(folder.glob("*.xml")):
        per_file = junit_results(path, build)
        failed_tcs = sum(1 for r in per_file.values() if not all(r))
        PER_SOURCE[build][path.stem] = (len(per_file), failed_tcs)
        for tc, results in per_file.items():
            merged[tc].extend(results)
            sources[tc].add(path.stem)
    status = {tc: ("Passed" if all(r) else "Failed", ", ".join(sorted(sources[tc]))) for tc, r in merged.items()}
    manual = folder / "manual-results.json"
    if manual.exists():
        for tc, (result, note) in json.loads(manual.read_text())["results"].items():
            status[tc] = (result, note)
            for bug in re.findall(r"BUG-\d{3}", note):
                FAILURE_BUGS[build][tc].add(bug)
    return status


def defects_by_tc() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for path in sorted((ROOT / "bugs").glob("BUG-*.md")):
        text = path.read_text(encoding="utf-8")
        found = re.search(r"\| Found by \| (.+?) \|", text)
        for tc in TC_RE.finditer(found.group(1) if found else ""):
            out[f"TC-{tc.group(1)}-{tc.group(2)}"].append(path.stem)
    return out


def expand_requirements(text: str) -> list[str]:
    reqs: list[str] = []
    for part in text.split(","):
        part = part.strip()
        rng = re.match(r"(REQ-[A-Z]+)-(\d+) to (REQ-[A-Z]+)-(\d+)", part)
        if rng and rng.group(1) == rng.group(3):
            reqs += [f"{rng.group(1)}-{i:02d}" for i in range(int(rng.group(2)), int(rng.group(4)) + 1)]
        elif part.startswith("REQ-"):
            reqs.append(part.split()[0])
    return reqs


def main() -> None:
    catalog_path = ROOT / "docs" / "03-test-cases.csv"
    rows = list(csv.DictReader(open(catalog_path, encoding="utf-8")))
    base_fields = ["tc_id", "requirement", "suite", "title", "technique", "priority",
                   "preconditions", "steps", "expected", "automation"]
    results = {b: build_results(b) for b in BUILDS}
    defects = defects_by_tc()

    for r in rows:
        for b in BUILDS:
            r[f"result_{b}"] = results[b].get(r["tc_id"], ("Not run", ""))[0]
        linked = set(defects.get(r["tc_id"], []))
        if r["result_rc1"] != "Passed":
            linked |= FAILURE_BUGS["rc1"].get(r["tc_id"], set())
        r["defects"] = " ".join(sorted(linked))
    with open(catalog_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=base_fields + [f"result_{b}" for b in BUILDS] + ["defects"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    req_ids = re.findall(r"^\| (REQ-[A-Z]+-\d+) \|", (ROOT / "docs" / "01-requirements.md").read_text(), re.M)
    by_req: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for req in expand_requirements(r["requirement"]):
            by_req[req].append(r)

    def counts(b):
        c = defaultdict(int)
        for r in rows:
            c[r[f"result_{b}"]] += 1
        return c

    lines = ["# Traceability matrix", "",
             "Generated by `scripts/traceability.py` from the JUnit reports in `reports/` and the bug files in",
             "`bugs/`. Do not edit by hand.", "",
             "## Execution summary", "",
             "| Build | Test cases | Passed | Failed | Blocked | Not run |", "|---|---|---|---|---|---|"]
    for b in BUILDS:
        c = counts(b)
        lines.append(f"| {b} | {len(rows)} | {c['Passed']} | {c['Failed']} | {c['Blocked']} | {c['Not run']} |")
    lines += ["", "Per report (a test case counts as failed in a report when any of its results failed):", "",
              "| Build | Report | Test cases with results | Failed |", "|---|---|---|---|"]
    for b in BUILDS:
        for name, (n, failed) in sorted(PER_SOURCE[b].items()):
            lines.append(f"| {b} | `{name}` | {n} | {failed} |")
    uncovered = [q for q in req_ids if q not in by_req]
    lines += ["", f"Requirements: {len(req_ids)}. Covered by at least one test case: {len(req_ids) - len(uncovered)}."]
    if uncovered:
        lines.append(f"Not covered: {', '.join(uncovered)}.")
    lines += ["", "## Requirement coverage", "",
              "| Requirement | Test cases | rc1 | rc2 | Defects |", "|---|---|---|---|---|"]
    for q in req_ids:
        tcs = by_req.get(q, [])
        ids = ", ".join(r["tc_id"] for r in tcs) or "none"
        agg = {}
        for b in BUILDS:
            states = {r[f"result_{b}"] for r in tcs}
            agg[b] = ("Failed" if "Failed" in states else "Blocked" if "Blocked" in states
                      else "Passed" if states == {"Passed"} else "Partial" if "Passed" in states else "Not run")
        bugs = sorted({d for r in tcs for d in r["defects"].split()})
        lines.append(f"| {q} | {ids} | {agg['rc1']} | {agg['rc2']} | {' '.join(bugs)} |")
    lines += ["", "## Test cases that did not pass in rc1", "",
              "| Test case | Priority | rc1 | rc2 | Defects |", "|---|---|---|---|---|"]
    for r in rows:
        if r["result_rc1"] != "Passed":
            lines.append(f"| {r['tc_id']} {r['title']} | {r['priority']} | {r['result_rc1']} | {r['result_rc2']} | {r['defects']} |")
    (ROOT / "docs" / "04-traceability.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for b in BUILDS:
        print(b, dict(counts(b)))
    print("uncovered requirements:", uncovered)


if __name__ == "__main__":
    main()
