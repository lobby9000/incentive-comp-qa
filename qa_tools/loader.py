"""
Load the generated dataset through the public API, the way a client would.

Works with any client that has .get/.post/.put/.patch returning responses with
.status_code and .json() (FastAPI's TestClient or httpx.Client).

Sequence (mirrors a real quarter):
  1. create sellers and quotas
  2. import every transaction dated before the leave date
  3. set the leavers INACTIVE
  4. import the rest
  5. close 2026-10, 2026-11 and 2026-12 in order

mode="import" uses POST /imports/transactions in batches (the normal path).
mode="single" posts one transaction at a time; it exists as a workaround for
when the import endpoint itself is broken, so the parallel run is not blocked.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

GEN = Path(__file__).resolve().parent.parent / "data" / "generated"
PERIODS = ["2026-10", "2026-11", "2026-12"]


class LoadError(RuntimeError):
    def __init__(self, step: str, response):
        self.step = step
        self.status = response.status_code
        try:
            self.body = response.json()
        except Exception:  # noqa: BLE001 - keep whatever the server sent
            self.body = response.text[:500]
        super().__init__(f"{step}: HTTP {self.status} {str(self.body)[:300]}")


def read_dataset(gen: Path = GEN) -> dict:
    sellers = list(csv.DictReader(open(gen / "sellers.csv", encoding="utf-8")))
    quotas = list(csv.DictReader(open(gen / "quotas.csv", encoding="utf-8")))
    txns = list(csv.DictReader(open(gen / "transactions.csv", encoding="utf-8")))
    manifest = json.loads((gen / "MANIFEST.json").read_text(encoding="utf-8"))
    return {"sellers": sellers, "quotas": quotas, "transactions": txns,
            "leave_date": date.fromisoformat(manifest["leave_date"])}


def to_payload(row: dict) -> dict:
    body = {"transaction_id": row["transaction_id"], "type": row["type"], "txn_date": row["txn_date"],
            "store_id": row["store_id"], "amount": row["amount"]}
    if row["type"] == "SALE":
        body["credits"] = [{"seller_id": row["seller_1"], "split_pct": int(row["split_1"])}]
        if row["seller_2"]:
            body["credits"].append({"seller_id": row["seller_2"], "split_pct": int(row["split_2"])})
    else:
        body["original_transaction_id"] = row["original_transaction_id"]
    return body


def _expect(response, ok: tuple, step: str):
    if response.status_code not in ok:
        raise LoadError(step, response)
    return response


def load_transactions(client, rows: list[dict], mode: str, batch: int) -> None:
    if mode == "import":
        for i in range(0, len(rows), batch):
            chunk = [to_payload(r) for r in rows[i:i + batch]]
            _expect(client.post("/imports/transactions", json={"transactions": chunk}), (201,),
                    f"import rows {i}..{i + len(chunk) - 1}")
    elif mode == "single":
        for r in rows:
            _expect(client.post("/transactions", json=to_payload(r)), (201,), f"transaction {r['transaction_id']}")
    else:
        raise ValueError("mode must be 'import' or 'single'")


def load(client, gen: Path = GEN, mode: str = "import", batch: int = 2000, close: bool = True) -> dict:
    data = read_dataset(gen)
    for s in data["sellers"]:
        _expect(client.post("/sellers", json={"seller_id": s["seller_id"], "name": s["name"],
                                             "store_id": s["store_id"]}), (201,), f"seller {s['seller_id']}")
    for q in data["quotas"]:
        _expect(client.put(f"/periods/{q['period_id']}/quotas/{q['seller_id']}", json={"amount": q["amount"]}),
                (200, 201), f"quota {q['period_id']} {q['seller_id']}")

    leave = data["leave_date"]
    before = [t for t in data["transactions"] if date.fromisoformat(t["txn_date"]) < leave]
    after = [t for t in data["transactions"] if date.fromisoformat(t["txn_date"]) >= leave]
    load_transactions(client, before, mode, batch)
    for s in data["sellers"]:
        if s["leaves_on"]:
            _expect(client.patch(f"/sellers/{s['seller_id']}", json={"status": "INACTIVE"}), (200,),
                    f"deactivate {s['seller_id']}")
    load_transactions(client, after, mode, batch)

    closes = {}
    if close:
        for p in PERIODS:
            closes[p] = _expect(client.post(f"/periods/{p}/close"), (200,), f"close {p}").json()
    return {"sellers": len(data["sellers"]), "quotas": len(data["quotas"]),
            "transactions": len(data["transactions"]), "closes": closes}
