import csv
import os
from datetime import date
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .models import Period, Store

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PLAN_PERIODS = [
    ("2026-10", date(2026, 10, 1), date(2026, 10, 31)),
    ("2026-11", date(2026, 11, 1), date(2026, 11, 30)),
    ("2026-12", date(2026, 12, 1), date(2026, 12, 31)),
]


def make_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///./comp.db")
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        # BUG-008 follow-up: enforce foreign keys on SQLite too, so local runs
        # fail the same way PostgreSQL does instead of hiding ordering bugs.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(Store)).first() is None:
            with open(DATA_DIR / "stores.csv", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    session.add(Store(
                        store_id=row["store_id"],
                        zone=row["zone"],
                        format=row["format"],
                        distribution_center=row["distribution_center"],
                        sales_floor_m2=int(row["sales_floor_m2"]),
                    ))
        if session.exec(select(Period)).first() is None:
            for pid, start, end in PLAN_PERIODS:
                session.add(Period(period_id=pid, start_date=start, end_date=end))
        session.commit()
