"""Run the SQL invariants in sql/ (PostgreSQL dialect). Each must return zero rows."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def checks() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


def tc_id(path: Path) -> str:
    first = path.read_text(encoding="utf-8").splitlines()[0]
    return first.replace("--", "").split("|")[0].strip()


def run(database_url: str) -> dict[str, list[dict]]:
    engine = create_engine(database_url)
    results = {}
    with engine.connect() as conn:
        for path in checks():
            rows = conn.execute(text(path.read_text(encoding="utf-8"))).mappings().all()
            results[path.name] = [dict(r) for r in rows]
    engine.dispose()
    return results
