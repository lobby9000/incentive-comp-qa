"""Returns and clawback: REQ-RET-01 to 05."""

import pytest

from conftest import error_code


@pytest.fixture
def split_sale(api):
    """SALE of 10,000.00 split 70/30 on 2026-10-05."""
    api.seller("S00001", store="T1000")
    api.seller("S00002", store="T1000")
    r = api.sale("2026-10-05", "10000.00", [("S00001", 70), ("S00002", 30)], tid="SALE-BASE")
    return r.json()["transaction_id"]


def credits_of(response) -> dict:
    return {c["seller_id"]: c["credit"] for c in response.json()["credits"]}


def test_TC_RET_001_full_return_mirrors_split(api, split_sale):
    r = api.ret("2026-10-20", "10000.00", split_sale)
    assert credits_of(r) == {"S00001": "-7000.00", "S00002": "-3000.00"}


def test_TC_RET_002_day_30_is_clawed_back(api, split_sale):
    r = api.ret("2026-11-04", "1000.00", split_sale)
    assert credits_of(r) == {"S00001": "-700.00", "S00002": "-300.00"}


def test_TC_RET_003_day_31_has_no_clawback(api, split_sale):
    r = api.ret("2026-11-05", "1000.00", split_sale)
    assert r.json()["credits"] == []


def test_TC_RET_004_odd_cent_partial_return(api, split_sale):
    r = api.ret("2026-10-20", "100.01", split_sale)
    assert credits_of(r) == {"S00001": "-70.01", "S00002": "-30.00"}


def test_TC_RET_005_cumulative_returns_up_to_sale_amount(api):
    api.seller("S00001")
    sale = api.sale("2026-10-10", "1000.00", [("S00001", 100)]).json()["transaction_id"]
    api.ret("2026-10-11", "600.00", sale)
    api.ret("2026-10-12", "400.00", sale)
    r = api.ret("2026-10-13", "0.01", sale, expect=422)
    assert error_code(r) == "RETURN_EXCEEDS_SALE"


def test_TC_RET_006_return_before_sale(api):
    api.seller("S00001")
    sale = api.sale("2026-10-10", "100.00", [("S00001", 100)]).json()["transaction_id"]
    r = api.ret("2026-10-09", "10.00", sale, expect=422)
    assert error_code(r) == "RETURN_BEFORE_SALE"


def test_TC_RET_007_unknown_original(api):
    r = api.ret("2026-10-09", "10.00", "NOPE-1", expect=422)
    assert error_code(r) == "UNKNOWN_ORIGINAL"


def test_TC_RET_008_return_of_a_return(api, split_sale):
    first = api.ret("2026-10-20", "10.00", split_sale).json()["transaction_id"]
    r = api.ret("2026-10-21", "1.00", first, expect=422)
    assert error_code(r) == "INVALID_ORIGINAL"


def test_TC_RET_009_return_with_its_own_credits(api, split_sale):
    r = api.ret("2026-10-20", "10.00", split_sale, expect=422,
                credits=[{"seller_id": "S00001", "split_pct": 100}])
    assert error_code(r) == "CREDITS_NOT_ALLOWED"


def test_TC_RET_010_return_posts_to_return_period(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", "100000.00")
    api.quota("2026-11", "S00001", "100000.00")
    sale = api.sale("2026-10-20", "10000.00", [("S00001", 100)]).json()["transaction_id"]
    r = api.ret("2026-11-02", "2000.00", sale)
    assert r.json()["period_id"] == "2026-11"
    assert api.statement("2026-10", "S00001").json()["net_credited"] == "10000.00"
    assert api.statement("2026-11", "S00001").json()["net_credited"] == "-2000.00"


def test_TC_RET_011_clawback_applies_to_inactive_seller(api, split_sale):
    api.deactivate("S00002")
    r = api.ret("2026-10-25", "1000.00", split_sale)
    assert credits_of(r) == {"S00001": "-700.00", "S00002": "-300.00"}


def test_TC_RET_012_same_day_return_is_clawed_back(api):
    api.seller("S00001")
    sale = api.sale("2026-10-10", "100.00", [("S00001", 100)]).json()["transaction_id"]
    r = api.ret("2026-10-10", "100.00", sale)
    assert credits_of(r) == {"S00001": "-100.00"}
