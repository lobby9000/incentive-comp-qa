"""
Shared fixtures. Every test gets a brand-new database:

* SQLite file in a temp folder by default (fast, isolated);
* PostgreSQL when TEST_DATABASE_URL is set, e.g.
  postgresql+psycopg://qa@localhost:5432/comp_test (tables are dropped first).

The `api` fixture wraps the HTTP calls so each test reads like its test case.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from app.main import create_app

PG_URL = os.environ.get("TEST_DATABASE_URL")


def fresh_database_url(tmp_path) -> str:
    if PG_URL:
        engine = create_engine(PG_URL)
        SQLModel.metadata.drop_all(engine)
        engine.dispose()
        return PG_URL
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def client(tmp_path):
    app = create_app(fresh_database_url(tmp_path))
    with TestClient(app) as c:
        yield c
    app.state.engine.dispose()


class Api:
    """Thin helpers over the HTTP contract. Each helper asserts the expected status."""

    def __init__(self, client: TestClient):
        self.c = client
        self._n = 0

    def _check(self, r, expect):
        if expect is not None:
            assert r.status_code == expect, f"expected {expect}, got {r.status_code}: {r.text}"
        return r

    def next_id(self, prefix="T") -> str:
        self._n += 1
        return f"{prefix}-{self._n:05d}"

    # sellers and quotas
    def seller(self, seller_id, store="T1000", name="Test Seller", expect=201):
        return self._check(self.c.post("/sellers", json={"seller_id": seller_id, "name": name,
                                                         "store_id": store}), expect)

    def deactivate(self, seller_id, expect=200):
        return self._check(self.c.patch(f"/sellers/{seller_id}", json={"status": "INACTIVE"}), expect)

    def quota(self, period, seller_id, amount, expect=None):
        return self._check(self.c.put(f"/periods/{period}/quotas/{seller_id}", json={"amount": amount}), expect)

    # transactions
    def sale(self, date, amount, credits, store="T1000", tid=None, expect=201):
        body = {"transaction_id": tid if tid is not None else self.next_id("SALE"), "type": "SALE", "txn_date": date,
                "store_id": store, "amount": amount,
                "credits": [{"seller_id": s, "split_pct": p} for s, p in credits]}
        return self._check(self.c.post("/transactions", json=body), expect)

    def ret(self, date, amount, original, store="T1000", tid=None, expect=201, **extra):
        body = {"transaction_id": tid if tid is not None else self.next_id("RET"), "type": "RETURN", "txn_date": date,
                "store_id": store, "amount": amount, "original_transaction_id": original, **extra}
        return self._check(self.c.post("/transactions", json=body), expect)

    # reporting and lifecycle
    def statement(self, period, seller_id, expect=200):
        return self._check(self.c.get(f"/periods/{period}/sellers/{seller_id}/statement"), expect)

    def close(self, period, expect=200):
        return self._check(self.c.post(f"/periods/{period}/close"), expect)

    def payouts(self, period, expect=200):
        return self._check(self.c.get(f"/periods/{period}/payouts"), expect)


@pytest.fixture
def api(client) -> Api:
    return Api(client)


def error_code(response) -> str:
    return response.json()["error"]["code"]
