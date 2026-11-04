"""Phase 5 - the site: overview, one page per signal, trends, risk score. Aggregated views only.

Pages are generated into ``docs/`` from the warehouse and the catalog, so the site can never
drift from the controls that actually ran. Charts are static PNGs (matplotlib) with the data
behind each one published as a CSV next to it (table view for accessibility).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import Config  # noqa: E402
from .engine import load_catalog, resolve_params  # noqa: E402
from .quality import _md_table  # noqa: E402

DISCLAIMER = """!!! warning "Signals, never accusations"
    An alert means *"this deserves a review"*, not *"there is an irregularity"*. No supplier,
    official or person is ranked or named; public entities appear only in aggregated views.
"""

# reference palette (dataviz skill, light mode)
SERIES = "#2a78d6"
ACCENT = "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

SEGMENT_LABELS = {
    "14": "Paper", "15": "Fuels", "42": "Medical equipment", "43": "IT equipment",
    "44": "Office supplies", "50": "Food", "51": "Drugs", "72": "Construction works",
    "76": "Cleaning", "78": "Transport", "80": "Consulting", "81": "Engineering",
    "92": "Security",
}


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURFACE)


def _fig(width: float = 7.0, height: float = 3.2):
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def _threshold(ax, x: float, label: str) -> None:
    ax.axvline(x, color=ACCENT, linewidth=1.5, linestyle="--")
    ax.annotate(label, xy=(x, 1), xycoords=("data", "axes fraction"), xytext=(4, -12),
                textcoords="offset points", color=INK, fontsize=8)


def _hist(values: np.ndarray, bins, path: Path, csv: Path, title: str, xlabel: str,
          threshold: float | None = None, tlabel: str = "", ylabel: str = "count") -> None:
    counts, edges = np.histogram(values, bins=bins)
    pd.DataFrame({"bin_from": edges[:-1].round(4), "bin_to": edges[1:].round(4),
                  "count": counts}).to_csv(csv, index=False)
    fig, ax = _fig()
    widths = np.diff(edges)
    ax.bar(edges[:-1], counts, width=widths * 0.92, align="edge", color=SERIES)
    if threshold is not None:
        _threshold(ax, threshold, tlabel)
    _style(ax, title, xlabel, ylabel)
    _save(fig, path)


# -- per-control distributions (population level, never alert lists) ---------------------------
def distributions(con: duckdb.DuckDBPyConnection, cfg: Config, catalog: dict, charts: Path,
                  data: Path) -> dict[str, str]:
    p = {c["id"]: resolve_params(c, cfg) for c in catalog["controls"]}
    out: dict[str, str] = {}

    def q(sql: str, params: dict | None = None) -> np.ndarray:
        return con.execute(sql, params or {}).df().iloc[:, 0].dropna().to_numpy(dtype=float)

    v = q("""SELECT a.amount / r.limit_pen FROM f_award a JOIN ref_minor_limit r USING (year)
             WHERE a.procurement_method = 'direct' AND a.amount <= r.limit_pen""")
    _hist(v, np.linspace(0, 1, 41), charts / "c01.png", data / "c01_distribution.csv",
          "Minor purchases by amount relative to the 8 UIT limit", "amount / limit of the year",
          p["C01"]["near_limit_ratio"], f"'just below' band starts at {p['C01']['near_limit_ratio']:.0%}",
          "purchases")
    out["C01"] = ("Minor purchases pile up just under the limit. Part of that pile is legitimate, "
                  "because budgets get sized to the limit, so C01 also requires repetition with the "
                  "same supplier inside a short window. *Synthetic-data caveat:* the spike at 96-97% "
                  "is partly an artefact of the generator, which caps the amount distribution there "
                  "(see Scope & limitations). On real data, the height of this pile is itself a "
                  "metric worth tracking by entity type.")

    v = q("SELECT least(n_tenderers, 8) FROM f_process WHERE is_competitive")
    _hist(v, np.arange(0.5, 9.5, 1), charts / "c02.png", data / "c02_distribution.csv",
          "Competitive processes by number of bidders (8 = 8 or more)", "bidders", 1.5,
          "single bid", "processes")
    share = float((v == 1).mean()) if len(v) else 0.0
    out["C02"] = (f"{share:.1%} of competitive processes received a single bid. When the rate is "
                  "this common, the signal becomes informative only in combination with others or "
                  "when an entity's rate stands well above the national rate for the method.")

    v = q("""SELECT date_diff('day', CAST(tender_start AS DATE), CAST(tender_end AS DATE))
                    - coalesce(r.min_days, $d)
             FROM f_process p LEFT JOIN ref_min_submission_days r USING (method_details)
             WHERE is_competitive AND tender_start IS NOT NULL""",
          {"d": p["C03"]["default_min_days"]})
    _hist(np.clip(v, -20, 40), np.arange(-20.5, 41.5, 1), charts / "c03.png",
          data / "c03_distribution.csv", "Submission period minus the method minimum",
          "days above (+) or below (-) the minimum, clipped to [-20, 40]", -0.5, "minimum",
          "processes")
    out["C03"] = "Bars left of the line are processes whose call was shorter than the minimum for their method."

    v = q(f"""WITH s AS (SELECT buyer_id, segment, year, supplier_id, sum(amount) AS amt, count(*) AS k
                         FROM f_award WHERE amount IS NOT NULL GROUP BY ALL),
                   t AS (SELECT buyer_id, segment, year, sum(amt) AS tot, sum(k) AS n FROM s GROUP BY ALL)
              SELECT sum(power(100 * amt / tot, 2)) FROM s JOIN t USING (buyer_id, segment, year)
              WHERE t.n >= {int(p['C04']['min_awards'])} GROUP BY buyer_id, segment, year""")
    _hist(v, np.linspace(0, 10000, 41), charts / "c04.png", data / "c04_distribution.csv",
          f"HHI of entity x segment x year cells (>= {p['C04']['min_awards']} awards)",
          "HHI (0-10,000)", p["C04"]["hhi_threshold"], "highly concentrated", "cells")
    out["C04"] = ("Many cells are concentrated by amount because one large contract dominates "
                  "them. C04 therefore flags only cells where the dominant supplier also holds "
                  "several awards.")

    v = q("""WITH b AS (SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) nb FROM f_bid
                        WHERE is_competitive GROUP BY ALL),
                  w AS (SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) nw FROM f_award
                        WHERE is_competitive GROUP BY ALL)
             SELECT nw / greatest(nb, nw) FROM w JOIN b USING (buyer_id, supplier_id, year)
             WHERE nw >= 3""")
    _hist(v, np.linspace(0, 1, 21), charts / "c05.png", data / "c05_distribution.csv",
          "Win rate of supplier-entity pairs with 3+ competitive wins in a year", "wins / bids",
          p["C05"]["min_win_rate"], "flag zone (with 6+ wins)", "pairs")
    out["C05"] = "Pairs right of the line with six or more wins are flagged."

    v = q("""SELECT 100 * (final_amount / original_amount - 1) FROM f_contract
             WHERE final_amount IS NOT NULL AND original_amount > 0""")
    _hist(np.clip(v, 0, 150), np.arange(0, 155, 5), charts / "c06.png", data / "c06_distribution.csv",
          "Amended contracts by cumulative increase", "increase over the original amount (%), clipped at 150",
          100 * p["C06"]["cap"], f"cap {p['C06']['cap']:.0%} (to verify)", "contracts")
    out["C06"] = "Most amendments stay well under the cap; the tail beyond it is what C06 reviews."

    v = q("""WITH s AS (SELECT classification_id, median(unit_amount) med, count(*) n FROM f_item GROUP BY 1)
             SELECT log10(unit_amount / med) FROM f_item JOIN s USING (classification_id)
             WHERE n >= $g AND med > 0""", {"g": p["C07"]["min_group"]})
    _hist(np.clip(v, -1.5, 1.5), np.linspace(-1.5, 1.5, 61), charts / "c07.png",
          data / "c07_distribution.csv", "Unit prices relative to their class median (log10)",
          "log10(unit price / class median), clipped to [-1.5, 1.5]",
          float(np.log10(p["C07"]["ratio"])), f"{p['C07']['ratio']:.0f}x median", "items")
    out["C07"] = "A log scale makes 'three times the median' and 'a third of it' symmetric."

    dig = con.execute("""SELECT d.digit, d.observed, d.expected FROM (
        SELECT unnest(from_json(evidence, '[{"digit":"INTEGER","observed":"DOUBLE","expected":"DOUBLE"}]')) d
        FROM aggregate_tests WHERE control_id = 'C08' AND scope_type = 'all')""").df()
    dig.to_csv(data / "c08_distribution.csv", index=False)
    fig, ax = _fig()
    ax.bar(dig.digit, dig.observed, width=0.7, color=SERIES, label="observed")
    ax.plot(dig.digit, dig.expected, color=INK, marker="o", markersize=4, linewidth=1.5,
            label="Benford expected")
    ax.set_xticks(range(1, 10))
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
    _style(ax, "First digit of all awarded amounts vs. Benford's law", "first digit", "share")
    _save(fig, charts / "c08.png")
    ent = con.execute("""SELECT mad, mad_null, flag FROM aggregate_tests
                         WHERE control_id = 'C08' AND scope_type = 'buyer'""").df()
    ent[["mad", "mad_null", "flag"]].round(4).sort_values("mad").to_csv(
        data / "c08_entities_anonymous.csv", index=False)
    fig, ax = _fig()
    ax.scatter(ent.mad_null, ent.mad, s=36, color=SERIES, edgecolor=SURFACE, linewidth=1.5)
    xs = np.linspace(0, max(0.02, float(ent.mad_null.max() if len(ent) else 0.02) * 1.1), 10)
    ax.plot(xs, 2 * xs, color=ACCENT, linestyle="--", linewidth=1.5)
    ax.annotate("2x sampling noise", xy=(xs[-2], 2 * xs[-2]), xytext=(-90, 4),
                textcoords="offset points", fontsize=8, color=INK)
    ax.axhline(0.015, color=INK2, linestyle=":", linewidth=1)
    ax.annotate("Nigrini 'nonconformity' (0.015)", xy=(0, 0.015), xytext=(4, 3),
                textcoords="offset points", fontsize=8, color=INK2)
    _style(ax, "Entities tested (anonymous): observed MAD vs. MAD expected from noise",
           "MAD expected from sampling noise for the entity's n", "observed MAD")
    _save(fig, charts / "c08_entities.png")
    out["C08"] = ("Each dot is an entity, unnamed. Dots above the dotted line would be "
                  "'nonconforming' under Nigrini's fixed ranges, but most sit below the dashed "
                  "line: their deviation is what sampling noise produces for that many amounts.")

    v = q("""SELECT date_diff('day', CAST(c.award_date AS DATE), CAST(c.date_signed AS DATE))
             FROM f_contract c JOIN f_process p USING (ocid)
             WHERE c.date_signed IS NOT NULL AND p.procurement_method <> 'direct'""")
    _hist(np.clip(v, 0, 200), np.arange(0, 205, 5), charts / "c09.png", data / "c09_distribution.csv",
          "Contracts by days from award to signature (excluding minor purchases)",
          "days, clipped at 200", p["C09"]["max_days"], f"{p['C09']['max_days']} days", "contracts")
    out["C09"] = "The long right tail beyond the line is where C09 looks."
    return out


# -- trend and overview charts --------------------------------------------------------------------
def trend_charts(con: duckdb.DuckDBPyConnection, charts: Path, data: Path) -> None:
    m = con.execute("""
        SELECT strftime(p.process_date, '%Y-%m') AS month, count(*) AS processes,
               count(*) FILTER (WHERE r.ocid IS NOT NULL) AS flagged,
               count(*) FILTER (WHERE r.priority = 'P1') AS p1
        FROM f_process p LEFT JOIN risk_scores r USING (ocid) GROUP BY 1 ORDER BY 1""").df()
    m["flagged_pct"] = (100 * m.flagged / m.processes).round(2)
    m.to_csv(data / "trend_monthly.csv", index=False)
    fig, ax = _fig(7, 3)
    x = np.arange(len(m))
    ax.plot(x, m.flagged_pct, color=SERIES, linewidth=2, marker="o", markersize=3)
    ax.set_xticks(x[::3], m.month[::3], rotation=0)
    ax.set_ylim(0, max(30, float(m.flagged_pct.max()) * 1.2))
    _style(ax, "Share of processes with at least one alert, by month", "", "% of processes")
    _save(fig, charts / "trend_flagged_share.png")

    c = con.execute("""
        SELECT a.control_id, strftime(p.process_date, '%Y-%m') AS month, count(DISTINCT a.ocid) AS n
        FROM alerts a JOIN f_process p USING (ocid) GROUP BY ALL ORDER BY ALL""").df()
    c.to_csv(data / "trend_by_control.csv", index=False)
    months = sorted(m.month)
    ids = sorted(c.control_id.unique())
    fig, axes = plt.subplots(2, 4, figsize=(9, 4.2), dpi=150, sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, cid in zip(axes.flat, ids, strict=False):
        s = c[c.control_id == cid].set_index("month")["n"].reindex(months, fill_value=0)
        ax.plot(range(len(months)), s.values, color=SERIES, linewidth=1.6)
        _style(ax, cid, "", "")
        ax.set_xticks([0, len(months) - 1], [months[0], months[-1]])
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[len(ids):]:
        ax.axis("off")
    fig.suptitle("Processes flagged per month, by control (each panel has its own scale)",
                 x=0.01, ha="left", fontsize=10, color=INK)
    _save(fig, charts / "trend_by_control.png")

    rs = con.execute("SELECT score FROM risk_scores").df().score.to_numpy()
    _hist(rs, np.arange(0, 102, 2.5), charts / "risk_score.png", data / "risk_score_histogram.csv",
          "Composite risk score of flagged processes", "score (0-100)", 50, "P1 from 50", "processes")

    by = con.execute("""SELECT control_id, count(DISTINCT ocid) AS processes FROM alerts
                        GROUP BY 1 ORDER BY 1 DESC""").df()
    fig, ax = _fig(7, 3)
    ax.barh(by.control_id, by.processes, color=SERIES, height=0.6)
    for y, v in enumerate(by.processes):
        ax.annotate(f"{v:,}", xy=(v, y), xytext=(4, -3), textcoords="offset points", fontsize=8, color=INK)
    _style(ax, "Processes flagged by each control", "processes", "")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    _save(fig, charts / "alerts_by_control.png")


# -- pages ----------------------------------------------------------------------------------------
def _param_table(spec: dict, cfg: Config) -> str:
    rows = []
    resolved = resolve_params(spec, cfg)
    for name, p in spec["parameters"].items():
        val = resolved[name]
        if isinstance(val, dict):
            val = "; ".join(f"{k}: {v.get('value', v) if isinstance(v, dict) else v}" for k, v in val.items())
        if "ref" in p:
            root = p["ref"].split(".")[0]
            node = cfg.thresholds.get(root, {})
            status = node.get("status", "")
            if not status and isinstance(node, dict):
                status = next((v.get("status") for v in node.values() if isinstance(v, dict)
                               and v.get("status")), "")
            origin = f"`thresholds.yaml: {p['ref']}` ({status or 'see file'})"
        else:
            origin = f"catalog literal{' - ' + p['note'] if p.get('note') else ''}"
        rows.append({"parameter": name, "value": val, "unit": p.get("unit", ""), "origin": origin})
    return _md_table(pd.DataFrame(rows))


def control_page(spec: dict, cfg: Config, con, metrics: pd.DataFrame | None, note: str) -> str:
    cid = spec["id"]
    fp = spec["expected_false_positives"]
    sql = (cfg.root / spec["sql"]).read_text(encoding="utf-8")
    if spec["level"] == "process":
        res = con.execute("""SELECT year, count(*) AS alerts, count(DISTINCT ocid) AS processes,
                                    round(avg(severity), 2) AS mean_severity
                             FROM alerts WHERE control_id = $c GROUP BY 1 ORDER BY 1""",
                          {"c": cid}).df()
        results = _md_table(res) if len(res) else "*No alerts in this run.*"
    else:
        res = con.execute("""SELECT scope_type, conformity, flag AS beyond_sampling_noise,
                                    count(*) AS scopes, sum(n) AS amounts, round(avg(mad), 4) AS mean_mad
                             FROM aggregate_tests WHERE control_id = $c GROUP BY ALL ORDER BY ALL""",
                          {"c": cid}).df()
        results = _md_table(res)
    val = ""
    if metrics is not None and cid in set(metrics.control_id):
        r = metrics[metrics.control_id == cid].drop(columns=["control_id"])
        val = f"\n### Validation on injected patterns\n\n{_md_table(r)}\n\nSee [Validation](../validation.md).\n"
    extra_chart = "\n![Entities tested](../assets/charts/c08_entities.png)\n" if cid == "C08" else ""
    causes = "\n".join(f"* {c}" for c in fp["causes"])
    return f"""# {cid} · {spec['name']}

