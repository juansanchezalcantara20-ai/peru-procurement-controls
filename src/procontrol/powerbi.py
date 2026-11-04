"""Export a star schema for Power BI Desktop (see powerbi/MODEL.md).

Files land in ``outputs/powerbi/`` which is git-ignored: the facts are alert-level and must stay
internal (rule: no rankings; entities only in aggregated views on anything published).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .engine import load_catalog
from .labels import entity_type

TABLES = {
    "dim_date": """
        SELECT DISTINCT CAST(process_date AS DATE) AS date, year(process_date) AS year,
               month(process_date) AS month, strftime(process_date, '%Y-%m') AS year_month
        FROM f_process WHERE process_date IS NOT NULL""",
    "dim_supplier": """
        SELECT party_id AS supplier_key, bool_or(is_natural_person) AS is_natural_person
        FROM parties WHERE roles LIKE '%tenderer%' OR roles LIKE '%supplier%' GROUP BY 1""",
    "dim_method": """
        SELECT DISTINCT method_details AS method, procurement_method, is_competitive FROM f_process""",
    "dim_segment": "SELECT DISTINCT segment FROM f_process",
    "fact_process": """
        SELECT p.ocid, p.buyer_id AS entity_key, CAST(p.process_date AS DATE) AS date,
               p.method_details AS method, p.segment, p.is_competitive, p.n_tenderers,
               a.supplier_id AS supplier_key, a.amount AS award_amount
        FROM f_process p
        LEFT JOIN (SELECT ocid, arg_min(supplier_id, award_id) AS supplier_id, sum(amount) AS amount
                   FROM f_award GROUP BY 1) a USING (ocid)""",
    "fact_contract": """
        SELECT ocid, contract_id, original_amount, final_amount, n_amendments,
               date_diff('day', CAST(award_date AS DATE), CAST(date_signed AS DATE)) AS days_award_to_signature
        FROM f_contract""",
    "fact_alert": """
        SELECT alert_id, control_id, ocid, severity, weight, weight * severity AS weighted_severity,
               scope_key FROM alerts""",
    "fact_risk_score": "SELECT ocid, score, priority, n_controls, controls FROM risk_scores",
    "fact_benford": """
        SELECT scope_type, scope_id, n, mad, mad_null, chi2, conformity, flag FROM aggregate_tests""",
    "fact_dq_issue": "SELECT check_id, check_name, severity, ocid, record_id FROM dq_issues",
}


def export(cfg, con: duckdb.DuckDBPyConnection) -> Path:
    out = cfg.path("outputs") / "powerbi"
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in TABLES.items():
        con.execute(sql).df().to_csv(out / f"{name}.csv", index=False)
    ent = con.execute("""SELECT p.buyer_id AS entity_key, any_value(pr.buyer_name) AS name
                         FROM f_process p JOIN processes pr USING (ocid) GROUP BY 1""").df()
    ent["entity_type"] = ent.pop("name").map(entity_type)
    ent.to_csv(out / "dim_entity.csv", index=False)
    catalog = load_catalog(cfg)
    pd.DataFrame([{
        "control_id": c["id"], "name": c["name"], "level": c["level"], "weight": c["weight"],
        "frequency": c["frequency"], "owner_role": c["owner_role"],
        "expected_fp_band": c["expected_false_positives"]["rate_band"], "threshold": c["threshold"],
    } for c in catalog["controls"]]).to_csv(out / "dim_control.csv", index=False)
    return out
