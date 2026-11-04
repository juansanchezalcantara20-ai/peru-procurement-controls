"""Data-quality checks and the clean analytical layer.

Before controlling the data, control its quality. Every check writes the offending records to
``dq_issues``; the clean views (``f_*``) then exclude what would distort a control:

* critical checks remove the record (or the affected field) from the analytical layer;
* warning checks are reported but the record stays.

The report is written to ``outputs/quality/`` and rendered into the site.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

ABSURD_RATIO = 100        # award > 100x its own tender estimate
ABSURD_CAP_PEN = 1e10     # or above S/ 10 billion for a single award
MIN_DATE, MAX_DATE = "2000-01-01", "2030-12-31"


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    severity: str  # critical | warning
    effect: str
    sql: str


KEPT = "(SELECT release_key FROM dq_kept_releases)"

CHECKS: list[Check] = [
    Check("DQ01", "Proceso publicado más de una vez", "warning",
          "Se conserva solo la publicación más reciente de cada proceso.",
          """SELECT ocid, CAST(release_key AS VARCHAR) AS record_id,
                    'release ' || release_id AS detail
             FROM releases WHERE release_key NOT IN """ + KEPT),
    Check("DQ02", "Proceso sin entidad compradora identificada", "critical",
          "El proceso queda fuera de todas las señales (no hay a quién atribuirlo).",
          f"""SELECT ocid, ocid, coalesce(buyer_name, '(no name)') FROM processes
              WHERE release_key IN {KEPT} AND (buyer_id IS NULL OR buyer_id = '')"""),
    Check("DQ03", "Adjudicación sin proveedor", "critical",
          "La adjudicación queda fuera de las señales que miran al proveedor.",
          f"""SELECT ocid, award_id, 'no supplier' FROM awards
              WHERE release_key IN {KEPT} AND supplier_id IS NULL"""),
    Check("DQ04", "Monto adjudicado negativo o cero", "critical",
          "Se descarta el monto; el proceso sigue en las señales que no usan montos.",
          f"""SELECT ocid, award_id, CAST(amount AS VARCHAR) FROM awards
              WHERE release_key IN {KEPT} AND amount <= 0"""),
    Check("DQ05", "Monto adjudicado absurdo", "critical",
          f"Se descarta el monto (más de {ABSURD_RATIO} veces el valor estimado "
          f"o más de S/ {ABSURD_CAP_PEN:,.0f}).",
          f"""SELECT a.ocid, a.award_id, CAST(a.amount AS VARCHAR) FROM awards a
              JOIN processes p USING (release_key)
              WHERE a.release_key IN {KEPT} AND a.amount > 0 AND (a.amount > {ABSURD_CAP_PEN}
                 OR (p.tender_amount > 0 AND a.amount > {ABSURD_RATIO} * p.tender_amount))"""),
    Check("DQ06", "Adjudicación en una moneda distinta al sol", "critical",
          "Se descarta el monto (no se intenta convertir la moneda).",
          f"""SELECT ocid, award_id, currency FROM awards
              WHERE release_key IN {KEPT} AND currency IS NOT NULL AND currency <> 'PEN'"""),
    Check("DQ07", "Plazo de ofertas que termina antes de empezar", "critical",
          "Se descartan las fechas del plazo (el proceso no entra a la señal de plazo corto).",
          f"""SELECT ocid, ocid, CAST(tender_start AS VARCHAR) || ' > ' || CAST(tender_end AS VARCHAR)
              FROM processes WHERE release_key IN {KEPT} AND tender_end < tender_start"""),
    Check("DQ08", "Adjudicación fechada antes del cierre de ofertas", "warning",
          "Solo se informa.",
          f"""SELECT a.ocid, a.award_id, CAST(a.award_date AS VARCHAR) FROM awards a
              JOIN processes p USING (release_key)
              WHERE a.release_key IN {KEPT} AND p.tender_end >= p.tender_start
                AND a.award_date < p.tender_end"""),
    Check("DQ09", "Contrato firmado antes de su adjudicación", "critical",
          "Se descarta la fecha de firma (el proceso no entra a la señal de demora en la firma).",
          f"""SELECT c.ocid, c.contract_id, CAST(c.date_signed AS VARCHAR) FROM contracts c
              JOIN awards a ON a.release_key = c.release_key AND a.award_id = c.award_id
              WHERE c.release_key IN {KEPT} AND c.date_signed < CAST(a.award_date AS DATE)"""),
    Check("DQ10", "Fecha fuera de un rango creíble", "warning",
          f"Solo se informa (rango de {MIN_DATE} a {MAX_DATE}).",
          f"""SELECT ocid, ocid, 'tender_start ' || CAST(tender_start AS VARCHAR) FROM processes
              WHERE release_key IN {KEPT} AND (tender_start < '{MIN_DATE}' OR tender_start > '{MAX_DATE}')
              UNION ALL
              SELECT ocid, contract_id, 'date_signed ' || CAST(date_signed AS VARCHAR) FROM contracts
              WHERE release_key IN {KEPT} AND (date_signed < '{MIN_DATE}' OR date_signed > '{MAX_DATE}')"""),
    Check("DQ11", "Identificador de adjudicación repetido en un proceso", "warning",
          "Solo se informa.",
          f"""SELECT ocid, award_id, CAST(count(DISTINCT supplier_id) AS VARCHAR) || ' suppliers'
              FROM awards WHERE release_key IN {KEPT}
              GROUP BY ocid, award_id HAVING count(*) > 1 AND count(DISTINCT supplier_id) = 1"""),
    Check("DQ12", "Mismo participante registrado con nombres distintos", "warning",
          "Solo se informa (las variantes de nombre son comunes en los registros).",
          f"""SELECT min(ocid), party_id, CAST(count(DISTINCT name) AS VARCHAR) || ' names'
              FROM parties WHERE release_key IN {KEPT}
              GROUP BY party_id HAVING count(DISTINCT name) > 1"""),
    Check("DQ13", "Artículo sin clasificación", "warning",
          "El artículo no entra a la señal de precios atípicos.",
          f"""SELECT ocid, item_id, 'no classification' FROM items
              WHERE release_key IN {KEPT} AND (classification_id IS NULL OR classification_id = '')"""),
    Check("DQ14", "Contrato que no corresponde a ninguna adjudicación", "warning",
          "Solo se informa.",
          f"""SELECT c.ocid, c.contract_id, coalesce(c.award_id, '(null)') FROM contracts c
              WHERE c.release_key IN {KEPT} AND NOT EXISTS (
                SELECT 1 FROM awards a WHERE a.release_key = c.release_key AND a.award_id = c.award_id)"""),
    Check("DQ15", "Número de postores distinto al de ofertas publicadas", "warning",
          "Solo se informa; se usa el número de postores distintos cuando está disponible.",
          f"""SELECT p.ocid, p.ocid, CAST(p.number_of_tenderers AS VARCHAR) || ' vs ' ||
                     CAST(count(DISTINCT b.supplier_id) AS VARCHAR)
              FROM processes p JOIN bids b USING (release_key)
              WHERE p.release_key IN {KEPT} AND p.number_of_tenderers IS NOT NULL
              GROUP BY p.ocid, p.number_of_tenderers
              HAVING count(DISTINCT b.supplier_id) <> p.number_of_tenderers"""),
]

COMPLETENESS = [
    ("processes", "buyer_id"), ("processes", "procurement_method"),
    ("processes", "method_details"), ("processes", "main_category"),
    ("processes", "tender_amount"), ("processes", "tender_start"), ("processes", "tender_end"),
    ("processes", "number_of_tenderers"), ("awards", "supplier_id"), ("awards", "amount"),
    ("awards", "award_date"), ("contracts", "date_signed"), ("contracts", "amount"),
    ("items", "classification_id"), ("items", "quantity"), ("items", "unit_amount"),
]


ANALYTICAL_LAYER = f"""
-- Clean analytical layer used by every control. Built after the DQ checks.
CREATE OR REPLACE VIEW f_process AS
SELECT p.ocid, p.buyer_id, p.procurement_method, p.method_details, p.main_category,
       p.tender_amount,
       CASE WHEN p.tender_end >= p.tender_start THEN p.tender_start END AS tender_start,
       CASE WHEN p.tender_end >= p.tender_start THEN p.tender_end END AS tender_end,
       coalesce(b.n_bidders, p.number_of_tenderers) AS n_tenderers,
       p.procurement_method IN ('open', 'selective') AS is_competitive,
       coalesce(seg.segment, 'unknown') AS segment,
       CAST(year(coalesce(p.date_published, p.tender_start, a.first_award)) AS INTEGER) AS year,
       coalesce(p.date_published, p.tender_start, a.first_award) AS process_date