{DISCLAIMER}

| | |
|---|---|
| **Control objective** | {spec['control_objective'].strip()} |
| **Risk mitigated** | {spec['risk_mitigated'].strip()} |
| **Threshold** | {spec['threshold']} |
| **Frequency** | {spec['frequency']} |
| **Owner role** | {spec['owner_role']} |
| **Evidence generated** | {spec['evidence']} |
| **Level** | {spec['level']} |
| **Weight in risk score** | {spec['weight']} - {spec['weight_rationale']} |
| **Methodological reference** | {spec['ocp_reference']} |

## Rule

{spec['rule'].strip()}

### Parameters

{_param_table(spec, cfg)}

### Expected false positives - {fp['rate_band']}

{causes}

## Distribution

![{cid} distribution](../assets/charts/{cid.lower()}.png)
{extra_chart}
{note}

Data behind the chart: `outputs/distributions/{cid.lower()}_distribution.csv`.

## Results of this run

{results}
{val}
## Exact rule (SQL executed by the engine)

```sql
{sql.strip()}
```
"""


def run(cfg: Config, con: duckdb.DuckDBPyConnection, meta: dict) -> dict:
    docs = cfg.path("docs")
    charts = docs / "assets" / "charts"
    data = cfg.path("outputs") / "distributions"
    charts.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    (docs / "controls").mkdir(exist_ok=True)
    catalog = load_catalog(cfg)
    notes = distributions(con, cfg, catalog, charts, data)
    trend_charts(con, charts, data)
    mpath = cfg.path("outputs") / "validation" / "control_metrics.csv"
    metrics = pd.read_csv(mpath) if mpath.exists() and meta.get("source") == "synthetic" else None

    for spec in catalog["controls"]:
        (docs / "controls" / f"{spec['id'].lower()}.md").write_text(
            control_page(spec, cfg, con, metrics, notes.get(spec["id"], "")), encoding="utf-8")
    write_catalog_index(docs, catalog, con)
    write_overview(docs, cfg, con, meta, catalog, metrics)
    write_trends(docs, con)
    write_risk_score(docs, con, catalog)
    from .powerbi import export

    export(cfg, con)
    return {"pages": len(catalog["controls"]) + 4}


def write_catalog_index(docs: Path, catalog: dict, con) -> None:
    counts = dict(con.execute("SELECT control_id, count(DISTINCT ocid) FROM alerts GROUP BY 1").fetchall())
    rows = [{"control": f"[{c['id']}]({c['id'].lower()}.md)", "name": c["name"],
             "frequency": c["frequency"], "owner role": c["owner_role"], "weight": c["weight"],
             "expected FP": c["expected_false_positives"]["rate_band"],
             "processes flagged": counts.get(c["id"], "aggregate test")}
            for c in catalog["controls"]]
    (docs / "controls" / "index.md").write_text(f"""# Control catalog

