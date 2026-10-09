-- TC-DB-006 | REQ-CLS-03
-- In a closed period every quota has exactly one payout row and every payout
-- row has a quota.
-- Healthy result: 0 rows.
SELECT 'missing_payout' AS problem, q.period_id, q.seller_id
FROM quota q
JOIN period p ON p.period_id = q.period_id AND p.status = 'CLOSED'
LEFT JOIN payout po ON po.period_id = q.period_id AND po.seller_id = q.seller_id
WHERE po.id IS NULL
UNION ALL
SELECT 'payout_without_quota', po.period_id, po.seller_id
FROM payout po
LEFT JOIN quota q ON q.period_id = po.period_id AND q.seller_id = po.seller_id
WHERE q.id IS NULL
UNION ALL
SELECT 'duplicate_payout', period_id, seller_id
FROM payout
GROUP BY period_id, seller_id
HAVING COUNT(*) > 1;
