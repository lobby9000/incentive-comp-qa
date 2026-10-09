"""
Build the Postman collection (v2.1) from readable Python definitions.

Requests run in order against a fresh database. Request names start with the
test case ID from docs/03-test-cases.csv so Newman's JUnit report traces back
to the catalog. Setup requests start with "Setup:".

A collection-level test runs after every request and checks the error
envelope (REQ-API-01) on any 4xx/5xx and a 2-second response budget.

Usage: python postman/build_collection.py   ->  postman/commission-engine.postman_collection.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

COLLECTION_TESTS = """
if (pm.response.code >= 400) {
    pm.test("Error body follows the REQ-API-01 envelope", function () {
        const j = pm.response.json();
        pm.expect(j).to.have.property("error");
        pm.expect(j.error).to.have.all.keys("code", "message", "details");
    });
}
pm.test("Response time under 2 s", function () {
    pm.expect(pm.response.responseTime).to.be.below(2000);
});
"""


def req(name, method, path, body=None, tests=""):
    item = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}] if body is not None else [],
            "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"],
                    "path": [p for p in path.split("/") if p]},
        },
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": tests.strip().splitlines()}}],
    }
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                                   "options": {"raw": {"language": "json"}}}
    return item


def status(tc, code):
    return f'pm.test("{tc} status {code}", function () {{ pm.response.to.have.status({code}); }});\n'


def error(tc, code, http):
    return status(tc, http) + (
        f'pm.test("{tc} error code {code}", function () {{\n'
        f'    pm.expect(pm.response.json().error.code).to.eql("{code}");\n}});\n')


def credits_are(tc, expected: dict):
    return (f'pm.test("{tc} credit lines", function () {{\n'
            f'    const got = {{}};\n'
            f'    pm.response.json().credits.forEach(function (c) {{ got[c.seller_id] = c.credit; }});\n'
            f'    pm.expect(got).to.eql({json.dumps(expected)});\n}});\n')


def sale(tid, date, amount, credits, store="T1000"):
    return {"transaction_id": tid, "type": "SALE", "txn_date": date, "store_id": store, "amount": amount,
            "credits": [{"seller_id": s, "split_pct": p} for s, p in credits]}


def ret(tid, date, amount, original, store="T1000"):
    return {"transaction_id": tid, "type": "RETURN", "txn_date": date, "store_id": store, "amount": amount,
            "original_transaction_id": original}


def statement_is(tc, attainment, qualified, payout):
    return status(tc, 200) + (
        f'pm.test("{tc} statement values", function () {{\n'
        f'    const s = pm.response.json();\n'
        f'    pm.expect([s.attainment_pct, s.qualified, s.payout]).to.eql({json.dumps([attainment, qualified, payout])});\n'
        f'}});\n')


def build() -> dict:
    folders = []

    folders.append(("00 Smoke", [
        req("TC-API-001 Health answers with status and version", "GET", "/health", tests=status("TC-API-001", 200) + """
pm.test("TC-API-001 status ok and version", function () {
    const j = pm.response.json();
    pm.expect(j.status).to.eql("ok");
    pm.expect(j.version).to.be.a("string").and.not.empty;
    pm.collectionVariables.set("buildVersion", j.version);
});"""),
    ]))

    setup = [
        req("TC-SEL-001 Create a seller", "POST", "/sellers",
            {"seller_id": "S00001", "name": "Ana García", "store_id": "T1000"},
            status("TC-SEL-001", 201) + """
pm.test("TC-SEL-001 body echoes input and is ACTIVE", function () {
    const j = pm.response.json();
    pm.expect(j).to.eql({seller_id: "S00001", name: "Ana García", store_id: "T1000", status: "ACTIVE"});
});"""),
        req("Setup: seller S00002 in T1000", "POST", "/sellers",
            {"seller_id": "S00002", "name": "Luis Pérez", "store_id": "T1000"}, status("Setup", 201)),
        req("TC-SEL-002 Duplicate seller is rejected", "POST", "/sellers",
            {"seller_id": "S00001", "name": "Ana García", "store_id": "T1000"},
            error("TC-SEL-002", "DUPLICATE_SELLER", 409)),
        req("TC-API-002 Unknown seller uses the standard error body", "GET", "/sellers/S99999",
            error("TC-API-002", "SELLER_NOT_FOUND", 404)),
        req("TC-API-003 Missing field reports VALIDATION_ERROR", "POST", "/sellers",
            {"seller_id": "S00009", "store_id": "T1000"}, error("TC-API-003", "VALIDATION_ERROR", 422)),
        req("TC-QTA-001 Create a quota", "PUT", "/periods/2026-10/quotas/S00001", {"amount": "90000.00"},
            status("TC-QTA-001", 201)),
        req("TC-QTA-001 Replace the quota", "PUT", "/periods/2026-10/quotas/S00001", {"amount": "100000.00"},
            status("TC-QTA-001", 200) + """
