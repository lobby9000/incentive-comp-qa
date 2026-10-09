-- TC-DB-005 | REQ-CRD-05, REQ-RET-05
-- Every transaction and every credit line sits in the period that contains the
-- transaction date (returns use their own date, not the sale's).
-- Healthy result: 0 rows.
SELECT t.transaction_id,
       t.txn_date,
       p.period_id AS expected_period,
       t.period_id AS txn_period,
       c.period_id AS credit_period
FROM txn t
JOIN period p ON t.txn_date BETWEEN p.start_date AND p.end_date
LEFT JOIN credit c ON c.transaction_id = t.transaction_id
WHERE t.period_id <> p.period_id
   OR c.period_id <> p.period_id;
