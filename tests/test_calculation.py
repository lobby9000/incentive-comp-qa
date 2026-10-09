"""Calculation through live statements: REQ-CAL-01 to 06, REQ-STM-01 to 04.

Rows TC-CAL-001 to 011 are the worked examples of requirements section 3.3.
"""

import pytest

from conftest import error_code

PERIOD = "2026-10"


def credit_seller(api, seller_id, quota, credited):
    """Create a seller with `quota` and net credited sales `credited` in 2026-10."""
    api.seller(seller_id)
    api.quota(PERIOD, seller_id, quota)
    if credited:
        remaining = float(credited)
        day = 1
        while remaining > 0.004:
            chunk = min(remaining, 1_000_000.00)
            api.sale(f"2026-10-{day:02d}", f"{chunk:.2f}", [(seller_id, 100)])
            remaining = round(remaining - chunk, 2)
            day += 1
    return api.statement(PERIOD, seller_id).json()


# Worked examples from requirements 3.3: quota, credited, attainment shown, qualifies, payout
EXAMPLES = {
    "TC-CAL-001": ("100000.00", "49999.99", "50.00", False, "0.00"),
    "TC-CAL-002": ("100000.00", "49995.00", "50.00", False, "0.00"),
    "TC-CAL-003": ("100000.00", "50000.00", "50.00", True, "500.00"),
    "TC-CAL-004": ("100000.00", "80000.00", "80.00", True, "800.00"),
    "TC-CAL-005": ("100000.00", "100000.00", "100.00", True, "1300.00"),
    "TC-CAL-006": ("100000.00", "150000.00", "150.00", True, "3300.00"),
    "TC-CAL-007": ("100000.00", "200000.00", "200.00", True, "5800.00"),
    "TC-CAL-008": ("100000.00", "250000.00", "250.00", True, "5800.00"),
    "TC-CAL-010": ("10000.00", "5000.50", "50.01", True, "50.01"),
    "TC-CAL-011": ("33333.33", "30000.00", "90.00", True, "350.00"),
}


def _example(api, tc):
    quota, credited, attainment, qualified, payout = EXAMPLES[tc]
    st = credit_seller(api, "S00001", quota, credited)
    assert (st["net_credited"], st["attainment_pct"], st["qualified"], st["payout"]) == \
        (credited, attainment, qualified, payout)


def test_TC_CAL_001_just_below_gate(api):
    _example(api, "TC-CAL-001")


def test_TC_CAL_002_rounded_display_does_not_open_the_gate(api):
    _example(api, "TC-CAL-002")


def test_TC_CAL_003_exactly_50_percent_qualifies(api):
    _example(api, "TC-CAL-003")


def test_TC_CAL_004_exactly_80_percent(api):
    _example(api, "TC-CAL-004")


def test_TC_CAL_005_exactly_100_percent(api):
    _example(api, "TC-CAL-005")


def test_TC_CAL_006_exactly_150_percent(api):
    _example(api, "TC-CAL-006")


def test_TC_CAL_007_exactly_200_percent(api):
    _example(api, "TC-CAL-007")


def test_TC_CAL_008_cap_above_200_percent(api):
    _example(api, "TC-CAL-008")


def test_TC_CAL_009_negative_net_credit(api):
    api.seller("S00001")
    api.quota("2026-10", "S00001", "100000.00")
    api.quota("2026-11", "S00001", "100000.00")
    sale = api.sale("2026-10-20", "1500.00", [("S00001", 100)]).json()["transaction_id"]
    api.ret("2026-11-03", "1500.00", sale)
    st = api.statement("2026-11", "S00001").json()
    assert (st["net_credited"], st["attainment_pct"], st["qualified"], st["payout"]) == \
        ("-1500.00", "-1.50", False, "0.00")


def test_TC_CAL_010_half_cent_tie_rounds_up(api):
    _example(api, "TC-CAL-010")


def test_TC_CAL_011_band_limits_between_cents(api):
    _example(api, "TC-CAL-011")


def test_TC_CAL_012_band_breakdown_at_150_percent(api):
    st = credit_seller(api, "S00001", "100000.00", "150000.00")
    bands = {b["band"]: (b["base"], b["commission"]) for b in st["bands"]}
    assert bands == {"A": ("80000.00", "800.00"), "B": ("20000.00", "500.00"),
                     "C": ("50000.00", "2000.00"), "D": ("0.00", "0.00")}
    assert st["source"] == "LIVE"


def test_TC_CAL_013_statement_without_quota(api):
    api.seller("S00001")
    r = api.statement(PERIOD, "S00001", expect=404)
    assert error_code(r) == "QUOTA_NOT_FOUND"


@pytest.mark.parametrize("quota,credited,shown", [
    ("30000.00", "10000.00", "33.33"),
    ("30000.00", "20000.00", "66.67"),
    ("100000.00", "12345.00", "12.35"),
])
def test_TC_CAL_014_attainment_display_rounds_half_up(api, quota, credited, shown):
    st = credit_seller(api, "S00001", quota, credited)
    assert st["attainment_pct"] == shown


def test_TC_CAL_015_band_display_tie_rounds_half_up(api):
    st = credit_seller(api, "S00001", "10000.00", "5000.50")
    band_a = next(b for b in st["bands"] if b["band"] == "A")
    assert band_a["commission"] == "50.01"


def test_TC_CAL_016_live_statement_reflects_new_sale(api):
    st = credit_seller(api, "S00001", "100000.00", "20000.00")
    assert st["net_credited"] == "20000.00"
    api.sale("2026-10-28", "10000.00", [("S00001", 100)])
    st = api.statement(PERIOD, "S00001").json()
    assert st["net_credited"] == "30000.00"
    assert st["source"] == "LIVE"