{DISCLAIMER}

Every control is defined once, in `controls/catalog.yaml`, with its exact rule in
`controls/sql/`. The engine runs them from there; this page is generated from the same file.
Catalog owner: **{catalog['owner_of_catalog']}**. Review cycle: {catalog['review_cycle']}.

{_md_table(pd.DataFrame(rows))}
""", encoding="utf-8")


def write_overview(docs: Path, cfg: Config, con, meta: dict, catalog: dict,
                   metrics: pd.DataFrame | None) -> None:
    k = con.execute("""SELECT (SELECT count(*) FROM f_process),
                              (SELECT count(*) FROM f_process WHERE is_competitive),
                              (SELECT round(sum(amount) / 1e6, 1) FROM f_award),
                              (SELECT count(*) FROM alerts),
                              (SELECT count(*) FROM risk_scores),
                              (SELECT count(*) FROM risk_scores WHERE priority = 'P1'),
                              (SELECT count(DISTINCT buyer_id) FROM f_process),
                              (SELECT min(year) FROM f_process), (SELECT max(year) FROM f_process)
                       """).fetchone()
    n_proc, n_comp, amount, n_alerts, n_flag, n_p1, n_ent, y0, y1 = k
    source = meta.get("source", "synthetic")
    banner = ("""!!! info "Data: synthetic (Plan C)"
    The build environment could not reach the OCP Data Registry or the OECE portal, so every
    figure on this site comes from a **seeded synthetic OCDS dataset** with injected, known risk
    patterns. It describes no real entity. The pipeline runs unchanged on the real publications
    (`procontrol run --source oece`).
