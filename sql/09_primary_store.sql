-- TC-DB-009 | REQ-CRD-04
-- The first seller of every sale belongs to the store where the sale happened.
-- Healthy result: 0 rows.
SELECT t.transaction_id,
       t.store_id,
       s.seller_id,
       s.store_id AS seller_store
FROM txn t
JOIN credit c ON c.transaction_id = t.transaction_id AND c.line_no = 1
JOIN seller s ON s.seller_id = c.seller_id
WHERE t.type = 'SALE'
  AND s.store_id <> t.store_id;