pm.test("TC-QTA-001 amount replaced", function () { pm.expect(pm.response.json().amount).to.eql("100000.00"); });"""),
        req("Setup: quota 2026-10 S00002", "PUT", "/periods/2026-10/quotas/S00002", {"amount": "100000.00"},
            status("Setup", 201)),
        req("Setup: quota 2026-11 S00001", "PUT", "/periods/2026-11/quotas/S00001", {"amount": "100000.00"},
            status("Setup", 201)),
        req("Setup: quota 2026-11 S00002", "PUT", "/periods/2026-11/quotas/S00002", {"amount": "100000.00"},
            status("Setup", 201)),
        req("Setup: seller S00003 to deactivate", "POST", "/sellers",
            {"seller_id": "S00003", "name": "Sofía Ruiz", "store_id": "T1000"}, status("Setup", 201)),
        req("TC-SEL-007 Deactivate a seller", "PATCH", "/sellers/S00003", {"status": "INACTIVE"},
            status("TC-SEL-007", 200) + """
pm.test("TC-SEL-007 status is INACTIVE", function () { pm.expect(pm.response.json().status).to.eql("INACTIVE"); });"""),
    ]
    folders.append(("01 Sellers and quotas", setup))

    sales = [
        req("TC-TXN-001 Single-seller sale credits the full amount", "POST", "/transactions",
            sale("PM-SALE-1", "2026-10-15", 1500.5, [("S00001", 100)]),
            status("TC-TXN-001", 201) + credits_are("TC-TXN-001", {"S00001": "1500.50"}) + """
pm.test("TC-TXN-001 posts to 2026-10", function () { pm.expect(pm.response.json().period_id).to.eql("2026-10"); });"""),
        req("TC-API-005 Money is a two-decimal string", "GET", "/transactions/PM-SALE-1",
            status("TC-API-005", 200) + """
pm.test("TC-API-005 amount and credit are strings with two decimals", function () {
    const j = pm.response.json();
    pm.expect(j.amount).to.eql("1500.50");
    pm.expect(j.credits[0].credit).to.eql("1500.50");
});"""),
        req("TC-TXN-002 Two-seller 70/30 split", "POST", "/transactions",
            sale("PM-SALE-2", "2026-10-16", "10000.00", [("S00001", 70), ("S00002", 30)]),
            status("TC-TXN-002", 201) + credits_are("TC-TXN-002", {"S00001": "7000.00", "S00002": "3000.00"})),
        req("TC-TXN-003 Odd-cent split gives the remainder to the first seller", "POST", "/transactions",
            sale("PM-SALE-3", "2026-10-16", "100.01", [("S00001", 50), ("S00002", 50)]),
            status("TC-TXN-003", 201) + credits_are("TC-TXN-003", {"S00001": "50.01", "S00002": "50.00"})),
        req("TC-TXN-005 Splits must add up to 100", "POST", "/transactions",
            sale("PM-SALE-4", "2026-10-16", "100.00", [("S00001", 60), ("S00002", 39)]),
            error("TC-TXN-005", "INVALID_SPLIT", 422)),
        req("TC-TXN-009 Inactive seller cannot receive credit", "POST", "/transactions",
            sale("PM-SALE-5", "2026-10-16", "100.00", [("S00003", 100)]),
            error("TC-TXN-009", "SELLER_INACTIVE", 422)),
        req("TC-TXN-012 Duplicate transaction is rejected", "POST", "/transactions",
            sale("PM-SALE-1", "2026-10-15", 1500.5, [("S00001", 100)]),
            error("TC-TXN-012", "DUPLICATE_TRANSACTION", 409)),
        req("TC-TXN-018 Unknown transaction", "GET", "/transactions/NOPE-404",
            error("TC-TXN-018", "TRANSACTION_NOT_FOUND", 404)),
    ]
    folders.append(("02 Sales and crediting", sales))

    returns = [
        req("Setup: sale 10,000.00 split 70/30 on 2026-10-05", "POST", "/transactions",
            sale("PM-BASE", "2026-10-05", "10000.00", [("S00001", 70), ("S00002", 30)]), status("Setup", 201)),
        req("TC-RET-001 Return in the window mirrors the split", "POST", "/transactions",
            ret("PM-RET-1", "2026-10-20", "2000.00", "PM-BASE"),
            status("TC-RET-001", 201) + credits_are("TC-RET-001", {"S00001": "-1400.00", "S00002": "-600.00"})),
        req("TC-RET-002 Return on day 30 is clawed back", "POST", "/transactions",
            ret("PM-RET-2", "2026-11-04", "1000.00", "PM-BASE"),
            status("TC-RET-002", 201) + credits_are("TC-RET-002", {"S00001": "-700.00", "S00002": "-300.00"})),
        req("TC-RET-003 Return on day 31 has no clawback", "POST", "/transactions",
            ret("PM-RET-3", "2026-11-05", "1000.00", "PM-BASE"),
            status("TC-RET-003", 201) + """