""" if source == "synthetic" else f"!!! info \"Data source: {source}\"\n")
    tv = cfg.to_verify()
    rec = ""
    if metrics is not None:
        rec = (f"Against the injected patterns, the process controls reach a mean recall of "
               f"**{metrics.recall.mean():.0%}**. Their share of alerts on neutral background ranges "
               f"from **{metrics.background_fp_share.min():.0%}** to "
               f"**{metrics.background_fp_share.max():.0%}**: see [Validation](validation.md).")
    (docs / "index.md").write_text(f"""# Peru procurement controls

{DISCLAIMER}

{banner}

Continuous-control analytics on Peruvian public procurement, published in the Open Contracting
Data Standard (OCDS). Each control is a written rule with a threshold, an owner role and an
expected false-positive rate, the way an internal-control or continuous-auditing function works.

## At a glance

| | |
|---|---|
| Period | {y0}-{y1} |
| Contracting processes (clean layer) | {n_proc:,} ({n_comp:,} competitive) |
| Awarded amount | S/ {amount:,.1f} million |
| Public entities (aggregated only) | {n_ent} |
| Controls running | {len(catalog['controls'])} ({sum(c['level'] == 'process' for c in catalog['controls'])} per process, {sum(c['level'] == 'aggregate' for c in catalog['controls'])} aggregate) |
| Alerts | {n_alerts:,} on {n_flag:,} processes ({100 * n_flag / n_proc:.1f}%) |
| Review priority P1 | {n_p1:,} processes |
| Thresholds still to verify | {len(tv)} (listed in `config/thresholds.yaml`) |

