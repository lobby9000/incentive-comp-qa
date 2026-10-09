-- TC-DB-003 | REQ-CRD-02, REQ-RET-04
-- (a) In a two-seller transaction the second line is floor(amount * split / 100),
--     signed: positive for sales, negative for returns. The first line gets the rest.
-- (b) A return inherits the sellers and splits of its original sale, line by line.
-- Healthy result: 0 rows.
WITH lines AS (
    SELECT c.transaction_id, c.line_no, c.seller_id, c.split_pct, c.credit_cents,
           t.type, t.amount_cents, t.original_transaction_id,
           CASE WHEN t.type = 'SALE' THEN 1 ELSE -1 END AS sign,
           COUNT(*) OVER (PARTITION BY c.transaction_id) AS n_lines
    FROM credit c
    JOIN txn t ON t.transaction_id = c.transaction_id
)
SELECT 'floor_rule' AS problem, l.transaction_id, l.line_no, l.credit_cents,
       l.sign * ((l.amount_cents * l.split_pct) / 100) AS expected_cents
FROM lines l
WHERE l.n_lines = 2 AND l.line_no = 2
  AND l.credit_cents <> l.sign * ((l.amount_cents * l.split_pct) / 100)
UNION ALL
SELECT 'not_inherited', l.transaction_id, l.line_no, l.credit_cents, NULL
FROM lines l
LEFT JOIN credit o ON o.transaction_id = l.original_transaction_id AND o.line_no = l.line_no
WHERE l.type = 'RETURN'
  AND (o.seller_id IS DISTINCT FROM l.seller_id OR o.split_pct IS DISTINCT FROM l.split_pct);
