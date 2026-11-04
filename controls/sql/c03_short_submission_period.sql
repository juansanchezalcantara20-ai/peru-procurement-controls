-- C03 Plazo de presentación de ofertas demasiado corto (Cardinal R003, mínimos por método).
-- La unión por método ignora mayúsculas y tildes («Licitación Pública» = «Licitación pública»).
WITH periods AS (
    SELECT p.ocid, p.buyer_id, p.year, p.method_details, p.tender_start, p.tender_end,
           date_diff('day', CAST(p.tender_start AS DATE), CAST(p.tender_end AS DATE)) AS days,
           coalesce(r.min_days, $default_min_days) AS min_days
    FROM f_process p
    LEFT JOIN ref_min_submission_days r
           ON lower(strip_accents(r.method_details)) = lower(strip_accents(p.method_details))
    WHERE p.is_competitive AND p.tender_start IS NOT NULL AND p.tender_end IS NOT NULL
)
SELECT s.ocid, s.buyer_id, a.supplier_id, s.year,
       greatest(0.1, 1.0 - s.days / s.min_days) AS severity,
       s.method_details AS scope_key,
       to_json(struct_pack(method := s.method_details, start := s.tender_start, "end" := s.tender_end,
                           days := s.days, min_days := s.min_days))::VARCHAR AS evidence
FROM periods s
LEFT JOIN (SELECT ocid, arg_min(supplier_id, award_id) AS supplier_id FROM f_award GROUP BY ocid) a
       USING (ocid)
WHERE s.days < s.min_days
