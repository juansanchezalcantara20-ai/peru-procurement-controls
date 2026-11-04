"""Phase 4 - validating the controls themselves.

Without a known truth there is no real precision. Two complementary checks:

1. **Injected patterns (synthetic data).** The generator records every injected risk pattern and
   data defect. For each control we measure recall (injected cases it catches) and how many of
   its alerts fall on background processes that were generated with no risk intent - by
   construction, those are false positives that mirror legitimate causes.
2. **Case review.** A small stratified sample of alerts is reviewed one by one, *blind* to the
   ground truth, with the context a reviewer would pull from the case file. The verdicts live in
   ``docs/validation/review_judgments.yaml``; the reveal against the ground truth is computed
   here. On real data the same worksheet and protocol apply, without the reveal.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import Config, load_yaml

PATTERN_OF = {
    "C01": "split_purchase", "C02": "single_bid", "C03": "short_submission_period",
    "C04": "supplier_concentration", "C05": "repeated_winner", "C06": "amendment_increase",
    "C07": "price_outlier", "C09": "award_signature_delay",
}
DQ_CHECK_OF = {
    "duplicate_ocid": "DQ01", "missing_buyer_id": "DQ02", "negative_award_amount": "DQ04",
    "absurd_award_amount": "DQ05", "non_pen_currency": "DQ06", "tender_end_before_start": "DQ07",
    "contract_signed_before_award": "DQ09",
}


def load_truth(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> bool:
    gt, dq = raw_dir / "ground_truth.csv", raw_dir / "dq_ground_truth.csv"
    if not gt.exists():
        return False
    for table, path in (("gt", gt), ("dq_gt", dq)):
        con.execute(f"CREATE OR REPLACE TABLE {table} AS "
                    f"SELECT * FROM read_csv('{path}', header=true, all_varchar=true)")
    return True


def control_metrics(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for cid, pattern in PATTERN_OF.items():
        r = con.execute("""
            WITH a AS (SELECT DISTINCT ocid FROM alerts WHERE control_id = $c),
                 t AS (SELECT DISTINCT ocid FROM gt WHERE pattern = $p
                       AND ocid IN (SELECT ocid FROM f_process)),
                 anyp AS (SELECT DISTINCT ocid FROM gt)
            SELECT (SELECT count(*) FROM t),
                   (SELECT count(*) FROM t WHERE ocid IN (SELECT ocid FROM a)),
                   (SELECT count(*) FROM a),
                   (SELECT count(*) FROM a WHERE ocid IN (SELECT ocid FROM t)),
                   (SELECT count(*) FROM a WHERE ocid IN (SELECT ocid FROM anyp)
                                             AND ocid NOT IN (SELECT ocid FROM t)),
                   (SELECT count(*) FROM a WHERE ocid NOT IN (SELECT ocid FROM anyp)),
                   (SELECT count(*) FROM f_process WHERE ocid NOT IN (SELECT ocid FROM anyp))
        """, {"c": cid, "p": pattern}).fetchone()
        injected, detected, alerts, on_target, on_other, background, bg_pop = r
        rows.append({
            "control_id": cid, "injected_pattern": pattern, "injected": injected,
            "detected": detected, "recall": round(detected / injected, 3) if injected else None,
            "alerts": alerts, "on_target_pattern": on_target,
            "on_other_injected_pattern": on_other, "on_background": background,
            "precision_vs_target": round(on_target / alerts, 3) if alerts else None,
            "background_fp_share": round(background / alerts, 3) if alerts else None,
            "background_alert_rate_pct": round(100 * background / bg_pop, 2) if bg_pop else None,
        })
    return pd.DataFrame(rows)


def priority_metrics(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Does the composite score triage? Share of flagged processes carrying an injected
    process-level pattern, by review priority (the entity-wide Benford pattern is left out)."""
    return con.execute("""
        WITH g AS (SELECT DISTINCT ocid FROM gt WHERE pattern <> 'benford_fabricated_amounts')
        SELECT priority, count(*) AS processes,
               count(*) FILTER (WHERE ocid IN (SELECT ocid FROM g)) AS with_injected_pattern,
               round(100.0 * count(*) FILTER (WHERE ocid IN (SELECT ocid FROM g)) / count(*), 1)
                   AS pct_injected
        FROM risk_scores GROUP BY 1 ORDER BY 1
    """).df()