FROM processes p
LEFT JOIN (SELECT release_key, count(DISTINCT supplier_id) AS n_bidders FROM bids
           WHERE supplier_id IS NOT NULL GROUP BY 1) b USING (release_key)
LEFT JOIN (SELECT release_key, min(award_date) AS first_award FROM awards GROUP BY 1) a
       USING (release_key)
LEFT JOIN (SELECT release_key, arg_max(left(classification_id, 2), quantity * unit_amount)
                  AS segment
           FROM items WHERE classification_id IS NOT NULL GROUP BY 1) seg USING (release_key)
WHERE p.release_key IN (SELECT release_key FROM dq_kept_releases)
  AND p.buyer_id IS NOT NULL AND p.buyer_id <> '';

CREATE OR REPLACE VIEW f_award AS
SELECT a.ocid, a.award_id, a.supplier_id, a.award_date, a.status,
       CASE WHEN a.amount > 0 AND coalesce(a.currency, 'PEN') = 'PEN'
             AND a.amount <= {ABSURD_CAP_PEN}
             AND NOT (p.tender_amount > 0 AND a.amount > {ABSURD_RATIO} * p.tender_amount)
            THEN a.amount END AS amount,
       f.buyer_id, f.segment, f.year, f.is_competitive, f.method_details, f.procurement_method
