"""Batch import: REQ-IMP-01, REQ-IMP-02."""

from conftest import error_code


def sale_row(tid, amount="100.00", seller="S00001", date="2026-10-10"):
    return {"transaction_id": tid, "type": "SALE", "txn_date": date, "store_id": "T1000",
            "amount": amount, "credits": [{"seller_id": seller, "split_pct": 100}]}


def return_row(tid, original, amount="100.00", date="2026-10-12"):
    return {"transaction_id": tid, "type": "RETURN", "txn_date": date, "store_id": "T1000",
            "amount": amount, "original_transaction_id": original}


def post_import(api, rows):
    return api.c.post("/imports/transactions", json={"transactions": rows})


def stored(api, tid) -> bool:
    return api.c.get(f"/transactions/{tid}").status_code == 200


def test_TC_IMP_001_batch_with_same_batch_return(api):
    api.seller("S00001")
    r = post_import(api, [sale_row("I-1", "300.00"), return_row("I-2", "I-1", "100.00")])
    assert r.status_code == 201, r.text
    assert r.json() == {"imported": 2, "sales": 1, "returns": 1, "credits": 2}
    assert api.c.get("/transactions/I-2").json()["credits"][0]["credit"] == "-100.00"


def test_TC_IMP_002_business_error_rejects_whole_batch(api):
    api.seller("S00001")
    r = post_import(api, [sale_row("I-1"), sale_row("I-2", seller="S99999"), sale_row("I-3")])
    assert r.status_code == 422
    assert error_code(r) == "IMPORT_REJECTED"
    details = r.json()["error"]["details"]
    assert [(d["row"], d["code"]) for d in details] == [(1, "UNKNOWN_SELLER")]
    assert not stored(api, "I-1") and not stored(api, "I-3")


def test_TC_IMP_003_schema_error_reports_row_and_stores_nothing(api):
    api.seller("S00001")
    rows = [sale_row("I-1"), sale_row("I-2"), sale_row("I-3", amount="0")]
    r = post_import(api, rows)
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"
    assert any("2" in d["loc"] for d in r.json()["error"]["details"])
    assert not stored(api, "I-1")


def test_TC_IMP_004_duplicate_id_inside_batch(api):
    api.seller("S00001")
    r = post_import(api, [sale_row("I-1"), sale_row("I-1")])
    assert r.status_code == 422
    assert error_code(r) == "IMPORT_REJECTED"
    assert [(d["row"], d["code"]) for d in r.json()["error"]["details"]] == [(1, "DUPLICATE_TRANSACTION")]
    assert not stored(api, "I-1")


def test_TC_IMP_005_batch_size_boundaries(api):
    api.seller("S00001")
    rows = [sale_row(f"B-{i}", "1.00") for i in range(5000)]
    r = post_import(api, rows)
    assert r.status_code == 201, r.text[:300]
    assert r.json()["imported"] == 5000
    rows = [sale_row(f"C-{i}", "1.00") for i in range(5001)]
    r = post_import(api, rows)
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_IMP_006_returns_in_batch_cannot_exceed_sale(api):
    api.seller("S00001")
    r = post_import(api, [sale_row("I-1", "100.00"), return_row("I-2", "I-1", "60.00"),
                          return_row("I-3", "I-1", "41.00")])
    assert r.status_code == 422
    assert error_code(r) == "IMPORT_REJECTED"
    assert [(d["row"], d["code"]) for d in r.json()["error"]["details"]] == [(2, "RETURN_EXCEEDS_SALE")]
