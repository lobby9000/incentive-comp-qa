"""Sales and crediting: REQ-CRD-01 to 05, REQ-FLD-01 to 05, REQ-CLS-04."""

import pytest

from conftest import error_code


@pytest.fixture
def two_sellers(api):
    api.seller("S00001", store="T1000")
    api.seller("S00002", store="T1000")
    return api


def credits_of(response) -> dict:
    return {c["seller_id"]: c["credit"] for c in response.json()["credits"]}


def test_TC_TXN_001_single_seller_sale(api):
    api.seller("S00001")
    r = api.sale("2026-10-15", "1500.50", [("S00001", 100)])
    body = r.json()
    assert body["period_id"] == "2026-10"
    assert body["credits"] == [{"seller_id": "S00001", "split_pct": 100, "credit": "1500.50"}]


def test_TC_TXN_002_split_70_30(two_sellers):
    r = two_sellers.sale("2026-10-15", "10000.00", [("S00001", 70), ("S00002", 30)])
    assert credits_of(r) == {"S00001": "7000.00", "S00002": "3000.00"}


def test_TC_TXN_003_odd_cent_split_remainder_to_first_seller(two_sellers):
    r = two_sellers.sale("2026-10-15", "100.01", [("S00001", 50), ("S00002", 50)])
    assert credits_of(r) == {"S00001": "50.01", "S00002": "50.00"}


def test_TC_TXN_004_one_cent_split_stores_zero_line(two_sellers):
    r = two_sellers.sale("2026-10-15", "0.01", [("S00001", 99), ("S00002", 1)])
    assert r.json()["credits"] == [
        {"seller_id": "S00001", "split_pct": 99, "credit": "0.01"},
        {"seller_id": "S00002", "split_pct": 1, "credit": "0.00"},
    ]


@pytest.mark.parametrize("splits", [(60, 39), (60, 41), (100, 1)])
def test_TC_TXN_005_splits_must_add_up_to_100(two_sellers, splits):
    r = two_sellers.sale("2026-10-15", "100.00", [("S00001", splits[0]), ("S00002", splits[1])], expect=422)
    assert error_code(r) == "INVALID_SPLIT"


def test_TC_TXN_006_zero_or_three_credit_lines(two_sellers):
    two_sellers.seller("S00003")
    r = two_sellers.sale("2026-10-15", "100.00", [], expect=422)
    assert error_code(r) == "VALIDATION_ERROR"
    r = two_sellers.sale("2026-10-15", "100.00", [("S00001", 40), ("S00002", 30), ("S00003", 30)], expect=422)
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_TXN_007_same_seller_twice(api):
    api.seller("S00001")
    r = api.sale("2026-10-15", "100.00", [("S00001", 50), ("S00001", 50)], expect=422)
    assert error_code(r) == "DUPLICATE_SELLER"


def test_TC_TXN_008_unknown_seller(api):
    r = api.sale("2026-10-15", "100.00", [("S99999", 100)], expect=422)
    assert error_code(r) == "UNKNOWN_SELLER"


def test_TC_TXN_009_inactive_seller_cannot_receive_credit(api):
    api.seller("S00001")
    api.deactivate("S00001")
    r = api.sale("2026-10-15", "100.00", [("S00001", 100)], expect=422)
    assert error_code(r) == "SELLER_INACTIVE"


def test_TC_TXN_010_primary_seller_store_rule(api):
    api.seller("S00001", store="T1000")
    api.seller("S00002", store="T1001")
    r = api.sale("2026-10-15", "100.00", [("S00002", 100)], store="T1000", expect=422)
    assert error_code(r) == "PRIMARY_SELLER_STORE_MISMATCH"
    api.sale("2026-10-15", "100.00", [("S00001", 60), ("S00002", 40)], store="T1000", expect=201)


@pytest.mark.parametrize("amount,valid", [
    ("0.00", False), ("0.01", True), ("1000000.00", True), ("1000000.01", False),
    (-1, False), ("10.005", False), ("1500.50", True), (1e3, True),
])
def test_TC_TXN_011_amount_boundaries(api, amount, valid):
    api.seller("S00001")
    r = api.sale("2026-10-15", amount, [("S00001", 100)], expect=None)
    if valid:
        assert r.status_code == 201, r.text
    else:
        assert r.status_code == 422, r.text
        assert error_code(r) == "VALIDATION_ERROR"


def test_TC_TXN_012_duplicate_transaction_is_not_counted_twice(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", "100000.00")
    api.sale("2026-10-15", "5000.00", [("S00001", 100)], tid="DUP-1")
    r = api.sale("2026-10-15", "5000.00", [("S00001", 100)], tid="DUP-1", expect=409)
    assert error_code(r) == "DUPLICATE_TRANSACTION"
    assert api.statement("2026-10", "S00001").json()["net_credited"] == "5000.00"


@pytest.mark.parametrize("tid,valid", [("A" * 32, True), ("A" * 33, False), ("HAS SPACE", False), ("", False)])
def test_TC_TXN_013_transaction_id_format(api, tid, valid):
    api.seller("S00001")
    r = api.sale("2026-10-15", "10.00", [("S00001", 100)], tid=tid, expect=None)
    if valid:
        assert r.status_code == 201, r.text
    else:
        assert r.status_code == 422, r.text
        assert error_code(r) == "VALIDATION_ERROR"


@pytest.mark.parametrize("date,status,code", [
    ("2026-09-30", 422, "OUT_OF_PLAN"), ("2026-10-01", 201, None),
    ("2026-12-31", 201, None), ("2027-01-01", 422, "OUT_OF_PLAN"),
])
def test_TC_TXN_014_plan_date_boundaries(api, date, status, code):
    api.seller("S00001")
    r = api.sale(date, "10.00", [("S00001", 100)], expect=status)
    if code:
        assert error_code(r) == code


def test_TC_TXN_015_sale_in_closed_period(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", "1000.00")
    api.close("2026-10")
    r = api.sale("2026-10-31", "10.00", [("S00001", 100)], expect=409)
    assert error_code(r) == "PERIOD_CLOSED"


def test_TC_TXN_016_sale_with_original_transaction(api):
    api.seller("S00001")
    first = api.sale("2026-10-15", "10.00", [("S00001", 100)]).json()["transaction_id"]
    body = {"transaction_id": "SALE-X", "type": "SALE", "txn_date": "2026-10-16", "store_id": "T1000",
            "amount": "10.00", "credits": [{"seller_id": "S00001", "split_pct": 100}],
            "original_transaction_id": first}
    r = api.c.post("/transactions", json=body)
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_TXN_017_unknown_store(api):
    api.seller("S00001")
    r = api.sale("2026-10-15", "10.00", [("S00001", 100)], store="T9999", expect=422)
    assert error_code(r) == "UNKNOWN_STORE"


def test_TC_TXN_018_read_transaction_and_unknown(two_sellers):
    tid = two_sellers.sale("2026-10-15", "10.00", [("S00001", 50), ("S00002", 50)]).json()["transaction_id"]
    r = two_sellers.c.get(f"/transactions/{tid}")
    assert r.status_code == 200
    assert [c["seller_id"] for c in r.json()["credits"]] == ["S00001", "S00002"]
    r = two_sellers.c.get("/transactions/NOPE-404")
    assert r.status_code == 404
    assert error_code(r) == "TRANSACTION_NOT_FOUND"
