"""Sellers and quotas: REQ-FLD-01, REQ-FLD-03, REQ-CRD-03, REQ-CLS-04."""

import pytest

from conftest import error_code


def test_TC_SEL_001_create_seller(api):
    r = api.seller("S00001", store="T1000", name="Ana García")
    assert r.json() == {"seller_id": "S00001", "name": "Ana García", "store_id": "T1000", "status": "ACTIVE"}


def test_TC_SEL_002_duplicate_seller_is_rejected(api):
    api.seller("S00001")
    r = api.seller("S00001", expect=409)
    assert error_code(r) == "DUPLICATE_SELLER"


def test_TC_SEL_003_unknown_store_is_rejected(api):
    r = api.seller("S00001", store="T9999", expect=422)
    assert error_code(r) == "UNKNOWN_STORE"


@pytest.mark.parametrize("seller_id", ["S1234", "S123456", "s12345", "X12345", "S1234A"])
def test_TC_SEL_004_seller_id_format_invalid(api, seller_id):
    r = api.seller(seller_id, expect=422)
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_SEL_004_seller_id_lowest_valid(api):
    api.seller("S00000")


def test_TC_SEL_005_name_boundaries(api):
    api.seller("S00001", name="N" * 80)
    for i, name in enumerate(["N" * 81, "   ", ""], start=2):
        r = api.seller(f"S0000{i}", name=name, expect=422)
        assert error_code(r) == "VALIDATION_ERROR"


def test_TC_SEL_006_unknown_seller(client):
    r = client.get("/sellers/S77777")
    assert r.status_code == 404
    assert error_code(r) == "SELLER_NOT_FOUND"


def test_TC_SEL_007_deactivate_and_invalid_status(api):
    api.seller("S00001")
    r = api.deactivate("S00001")
    assert r.json()["status"] == "INACTIVE"
    r = api.c.patch("/sellers/S00001", json={"status": "FIRED"})
    assert r.status_code == 422
    assert error_code(r) == "VALIDATION_ERROR"


def test_TC_QTA_001_create_then_replace(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", 1000, expect=201)
    r = api.quota("2026-10", "S00001", 2000, expect=200)
    assert r.json()["amount"] == "2000.00"


@pytest.mark.parametrize("amount,valid", [
    (0, False), ("0.00", False), ("0.01", True), ("10000000.00", True),
    ("10000000.01", False), (-5, False), ("100.005", False),
])
def test_TC_QTA_002_quota_amount_boundaries(api, amount, valid):
    api.seller("S00001")
    r = api.quota("2026-10", "S00001", amount)
    if valid:
        assert r.status_code in (200, 201), r.text
    else:
        assert r.status_code == 422, r.text
        assert error_code(r) == "VALIDATION_ERROR"


def test_TC_QTA_003_unknown_period_or_seller(api):
    api.seller("S00001")
    r = api.quota("2026-09", "S00001", 1000, expect=404)
    assert error_code(r) == "PERIOD_NOT_FOUND"
    r = api.quota("2026-10", "S88888", 1000, expect=404)
    assert error_code(r) == "SELLER_NOT_FOUND"


def test_TC_QTA_004_quota_change_in_closed_period(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", 1000, expect=201)
    api.close("2026-10")
    r = api.quota("2026-10", "S00001", 5000, expect=409)
    assert error_code(r) == "PERIOD_CLOSED"
