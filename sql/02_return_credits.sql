-- TC-DB-002 | REQ-RET-04
-- Returns within 30 days of the sale carry credits that add up to minus the
-- return amount. Returns on day 31 or later carry no credit lines.
-- Healthy result: 0 rows.
SELECT r.transaction_id,
       r.txn_date - s.txn_date          AS days_since_sale,
       r.amount_cents,
       COALESCE(SUM(c.credit_cents), 0) AS credited_cents,
       COUNT(c.id)                      AS credit_lines
FROM txn r
JOIN txn s ON s.transaction_id = r.original_transaction_id
LEFT JOIN credit c ON c.transaction_id = r.transaction_id
WHERE r.type = 'RETURN'
GROUP BY r.transaction_id, r.txn_date, s.txn_date, r.amount_cents
HAVING (r.txn_date - s.txn_date <= 30 AND COALESCE(SUM(c.credit_cents), 0) <> -r.amount_cents)
    OR (r.txn_date - s.txn_date > 30 AND COUNT(c.id) > 0);
