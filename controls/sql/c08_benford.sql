-- C08 Ley de Benford sobre los montos adjudicados: prueba agregada, nunca una alerta individual.
-- Columnas de salida (controles agregados): scope_type, scope_id, n, mad, mad_null, chi2, conformity,
--                                            flag, evidence
-- mad_null = MAD esperada si los montos siguieran exactamente a Benford, para una muestra de tamaño n:
--            (1/9) * sum_d sqrt(2 p_d (1 - p_d) / (pi n))
-- flag     = MAD > excess_ratio * mad_null, es decir, más de lo que explica el azar del muestreo
--            (excess_ratio 2.0 ~ percentil 99.9 bajo azar puro, por simulación; ver decisiones D20)
WITH digits AS (
    SELECT buyer_id, CAST(left(CAST(CAST(floor(amount) AS BIGINT) AS VARCHAR), 1) AS INTEGER) AS d
    FROM f_award WHERE amount >= $min_amount
),
scoped AS (
    SELECT 'all' AS scope_type, 'all' AS scope_id, d FROM digits
    UNION ALL
    SELECT 'buyer', buyer_id, d FROM digits
),
sizes AS (SELECT scope_type, scope_id, count(*) AS n FROM scoped GROUP BY ALL),
grid AS (
    SELECT s.scope_type, s.scope_id, s.n, g.d, log10(1 + 1.0 / g.d) AS expected
    FROM sizes s CROSS JOIN range(1, 10) g(d)
    WHERE s.n >= $min_n
),
freq AS (
    SELECT g.*, coalesce(c.k, 0) AS observed_n, coalesce(c.k, 0) / g.n AS observed
    FROM grid g
    LEFT JOIN (SELECT scope_type, scope_id, d, count(*) AS k FROM scoped GROUP BY ALL) c
           USING (scope_type, scope_id, d)
)
SELECT scope_type, scope_id, any_value(n) AS n,
       avg(abs(observed - expected)) AS mad,
       avg(sqrt(2 * expected * (1 - expected) / (pi() * n))) AS mad_null,
       sum(power(observed_n - n * expected, 2) / (n * expected)) AS chi2,
       CASE WHEN avg(abs(observed - expected)) <= $mad_close THEN 'conformidad cercana'
            WHEN avg(abs(observed - expected)) <= $mad_acceptable THEN 'conformidad aceptable'
            WHEN avg(abs(observed - expected)) <= $mad_marginal THEN 'conformidad marginal'
            ELSE 'no conformidad' END AS conformity,
       avg(abs(observed - expected)) > $excess_ratio * avg(sqrt(2 * expected * (1 - expected) / (pi() * n)))
           AS flag,
       to_json(list(struct_pack(digit := d, observed := round(observed, 4),
                                expected := round(expected, 4)) ORDER BY d))::VARCHAR AS evidence
FROM freq
GROUP BY scope_type, scope_id
