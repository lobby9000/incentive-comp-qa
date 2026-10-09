-- TC-DB-001 | REQ-CRD-02
-- The credit lines of every sale add up exactly to the sale amount.
-- Healthy result: 0 rows.
SELECT t.transaction_id,
       t.amount_cents,
       COALESCE(SUM(c.credit_cents), 0) AS credited_cents
FROM txn t
LEFT JOIN credit c ON c.transaction_id = t.transaction_id
WHERE t.type = 'SALE'
GROUP BY t.transaction_id, t.amount_cents
HAVING COALESCE(SUM(c.credit_cents), 0) <> t.amount_cents;
