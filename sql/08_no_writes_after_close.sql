-- TC-DB-008 | REQ-CLS-04
-- Nothing was written to a period after it was closed.
-- Healthy result: 0 rows.
SELECT 'transaction' AS kind, t.transaction_id AS id, t.created_at AS written_at, p.closed_at
FROM txn t
JOIN period p ON p.period_id = t.period_id
WHERE p.status = 'CLOSED' AND t.created_at > p.closed_at
UNION ALL
SELECT 'credit', c.transaction_id, c.created_at, p.closed_at
FROM credit c
JOIN period p ON p.period_id = c.period_id
WHERE p.status = 'CLOSED' AND c.created_at > p.closed_at
UNION ALL
SELECT 'quota', q.seller_id, q.updated_at, p.closed_at
FROM quota q
JOIN period p ON p.period_id = q.period_id
WHERE p.status = 'CLOSED' AND q.updated_at > p.closed_at;
