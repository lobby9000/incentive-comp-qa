# Test plan: Commission Engine 0.1.0

| | |
|---|---|
| System under test | Commission Engine REST API, builds `0.1.0-rc1` and later |
| Basis | `docs/01-requirements.md` (v1.0, clarified to v1.1 during test design) |
| Author | Luis A. Quiroz |
| Test data | `data/generated/` (seed 20261008) and per-test fixtures |

## 1. Scope

**In scope:** every requirement in sections 3 and 4 of the requirements: crediting
and split rules, returns and clawback, the commission calculation, statements,
period close and locking, batch import, field validation and the API contract.

**Out of scope:** the items listed as out of scope in the requirements, load and
security testing, and browser UI (the product has none).

## 2. Approach

Testing is risk-based: the effort goes first to anything that can pay a seller the
wrong amount, pay twice, or leave the database in a partial state.

| Level | What it checks | Tool | Runs on |
|---|---|---|---|
| API functional, black box | Each requirement through the public endpoints, including negative and boundary cases | pytest + FastAPI TestClient | SQLite, every commit |
| API contract and smoke | The same contract against a running server, as an external client sees it | Postman collection, Newman CLI | PostgreSQL 16, every commit (CI) |
| Database | Invariants on stored rows after a full-volume load, with SQL that must return zero rows | PostgreSQL 16, `sql/*.sql` | CI |
| Calculation (parallel run) | Every payout of a 25,259-transaction dataset against an independent Excel model, to the cent | `oracle/`, `scripts/reconcile.py` | CI |
| Exploratory, manual | What scripted cases miss: odd inputs, sequences, readability of errors | Postman and Swagger UI (`/docs`), charters in `docs/05-exploratory-charters.md` | Before sign-off |
| Regression | All automated suites on every build and pull request | GitHub Actions | CI |

### Test design techniques

* **Equivalence partitioning** for field rules (valid and invalid classes of IDs, dates, amounts).
* **Boundary value analysis** on every numeric or date edge in the plan: the 50% gate, the
  band limits at 80%, 100%, 150% and 200%, the 30/31-day clawback window, amount and quota
  limits, the first and last day of the plan, the 5,000-row import limit.
* **Decision table** for qualification by band (gate x band reached).
* **State transition** for periods (OPEN to CLOSED, and what each state allows).
* **Error guessing** from common money defects: banker's rounding, rounding before comparing,
  floor of negative numbers, floating point in money, double posting on retries.
* **Parallel run** against an independent oracle for the calculation (a test oracle that does
  not share code or arithmetic with the engine).

## 3. Risks and priorities

| Risk | Impact | Priority of covering tests |
|---|---|---|
| R1. A payout is calculated wrong (rounding, gate, bands, cap) | Sellers paid incorrectly | P1 |
| R2. A sale or return is counted twice or lost | Wrong payouts, audit findings | P1 |
| R3. A failed import or close leaves partial data | Data integrity | P1 |
| R4. A closed period changes after payouts were stored | Payouts no longer match data | P1 |
| R5. Invalid input accepted or valid input rejected | Bad data or blocked operations | P2 |
| R6. Error codes and formats differ from the contract | Client integrations break | P3 |

Priority: **P1** must pass before release, **P2** should pass (a failure needs an
agreed workaround), **P3** is desirable.

## 4. Defect management

Defects are logged in Jira (project `COMP`) and mirrored as markdown in `bugs/`.
Workflow: Open, In Progress, Fixed, Retest, Closed (or Reopened).

| Severity | Meaning |
|---|---|
| S1 Critical | Wrong money, data loss or corruption, no workaround |
| S2 Major | A business rule is not enforced or a main flow fails |
| S3 Minor | Wrong code, message or format, but the flow still works |
| S4 Trivial | Cosmetic |

Priority (Highest to Lowest) is set at triage from severity and how often the
case happens in real data.

## 5. Entry and exit criteria

**Entry:**

* build deployed and `/health` answers
* requirements baselined
* dataset generated
* oracle self-check passing (13/13 spec examples)

**Exit:**

* all P1 cases pass
* no open S1 or S2 defects
* reconciliation matches 100% of payouts to the cent
* all SQL invariants return zero rows
* the test summary report is published

## 6. Environments

| | Local | CI |
|---|---|---|
| Python | 3.12+ | 3.12 |
| Database | SQLite file | PostgreSQL 16 service container |
| Newman | 6.x | 6.x |
| LibreOffice (oracle rebuild only) | optional | `libreoffice-calc` |

## 7. Estimates

| Activity | Hours |
|---|---|
| Requirements review and test design | 6 |
| pytest automation | 8 |
| Postman collection and Newman setup | 4 |
| SQL invariants | 2 |
| Dataset and Excel oracle | 4 |
| Execution and triage, rc1 | 3 |
| Retest and regression, rc2 | 1 |
| Reporting | 2 |
| **Total** | **30** |

## 8. Requirements review (static testing)

Findings raised while designing test cases, before any execution. Each was
resolved and the requirements were updated to v1.1.

| ID | Finding | Resolution (v1.1) |
|---|---|---|
| RR-01 | REQ-CRD-01 names no error code when splits do not add up to 100, when a sale credits 0 or more than 2 sellers, or when a SALE has no credits. | `INVALID_SPLIT` (422) when splits do not add up to 100, and `VALIDATION_ERROR` (422) for the number of credit lines. |
| RR-02 | REQ-API-01 (schema errors return `VALIDATION_ERROR`) and REQ-IMP-02 (list every failing row) overlap for a schema-invalid row inside an import. | Schema errors keep the `VALIDATION_ERROR` body and carry the row index in `details[].loc` (`body.transactions.<row>.<field>`). Business-rule failures use `IMPORT_REJECTED`. In both cases nothing is stored. |
| RR-03 | REQ-STM-03 does not say how displayed band values are rounded. | Every displayed money or percentage value rounds half-up, as in REQ-CAL-06. |
| RR-04 | "Half-up" is ambiguous for negative attainment. | Ties round away from zero (-1.005% shows as -1.01%). |

## 9. Deliverables

`docs/03-test-cases.csv` (catalog), `docs/04-traceability.md` (requirements to tests to
defects), `docs/05-exploratory-charters.md`, `docs/06-test-summary-report.md`,
`tests/`, `postman/`, `sql/`, `oracle/`, `bugs/` and `reports/`.
