"""Period close and locking: REQ-CLS-01 to 05, REQ-STM-02."""

from decimal import Decimal

import pytest

from conftest import error_code


@pytest.fixture
def october(api):
    """Three sellers with quotas; two of them with sales."""
    for sid in ("S00001", "S00002", "S00003"):
        api.seller(sid)
        api.quota("2026-10", sid, "100000.00")
    api.sale("2026-10-10", "120000.00", [("S00001", 100)])
    api.sale("2026-10-11", "60000.00", [("S00002", 100)])
    return api


def test_TC_CLS_001_close_stores_one_row_per_quota(october):
    summary = october.close("2026-10").json()
    rows = october.payouts("2026-10").json()
    assert summary["status"] == "CLOSED"
    assert summary["sellers"] == 3 == len(rows)
    assert Decimal(summary["total_payout"]) == sum(Decimal(r["payout"]) for r in rows)
    # 120% -> 800 + 500 + 20,000 x 4% = 2,100.00 ; 60% -> 600.00 ; no sales -> 0.00
    assert {r["seller_id"]: r["payout"] for r in rows} == {"S00001": "2100.00", "S00002": "600.00",
                                                          "S00003": "0.00"}


def test_TC_CLS_002_close_twice_is_rejected(october):
    october.close("2026-10")
    r = october.close("2026-10", expect=409)
    assert error_code(r) == "PERIOD_ALREADY_CLOSED"
    assert len(october.payouts("2026-10").json()) == 3


def test_TC_CLS_003_periods_close_in_order(october):
    r = october.close("2026-11", expect=409)
    assert error_code(r) == "PREVIOUS_PERIOD_OPEN"


def test_TC_CLS_004_credited_seller_without_quota_blocks_close(october):
    october.seller("S00009")
    october.sale("2026-10-12", "500.00", [("S00009", 100)])
    r = october.close("2026-10", expect=409)
    assert error_code(r) == "QUOTA_MISSING"
    assert "S00009" in r.json()["error"]["details"]
    periods = {p["period_id"]: p["status"] for p in october.c.get("/periods").json()}
    assert periods["2026-10"] == "OPEN"
    assert error_code(october.payouts("2026-10", expect=409)) == "PERIOD_NOT_CLOSED"


def test_TC_CLS_005_quota_without_credits_gets_zero_row(october):
    october.close("2026-10")
    row = next(r for r in october.payouts("2026-10").json() if r["seller_id"] == "S00003")
    assert (row["net_credited"], row["payout"]) == ("0.00", "0.00")


def test_TC_CLS_006_closed_period_rejects_sales_and_returns(october):
    sale = october.sale("2026-10-20", "100.00", [("S00001", 100)]).json()["transaction_id"]
    october.close("2026-10")
    r = october.sale("2026-10-31", "100.00", [("S00001", 100)], expect=409)
    assert error_code(r) == "PERIOD_CLOSED"
    r = october.ret("2026-10-31", "10.00", sale, expect=409)
    assert error_code(r) == "PERIOD_CLOSED"


def test_TC_CLS_007_statement_after_close_uses_stored_values(october):
    october.close("2026-10")
    st = october.statement("2026-10", "S00001").json()
    row = next(r for r in october.payouts("2026-10").json() if r["seller_id"] == "S00001")
    assert st["source"] == "CLOSED"
    assert st["payout"] == row["payout"]
    assert st["net_credited"] == row["net_credited"]


def test_TC_CLS_008_payouts_of_open_period(api):
    r = api.payouts("2026-11", expect=409)
    assert error_code(r) == "PERIOD_NOT_CLOSED"


def test_TC_CLS_009_unknown_period(api):
    r = api.close("2027-01", expect=404)
    assert error_code(r) == "PERIOD_NOT_FOUND"