{rec}

![Processes flagged by each control](assets/charts/alerts_by_control.png)

## How to read this site

1. **[Data quality](data-quality.md)** comes first, because a control is only as good as its
   data.
2. **[Control catalog](controls/index.md)** has one page per signal: objective, rule,
   threshold, owner, evidence, expected false positives, the distribution behind it and the
   exact SQL.
3. **[Risk score](risk-score.md)** shows how alerts combine into a review priority.
4. **[Trends](trends.md)** shows how signals move over time, aggregated.
5. **[Validation](validation.md)** shows how well each control finds planted patterns, and a
   blind review of 20 alerts.
6. **[Decisions](metodologia/decisiones.md)** gives every design choice and why.
""", encoding="utf-8")


def write_trends(docs: Path, con) -> None:
    seg = con.execute("""
        SELECT p.segment, count(DISTINCT p.ocid) AS processes, count(DISTINCT r.ocid) AS flagged,
               round(100.0 * count(DISTINCT r.ocid) / count(DISTINCT p.ocid), 1) AS flagged_pct
        FROM f_process p LEFT JOIN risk_scores r USING (ocid) GROUP BY 1 ORDER BY flagged_pct DESC, segment""").df()
    seg.insert(1, "category", seg.segment.map(SEGMENT_LABELS).fillna(""))
    meth = con.execute("""
        SELECT p.method_details AS method, count(DISTINCT p.ocid) AS processes,
               count(DISTINCT r.ocid) AS flagged,
               round(100.0 * count(DISTINCT r.ocid) / count(DISTINCT p.ocid), 1) AS flagged_pct,
               count(DISTINCT r.ocid) FILTER (WHERE r.priority = 'P1') AS p1
        FROM f_process p LEFT JOIN risk_scores r USING (ocid) GROUP BY 1 ORDER BY processes DESC, method""").df()
    etype = con.execute("""
        SELECT regexp_extract(any_value(pa.name), '\\((.*)\\)', 1) AS entity_type, p.buyer_id,
               count(DISTINCT p.ocid) AS processes, count(DISTINCT r.ocid) AS flagged
        FROM f_process p LEFT JOIN risk_scores r USING (ocid)
        LEFT JOIN parties pa ON pa.party_id = p.buyer_id
        GROUP BY p.buyer_id""").df()
    by_type = (etype.groupby("entity_type").agg(entities=("buyer_id", "count"),
                                                processes=("processes", "sum"),
                                                flagged=("flagged", "sum")).reset_index())
    by_type["flagged_pct"] = (100 * by_type.flagged / by_type.processes).round(1)
    spread = pd.read_csv(docs.parent / "outputs" / "signals" / "entity_alert_concentration.csv")
    (docs / "trends.md").write_text(f"""# Trends and aggregated views

