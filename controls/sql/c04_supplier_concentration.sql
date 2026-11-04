-- C04 Supplier concentration by entity and category (HHI on awarded amount).
WITH by_supplier AS (
    SELECT buyer_id, segment, year, supplier_id, sum(amount) AS amt, count(*) AS n
    FROM f_award WHERE amount IS NOT NULL
    GROUP BY ALL
),
hhi AS (
    SELECT b.buyer_id, b.segment, b.year,
           sum(power(100.0 * b.amt / t.total, 2)) AS hhi,
           any_value(t.total) AS total, any_value(t.n_awards) AS n_awards, count(*) AS n_suppliers,
           arg_max(b.supplier_id, b.amt) AS top_supplier, arg_max(b.n, b.amt) AS top_awards, max(b.amt) / any_value(t.total) AS top_share
    FROM by_supplier b
    JOIN (SELECT buyer_id, segment, year, sum(amt) AS total, sum(n) AS n_awards
          FROM by_supplier GROUP BY ALL) t USING (buyer_id, segment, year)
    GROUP BY ALL
)
SELECT a.ocid, a.buyer_id, a.supplier_id, a.year,
       (h.hhi - $hhi_threshold) / (10000.0 - $hhi_threshold) AS severity,
       h.buyer_id || '|' || h.segment || '|' || h.year AS scope_key,
       to_json(struct_pack(segment := h.segment, hhi := round(h.hhi, 0), n_awards := h.n_awards,
                           n_suppliers := h.n_suppliers, top_supplier_share := round(h.top_share, 3), top_supplier_awards := h.top_awards,
                           cell_total := round(h.total, 2)))::VARCHAR AS evidence
FROM hhi h
JOIN f_award a ON a.buyer_id = h.buyer_id AND a.segment = h.segment AND a.year = h.year
              AND a.supplier_id = h.top_supplier AND a.amount IS NOT NULL
WHERE h.n_awards >= $min_awards AND h.hhi > $hhi_threshold AND h.top_awards >= $min_top_awards