def benford_metrics(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        WITH inj AS (SELECT DISTINCT p.buyer_id FROM gt JOIN f_process p USING (ocid)
                     WHERE pattern = 'benford_fabricated_amounts')
        SELECT CASE WHEN scope_type = 'all' THEN 'all awards'
                    WHEN scope_id IN (SELECT buyer_id FROM inj) THEN 'injected entity'
                    ELSE 'other entities' END AS scope,
               count(*) AS scopes_tested,
               count(*) FILTER (WHERE conformity = 'no conformidad') AS nigrini_nonconformity,
               count(*) FILTER (WHERE flag) AS flagged_beyond_noise,
               round(avg(mad), 4) AS mean_mad, round(avg(mad_null), 4) AS mean_mad_null
        FROM aggregate_tests WHERE control_id = 'C08'
        GROUP BY 1 ORDER BY 1
    """).df()


def dq_metrics(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for defect, check in DQ_CHECK_OF.items():
        injected, found = con.execute("""
            SELECT count(DISTINCT g.ocid),
                   count(DISTINCT g.ocid) FILTER (WHERE g.ocid IN (
                       SELECT ocid FROM dq_issues WHERE check_id = $c))
            FROM dq_gt g WHERE g.defect = $d
        """, {"c": check, "d": defect}).fetchone()
        total = con.execute("SELECT count(DISTINCT ocid) FROM dq_issues WHERE check_id = $c",
                            {"c": check}).fetchone()[0]
        rows.append({"defect": defect, "check_id": check, "injected": injected, "detected": found,
                     "flagged_total": total})
    return pd.DataFrame(rows)


# -- case review ---------------------------------------------------------------------------------
def review_sample(con: duckdb.DuckDBPyConnection, per_control: int, extra_top: int,
                  seed: int) -> pd.DataFrame:
    """Stratified sample: `per_control` alerts per process control + the top-scored processes."""
    con.execute(f"SELECT setseed({(seed % 1000) / 1000})")
    sample = con.execute(f"""
        WITH ranked AS (
            SELECT a.*, row_number() OVER (PARTITION BY control_id ORDER BY hash(ocid || '{seed}')) AS rk
            FROM alerts a)
        SELECT control_id, ocid FROM ranked WHERE rk <= {per_control}
        UNION
        SELECT a.control_id, a.ocid FROM (
            SELECT ocid FROM risk_scores ORDER BY score DESC, ocid LIMIT {extra_top}) t
        JOIN (SELECT control_id, ocid,
                     row_number() OVER (PARTITION BY ocid ORDER BY weight * severity DESC, control_id) r
              FROM alerts) a ON a.ocid = t.ocid AND a.r = 1
    """).df()
    return sample.sort_values(["control_id", "ocid"]).reset_index(drop=True)


def review_context(con: duckdb.DuckDBPyConnection, sample: pd.DataFrame) -> pd.DataFrame:
    """Context a reviewer would pull from the case file. No ground truth here."""
    con.register("_s", sample)
    df = con.execute("""
        WITH single_rate AS (
            SELECT buyer_id, method_details, avg(CASE WHEN n_tenderers = 1 THEN 1.0 ELSE 0 END) AS r,
                   count(*) AS n
            FROM f_process WHERE is_competitive GROUP BY ALL),
        global_single AS (
            SELECT method_details, avg(CASE WHEN n_tenderers = 1 THEN 1.0 ELSE 0 END) AS r
            FROM f_process WHERE is_competitive GROUP BY ALL),
        supplier_minor AS (
            SELECT buyer_id, supplier_id, year, count(*) AS n_minor
            FROM f_award WHERE procurement_method = 'direct' GROUP BY ALL),
        buyer_price AS (   -- does the whole entity price high? (median ratio to class median)
            SELECT i.buyer_id, median(i.unit_amount / s.med) AS buyer_price_ratio
            FROM f_item i JOIN (SELECT classification_id, median(unit_amount) AS med
                                FROM f_item GROUP BY 1) s USING (classification_id)
            GROUP BY 1),
        scores AS (SELECT ocid, score, priority, controls FROM risk_scores)
        SELECT s.control_id, s.ocid, a.alert_id, a.severity, a.evidence,
               p.method_details, p.segment, p.year, c.score, c.priority, c.controls,
               round(sr.r, 3) AS entity_single_bid_rate, sr.n AS entity_competitive_n,
               round(gs.r, 3) AS global_single_bid_rate,
               sm.n_minor AS supplier_minor_purchases_at_entity,
               round(bp.buyer_price_ratio, 2) AS entity_median_price_ratio
        FROM _s s
        JOIN alerts a ON a.control_id = s.control_id AND a.ocid = s.ocid
        JOIN f_process p ON p.ocid = s.ocid
        LEFT JOIN scores c ON c.ocid = s.ocid
        LEFT JOIN single_rate sr ON sr.buyer_id = p.buyer_id AND sr.method_details = p.method_details
        LEFT JOIN global_single gs ON gs.method_details = p.method_details
        LEFT JOIN supplier_minor sm ON sm.buyer_id = a.buyer_id AND sm.supplier_id = a.supplier_id
                                   AND sm.year = a.year
        LEFT JOIN buyer_price bp ON bp.buyer_id = p.buyer_id
        QUALIFY row_number() OVER (PARTITION BY s.control_id, s.ocid ORDER BY a.severity DESC) = 1
        ORDER BY s.control_id, s.ocid
    """).df()
    con.unregister("_s")
    df.insert(0, "case", [f"R{k:02d}" for k in range(1, len(df) + 1)])
    return df


# Some injections mechanically produce what another control measures:
# * the Benford injection rewrites every amount of one entity (bids, awards, unit prices), so it
#   can trigger amount-based controls, but not date, bidder-count or amendment-ratio controls;
# * forcing one supplier to win most of a cell (concentration) also makes it a repeated winner,
#   and vice versa.
# A case counts as "truly positive" for a control when it carries that control's own pattern or
# an injected pattern that mechanically affects what the control measures.
AFFECTS = {
    "benford_fabricated_amounts": {"C01", "C04", "C07"},
    "supplier_concentration": {"C05"},
    "repeated_winner": {"C04"},
}


def reveal(con: duckdb.DuckDBPyConnection, ctx: pd.DataFrame) -> pd.DataFrame:
    truth = con.execute("SELECT ocid, list(DISTINCT pattern) AS p FROM gt GROUP BY 1").df()
    m = dict(zip(truth.ocid, truth.p, strict=True))
    labels, positive = [], []
    for cid, ocid in zip(ctx.control_id, ctx.ocid, strict=True):
        pats = sorted(m.get(ocid, []))
        labels.append("+".join(pats) if pats else "background (no injected pattern)")
        positive.append(any(p == PATTERN_OF.get(cid) or cid in AFFECTS.get(p, set()) for p in pats))
    return pd.DataFrame({"ground_truth": labels, "truly_positive": positive}, index=ctx.index)


# -- pipeline step -------------------------------------------------------------------------------
def run(cfg: Config, con: duckdb.DuckDBPyConnection, meta: dict) -> dict:
    out = cfg.path("outputs") / "validation"
    private = cfg.path("outputs") / "private"
    out.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    vcfg = cfg.settings["validation"]
    synthetic = meta.get("source") == "synthetic" and load_truth(
        con, cfg.path("raw_dir") / "synthetic")

    sample = review_sample(con, per_control=2, extra_top=max(0, int(vcfg["review_sample_size"]) - 16),
                           seed=int(vcfg["review_seed"]))
    ctx = review_context(con, sample)
    ctx.to_csv(private / "review_worksheet.csv", index=False)  # git-ignored, alert-level

    result: dict = {"review_cases": int(len(ctx))}
    if synthetic:
        metrics = control_metrics(con)
        benford = benford_metrics(con)
        priority = priority_metrics(con)
        priority.to_csv(out / "priority_metrics.csv", index=False)
        dq = dq_metrics(con)
        metrics.to_csv(out / "control_metrics.csv", index=False)
        benford.to_csv(out / "benford_validation.csv", index=False)
        dq.to_csv(out / "dq_validation.csv", index=False)
        ctx = ctx.join(reveal(con, ctx))
        result.update(mean_recall=round(float(metrics.recall.mean()), 3),
                      dq_detected=int(dq.detected.sum()), dq_injected=int(dq.injected.sum()))
    else:
        metrics = benford = dq = priority = None

    if synthetic:
        # The blind review only exists for the simulated data (it needs the reveal). On real data
        # the worksheet above stays private and the published review keeps the simulated one.
        judgments_path = cfg.path("docs") / "validation" / "review_judgments.yaml"
        judgments = load_yaml(judgments_path) if judgments_path.exists() else {"cases": []}
        review = merge_judgments(ctx, judgments)
        review_public = review.drop(columns=["ocid", "alert_id", "evidence"], errors="ignore")
        review_public.to_csv(out / "case_review.csv", index=False)
        result["review_judged"] = int(review["verdict"].notna().sum())
    return result


def merge_judgments(ctx: pd.DataFrame, judgments: dict) -> pd.DataFrame:
    rows = {(j["control_id"], j["ocid"]): j for j in judgments.get("cases", [])}
    ctx = ctx.copy()
    found = [rows.get((c, o), {}) for c, o in zip(ctx.control_id, ctx.ocid, strict=True)]
    ctx["verdict"] = [j.get("verdict") for j in found]
    ctx["reason"] = [j.get("reason") for j in found]
    ctx["blind"] = [j.get("blind", True) for j in found]
    return ctx
