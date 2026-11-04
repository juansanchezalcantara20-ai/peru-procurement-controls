"""Signal engine: runs every control straight from ``controls/catalog.yaml``.

The catalog is the only place where a control is defined. For each entry the engine

1. resolves its parameters (literal ``value`` or ``ref`` into ``config/thresholds.yaml``);
2. runs the SQL file named in ``sql`` with those parameters bound as ``$name``;
3. appends the rows to ``alerts`` (process controls) or ``aggregate_tests`` (population tests).

It then computes the composite risk score per process with the catalog's ``risk_score`` method.

Signals, never accusations: an alert means "this deserves a review".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .config import Config, load_yaml

REQUIRED_FIELDS = [
    "id", "name", "ocp_reference", "control_objective", "risk_mitigated", "rule", "parameters",
    "threshold", "frequency", "owner_role", "evidence", "expected_false_positives", "weight",
    "weight_rationale", "level", "sql",
]
PROCESS_COLUMNS = ["ocid", "buyer_id", "supplier_id", "year", "severity", "scope_key", "evidence"]
AGGREGATE_COLUMNS = ["scope_type", "scope_id", "n", "mad", "mad_null", "chi2", "conformity", "flag",
                     "evidence"]
_PARAM = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class Control:
    spec: dict[str, Any]
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.spec["id"]

    @property
    def level(self) -> str:
        return self.spec["level"]

    @property
    def weight(self) -> float:
        return float(self.spec["weight"])


def load_catalog(cfg: Config, path: Path | None = None) -> dict[str, Any]:
    catalog = load_yaml(path or cfg.root / "controls" / "catalog.yaml")
    validate_catalog(catalog, cfg)
    return catalog


def validate_catalog(catalog: dict[str, Any], cfg: Config) -> None:
    ids = set()
    for spec in catalog["controls"]:
        missing = [f for f in REQUIRED_FIELDS if f not in spec]
        if missing:
            raise ValueError(f"control {spec.get('id')} misses fields {missing}")
        if spec["id"] in ids:
            raise ValueError(f"duplicate control id {spec['id']}")
        ids.add(spec["id"])
        if spec["level"] not in ("process", "aggregate"):
            raise ValueError(f"{spec['id']}: level must be process or aggregate")
        if not 0 <= float(spec["weight"]) <= 1:
            raise ValueError(f"{spec['id']}: weight must be in [0, 1]")
        if not (cfg.root / spec["sql"]).exists():
            raise ValueError(f"{spec['id']}: SQL file {spec['sql']} not found")
        for name, p in spec["parameters"].items():
            if "value" not in p and "ref" not in p:
                raise ValueError(f"{spec['id']}.{name}: needs value or ref")


def resolve_params(spec: dict[str, Any], cfg: Config) -> dict[str, Any]:
    out = {}
    for name, p in spec["parameters"].items():
        out[name] = cfg.resolve(p["ref"]) if "ref" in p else p["value"]
    return out


def build_reference_tables(con: duckdb.DuckDBPyConnection, cfg: Config,
                           catalog: dict[str, Any]) -> None:
    """Reference tables derived from thresholds.yaml (year-dependent or per-method values)."""
    c01 = next((c for c in catalog["controls"] if c["id"] == "C01"), None)
    limit_uit = (resolve_params(c01, cfg)["limit_uit"] if c01
                 else cfg.thresholds["minor_purchase_limit_uit"]["value"])
    uit = cfg.uit_by_year()
    rows = [(y, v, v * float(limit_uit)) for y, v in sorted(uit.items())]
    con.execute("CREATE OR REPLACE TABLE ref_minor_limit (year INTEGER, uit DOUBLE, limit_pen DOUBLE)")
    con.executemany("INSERT INTO ref_minor_limit VALUES (?, ?, ?)", rows)
    by_method = cfg.thresholds["min_submission_days"]["by_method"]
    con.execute("CREATE OR REPLACE TABLE ref_min_submission_days (method_details VARCHAR, min_days INTEGER)")
    con.executemany("INSERT INTO ref_min_submission_days VALUES (?, ?)",
                    [(m, int(v["value"])) for m, v in by_method.items()])


def render(cfg: Config, control: Control) -> tuple[str, dict[str, Any]]:
    sql = (cfg.root / control.spec["sql"]).read_text(encoding="utf-8")
    used = set(_PARAM.findall(sql))
    missing = used - set(control.params)
    if missing:
        raise ValueError(f"{control.id}: SQL uses undefined parameters {sorted(missing)}")
    binds = {k: v for k, v in control.params.items() if k in used}
    return sql, binds


def run_control(con: duckdb.DuckDBPyConnection, cfg: Config, control: Control) -> pd.DataFrame:
    sql, binds = render(cfg, control)
    df = con.execute(sql, binds).df()
    expected = PROCESS_COLUMNS if control.level == "process" else AGGREGATE_COLUMNS
    if list(df.columns) != expected:
        raise ValueError(f"{control.id}: output columns {list(df.columns)} != {expected}")
    if control.level == "process":
        # rounded: parallel float sums are not bit-reproducible, published results must be
        df["severity"] = df["severity"].astype(float).clip(0.0, 1.0).round(4)
    return df


def run_all(con: duckdb.DuckDBPyConnection, cfg: Config,
            catalog: dict[str, Any] | None = None) -> dict[str, pd.DataFrame]:
    catalog = catalog or load_catalog(cfg)
    build_reference_tables(con, cfg, catalog)
    alerts, aggregates = [], []
    for spec in catalog["controls"]:
        control = Control(spec, resolve_params(spec, cfg))
        df = run_control(con, cfg, control)
        df.insert(0, "control_id", control.id)
        if control.level == "process":
            df["weight"] = control.weight
            alerts.append(df)
        else:
            aggregates.append(df)
    alerts_df = (pd.concat(alerts, ignore_index=True) if alerts
                 else pd.DataFrame(columns=["control_id", *PROCESS_COLUMNS, "weight"]))
    alerts_df.insert(0, "alert_id", [f"A{k:06d}" for k in range(1, len(alerts_df) + 1)])
    agg_df = (pd.concat(aggregates, ignore_index=True) if aggregates
              else pd.DataFrame(columns=["control_id", *AGGREGATE_COLUMNS]))

    con.register("_alerts", alerts_df)
    con.execute("CREATE OR REPLACE TABLE alerts AS SELECT * FROM _alerts")
    con.unregister("_alerts")
    con.register("_agg", agg_df)
    con.execute("CREATE OR REPLACE TABLE aggregate_tests AS SELECT * FROM _agg")
    con.unregister("_agg")
    scores = compute_risk_scores(con, catalog)
    return {"alerts": alerts_df, "aggregate_tests": agg_df, "risk_scores": scores}


def compute_risk_scores(con: duckdb.DuckDBPyConnection, catalog: dict[str, Any]) -> pd.DataFrame:
    """Noisy-OR combination: score = 100 * (1 - prod(1 - w * s)), one term per control."""
    pri = catalog["risk_score"]["review_priority"]
    p1 = float(re.search(r"[\d.]+", pri["P1"]).group())
    p2 = float(re.search(r"[\d.]+", pri["P2"]).group())
    con.execute("""
        CREATE OR REPLACE TABLE risk_scores AS
        WITH per_control AS (   -- one term per control and process: its strongest alert
            SELECT ocid, control_id, max(weight * severity) AS ws
            FROM alerts GROUP BY ocid, control_id
        )
        SELECT pc.ocid, p.buyer_id, p.year, p.segment, p.method_details,
               count(*) AS n_controls,
               string_agg(pc.control_id, ',' ORDER BY pc.control_id) AS controls,
               round(100 * (1 - exp(sum(ln(greatest(1e-12, 1 - pc.ws))))), 1) AS score
        FROM per_control pc
        JOIN f_process p USING (ocid)
        GROUP BY ALL
    """)
    con.execute(f"""
        ALTER TABLE risk_scores ADD COLUMN priority VARCHAR;
        UPDATE risk_scores SET priority = CASE WHEN score >= {p1} THEN 'P1'
                                              WHEN score >= {p2} THEN 'P2' ELSE 'P3' END;
    """)
    return con.execute("SELECT * FROM risk_scores").df()


# -- pipeline step -----------------------------------------------------------------------------
def run(cfg: Config, con: duckdb.DuckDBPyConnection, meta: dict) -> dict:
    catalog = load_catalog(cfg)
    res = run_all(con, cfg, catalog)
    out = cfg.path("outputs") / "signals"
    out.mkdir(parents=True, exist_ok=True)
    write_aggregates(con, out)
    alerts = res["alerts"]
    return {
        "alerts": int(len(alerts)),
        "processes_with_alerts": int(alerts["ocid"].nunique()) if len(alerts) else 0,
        "controls_run": len(catalog["controls"]),
        "by_control": {k: int(v) for k, v in alerts.groupby("control_id").size().items()},
    }


def write_aggregates(con: duckdb.DuckDBPyConnection, out: Path) -> None:
    """Versioned outputs are aggregated only: no OCIDs, suppliers or individual entities."""
    queries = {
        "alerts_by_control_year": """
            SELECT a.control_id, a.year, count(*) AS alerts, count(DISTINCT a.ocid) AS processes,
                   round(avg(a.severity), 3) AS mean_severity
            FROM alerts a GROUP BY ALL ORDER BY ALL""",
        "alerts_by_control_month": """
            SELECT a.control_id, strftime(p.process_date, '%Y-%m') AS month, count(*) AS alerts
            FROM alerts a JOIN f_process p USING (ocid) GROUP BY ALL ORDER BY ALL""",
        "processes_by_month": """
            SELECT strftime(process_date, '%Y-%m') AS month, count(*) AS processes,
                   count(*) FILTER (WHERE is_competitive) AS competitive
            FROM f_process GROUP BY ALL ORDER BY ALL""",
        "alert_rate_by_method": """
            SELECT p.method_details, count(DISTINCT p.ocid) AS processes,
                   count(DISTINCT a.ocid) AS processes_with_alert,
                   round(100.0 * count(DISTINCT a.ocid) / count(DISTINCT p.ocid), 2) AS pct
            FROM f_process p LEFT JOIN alerts a USING (ocid) GROUP BY ALL ORDER BY processes DESC, 1""",
        "alert_rate_by_segment": """
            SELECT p.segment, count(DISTINCT p.ocid) AS processes,
                   count(DISTINCT a.ocid) AS processes_with_alert,
                   round(100.0 * count(DISTINCT a.ocid) / count(DISTINCT p.ocid), 2) AS pct
            FROM f_process p LEFT JOIN alerts a USING (ocid) GROUP BY ALL ORDER BY ALL""",
        "risk_score_distribution": """
            SELECT priority, n_controls, count(*) AS processes, round(avg(score), 1) AS mean_score
            FROM risk_scores GROUP BY ALL ORDER BY ALL""",
        "control_cooccurrence": """
            SELECT a.control_id AS control_a, b.control_id AS control_b,
                   count(DISTINCT a.ocid) AS processes
            FROM (SELECT DISTINCT ocid, control_id FROM alerts) a
            JOIN (SELECT DISTINCT ocid, control_id FROM alerts) b
              ON a.ocid = b.ocid AND a.control_id < b.control_id
            GROUP BY ALL ORDER BY ALL""",
        "entity_alert_concentration": """
            -- how alerts spread across entities, without naming any entity
            WITH e AS (SELECT p.buyer_id, count(DISTINCT p.ocid) AS processes,
                              count(DISTINCT a.ocid) AS flagged
                       FROM f_process p LEFT JOIN alerts a USING (ocid) GROUP BY 1)
            SELECT CASE WHEN 100.0 * flagged / processes < 5 THEN 'a) <5%'
                        WHEN 100.0 * flagged / processes < 10 THEN 'b) 5-10%'
                        WHEN 100.0 * flagged / processes < 20 THEN 'c) 10-20%'
                        ELSE 'd) >=20%' END AS share_of_processes_flagged,
                   count(*) AS entities
            FROM e GROUP BY 1 ORDER BY 1""",
        "benford_summary": """
            SELECT scope_type, conformity, flag AS beyond_sampling_noise, count(*) AS scopes,
                   round(avg(mad), 4) AS mean_mad, round(avg(mad_null), 4) AS mean_mad_null,
                   sum(n) AS amounts
            FROM aggregate_tests WHERE control_id = 'C08' GROUP BY ALL ORDER BY ALL""",
        "benford_overall_digits": """
            SELECT d.digit, d.observed, d.expected FROM (
                SELECT unnest(from_json(evidence,
                    '[{"digit":"INTEGER","observed":"DOUBLE","expected":"DOUBLE"}]')) AS d
                FROM aggregate_tests WHERE control_id = 'C08' AND scope_type = 'all')""",
    }
    for name, sql in queries.items():
        con.execute(sql).df().to_csv(out / f"{name}.csv", index=False)
    meta = {"note": "Aggregated outputs only. Alert-level detail stays in the local DuckDB warehouse."}
    (out / "README.json").write_text(json.dumps(meta, indent=2) + "\n")
