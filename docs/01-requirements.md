# Requirements: Commission Engine for plan RET-Q4-2026

| | |
|---|---|
| Document | Requirements and acceptance criteria |
| Plan | RET-Q4-2026, retail floor sales, Q4 FY2026 |
| Version | 1.1 (1.0 was the baseline for build `0.1.0-rc1`, 1.1 adds clarifications from test design, see section 6) |
| Currency | MXN |
| Status | Approved for implementation |

## 1. Purpose

The Commission Engine credits retail sales to sellers, measures each seller's
attainment against a monthly quota, and calculates commission payouts with a
tiered plan (gate, accelerators and cap). It exposes a REST API. This document
is the single source of truth for development and for test design: every test
case in `docs/03-test-cases.csv` traces to a requirement ID below.

The store network is the 61-store dimension from the
[Retail Logistics case](https://github.com/lobby9000/Retail-Business-Data-Cases)
(`data/stores.csv`). All data is synthetic.

## 2. Glossary

| Term | Meaning |
|---|---|
| Seller | A sales associate who can receive credit. ID format `S` + 5 digits. |
| Period | A calendar month of the plan: `2026-10`, `2026-11`, `2026-12`. |
| Quota | Target sales for one seller in one period, in MXN. |
| Credit | The share of a transaction attributed to one seller, in MXN. Positive for sales, negative for clawed-back returns. |
| Net credited sales | Sum of a seller's credits in a period. |
| Attainment | Net credited sales divided by quota. |
| Clawback | A return that reduces the credit of the sellers of the original sale. |
| Close | Freezing a period and storing its payouts. |

## 3. Plan rules

### 3.1 Crediting

| ID | Requirement |
|---|---|
| REQ-CRD-01 | A SALE credits 1 or 2 sellers (`VALIDATION_ERROR` otherwise). Each credit line has an integer `split_pct` from 1 to 100 and the splits of a sale add up to exactly 100 (`INVALID_SPLIT`). |
| REQ-CRD-02 | Credits are allocated in cents. With two sellers, the second seller receives `floor(amount_cents * split_pct / 100)` and the first seller receives the remainder. The credits of a transaction always add up exactly to its amount. A credit line is stored even when its value is 0.00. |
| REQ-CRD-03 | Every credited seller must exist (`UNKNOWN_SELLER`) and be ACTIVE (`SELLER_INACTIVE`). A seller cannot appear twice in the same sale (`DUPLICATE_SELLER`). |
| REQ-CRD-04 | The first seller of a sale must belong to the sale's store (`PRIMARY_SELLER_STORE_MISMATCH`). The second seller may belong to any store (floating staff). |
| REQ-CRD-05 | Credits post to the period that contains the transaction date. |

### 3.2 Returns and clawback

| ID | Requirement |
|---|---|
| REQ-RET-01 | A RETURN references an existing SALE through `original_transaction_id` (`UNKNOWN_ORIGINAL`). Referencing a RETURN is rejected (`INVALID_ORIGINAL`). A RETURN must not include `credits` because it inherits the sellers and splits of the original sale (`CREDITS_NOT_ALLOWED`). |
| REQ-RET-02 | The total returned against a sale cannot exceed the sale amount (`RETURN_EXCEEDS_SALE`). |
| REQ-RET-03 | The return date cannot be earlier than the sale date (`RETURN_BEFORE_SALE`). |
| REQ-RET-04 | Clawback window: when `return_date - sale_date` is **30 calendar days or less**, the return creates negative credits. Their magnitudes are computed with the REQ-CRD-02 rule applied to the return amount and then negated. When the difference is 31 days or more, the return is stored but creates **no credit lines**. |
| REQ-RET-05 | Return credits post to the period of the return date, not the period of the original sale. Inherited sellers receive the clawback even if they are INACTIVE now. |

### 3.3 Calculation

| ID | Requirement |
|---|---|
| REQ-CAL-01 | Net credited sales `C` for a seller and period is the sum of all their credit lines in that period. |
| REQ-CAL-02 | Attainment `A = C / Q`, where `Q` is the seller's quota for the period. |
| REQ-CAL-03 | Gate: a seller qualifies only when `A >= 50%`. The gate is evaluated on the **exact, unrounded** attainment. A seller that does not qualify earns 0.00. |
| REQ-CAL-04 | Marginal rate table. Each slice of `C`, measured as a share of `Q`, earns the rate of its band: |
| | Band A: 0% to 80% of quota at **1.0%** |
| | Band B: 80% to 100% at **2.5%** |
| | Band C: 100% to 150% at **4.0%** (accelerator) |
| | Band D: 150% to 200% at **5.0%** (accelerator) |
| | Above 200%: 0% (cap) |
| | `payout = sum over bands of rate * max(0, min(C, upper * Q) - lower * Q)` |
| REQ-CAL-05 | The payout is never negative. When `C <= 0` the payout is 0.00 and the negative attainment is still reported. |
| REQ-CAL-06 | All intermediate values keep full precision. Only the final payout is rounded to cents, **half-up** (0.005 rounds to 0.01). Attainment is displayed as a percentage with 2 decimals, half-up, with ties on negative values rounding away from zero. |

#### Worked examples (Q = 100,000.00 unless stated)

| C | Attainment shown | Qualifies | Payout |
|---|---|---|---|
| 49,999.99 | 50.00% | No | 0.00 |
| 49,995.00 | 50.00% (exact 49.995%) | No | 0.00 |
| 50,000.00 | 50.00% | Yes | 500.00 |
| 80,000.00 | 80.00% | Yes | 800.00 |
| 100,000.00 | 100.00% | Yes | 1,300.00 |
| 150,000.00 | 150.00% | Yes | 3,300.00 |
| 200,000.00 | 200.00% | Yes | 5,800.00 |
| 250,000.00 | 250.00% | Yes | 5,800.00 (cap) |
| -1,500.00 | -1.50% | No | 0.00 |
| 5,000.50 with Q = 10,000.00 | 50.01% | Yes | 50.01 (50.005 rounds up) |

### 3.4 Period close

| ID | Requirement |
|---|---|
| REQ-CLS-01 | Periods close in order. Closing a period while an earlier period is OPEN is rejected (`PREVIOUS_PERIOD_OPEN`). Closing a CLOSED period is rejected (`PERIOD_ALREADY_CLOSED`). |
| REQ-CLS-02 | Every seller with at least one credit line in the period must have a quota for it, otherwise the close is rejected and lists the sellers (`QUOTA_MISSING`). |
| REQ-CLS-03 | Close stores exactly one payout row per seller with a quota in the period, including sellers with no credits (payout 0.00). The close is atomic: all rows are stored or none. |
| REQ-CLS-04 | After close the period is locked: new transactions dated in it and quota changes are rejected (`PERIOD_CLOSED`). |
| REQ-CLS-05 | The close response reports the number of payout rows and `total_payout`, which equals the sum of the stored rows. |

### 3.5 Statements

| ID | Requirement |
|---|---|
| REQ-STM-01 | `GET /periods/{period}/sellers/{seller}/statement` returns quota, net credited sales, attainment, the qualification flag, one entry per band (base and commission) and the payout. |
| REQ-STM-02 | For an OPEN period the statement is calculated live (`source: LIVE`). For a CLOSED period it returns the stored payout (`source: CLOSED`). |
| REQ-STM-03 | Band commissions are shown rounded individually (half-up) for readability. The payout is rounded once from the exact total (REQ-CAL-06), so it may differ from the sum of the displayed band values by at most 0.01 per band. |
| REQ-STM-04 | A statement for a seller without a quota in the period returns `QUOTA_NOT_FOUND`. |

## 4. API contract

### 4.1 Conventions

| ID | Requirement |
|---|---|
| REQ-API-01 | Every error response has the body `{"error": {"code": str, "message": str, "details": list}}`. Schema errors (missing field, wrong type, unknown field) return 422 with code `VALIDATION_ERROR`. |
| REQ-API-02 | Money in responses is a string with exactly two decimals (`"1300.00"`). Money in requests is a JSON number or string with at most two decimals. |
| REQ-API-03 | Dates use ISO 8601 `YYYY-MM-DD`. |

### 4.2 Endpoints

| Method and path | Success | Errors |
|---|---|---|
| `GET /health` | 200 `{"status": "ok", "version": str}` | |
| `POST /sellers` | 201 seller | 409 `DUPLICATE_SELLER`, 422 `UNKNOWN_STORE`, 422 `VALIDATION_ERROR` |
| `GET /sellers/{seller_id}` | 200 seller | 404 `SELLER_NOT_FOUND` |
| `PATCH /sellers/{seller_id}` | 200 seller (`status` ACTIVE or INACTIVE) | 404 `SELLER_NOT_FOUND`, 422 |
| `GET /periods` | 200 list of periods with status | |
| `PUT /periods/{period}/quotas/{seller_id}` | 201 when created, 200 when replaced | 404 `PERIOD_NOT_FOUND`, 404 `SELLER_NOT_FOUND`, 409 `PERIOD_CLOSED`, 422 |
| `POST /transactions` | 201 transaction with its credit lines | 409 `DUPLICATE_TRANSACTION`, 409 `PERIOD_CLOSED`, 422 (codes in section 3) |
| `GET /transactions/{transaction_id}` | 200 transaction with credit lines | 404 `TRANSACTION_NOT_FOUND` |
| `POST /imports/transactions` | 201 `{"imported", "sales", "returns", "credits"}` | 422 `IMPORT_REJECTED` with one detail per failing row |
| `GET /periods/{period}/sellers/{seller_id}/statement` | 200 statement | 404 `PERIOD_NOT_FOUND`, `SELLER_NOT_FOUND`, `QUOTA_NOT_FOUND` |
| `POST /periods/{period}/close` | 200 close summary | 404, 409 `PERIOD_ALREADY_CLOSED`, `PREVIOUS_PERIOD_OPEN`, `QUOTA_MISSING` |
| `GET /periods/{period}/payouts` | 200 list of payout rows | 404 `PERIOD_NOT_FOUND`, 409 `PERIOD_NOT_CLOSED` |

### 4.3 Field rules

| ID | Requirement |
|---|---|
| REQ-FLD-01 | `seller_id` matches `^S[0-9]{5}$`. `name` is 1 to 80 characters and not blank. `store_id` must exist in the store dimension. |
| REQ-FLD-02 | `transaction_id` matches `^[A-Za-z0-9_-]{1,32}$` and is unique across all transactions (`DUPLICATE_TRANSACTION`, 409). |
| REQ-FLD-03 | Transaction `amount` is greater than 0.00 and at most 1,000,000.00. Quota `amount` is greater than 0.00 and at most 10,000,000.00. Both accept at most two decimals. |
| REQ-FLD-04 | The transaction date must fall inside a plan period (`OUT_OF_PLAN`, 422). A date inside a CLOSED period returns 409 `PERIOD_CLOSED`. |
| REQ-FLD-05 | `type` is `SALE` or `RETURN`. A SALE requires `credits` and must not carry `original_transaction_id`. |

### 4.4 Batch import

| ID | Requirement |
|---|---|
| REQ-IMP-01 | `POST /imports/transactions` accepts 1 to 5,000 transactions applying the same rules as `POST /transactions`. Rows are processed in order, so a return may reference a sale earlier in the same batch. |
| REQ-IMP-02 | The import is atomic. If any row fails, nothing is stored and the response lists every failing row with its index and error code. Schema errors keep the `VALIDATION_ERROR` body with the row index in `details[].loc`, and business-rule failures return `IMPORT_REJECTED`. |

## 5. Out of scope for v1

Authentication, multi-currency, carry-forward of negative balances, draws and
guarantees, SPIFFs, quota proration for mid-period hires, and a user
interface. These are listed so that their absence is a decision, not a gap.

## 6. Revision history

| Version | Change | Source |
|---|---|---|
| 1.0 | Baseline for build `0.1.0-rc1`. | |
| 1.1 | Error codes for split and credit-count failures (REQ-CRD-01). Schema errors inside imports (REQ-IMP-02). Half-up rounding for displayed band values (REQ-STM-03) and for negative attainment (REQ-CAL-06). Clarifications only, no rule changed. | Requirements review RR-01 to RR-04 in `docs/02-test-plan.md` |