FROM awards a
JOIN processes p USING (release_key)
JOIN f_process f ON f.ocid = a.ocid
WHERE a.release_key IN (SELECT release_key FROM dq_kept_releases)
  AND a.supplier_id IS NOT NULL;

CREATE OR REPLACE VIEW f_item AS
SELECT i.ocid, i.item_id, i.classification_id, i.quantity, i.unit_amount, f.buyer_id,
       f.segment, f.year
FROM items i JOIN f_process f ON f.ocid = i.ocid
WHERE i.release_key IN (SELECT release_key FROM dq_kept_releases)
  AND i.classification_id IS NOT NULL AND i.classification_id <> ''
  AND i.unit_amount > 0 AND coalesce(i.currency, 'PEN') = 'PEN';

CREATE OR REPLACE VIEW f_bid AS
SELECT b.ocid, b.supplier_id, b.amount, f.buyer_id, f.year, f.is_competitive
FROM bids b JOIN f_process f ON f.ocid = b.ocid
WHERE b.release_key IN (SELECT release_key FROM dq_kept_releases)
  AND b.supplier_id IS NOT NULL;

CREATE OR REPLACE VIEW f_contract AS
SELECT c.ocid, c.contract_id, c.award_id, fa.supplier_id, fa.buyer_id, fa.year,
       fa.is_competitive, fa.method_details, fa.award_date,
       CASE WHEN c.date_signed >= CAST(fa.award_date AS DATE) THEN c.date_signed END AS date_signed,
       coalesce(fa.amount, CASE WHEN c.amount > 0 THEN c.amount END) AS original_amount,
       am.final_amount, am.n_amendments
FROM contracts c
JOIN f_award fa ON fa.ocid = c.ocid AND fa.award_id = c.award_id
LEFT JOIN (SELECT release_key, contract_id, count(*) AS n_amendments,
                  arg_max(amended_amount, amendment_date) AS final_amount
           FROM amendments GROUP BY 1, 2) am
       ON am.release_key = c.release_key AND am.contract_id = c.contract_id
WHERE c.release_key IN (SELECT release_key FROM dq_kept_releases);
"""


def build_kept_releases(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE dq_kept_releases AS
        SELECT release_key FROM (
            SELECT release_key, row_number() OVER (
                PARTITION BY ocid ORDER BY release_date DESC NULLS LAST, release_key DESC) AS rn
            FROM releases) WHERE rn = 1
    """)