pm.test("TC-RET-003 no credit lines", function () { pm.expect(pm.response.json().credits).to.eql([]); });"""),
        req("TC-RET-005 Returns cannot exceed the sale", "POST", "/transactions",
            ret("PM-RET-4", "2026-11-06", "6000.01", "PM-BASE"),
            error("TC-RET-005", "RETURN_EXCEEDS_SALE", 422)),
    ]
    folders.append(("03 Returns and clawback", returns))

    calc = []
    cases = [
        ("TC-CAL-002", "S00010", "100000.00", "49995.00", ["50.00", False, "0.00"],
         "49,995.00 shows 50.00% but does not qualify"),
        ("TC-CAL-003", "S00011", "100000.00", "50000.00", ["50.00", True, "500.00"], "Exactly 50% qualifies"),
        ("TC-CAL-005", "S00012", "100000.00", "100000.00", ["100.00", True, "1300.00"], "Exactly 100%"),
        ("TC-CAL-008", "S00013", "100000.00", "250000.00", ["250.00", True, "5800.00"], "250% is capped"),
        ("TC-CAL-010", "S00014", "10000.00", "5000.50", ["50.01", True, "50.01"], "Half-cent tie rounds up"),
        ("TC-CAL-012", "S00015", "100000.00", "150000.00", ["150.00", True, "3300.00"], "Band breakdown at 150%"),
    ]
    for tc, sid, quota, amount, expected, title in cases:
        calc.append(req(f"Setup: seller {sid}", "POST", "/sellers",
                        {"seller_id": sid, "name": f"Calc {sid}", "store_id": "T1000"}, status("Setup", 201)))
        calc.append(req(f"Setup: quota {sid}", "PUT", f"/periods/2026-10/quotas/{sid}", {"amount": quota},
                        status("Setup", 201)))
        calc.append(req(f"Setup: sale for {sid}", "POST", "/transactions",
                        sale(f"PM-{sid}", "2026-10-20", amount, [(sid, 100)]), status("Setup", 201)))
        tests = statement_is(tc, *expected)
        if tc == "TC-CAL-012":
            tests += """
pm.test("TC-CAL-012 band breakdown", function () {
    const b = {};
    pm.response.json().bands.forEach(function (x) { b[x.band] = [x.base, x.commission]; });
    pm.expect(b).to.eql({A: ["80000.00", "800.00"], B: ["20000.00", "500.00"],
                         C: ["50000.00", "2000.00"], D: ["0.00", "0.00"]});
});"""
        calc.append(req(f"{tc} {title}", "GET", f"/periods/2026-10/sellers/{sid}/statement", tests=tests))
    folders.append(("04 Calculation", calc))

    imports = [
        req("TC-IMP-001 Batch with a sale and a same-batch return", "POST", "/imports/transactions",
            {"transactions": [sale("PM-IMP-1", "2026-10-21", "300.00", [("S00001", 100)]),
                              ret("PM-IMP-2", "2026-10-22", "100.00", "PM-IMP-1")]},
            status("TC-IMP-001", 201) + """
pm.test("TC-IMP-001 counts", function () {
    pm.expect(pm.response.json()).to.eql({imported: 2, sales: 1, returns: 1, credits: 2});
});"""),
        req("TC-IMP-002 One invalid row rejects the whole batch", "POST", "/imports/transactions",
            {"transactions": [sale("PM-IMP-3", "2026-10-21", "100.00", [("S00001", 100)]),
                              sale("PM-IMP-4", "2026-10-21", "100.00", [("S99999", 100)])]},
            error("TC-IMP-002", "IMPORT_REJECTED", 422) + """
