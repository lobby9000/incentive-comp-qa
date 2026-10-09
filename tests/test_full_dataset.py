"""
Full-volume run: load the 25,259-transaction dataset through the API, close the
quarter, then
  * reconcile every payout against the Excel oracle (TC-REC-001 to 003), and
  * run the SQL invariants on the stored rows (TC-DB-001 to 009, PostgreSQL only).

Marked `fullload`; run with:  pytest -m fullload
Set TEST_DATABASE_URL to a PostgreSQL URL to include the database checks.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel

from app.main import create_app
from qa_tools import loader, reconcile, sql_checks

pytestmark = pytest.mark.fullload
PG_URL = os.environ.get("TEST_DATABASE_URL")
MODE = os.environ.get("LOAD_MODE", "import")


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    if PG_URL:
        engine = create_engine(PG_URL)
        SQLModel.metadata.drop_all(engine)
        engine.dispose()
        url = PG_URL
    else:
        url = f"sqlite:///{tmp_path_factory.mktemp('full') / 'full.db'}"
    app = create_app(url)
    with TestClient(app) as client:
        result = loader.load(client, mode=MODE)
        payouts = {}
        for p in loader.PERIODS:
            for row in client.get(f"/periods/{p}/payouts").json():
                payouts[(p, row["seller_id"])] = row
        yield {"url": url, "load": result, "payouts": payouts}
    app.state.engine.dispose()


def test_TC_REC_001_every_payout_matches_oracle(loaded):
    mismatches = reconcile.compare_payouts(loaded["payouts"], reconcile.read_oracle())
    assert len(loaded["payouts"]) == 750
    assert mismatches == [], f"{len(mismatches)} mismatching fields, first: {mismatches[:5]}"


def test_TC_REC_002_period_totals_match_oracle(loaded):
    assert reconcile.compare_totals(loaded["load"]["closes"]) == []


def test_TC_REC_003_api_payouts_match_stored_rows(loaded):
    engine = create_engine(loaded["url"])
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT period_id, seller_id, payout_cents, credited_cents FROM payout")).all()
    engine.dispose()
    stored = {(r[0], r[1]): (r[2], r[3]) for r in rows}
    api = {k: (round(float(v["payout"]) * 100), round(float(v["net_credited"]) * 100))
           for k, v in loaded["payouts"].items()}
    assert stored == api


def _sql(loaded, name):
    if not loaded["url"].startswith("postgresql"):
        pytest.skip("SQL invariants are written for PostgreSQL; set TEST_DATABASE_URL")
    engine = create_engine(loaded["url"])
    with engine.connect() as conn:
        rows = conn.execute(text((sql_checks.SQL_DIR / name).read_text())).mappings().all()
    engine.dispose()
    assert [dict(r) for r in rows] == []


def test_TC_DB_001_sale_credits_sum(loaded):
    _sql(loaded, "01_sale_credits_sum.sql")


def test_TC_DB_002_return_credits(loaded):
    _sql(loaded, "02_return_credits.sql")


def test_TC_DB_003_split_floor_rule(loaded):
    _sql(loaded, "03_split_floor_rule.sql")


def test_TC_DB_004_returns_not_exceed_sale(loaded):
    _sql(loaded, "04_returns_not_exceed_sale.sql")


def test_TC_DB_005_credit_period(loaded):
    _sql(loaded, "05_credit_period.sql")


def test_TC_DB_006_payout_per_quota(loaded):
    _sql(loaded, "06_payout_per_quota.sql")


def test_TC_DB_007_payout_credited(loaded):
    _sql(loaded, "07_payout_credited.sql")


def test_TC_DB_008_no_writes_after_close(loaded):
    _sql(loaded, "08_no_writes_after_close.sql")


def test_TC_DB_009_primary_store(loaded):
    _sql(loaded, "09_primary_store.sql")