def run_quality(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    build_kept_releases(con)
    con.execute("""CREATE OR REPLACE TABLE dq_issues (
        check_id VARCHAR, check_name VARCHAR, severity VARCHAR, ocid VARCHAR,
        record_id VARCHAR, detail VARCHAR)""")
    for chk in CHECKS:
        con.execute(
            f"INSERT INTO dq_issues SELECT ?, ?, ?, * FROM ({chk.sql})",
            [chk.id, chk.name, chk.severity],
        )
    con.execute(ANALYTICAL_LAYER)

    counts = con.execute(
        "SELECT check_id, count(*) AS n FROM dq_issues GROUP BY 1"
    ).df().set_index("check_id")["n"].to_dict()
    summary = pd.DataFrame(
        [
            {"check_id": c.id, "check": c.name, "severity": c.severity,
             "records": int(counts.get(c.id, 0)), "effect": c.effect}
            for c in CHECKS
        ]
    )

    comp_rows = []
    for table, col in COMPLETENESS:
        total, missing = con.execute(
            f"""SELECT count(*), count(*) FILTER (WHERE {col} IS NULL)
                FROM {table} WHERE release_key IN (SELECT release_key FROM dq_kept_releases)"""
        ).fetchone()
        comp_rows.append({"table": table, "field": col, "rows": total, "missing": missing,
                          "missing_pct": round(100 * missing / total, 2) if total else None})
    completeness = pd.DataFrame(comp_rows)

    volumes = con.execute("""
        SELECT 'releases (raw)' AS layer, count(*) AS n FROM releases
        UNION ALL SELECT 'processes kept (one per OCID)', count(*) FROM dq_kept_releases
        UNION ALL SELECT 'processes in analytical layer', count(*) FROM f_process
        UNION ALL SELECT 'awards in analytical layer', count(*) FROM f_award
        UNION ALL SELECT 'awards with usable amount', count(amount) FROM f_award
        UNION ALL SELECT 'contracts in analytical layer', count(*) FROM f_contract
    """).df()
    return {"summary": summary, "completeness": completeness, "volumes": volumes}


def _cell(v) -> str:
    if isinstance(v, list | tuple):
        return ", ".join(map(str, v))
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).replace("|", "/").replace("\n", " ")


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    return "\n".join(lines)


SEVERITY_ES = {"critical": "crítico", "warning": "menor"}


def write_quality_report(results: dict[str, pd.DataFrame], out_dir, docs_dir,
                         source_label: str) -> None:
    """CSV outputs plus the technical data-quality page (under Metodología)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in results.items():
        df.to_csv(out_dir / f"dq_{name}.csv", index=False)
    summary = results["summary"].copy()
    summary["severity"] = summary["severity"].map(SEVERITY_ES)
    summary = summary.rename(columns={"check_id": "código", "check": "revisión", "severity": "gravedad",
                                      "records": "registros", "effect": "qué se hace"})
    comp = results["completeness"].rename(columns={"table": "tabla", "field": "campo", "rows": "filas",
                                                   "missing": "vacíos", "missing_pct": "% vacíos"})
    vol = results["volumes"].rename(columns={"layer": "capa", "n": "cantidad"})
    vol["capa"] = vol["capa"].map(VOLUME_ES).fillna(vol["capa"])
    (docs_dir / "metodologia").mkdir(parents=True, exist_ok=True)
    (docs_dir / "metodologia" / "calidad.md").write_text(f"""# Calidad del dato: detalle técnico

**Fuente:** {source_label}

Cada revisión se ejecuta sobre las tablas aplanadas de OCDS (Open Contracting Data Standard, el
estándar internacional de datos abiertos de contrataciones). La columna «qué se hace» dice cómo
trata la capa analítica los registros encontrados. Las revisiones críticas sacan el registro, o
solo el campo dañado, de las vistas `f_*` que leen todas las señales; las menores solo se informan.

## Volúmenes a lo largo del proceso

{_md_table(vol)}

## Revisiones

{_md_table(summary)}

## Campos vacíos (última publicación de cada proceso)

Las fechas del plazo de ofertas están vacías, como es de esperar, en las compras menores y
directas, que no tienen convocatoria.

{_md_table(comp)}
""", encoding="utf-8")


VOLUME_ES = {
    "releases (raw)": "publicaciones (crudas)",
    "processes kept (one per OCID)": "procesos conservados (uno por OCID)",
    "processes in analytical layer": "procesos en la capa analítica",
    "awards in analytical layer": "adjudicaciones en la capa analítica",
    "awards with usable amount": "adjudicaciones con monto utilizable",
    "contracts in analytical layer": "contratos en la capa analítica",
}
