-- C05 El mismo ganador repetido en la misma entidad (procesos competitivos).
WITH bids AS (
    SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) AS n_bids
    FROM f_bid WHERE is_competitive GROUP BY ALL
),
wins AS (
    SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) AS n_wins,
           list(DISTINCT ocid) AS won
    FROM f_award WHERE is_competitive GROUP BY ALL
),
pairs AS (
    SELECT w.*, greatest(b.n_bids, w.n_wins) AS n_bids,
           w.n_wins / greatest(b.n_bids, w.n_wins) AS win_rate
    FROM wins w LEFT JOIN bids b USING (buyer_id, supplier_id, year)
    WHERE w.n_wins >= $min_wins
)
SELECT unnest(p.won) AS ocid, p.buyer_id, p.supplier_id, p.year,
       p.win_rate * least(1.0, p.n_wins / (2.0 * $min_wins)) AS severity,
       p.buyer_id || '|' || p.supplier_id || '|' || p.year AS scope_key,
       to_json(struct_pack(wins := p.n_wins, bids := p.n_bids,
                           win_rate := round(p.win_rate, 3)))::VARCHAR AS evidence
FROM pairs p
WHERE p.win_rate >= $min_win_rate
