-- TC-DB-007 | REQ-CAL-01
-- The credited amount and quota stored on each payout row equal the sum of the
-- seller's credit lines and the quota table.
-- Healthy result: 0 rows.
SELECT po.period_id,
       po.seller_id,
       po.credited_cents,
       COALESCE(SUM(c.credit_cents), 0) AS sum_of_credits,
       po.quota_cents,
       q.amount_cents AS quota_table_cents
FROM payout po
JOIN quota q ON q.period_id = po.period_id AND q.seller_id = po.seller_id
LEFT JOIN credit c ON c.period_id = po.period_id AND c.seller_id = po.seller_id
GROUP BY po.period_id, po.seller_id, po.credited_cents, po.quota_cents, q.amount_cents
HAVING po.credited_cents <> COALESCE(SUM(c.credit_cents), 0)
    OR po.quota_cents <> q.amount_cents;
