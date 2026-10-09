# Shortcuts for local runs. Every target is a plain command you can also type.
PY ?= python3
PG ?= postgresql+psycopg://qa:qa@localhost:5432

.PHONY: install run test test-pg fullload newman reconcile oracle data traceability mutation db

install:            ## install dependencies
	$(PY) -m pip install -r requirements-dev.txt

db:                 ## start PostgreSQL 16 in Docker (optional)
	docker compose up -d db

run:                ## start the API on a local SQLite file
	DATABASE_URL=sqlite:///./comp.db $(PY) -m uvicorn app.main:app --reload

test:               ## functional suite on SQLite
	$(PY) -m pytest

test-pg:            ## functional suite on PostgreSQL
	TEST_DATABASE_URL=$(PG)/comp_test $(PY) -m pytest

fullload:           ## full dataset, parallel run and SQL invariants on PostgreSQL
	TEST_DATABASE_URL=$(PG)/comp_test $(PY) -m pytest -m fullload

newman:             ## Postman collection against a fresh SQLite server
	scripts/run_newman.sh local

reconcile:          ## parallel run report in reports/local/
	$(PY) scripts/reconcile.py --in-process --database-url $(PG)/comp_test --label local

data:               ## regenerate the synthetic dataset
	$(PY) data/generate.py

oracle:             ## rebuild and recalculate the Excel oracle (needs LibreOffice)
	$(PY) oracle/build_oracle.py && $(PY) oracle/recalc.py oracle/commission_oracle.xlsx && $(PY) oracle/extract.py

traceability:       ## rebuild docs/04-traceability.md from the reports
	$(PY) scripts/traceability.py

mutation:           ## seeded-fault check of the suite
	$(PY) scripts/mutation_check.py --label local
