-- C01 Compras partidas debajo del límite de compra menor.
-- Columnas de salida (controles por proceso): ocid, buyer_id, supplier_id, year, severity, scope_key, evidence
WITH near AS (
    SELECT a.ocid, a.buyer_id, a.supplier_id, a.segment, a.year,
           CAST(a.award_date AS DATE) AS d, a.amount, r.limit_pen
    FROM f_award a
    JOIN ref_minor_limit r ON r.year = a.year
    WHERE list_contains($minor_methods, a.procurement_method)
      AND a.amount IS NOT NULL
      AND a.amount <= r.limit_pen
      AND a.amount >= $near_limit_ratio * r.limit_pen
),
clusters AS (
    -- cada compra cercana al límite abre una ventana; los miembros son las compras dentro de ella
    SELECT x.ocid AS anchor, x.buyer_id, x.supplier_id, x.segment, x.year, x.d AS start_date,
           max(x.limit_pen) AS limit_pen, count(*) AS n, sum(y.amount) AS total,
           list(y.ocid ORDER BY y.d, y.ocid) AS members,
           list(y.amount ORDER BY y.d, y.ocid) AS amounts
    FROM near x
    JOIN near y
      ON y.buyer_id = x.buyer_id AND y.supplier_id = x.supplier_id AND y.segment = x.segment
     AND y.d BETWEEN x.d AND x.d + CAST($window_days AS INTEGER)
    GROUP BY ALL
    HAVING count(*) >= $min_purchases AND sum(y.amount) > max(x.limit_pen)
),
flagged AS (
    SELECT unnest(members) AS ocid, c.*
    FROM clusters c
)
SELECT f.ocid, f.buyer_id, f.supplier_id, f.year,
       least(1.0, arg_max(f.n, f.n) / 5.0) AS severity,
       arg_max(f.buyer_id || '|' || f.supplier_id || '|' || f.segment || '|' || f.start_date, f.n) AS scope_key,
       to_json(arg_max(struct_pack(
           n_purchases := f.n, cluster_total := round(f.total, 2), limit_pen := f.limit_pen,
           total_vs_limit := round(f.total / f.limit_pen, 2), window_start := f.start_date,
           segment := f.segment, members := f.members, amounts := f.amounts), f.n))::VARCHAR AS evidence
FROM flagged f
GROUP BY f.ocid, f.buyer_id, f.supplier_id, f.year
