# Test summary report: Commission Engine 0.1.0

| | |
|---|---|
| Builds tested | `0.1.0-rc1` (first build), `0.1.0-rc2` (fixes) |
| Basis | Requirements v1.1, test plan `docs/02-test-plan.md` |
| Environments | SQLite (local), PostgreSQL 16 (production-like), Newman 6 against a running server |
| Author | Luis A. Quiroz |
| Recommendation | **Release 0.1.0** (rc2 promoted). All exit criteria are met. |

## 1. Results at a glance

| | rc1 | rc2 |
|---|---|---|
| Test cases (92) passed | 30 | **92** |
| Test cases failed or blocked | 60 (51 failed, 9 blocked) | 0 |
| pytest results on SQLite | 96 of 107 passed | 108 of 108 |
| pytest results on PostgreSQL | 52 of 107 passed | 108 of 108 |
| Newman assertions (61 requests) | 129 of 173 passed | 158 of 158 |
| Full dataset load (25,259 transactions) | Blocked | Loaded in 81 s |
| Payouts matching the Excel oracle | 552 of 750 (workaround run) | **750 of 750** |
| Net payout error over the quarter | **6,566.74 MXN overpaid** | 0.00 |
| SQL invariants with zero violations | Blocked | 9 of 9 |
| Open defects | 8 | 0 |

TC-API-008 was added after rc1 to close a coverage gap (section 5), so rc1
counts it as not run.

## 2. Defects

Eight product defects were found in rc1. All were fixed in rc2 and verified.

| ID | Summary | Severity | Found by | Impact on the dataset |
|---|---|---|---|---|
| [BUG-008](../bugs/BUG-008.md) | Every sale fails on PostgreSQL (credit rows inserted before their transaction) | S1 | Functional suite on PostgreSQL | Nothing could be stored on the production database |
| [BUG-001](../bugs/BUG-001.md) | Import returns 500 when a batch has a return after a sale | S1 | TC-IMP-001, full load | Data loading through the import endpoint impossible |
| [BUG-004](../bugs/BUG-004.md) | Returns on day 30 are not clawed back | S2 | TC-RET-002, parallel run | 26 payouts overpaid, 6,066.83 MXN |
| [BUG-002](../bugs/BUG-002.md) | Gate evaluated on rounded attainment (49.995% qualifies) | S2 | TC-CAL-001/002, parallel run | 1 payout overpaid, 499.95 MXN |
| [BUG-003](../bugs/BUG-003.md) | Payout ties use banker's rounding | S2 | TC-CAL-010, parallel run | 4 payouts underpaid by 0.01 |
| [BUG-005](../bugs/BUG-005.md) | Odd-cent clawback moves a cent between sellers | S2 | TC-RET-004, parallel run | 171 statements with a wrong credited amount, 2 payouts off by 0.01 |
| [BUG-006](../bugs/BUG-006.md) | Displayed attainment and band values use banker's rounding | S3 | TC-CAL-014/015 | Display only |
| [BUG-007](../bugs/BUG-007.md) | 404, 405 and 500 bypass the error envelope | S3 | TC-API-006, Newman | Clients parsing `error.code` break |

By severity: 2 critical, 4 major, 2 minor. In the rc1 parallel run, 198 of the
750 statements differed from the oracle. Every difference was traced to
BUG-002, BUG-003, BUG-004 or BUG-005, and none was left unexplained.

## 3. What each technique contributed

| Technique | Defects it caught first |
|---|---|
| Boundary value analysis from the worked examples | BUG-002, BUG-003, BUG-004, BUG-005, BUG-006 |
| Running the same suite on PostgreSQL, not only SQLite | BUG-008 |
| Full-volume load (25,259 rows) | BUG-001 (also caught by TC-IMP-001) |
| Error guessing on the contract | BUG-007 |
| Parallel run against the Excel oracle | Quantified the money impact of BUG-002 to BUG-005, and found 3 natural rounding ties in ordinary sellers, not only in the crafted boundary seller |

## 4. How strong is the suite

`scripts/mutation_check.py` seeds 18 faults on purpose, one at a time (an
inclusive bound made exclusive, a rate, a band limit, the cap, a rounding mode,
a removed validation) and runs the functional suite against each.
**18 of 18 were detected** (`reports/rc2/mutation.json`). These are the only
intentional faults in the project.

## 5. Process findings

| ID | Finding | Action |
|---|---|---|
| RR-01 to RR-04 | Four requirement gaps found while designing tests, before any execution | Requirements v1.1 |
| TD-01 | Test-script defect: the empty `transaction_id` case of TC-TXN-013 sent a generated ID, so it failed for the wrong reason in rc1 | Helper fixed. The case now sends an empty ID and passes against rc2 for the right reason |
| PI-01 | BUG-008 was invisible on SQLite, which does not enforce foreign keys by default | CI runs the functional suite on PostgreSQL. SQLite now runs with foreign keys on |
| PI-02 | The traceability matrix showed REQ-API-03 (ISO dates) had no test case | TC-API-008 added |
| PI-03 | A random dataset rarely lands exactly on a gate or a band limit | 12 boundary sellers built from the worked examples were added to the dataset |

## 6. Exit criteria

| Criterion | Status |
|---|---|
| All P1 test cases pass | Met (40 of 40 in rc2) |
| No open S1 or S2 defects | Met |
| Reconciliation matches 100% of payouts to the cent | Met (750 of 750) |
| All SQL invariants return zero rows | Met (9 of 9) |
| Test summary report published | This document |

## 7. Residual risks

Not covered by this cycle: concurrent writes (two imports at once), load and
security testing, and everything listed as out of scope in the requirements.
The full-dataset import takes about 81 seconds on a laptop, which is fine for
a monthly process but has no agreed target yet.

## 8. Evidence

| What | Where |
|---|---|
| JUnit reports, Newman HTML reports | `reports/rc1/`, `reports/rc2/` |
| Parallel-run reports | `reports/rc1/reconciliation-workaround-sqlite/`, `reports/rc2/reconciliation/` |
| SQL invariant results | `reports/rc2/reconciliation/sql-checks.json` |
| Traceability matrix | `docs/04-traceability.md` |
| Defect reports and Jira import file | `bugs/` |