{DISCLAIMER}

![Share of processes flagged by month](assets/charts/trend_flagged_share.png)

![Processes flagged per month by control](assets/charts/trend_by_control.png)

Data: `outputs/distributions/trend_monthly.csv` and `trend_by_control.csv`.

## By procurement method

{_md_table(meth)}

## By category (UNSPSC segment)

{_md_table(seg)}

## By type of entity

Entities are grouped by type; no individual entity is shown.

{_md_table(by_type)}

## How alerts spread across entities

Number of entities by the share of their processes that carry at least one alert. The groups
are not ranked and no entity is named.

{_md_table(spread)}
""", encoding="utf-8")


def write_risk_score(docs: Path, con, catalog: dict) -> None:
    rs = catalog["risk_score"]
    dist = con.execute("""SELECT priority, count(*) AS processes, round(avg(score), 1) AS mean_score,
                                 round(avg(n_controls), 2) AS mean_controls
                          FROM risk_scores GROUP BY 1 ORDER BY 1""").df()
    combos = con.execute("""SELECT controls, count(*) AS processes, round(avg(score), 1) AS mean_score
                            FROM risk_scores WHERE n_controls >= 2 GROUP BY 1
                            ORDER BY processes DESC, controls LIMIT 12""").df()
    weights = pd.DataFrame([{"control": c["id"], "name": c["name"], "weight": c["weight"],
                             "rationale": c["weight_rationale"]} for c in catalog["controls"]])
    pri = "\n".join(f"* **{k}**: {v}" for k, v in rs["review_priority"].items())
    (docs / "risk-score.md").write_text(f"""# Composite risk score

{DISCLAIMER}

**Formula:** `{rs['formula']}`

{rs['rationale'].strip()}

Each rule computes the severity (0-1) as the distance past its threshold. For example, an
amendment at +100% against a 25% cap has severity (1.00 - 0.25) / 0.75 = 1. Only the
strongest alert of each control counts for a process.

## Weights

{_md_table(weights)}

## Review priority

{pri}

![Risk score distribution](assets/charts/risk_score.png)

{_md_table(dist)}

## Most frequent combinations of signals

Processes where several independent controls fire together are the best use of a reviewer's
time, because each extra signal makes a legitimate explanation less likely.

{_md_table(combos)}

*The score orders the review queue. It does not measure wrongdoing.*
""", encoding="utf-8")

