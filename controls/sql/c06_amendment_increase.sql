-- C06 Modificaciones contractuales que suben el monto por encima del tope.
SELECT c.ocid, c.buyer_id, c.supplier_id, c.year,
       least(1.0, (c.final_amount / c.original_amount - 1 - $cap) / (1 - $cap)) AS severity,
       c.contract_id AS scope_key,
       to_json(struct_pack(contract_id := c.contract_id, original_amount := c.original_amount,
                           amended_amount := c.final_amount,
                           increase_pct := round(100 * (c.final_amount / c.original_amount - 1), 1),
                           n_amendments := c.n_amendments))::VARCHAR AS evidence
FROM f_contract c
WHERE c.final_amount IS NOT NULL AND c.original_amount > 0
  AND c.final_amount / c.original_amount - 1 > $cap
