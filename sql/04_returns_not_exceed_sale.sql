-- TC-DB-004 | REQ-RET-02
-- The total returned against a sale never exceeds the sale amount.
-- Healthy result: 0 rows.
SELECT s.transaction_id,
       s.amount_cents,
       SUM(r.amount_cents) AS returned_cents
FROM txn s
JOIN txn r ON r.original_transaction_id = s.transaction_id
GROUP BY s.transaction_id, s.amount_cents
HAVING SUM(r.amount_cents) > s.amount_cents;
