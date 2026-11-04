-- C07 Precio unitario atípico frente a la mediana de su clase UNSPSC.
WITH stats AS (
    SELECT classification_id, median(unit_amount) AS med, count(*) AS n
    FROM f_item GROUP BY 1
),
hits AS (
    SELECT i.ocid, i.buyer_id, i.year, i.item_id, i.classification_id, i.unit_amount, s.med, s.n,
           i.unit_amount / s.med AS ratio
    FROM f_item i JOIN stats s USING (classification_id)
    WHERE s.n >= $min_group AND s.med > 0 AND i.unit_amount >= $ratio * s.med
)
SELECT h.ocid, h.buyer_id, a.supplier_id, h.year,
       least(1.0, ln(max(h.ratio)) / ln(10.0)) AS severity,
       arg_max(h.classification_id, h.ratio) AS scope_key,
       to_json(arg_max(struct_pack(item_id := h.item_id, class := h.classification_id,
                                   unit_price := h.unit_amount, class_median := round(h.med, 2),
                                   ratio := round(h.ratio, 2), class_n := h.n), h.ratio))::VARCHAR AS evidence
FROM hits h
LEFT JOIN (SELECT ocid, arg_min(supplier_id, award_id) AS supplier_id FROM f_award GROUP BY ocid) a
       USING (ocid)
GROUP BY h.ocid, h.buyer_id, a.supplier_id, h.year
