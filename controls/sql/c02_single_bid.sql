-- C02 Single bidder in a competitive procedure (Cardinal R018).
SELECT p.ocid, p.buyer_id, a.supplier_id, p.year,
       1.0 AS severity,
       p.method_details AS scope_key,
       to_json(struct_pack(method := p.method_details, procurement_method := p.procurement_method,
                           n_bidders := p.n_tenderers, award_amount := a.amount))::VARCHAR AS evidence
FROM f_process p
LEFT JOIN (SELECT ocid, arg_min(supplier_id, award_id) AS supplier_id, sum(amount) AS amount
           FROM f_award GROUP BY ocid) a USING (ocid)
WHERE list_contains($competitive_methods, p.procurement_method)
  AND p.n_tenderers = 1
