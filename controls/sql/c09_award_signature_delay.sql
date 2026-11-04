-- C09 Tiempo atípico entre la adjudicación y la firma del contrato.
SELECT c.ocid, c.buyer_id, c.supplier_id, c.year,
       least(1.0, (date_diff('day', CAST(c.award_date AS DATE), CAST(c.date_signed AS DATE)) - $max_days)
                  / (2.0 * $max_days)) AS severity,
       c.method_details AS scope_key,
       to_json(struct_pack(award_date := CAST(c.award_date AS DATE), signed := CAST(c.date_signed AS DATE),
                           days := date_diff('day', CAST(c.award_date AS DATE), CAST(c.date_signed AS DATE)),
                           max_days := $max_days))::VARCHAR AS evidence
FROM f_contract c
JOIN f_process p ON p.ocid = c.ocid
WHERE c.date_signed IS NOT NULL
  AND NOT list_contains($excluded_methods, p.procurement_method)
  AND date_diff('day', CAST(c.award_date AS DATE), CAST(c.date_signed AS DATE)) > $max_days
