"""Drop every table of the Commission Engine so the next start begins empty.

Usage: python scripts/reset_db.py <database_url>
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import SQLModel, create_engine  # noqa: E402

import app.models  # noqa: E402,F401  (registers the tables)

url = sys.argv[1]
if url.startswith("sqlite:///"):
    path = Path(url.replace("sqlite:///", "", 1))
    path.unlink(missing_ok=True)
else:
    engine = create_engine(url)
    SQLModel.metadata.drop_all(engine)
    engine.dispose()
print(f"reset {url}")