pm.test("TC-IMP-002 reports row 1 UNKNOWN_SELLER", function () {
    const d = pm.response.json().error.details;
    pm.expect(d.map(function (x) { return [x.row, x.code]; })).to.eql([[1, "UNKNOWN_SELLER"]]);
});"""),
        req("TC-IMP-002 Valid row of the rejected batch was not stored", "GET", "/transactions/PM-IMP-3",
            error("TC-IMP-002", "TRANSACTION_NOT_FOUND", 404)),
    ]
    folders.append(("05 Import", imports))

    close = [
        req("TC-CLS-003 Periods close in order", "POST", "/periods/2026-11/close",
            error("TC-CLS-003", "PREVIOUS_PERIOD_OPEN", 409)),
        req("TC-CLS-001 Close 2026-10", "POST", "/periods/2026-10/close",
            status("TC-CLS-001", 200) + """
pm.test("TC-CLS-001 close summary", function () {
    const j = pm.response.json();
    pm.expect(j.status).to.eql("CLOSED");
    pm.collectionVariables.set("octTotal", j.total_payout);
    pm.collectionVariables.set("octSellers", j.sellers);
});"""),
        req("TC-CLS-001 Total payout equals the stored rows", "GET", "/periods/2026-10/payouts",
            status("TC-CLS-001", 200) + """
pm.test("TC-CLS-001 rows and total agree with the close response", function () {
    const rows = pm.response.json();
    let cents = 0;
    rows.forEach(function (r) { cents += Math.round(parseFloat(r.payout) * 100); });
    pm.expect(rows.length).to.eql(Number(pm.collectionVariables.get("octSellers")));
    pm.expect((cents / 100).toFixed(2)).to.eql(pm.collectionVariables.get("octTotal"));
});"""),
        req("TC-CLS-002 Closing twice is rejected", "POST", "/periods/2026-10/close",
            error("TC-CLS-002", "PERIOD_ALREADY_CLOSED", 409)),
        req("TC-CLS-007 Statement after close uses stored values", "GET", "/periods/2026-10/sellers/S00011/statement",
            status("TC-CLS-007", 200) + """
pm.test("TC-CLS-007 source CLOSED and same payout", function () {
    const s = pm.response.json();
    pm.expect(s.source).to.eql("CLOSED");
    pm.expect(s.payout).to.eql("500.00");
});"""),
        req("TC-TXN-015 Sale dated in a closed period", "POST", "/transactions",
            sale("PM-LATE", "2026-10-31", "100.00", [("S00001", 100)]),
            error("TC-TXN-015", "PERIOD_CLOSED", 409)),
        req("TC-CLS-006 Return dated in a closed period", "POST", "/transactions",
            ret("PM-LATE-RET", "2026-10-31", "10.00", "PM-SALE-2"),
            error("TC-CLS-006", "PERIOD_CLOSED", 409)),
        req("TC-QTA-004 Quota change in a closed period", "PUT", "/periods/2026-10/quotas/S00001",
            {"amount": "5000.00"}, error("TC-QTA-004", "PERIOD_CLOSED", 409)),
    ]
    folders.append(("06 Close and lock", close))

    return {
        "info": {
            "name": "Commission Engine QA",
            "description": ("Contract and functional checks for the Commission Engine API (plan RET-Q4-2026). "
                            "Run in order against a fresh database. Request names carry the test case IDs "
                            "of docs/03-test-cases.csv."),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": [{"listen": "test", "script": {"type": "text/javascript",
                                                "exec": COLLECTION_TESTS.strip().splitlines()}}],
        "variable": [{"key": "octTotal", "value": ""}, {"key": "octSellers", "value": ""},
                     {"key": "buildVersion", "value": ""}],
        "item": [{"name": name, "item": items} for name, items in folders],
    }


def main():
    out = HERE / "commission-engine.postman_collection.json"
    out.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    env = {"name": "local", "values": [{"key": "baseUrl", "value": "http://localhost:8000", "enabled": True}]}
    (HERE / "local.postman_environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    n = sum(len(f["item"]) for f in build()["item"])
    print(f"wrote {out.name} with {n} requests")


if __name__ == "__main__":
    main()
