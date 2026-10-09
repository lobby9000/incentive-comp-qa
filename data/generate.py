"""
Synthetic dataset for plan RET-Q4-2026.

Deterministic (fixed seed). Builds sellers on top of the 61-store dimension,
monthly quotas, sales with split credit, and returns, plus a small set of
hand-crafted "boundary" sellers whose numbers sit exactly on the edges named
in the requirements (gate, band limits, cap, rounding ties, clawback window).
A random dataset alone would almost never land on those edges.

Output: data/generated/{sellers,quotas,transactions}.csv and MANIFEST.json
Usage:  python data/generate.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261008
HERE = Path(__file__).resolve().parent
OUT = HERE / "generated"

PERIODS = {
    "2026-10": (date(2026, 10, 1), date(2026, 10, 31)),
    "2026-11": (date(2026, 11, 1), date(2026, 11, 30)),
    "2026-12": (date(2026, 12, 1), date(2026, 12, 31)),
}
SEASON = {"2026-10": 1.00, "2026-11": 1.25, "2026-12": 1.50}
SELLERS_PER_FORMAT = {"Departamental": 5, "Boutique": 3, "Express": 2}
BASE_QUOTA = {"Departamental": 260_000, "Boutique": 180_000, "Express": 110_000}
LEAVE_DATE = date(2026, 11, 15)  # three sellers leave the company on this date
SPLITS = [(50, 50), (60, 40), (70, 30), (80, 20), (90, 10)]

FIRST = ["Ana", "Luis", "María", "José", "Fernanda", "Carlos", "Daniela", "Jorge", "Sofía", "Miguel",
         "Valeria", "Ricardo", "Paola", "Andrés", "Camila", "Diego", "Lucía", "Héctor", "Regina", "Iván",
         "Ximena", "Arturo", "Mariana", "Emilio", "Renata", "Óscar", "Karla", "Raúl", "Natalia", "Saúl"]
LAST = ["García", "Hernández", "López", "Martínez", "González", "Pérez", "Rodríguez", "Sánchez",
        "Ramírez", "Cruz", "Flores", "Gómez", "Morales", "Vázquez", "Reyes", "Jiménez", "Torres",
        "Díaz", "Gutiérrez", "Ruiz", "Mendoza", "Aguilar", "Ortiz", "Castillo", "Romero", "Chávez"]


def money(x: float) -> str:
    return f"{x:.2f}"


def period_of(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def load_stores() -> list[dict]:
    with open(HERE / "stores.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def performance(rng: random.Random) -> float:
    """Seller performance relative to quota; spread so that every band is populated."""
    bucket = rng.random()
    if bucket < 0.08:
        return rng.uniform(0.25, 0.49)
    if bucket < 0.25:
        return rng.uniform(0.50, 0.80)
    if bucket < 0.50:
        return rng.uniform(0.80, 1.00)
    if bucket < 0.85:
        return rng.uniform(1.00, 1.50)
    if bucket < 0.95:
        return rng.uniform(1.50, 2.00)
    return rng.uniform(2.00, 2.60)


def ticket(rng: random.Random) -> float:
    amount = rng.lognormvariate(8.75, 0.80)  # median about 6,300 MXN
    if rng.random() < 0.04:
        amount = rng.uniform(15_000, 60_000)  # big-ticket items
    amount = min(max(amount, 149.0), 85_000.0)
    return round(amount, 2)


def build():
    rng = random.Random(SEED)
    stores = load_stores()
    m2 = [int(s["sales_floor_m2"]) for s in stores]
    m2_min, m2_max = min(m2), max(m2)

    # ------------------------------------------------------------ sellers
    sellers = []
    n = 0
    for s in stores:
        for _ in range(SELLERS_PER_FORMAT[s["format"]]):
            sellers.append({
                "seller_id": f"S{10000 + n:05d}",
                "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                "store_id": s["store_id"],
                "format": s["format"],
                "zone": s["zone"],
                "size": (int(s["sales_floor_m2"]) - m2_min) / (m2_max - m2_min),
                "leaves_on": "",
            })
            n += 1
    for leaver in rng.sample(sellers, 3):
        leaver["leaves_on"] = LEAVE_DATE.isoformat()
    by_store: dict[str, list[dict]] = {}
    by_zone: dict[str, list[dict]] = {}
    for s in sellers:
        by_store.setdefault(s["store_id"], []).append(s)
        by_zone.setdefault(s["zone"], []).append(s)

    def active_on(seller: dict, d: date) -> bool:
        return not seller["leaves_on"] or d < LEAVE_DATE

    # ------------------------------------------------------------ quotas
    quotas = []
    for s in sellers:
        for pid in PERIODS:
            if s["leaves_on"] and pid == "2026-12":
                continue
            q = BASE_QUOTA[s["format"]] * SEASON[pid] * (0.85 + 0.30 * s["size"]) * rng.uniform(0.85, 1.15)
            quotas.append({"period_id": pid, "seller_id": s["seller_id"], "amount": money(round(q, -1))})

    # ------------------------------------------------------------ sales
    sales = []
    quota_of = {(q["period_id"], q["seller_id"]): float(q["amount"]) for q in quotas}
    for s in sellers:
        base_perf = performance(rng)
        for pid, (start, end) in PERIODS.items():
            if (pid, s["seller_id"]) not in quota_of:
                continue
            last_day = end
            if s["leaves_on"] and pid == "2026-11":
                last_day = LEAVE_DATE - timedelta(days=1)
            target = quota_of[(pid, s["seller_id"])] * base_perf * rng.uniform(0.85, 1.15)
            total = 0.0
            while total < target:
                d = start + timedelta(days=rng.randint(0, (last_day - start).days))
                amount = ticket(rng)
                total += amount
                credit = [(s["seller_id"], 100)]
                if rng.random() < 0.15:
                    if rng.random() < 0.75:
                        pool = [x for x in by_store[s["store_id"]] if x is not s]
                    else:
                        pool = [x for x in by_zone[s["zone"]] if x["store_id"] != s["store_id"]]
                    pool = [x for x in pool if active_on(x, d)]
                    if pool:
                        p1, p2 = rng.choice(SPLITS)
                        credit = [(s["seller_id"], p1), (rng.choice(pool)["seller_id"], p2)]
                sales.append({"type": "SALE", "txn_date": d, "store_id": s["store_id"],
                              "amount": amount, "credits": credit, "original": None})

    # ------------------------------------------------------------ returns
    leaver_ids = {s["seller_id"] for s in sellers if s["leaves_on"]}
    returns = []
    for sale in sales:
        if rng.random() >= 0.07:
            continue
        remaining = sale["amount"]
        n_returns = 2 if rng.random() < 0.10 else 1
        last = sale["txn_date"]
        for _ in range(n_returns):
            offset = rng.randint(0, 30) if rng.random() < 0.80 else rng.randint(31, 45)
            d = max(last, sale["txn_date"] + timedelta(days=offset))
            if d > date(2026, 12, 31):
                break
            in_window = (d - sale["txn_date"]).days <= 30
            sellers_of_sale = {c[0] for c in sale["credits"]}
            # a December clawback on a seller with no December quota would block the close
            if in_window and period_of(d) == "2026-12" and sellers_of_sale & leaver_ids:
                break
            if n_returns == 1 and rng.random() < 0.70:
                amount = remaining
            else:
                amount = round(remaining * rng.uniform(0.10, 0.90), 2)
            if amount <= 0 or amount > remaining:
                break
            store = sale["store_id"] if rng.random() < 0.85 else rng.choice(stores)["store_id"]
            returns.append({"type": "RETURN", "txn_date": d, "store_id": store,
                            "amount": amount, "credits": [], "original": sale})
            remaining = round(remaining - amount, 2)
            last = d
            if remaining <= 0:
                break

    return sellers, quotas, sales, returns, stores


def boundary_scenarios(sellers: list[dict], quotas: list[dict], sales: list[dict], returns: list[dict]):
    """Hand-crafted sellers on the edges of requirements 3.2 and 3.3 (store T1000)."""
    store = "T1000"
    specs = {
        # seller: (quota per period, description)
        "S19001": ("100000.00", "Exactly 50.00% attainment: qualifies, pays 500.00"),
        "S19002": ("100000.00", "49.995% attainment: shows 50.00% but does not qualify"),
        "S19003": ("100000.00", "Exactly 100%: pays 1,300.00"),
        "S19004": ("100000.00", "Exactly 200%: pays 5,800.00"),
        "S19005": ("100000.00", "250%: capped at 5,800.00"),
        "S19006": ("10000.00", "Half-cent tie: 50.005 rounds up to 50.01"),
        "S19007": ("33333.33", "Band limits fall between cents: pays 350.00"),
        "S19008": ("50000.00", "Odd-cent 50/50 split with S19009"),
        "S19009": ("50000.00", "Second seller of the odd-cent split"),
        "S19010": ("40000.00", "Returns on day 30 (clawback) and day 31 (no clawback)"),
        "S19011": ("40000.00", "Second seller of the S19010 sales"),
        "S19012": ("20000.00", "November net credit is negative: pays 0.00"),
    }
    for sid, (q, desc) in specs.items():
        sellers.append({"seller_id": sid, "name": f"Boundary {sid[-2:]}", "store_id": store,
                        "format": "Boutique", "zone": "Metro", "size": 0, "leaves_on": "",
                        "scenario": desc})
        for pid in PERIODS:
            quotas.append({"period_id": pid, "seller_id": sid, "amount": q})

    def sale(sid, d, amount, credits=None):
        rec = {"type": "SALE", "txn_date": d, "store_id": store, "amount": amount,
               "credits": credits or [(sid, 100)], "original": None}
        sales.append(rec)
        return rec

    def ret(original, d, amount):
        returns.append({"type": "RETURN", "txn_date": d, "store_id": store, "amount": amount,
                        "credits": [], "original": original})

    oct_ = date(2026, 10, 1)
    # Gate and bands (October)
    for sid, chunks in {
        "S19001": [20000.00, 20000.00, 10000.00],
        "S19002": [25000.00, 24995.00],
        "S19003": [40000.00, 35000.00, 25000.00],
        "S19004": [80000.00, 70000.00, 50000.00],
        "S19005": [100000.00, 100000.00, 50000.00],
        "S19006": [2500.25, 2500.25],
        "S19007": [15000.00, 15000.00],
    }.items():
        for i, amount in enumerate(chunks):
            sale(sid, oct_ + timedelta(days=2 + 3 * i), amount)
    # Odd-cent split, plus enough volume to qualify
    for i in range(5):
        sale("S19008", oct_ + timedelta(days=4 + i), 100.01, [("S19008", 50), ("S19009", 50)])
    sale("S19008", oct_ + timedelta(days=12), 30000.00)
    sale("S19009", oct_ + timedelta(days=13), 30000.00)
    # Clawback window: sales on Oct 5, returns on Nov 4 (30 days) and Nov 5 (31 days)
    a = sale("S19010", date(2026, 10, 5), 10000.00, [("S19010", 70), ("S19011", 30)])
    b = sale("S19010", date(2026, 10, 5), 8000.00, [("S19010", 70), ("S19011", 30)])
    ret(a, date(2026, 11, 4), 100.01)
    ret(b, date(2026, 11, 5), 500.00)
    sale("S19010", date(2026, 10, 20), 25000.00)
    sale("S19010", date(2026, 11, 20), 30000.00)
    sale("S19011", date(2026, 10, 21), 25000.00)
    sale("S19011", date(2026, 11, 21), 30000.00)
    # Negative month: October sale fully returned in November, no November sales
    c = sale("S19012", date(2026, 10, 25), 20000.00)
    sale("S19012", date(2026, 10, 26), 5000.00)
    ret(c, date(2026, 11, 10), 20000.00)


def main():
    sellers, quotas, sales, returns, _ = build()
    boundary_scenarios(sellers, quotas, sales, returns)

    # ids in chronological order; sales before returns on the same day
    sales.sort(key=lambda t: t["txn_date"])
    for i, t in enumerate(sales, start=1):
        t["transaction_id"] = f"SALE-{i:06d}"
    returns.sort(key=lambda t: (t["txn_date"], t["original"]["transaction_id"]))
    for i, t in enumerate(returns, start=1):
        t["transaction_id"] = f"RET-{i:06d}"
    txns = sorted(sales + returns, key=lambda t: (t["txn_date"], t["type"] == "RETURN", t["transaction_id"]))

    OUT.mkdir(exist_ok=True)
    with open(OUT / "sellers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seller_id", "name", "store_id", "leaves_on", "scenario"])
        for s in sellers:
            w.writerow([s["seller_id"], s["name"], s["store_id"], s["leaves_on"], s.get("scenario", "")])
    with open(OUT / "quotas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["period_id", "seller_id", "amount"])
        for q in quotas:
            w.writerow([q["period_id"], q["seller_id"], q["amount"]])
    with open(OUT / "transactions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["transaction_id", "type", "txn_date", "store_id", "amount",
                    "seller_1", "split_1", "seller_2", "split_2", "original_transaction_id"])
        for t in txns:
            c = t["credits"] + [("", "")] * (2 - len(t["credits"]))
            w.writerow([t["transaction_id"], t["type"], t["txn_date"].isoformat(), t["store_id"],
                        money(t["amount"]), c[0][0], c[0][1], c[1][0], c[1][1],
                        t["original"]["transaction_id"] if t["original"] else ""])

    manifest = {
        "seed": SEED,
        "sellers": len(sellers),
        "quotas": len(quotas),
        "sales": len(sales),
        "returns": len(returns),
        "split_sales": sum(1 for t in sales if len(t["credits"]) == 2),
        "leave_date": LEAVE_DATE.isoformat(),
        "sha256": {
            name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
            for name in ("sellers.csv", "quotas.csv", "transactions.csv")
        },
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "sha256"}, indent=2))


if __name__ == "__main__":
    main()
