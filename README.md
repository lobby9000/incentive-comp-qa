# Incentive Compensation API: a QA case study

[![QA](https://github.com/lobby9000/incentive-comp-qa/actions/workflows/qa.yml/badge.svg)](https://github.com/lobby9000/incentive-comp-qa/actions/workflows/qa.yml)

A full QA cycle on a sales-commission engine, the kind of calculation that
sales performance management software automates: split credit, returns that
claw back commission, a 50% gate, tiered accelerators and a cap. The engine is
a small REST API (FastAPI, SQLModel, PostgreSQL). The point of the repository is
the testing around it: requirements review, test design, API and database
testing, defect tracking, regression in CI and a parallel run against an
independent Excel model.

## Results

| | Build rc1 | Build rc2 |
|---|---|---|
| Test cases passed (92 designed from the requirements) | 30 | **92** |
| Defects open | 8 (2 critical) | 0 |
| Payouts matching the Excel oracle, to the cent | 552 of 750 | **750 of 750** |
| Money error over the quarter | 6,566.74 MXN overpaid | 0.00 |
| SQL invariants on 25,259 stored transactions | blocked | 9 of 9 clean |
| Postman/Newman assertions | 129 of 173 | 158 of 158 |

The suite also detects 18 of 18 faults seeded on purpose
([mutation check](scripts/mutation_check.py)). Full figures are in the
[test summary report](docs/06-test-summary-report.md).

## Three defects worth reading

* **[BUG-008](bugs/BUG-008.md): every sale failed on PostgreSQL and passed on SQLite.**
  The ORM wrote credit lines before their transaction. SQLite does not enforce
  foreign keys by default, so the local suite was green. Running the same suite
  on the production database engine caught it, and CI now does that on every push.
* **[BUG-004](bugs/BUG-004.md): returns on day 30 were not clawed back.** A `<`
  that should have been `<=`. Boundary testing found it in one case. The parallel
  run measured it: 26 payouts overpaid, 6,066.83 MXN.
* **[BUG-002](bugs/BUG-002.md): 49.995% passed a 50% gate.** The engine compared the
  rounded display value. The requirements now state the gate uses the exact value,
  and a crafted boundary seller in the dataset keeps it covered.

## How the testing was done

1. **Requirements first.** [Requirements](docs/01-requirements.md) with IDs and
   worked examples. Reviewing them for testability found four gaps before any code
   ran (RR-01 to RR-04 in the [test plan](docs/02-test-plan.md)).
2. **Test design.** [92 test cases](docs/03-test-cases.csv) from equivalence
   partitioning, boundary values (gate, band limits, clawback day 30/31, amount
   limits), state transitions for period close and error guessing on money
   (banker's rounding, rounding before comparing, floor of negatives), each
   prioritized by risk.
3. **Automation.** pytest for the API ([tests/](tests/)), a Postman collection run
   with Newman ([postman/](postman/)), and SQL that must return zero rows on a
   healthy database ([sql/](sql/)).
4. **Parallel run.** An [Excel model](oracle/) re-implements the plan with
   formulas in integer cents and reconciles every payout of a 25,259-transaction
   quarter with the API.
5. **Defects.** Each one with steps, expected and actual results, impact and
   root cause ([bugs/](bugs/)), plus a [CSV ready for Jira import](bugs/jira-import.csv).
6. **Retest and regression.** Fixes are separate commits named after the bug.
   The [traceability matrix](docs/04-traceability.md) is generated from the
   JUnit reports, so it cannot drift from the real results.

## Tools

| Tool | Used for |
|---|---|
| Python, pytest | API and functional tests, data generation, reconciliation |
| Postman, Newman | Contract tests against a running server, HTML and JUnit reports |
| PostgreSQL 16, SQL | Database testing with invariant queries |
| Excel (LibreOffice in CI) | Independent test oracle for the calculation |
| Jira | Defect tracking (CSV import of the eight defects) |
| GitHub Actions | Regression on every push, on SQLite and PostgreSQL |
| FastAPI, SQLModel | The system under test |

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

pytest                                   # functional suite on SQLite (108 results)
uvicorn app.main:app --reload            # API at http://localhost:8000/docs

# PostgreSQL (docker compose up -d db, or your own server)
export TEST_DATABASE_URL=postgresql+psycopg://qa:qa@localhost:5432/comp_test
pytest                                   # same suite on PostgreSQL
pytest -m fullload                       # 25,259 transactions, oracle, SQL invariants

scripts/run_newman.sh local              # Postman collection (npm i -g newman newman-reporter-htmlextra)
```

Shortcuts for these commands are in the [Makefile](Makefile).

## Repository map

```
app/            system under test (FastAPI + SQLModel)
docs/           requirements, test plan, test cases, traceability, charters, summary report
tests/          pytest suite, one test per test case ID
postman/        collection builder and the exported collection
sql/            database invariants (each must return 0 rows)
oracle/         Excel oracle: builder, LibreOffice recalculation, extracted results
data/           store dimension and the seeded dataset generator
bugs/           defect reports and the Jira import file
reports/        JUnit, Newman HTML and reconciliation reports for rc1 and rc2
scripts/        reconciliation, Newman runner, traceability, mutation check
qa_tools/       loader and comparison helpers shared by tests and scripts
```

## How this was built

I used an AI assistant (Claude) to draft the requirements, implement the engine
and scaffold the test tooling. The defects listed were found by the test suite
in the first build and were not planted. The
18 faults in `scripts/mutation_check.py` are the only intentional ones, and they
exist only to measure the suite.

## Data

All data is synthetic. The 61 stores come from my
[Retail Logistics case](https://github.com/lobby9000/Retail-Business-Data-Cases).
Sellers, quotas, 23,861 sales and 1,398 returns are generated with a fixed seed
(`data/generate.py`).

Luis A. Quiroz

Case study page: [lobby9000.github.io/qa-case-study.html](https://lobby9000.github.io/qa-case-study.html) · Licence: [MIT](LICENSE)

---

Part of the portfolio of Luis Ángel Quiroz López · [lobby9000.github.io](https://lobby9000.github.io) · [LinkedIn](https://www.linkedin.com/in/llqq) · [GitHub](https://github.com/lobby9000)
