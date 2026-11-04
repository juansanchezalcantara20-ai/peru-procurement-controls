"""The site, written for a logistics, internal-control or administration manager.

Every page can be read on its own: plain Spanish, figures as «N de cada 100», every chart titled
with its conclusion and followed by a sentence on how to read it, every acronym explained the
first time it appears on the page. Technical material only inside «Detalle técnico» blocks and
under Metodología. Aggregated views only (rule: signals, never accusations).
"""

from __future__ import annotations

import json
import shutil
import textwrap
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import Config  # noqa: E402
from .engine import load_catalog, resolve_params  # noqa: E402
from .labels import (  # noqa: E402
    METHOD_ES,
    PATTERN_ES,
    SLUGS,
    data_label,
    entity_type,
    fecha,
    k_anonymous,
    num,
    per,
    segment_label,
    soles,
)
from .quality import _md_table  # noqa: E402

AVISO = """!!! warning "Señales, nunca acusaciones"
    Una alerta significa **«este caso merece revisión»**, no «hay una irregularidad». Este sitio
    no nombra ni ordena a ningún proveedor, funcionario o persona; las entidades públicas solo
    aparecen agrupadas.
"""

# reference palette (dataviz skill, light mode)
SERIES, ACCENT = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

OLD_PAGES = ["controls", "trends.md", "risk-score.md", "validation.md", "data-quality.md"]


# -- chart helpers ----------------------------------------------------------------------------------
def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(textwrap.fill(title, 70), loc="left", fontsize=11, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURFACE)


def _fig(width: float = 7.0, height: float = 3.3):
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def _save(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def _threshold(ax, x: float, label: str) -> None:
    ax.axvline(x, color=ACCENT, linewidth=1.5, linestyle="--")
    ax.annotate(label, xy=(x, 1), xycoords=("data", "axes fraction"), xytext=(4, -12),
                textcoords="offset points", color=INK, fontsize=8)


def _hist(values, bins, path: Path, csv: Path, title: str, xlabel: str,
          threshold: float | None = None, tlabel: str = "", ylabel: str = "cantidad") -> None:
    counts, edges = np.histogram(values, bins=bins)
    pd.DataFrame({"desde": edges[:-1].round(4), "hasta": edges[1:].round(4),
                  "cantidad": counts}).to_csv(csv, index=False)
    fig, ax = _fig()
    ax.bar(edges[:-1], counts, width=np.diff(edges) * 0.92, align="edge", color=SERIES)
    if threshold is not None:
        _threshold(ax, threshold, tlabel)
    _style(ax, title, xlabel, ylabel)
    _save(fig, path)


def _img(rel: str, alt: str, how: str) -> str:
    return f"![{alt}]({rel})\n\n*Cómo leerlo:* {how}\n"


def _details(title: str, body: str) -> str:
    return f'??? info "{title}"\n\n' + textwrap.indent(body.strip() + "\n", "    ") + "\n"


# -- context ----------------------------------------------------------------------------------------
class Site:
    def __init__(self, cfg: Config, con: duckdb.DuckDBPyConnection, meta: dict):
        self.cfg, self.con, self.meta = cfg, con, meta
        self.docs = cfg.path("docs")
        self.charts = self.docs / "assets" / "charts"
        self.data = cfg.path("outputs") / "distributions"
        self.catalog = load_catalog(cfg)
        self.controls = {c["id"]: c for c in self.catalog["controls"]}
        self.params = {c["id"]: resolve_params(c, cfg) for c in self.catalog["controls"]}
        self.label = data_label(meta)
        self.tag = f"<small>({self.label})</small>"
        self.synthetic = meta.get("source", "synthetic") == "synthetic"
        self.k = int(cfg.settings.get("site", {}).get("min_entities_per_group", 3))
        vdir = cfg.path("outputs") / "validation"
        self.metrics = _read(vdir / "control_metrics.csv")
        self.priority = _read(vdir / "priority_metrics.csv")
        self.benford_v = _read(vdir / "benford_validation.csv")
        self.dq_v = _read(vdir / "dq_validation.csv")
        self.review = _read(vdir / "case_review.csv")

    def q(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        return self.con.execute(sql, params or {}).df()

    def one(self, sql: str, params: dict | None = None):
        return self.con.execute(sql, params or {}).fetchone()[0]

    def link(self, cid: str, prefix: str = "") -> str:
        return f"[{self.controls[cid]['name']}]({prefix}{SLUGS[cid]}.md)"

    def fp_share(self, cid: str) -> float | None:
        if self.metrics is None or cid not in set(self.metrics.control_id):
            return None
        return float(self.metrics.set_index("control_id").loc[cid, "background_fp_share"])

    def banner(self) -> str:
        if self.synthetic:
            return """!!! note "Datos simulados"
    Todas las cifras de este sitio vienen de **datos simulados**: un conjunto inventado con la
    misma estructura que las compras públicas reales, en el que se sembraron casos de riesgo a
    propósito para comprobar que las señales los encuentran. No describe a ninguna entidad real.
    Cuando corran los datos reales, este aviso cambiará solo.
"""
        who = {"oece": "del OECE (Organismo Especializado para las Contrataciones Públicas Eficientes)",
               "perucompras": "de Perú Compras (la central de compras del Estado)"}.get(
            self.meta.get("source"), "")
        when = fecha((self.meta.get("download") or {}).get("downloaded_at"))
        return f"""!!! note "Datos reales"
    Las cifras de este sitio son **datos reales {who}, descargados el {when}**, publicados en el
    registro de datos abiertos de contrataciones de Open Contracting Partnership. La comprobación
    de que las señales funcionan (página «¿Funciona?») se hizo con datos simulados, porque en datos
    reales no se sabe de antemano qué casos son irregulares.
"""


def _read(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


# -- entry point ------------------------------------------------------------------------------------
def run(cfg: Config, con: duckdb.DuckDBPyConnection, meta: dict) -> dict:
    s = Site(cfg, con, meta)
    for old in OLD_PAGES:
        p = s.docs / old
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    s.charts.mkdir(parents=True, exist_ok=True)
    s.data.mkdir(parents=True, exist_ok=True)
    (s.docs / "senales").mkdir(exist_ok=True)

    stats = signal_stats(s)
    charts = signal_charts(s)
    overview_charts(s)
    for cid in s.controls:
        (s.docs / "senales" / f"{SLUGS[cid]}.md").write_text(signal_page(s, cid, stats, charts),
                                                             encoding="utf-8")
    (s.docs / "senales" / "index.md").write_text(signals_index(s, stats), encoding="utf-8")
    (s.docs / "index.md").write_text(home(s, stats), encoding="utf-8")
    (s.docs / "funciona.md").write_text(works_page(s), encoding="utf-8")
    (s.docs / "datos.md").write_text(data_page(s), encoding="utf-8")
    (s.docs / "glosario.md").write_text(glossary(s), encoding="utf-8")
    (s.docs / "metodologia" / "index.md").write_text(methodology(s), encoding="utf-8")
    (s.docs / "datos.json").write_text(json.dumps({
        "fuente": "simulados" if s.synthetic else meta.get("source"),
        "etiqueta": s.label,
        "descargado": (meta.get("download") or {}).get("downloaded_at"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from .powerbi import export

    export(cfg, con)
    return {"pages": len(s.controls) + 7, "label": s.label}


# -- numbers ----------------------------------------------------------------------------------------
def signal_stats(s: Site) -> dict:
    total = s.one("SELECT count(*) FROM f_process")
    comp = s.one("SELECT count(*) FROM f_process WHERE is_competitive")
    by = s.q("SELECT control_id, count(DISTINCT ocid) AS n FROM alerts GROUP BY 1")
    flagged = dict(zip(by.control_id, by.n, strict=True))
    years = s.q("""SELECT control_id, year, count(DISTINCT ocid) AS n FROM alerts
                   GROUP BY ALL ORDER BY ALL""")
    ben = s.q("""SELECT count(*) FILTER (WHERE scope_type = 'buyer') AS tested,
                        count(*) FILTER (WHERE scope_type = 'buyer' AND flag) AS flagged,
                        count(*) FILTER (WHERE scope_type = 'buyer' AND conformity = 'no conformidad')
                            AS nigrini
                 FROM aggregate_tests WHERE control_id = 'C08'""").iloc[0]
    return {
        "total": total, "competitive": comp, "flagged": flagged, "years": years,
        "with_alert": s.one("SELECT count(*) FROM risk_scores"),
        "p1": s.one("SELECT count(*) FROM risk_scores WHERE priority = 'P1'"),
        "p2": s.one("SELECT count(*) FROM risk_scores WHERE priority = 'P2'"),
        "amount": s.one("SELECT coalesce(sum(amount), 0) FROM f_award"),
        "entities": s.one("SELECT count(DISTINCT buyer_id) FROM f_process"),
        "y0": s.one("SELECT min(year) FROM f_process"), "y1": s.one("SELECT max(year) FROM f_process"),
        "minor": s.one("SELECT count(*) FROM f_award WHERE procurement_method = 'direct'"),
        "benford": {k: int(v) for k, v in ben.items()},
    }


# -- charts -----------------------------------------------------------------------------------------
def signal_charts(s: Site) -> dict[str, dict]:
    p, c, d = s.params, s.charts, s.data
    out: dict[str, dict] = {}

    def vals(sql: str, params: dict | None = None) -> np.ndarray:
        return s.q(sql, params).iloc[:, 0].dropna().to_numpy(dtype=float)

    v = vals("""SELECT a.amount / r.limit_pen FROM f_award a JOIN ref_minor_limit r USING (year)
                WHERE a.procurement_method = 'direct' AND a.amount <= r.limit_pen""")
    near = p["C01"]["near_limit_ratio"]
    if len(v):
        title = (f"{per((v >= near).sum(), len(v))} compras menores quedaron a menos de "
                 f"{round(100 * (1 - near))}% del límite")
        _hist(v, np.linspace(0, 1, 41), c / "c01.png", d / "c01_distribucion.csv", title,
              "monto de la compra como proporción del límite del año (1 = justo en el límite)",
              near, "zona «justo debajo del límite»", "compras")
        out["C01"] = {"img": "c01.png", "title": title, "how": (
            "cada barra cuenta las compras menores según qué tan cerca quedaron del límite. Las "
            "que están a la derecha de la línea naranja quedaron muy cerca. Un montón de compras "
            "pegadas al límite no prueba nada por sí solo; la señal salta cuando además se repiten "
            "con el mismo proveedor en pocos días."
            + (" En los datos simulados, el pico en 96-97% es en parte un efecto del generador "
               "(ver «De dónde salen los datos»)." if s.synthetic else ""))}

    v = vals("SELECT least(n_tenderers, 8) FROM f_process WHERE is_competitive AND n_tenderers >= 1")
    if len(v):
        title = f"{per((v == 1).sum(), len(v))} concursos tuvieron un solo postor"
        _hist(v, np.arange(0.5, 9.5, 1), c / "c02.png", d / "c02_distribucion.csv", title,
              "número de postores (8 = ocho o más)", 1.5, "un solo postor", "concursos")
        out["C02"] = {"img": "c02.png", "title": title, "how": (
            "cada barra cuenta los concursos según cuántas empresas se presentaron. La barra de la "
            "izquierda de la línea son los concursos con una sola oferta.")}

    v = vals("""SELECT date_diff('day', CAST(tender_start AS DATE), CAST(tender_end AS DATE))
                       - coalesce(r.min_days, $d)
                FROM f_process p LEFT JOIN ref_min_submission_days r
                  ON lower(strip_accents(r.method_details)) = lower(strip_accents(p.method_details))
                WHERE is_competitive AND tender_start IS NOT NULL""",
             {"d": p["C03"]["default_min_days"]})
    if len(v):
        title = f"{per((v < 0).sum(), len(v))} concursos dieron menos días que el mínimo para ofertar"
        _hist(np.clip(v, -20, 40), np.arange(-20.5, 41.5, 1), c / "c03.png", d / "c03_distribucion.csv",
              title, "días por encima (+) o por debajo (−) del mínimo del tipo de proceso", -0.5,
              "mínimo", "concursos")
        out["C03"] = {"img": "c03.png", "title": title, "how": (
            "cada barra cuenta los concursos según cuántos días de margen dieron sobre el mínimo "
            "para su tipo de proceso. Las barras a la izquierda de la línea dieron menos días que "
            "el mínimo.")}

    cells = s.q(f"""
        WITH b AS (SELECT buyer_id, segment, year, supplier_id, sum(amount) AS amt, count(*) AS k
                   FROM f_award WHERE amount IS NOT NULL GROUP BY ALL),
             t AS (SELECT buyer_id, segment, year, sum(amt) AS tot, sum(k) AS n FROM b GROUP BY ALL)
        SELECT sum(power(100 * amt / tot, 2)) AS hhi FROM b JOIN t USING (buyer_id, segment, year)
        WHERE t.n >= {int(p['C04']['min_awards'])} GROUP BY buyer_id, segment, year""")
    v = cells.hhi.to_numpy(dtype=float)
    if len(v):
        thr = p["C04"]["hhi_threshold"]
        title = f"{per((v > thr).sum(), len(v))} rubros de una entidad están muy concentrados en pocos proveedores"
        _hist(v, np.linspace(0, 10000, 41), c / "c04.png", d / "c04_distribucion.csv", title,
              "índice de concentración (0 = muy repartido, 10,000 = un solo proveedor)", thr,
              "muy concentrado", "rubros")
        out["C04"] = {"img": "c04.png", "title": title, "how": (
            "cada barra cuenta rubros (un tipo de compra de una entidad en un año) según qué tan "
            "concentrado está el gasto. A la derecha de la línea, pocos proveedores se llevan casi "
            "todo. Muchos rubros quedan ahí por un solo contrato grande; por eso la señal exige "
            "además que el proveedor principal tenga varios contratos.")}

    pairs = s.q("""WITH b AS (SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) nb FROM f_bid
                              WHERE is_competitive GROUP BY ALL),
                        w AS (SELECT buyer_id, supplier_id, year, count(DISTINCT ocid) nw FROM f_award
                              WHERE is_competitive GROUP BY ALL)
                   SELECT nw / greatest(nb, nw) AS rate, nw FROM w JOIN b USING (buyer_id, supplier_id, year)
                   WHERE nw >= 3""")
    if len(pairs):
        mw, mr = p["C05"]["min_wins"], p["C05"]["min_win_rate"]
        hit = int(((pairs.nw >= mw) & (pairs.rate >= mr)).sum())
        title = f"Solo {num(hit)} de {num(len(pairs))} parejas entidad–proveedor ganan casi siempre"
        _hist(pairs.rate.to_numpy(), np.linspace(0, 1, 21), c / "c05.png", d / "c05_distribucion.csv",
              title, "proporción de concursos ganados sobre los que ofertó (1 = ganó todos)", mr,
              f"{round(100 * mr)} de cada 100 o más", "parejas")
        out["C05"] = {"img": "c05.png", "title": title, "how": (
            "cada barra cuenta parejas de una entidad y un proveedor que ganó al menos 3 concursos "
            "en un año, según la proporción de concursos que ganó. La señal salta a la derecha de "
            f"la línea cuando además ganó {mw} o más.")}

    v = vals("""SELECT 100 * (final_amount / original_amount - 1) FROM f_contract
                WHERE final_amount IS NOT NULL AND original_amount > 0""")
    if len(v):
        cap = 100 * p["C06"]["cap"]
        title = f"{per((v > cap).sum(), len(v))} contratos con adendas superaron el tope de {cap:.0f}%"
        _hist(np.clip(v, 0, 150), np.arange(0, 155, 5), c / "c06.png", d / "c06_distribucion.csv",
              title, "cuánto creció el contrato sobre su monto original (%; 150 = 150% o más)", cap,
              f"tope {cap:.0f}% (por verificar)", "contratos")
        out["C06"] = {"img": "c06.png", "title": title, "how": (
            "cada barra cuenta los contratos modificados según cuánto creció su monto. A la derecha "
            "de la línea están los que pasaron el tope.")}

    v = vals("""WITH t AS (SELECT classification_id, median(unit_amount) med, count(*) n
                           FROM f_item GROUP BY 1)
                SELECT unit_amount / med FROM f_item JOIN t USING (classification_id)
                WHERE n >= $g AND med > 0""", {"g": p["C07"]["min_group"]})
    if len(v):
        r = p["C07"]["ratio"]
        title = f"{per((v >= r).sum(), len(v))} artículos costaron {r:.0f} veces o más que el precio típico"
        lv = np.log10(np.clip(v, 10 ** -1.5, 10 ** 1.5))
        _hist(lv, np.linspace(-1.5, 1.5, 61), c / "c07.png", d / "c07_distribucion.csv", title,
              "precio frente al típico de su clase (0 = igual; 1 = 10 veces más; −1 = 10 veces menos)",
              float(np.log10(r)), f"{r:.0f} veces el típico", "artículos")
        out["C07"] = {"img": "c07.png", "title": title, "how": (
            "cada barra cuenta artículos según cuánto se alejó su precio del típico para su clase. "
            "La escala está comprimida para que «tres veces más caro» y «tres veces más barato» "
            "queden a la misma distancia del centro. A la derecha de la línea están los que "
            "costaron tres veces o más.")}

    dig = s.q("""SELECT d.digit, d.observed, d.expected FROM (
        SELECT unnest(from_json(evidence, '[{"digit":"INTEGER","observed":"DOUBLE","expected":"DOUBLE"}]')) d
        FROM aggregate_tests WHERE control_id = 'C08' AND scope_type = 'all')""")
    ent = s.q("SELECT mad, mad_null, flag FROM aggregate_tests WHERE control_id = 'C08' AND scope_type = 'buyer'")
    if len(dig):
        dig.rename(columns={"digit": "primer_digito", "observed": "observado", "expected": "esperado"}).to_csv(
            d / "c08_distribucion.csv", index=False)
        gap = float((dig.observed - dig.expected).abs().max())
        title = ("Los montos del conjunto siguen de cerca la ley de Benford" if gap < 0.02 else
                 "Los montos del conjunto se alejan de la ley de Benford en algunos dígitos")
        fig, ax = _fig()
        ax.bar(dig.digit, 100 * dig.observed, width=0.7, color=SERIES, label="montos observados")
        ax.plot(dig.digit, 100 * dig.expected, color=INK, marker="o", markersize=4, linewidth=1.5,
                label="lo esperado en cifras naturales")
        ax.set_xticks(range(1, 10))
        ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
        _style(ax, title, "primer dígito del monto", "de cada 100 montos")
        _save(fig, c / "c08.png")
        k_flag, k_tot = int(ent.flag.sum()) if len(ent) else 0, len(ent)
        title2 = f"{num(k_flag)} de {num(k_tot)} entidades se alejan de Benford más de lo que explica el azar"
        ent[["mad", "mad_null", "flag"]].round(4).sort_values("mad").to_csv(
            d / "c08_entidades_anonimas.csv", index=False)
        fig, ax = _fig()
        ax.scatter(ent.mad_null, ent.mad, s=36, color=SERIES, edgecolor=SURFACE, linewidth=1.5)
        xs = np.linspace(0, max(0.02, float(ent.mad_null.max() if k_tot else 0.02) * 1.1), 10)
        ax.plot(xs, 2 * xs, color=ACCENT, linestyle="--", linewidth=1.5)
        ax.annotate("doble de lo esperable por azar", xy=(xs[-2], 2 * xs[-2]), xytext=(-150, 4),
                    textcoords="offset points", fontsize=8, color=INK)
        _style(ax, title2, "desviación que produciría el puro azar con esa cantidad de montos",
               "desviación observada")
        _save(fig, c / "c08_entidades.png")
        out["C08"] = {"img": "c08.png", "title": title, "how": (
            "las barras muestran, de cada 100 montos, cuántos empiezan con cada dígito; la línea "
            "negra es lo que se ve en cifras naturales (unos 30 de cada 100 empiezan con 1 y menos "
            "de 5 con 9)."),
            "img2": "c08_entidades.png", "title2": title2, "how2": (
            "cada punto es una entidad, sin nombre. Más arriba significa que sus montos se alejan "
            "más de Benford. Los puntos sobre la línea naranja se alejan más del doble de lo que "
            "el puro azar produciría con su cantidad de montos; solo esos merecen atención.")}

    v = vals("""SELECT date_diff('day', CAST(c.award_date AS DATE), CAST(c.date_signed AS DATE))
                FROM f_contract c JOIN f_process p USING (ocid)
                WHERE c.date_signed IS NOT NULL
                  AND NOT list_contains($x, p.procurement_method)""",
             {"x": p["C09"]["excluded_methods"]})
    if len(v):
        md = p["C09"]["max_days"]
        title = f"{per((v > md).sum(), len(v))} contratos se firmaron más de {md} días después de elegir al ganador"
        _hist(np.clip(v, 0, 200), np.arange(0, 205, 5), c / "c09.png", d / "c09_distribucion.csv", title,
              "días entre la adjudicación y la firma (200 = 200 o más)", md, f"{md} días", "contratos")
        out["C09"] = {"img": "c09.png", "title": title, "how": (
            "cada barra cuenta los contratos según cuántos días pasaron entre la adjudicación y la "
            "firma. La mayoría se firma en pocos días; la cola a la derecha de la línea es lo que "
            "la señal revisa.")}
    return out


def overview_charts(s: Site) -> None:
    m = s.q("""SELECT strftime(p.process_date, '%Y-%m') AS mes, count(*) AS procesos,
                      count(*) FILTER (WHERE r.ocid IS NOT NULL) AS con_alerta
               FROM f_process p LEFT JOIN risk_scores r USING (ocid)
               WHERE p.process_date IS NOT NULL GROUP BY 1 ORDER BY 1""")
    m["por_cada_100"] = (100 * m.con_alerta / m.procesos).round(2)
    m.to_csv(s.data / "tendencia_mensual.csv", index=False)
    if len(m):
        lo, hi = m.por_cada_100.min(), m.por_cada_100.max()
        fig, ax = _fig(7, 3)
        x = np.arange(len(m))
        ax.plot(x, m.por_cada_100, color=SERIES, linewidth=2, marker="o", markersize=3)
        ax.set_xticks(x[::3], m.mes[::3])
        ax.set_ylim(0, max(30, float(hi) * 1.2))
        _style(ax, f"Cada mes, entre {lo:.0f} y {hi:.0f} de cada 100 procesos tuvieron alguna alerta",
               "mes", "de cada 100 procesos")
        _save(fig, s.charts / "tendencia.png")

    by = s.q("SELECT control_id, count(DISTINCT ocid) AS n FROM alerts GROUP BY 1")
    by["señal"] = by.control_id.map(lambda c: s.controls[c]["short_title"])
    by = by.sort_values("n")
    if len(by):
        top = by.iloc[-1]
        fig, ax = _fig(7, 3.4)
        ax.barh(by["señal"], by.n, color=SERIES, height=0.6)
        for y, val in enumerate(by.n):
            ax.annotate(f"{val:,}", xy=(val, y), xytext=(4, -3), textcoords="offset points",
                        fontsize=8, color=INK)
        _style(ax, f"«{top['señal']}» es la señal que más procesos marca", "procesos con alerta", "")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.grid(axis="y", visible=False)
        _save(fig, s.charts / "alertas_por_senal.png")

    rs = s.q("SELECT score FROM risk_scores").score.to_numpy()
    if len(rs):
        _hist(rs, np.arange(0, 102, 2.5), s.charts / "puntaje.png", s.data / "puntaje_histograma.csv",
              f"La mayoría de los procesos con alerta tiene prioridad media o baja; {per((rs >= 50).sum(), len(rs))} es prioridad alta",
              "puntaje de prioridad (0 a 100)", 50, "prioridad alta desde 50", "procesos")


# -- pages ------------------------------------------------------------------------------------------
def home(s: Site, st: dict) -> str:
    t = s.tag
    n_sig = sum(c["level"] == "process" for c in s.controls.values())
    return f"""# Controles sobre las compras públicas del Perú

{AVISO}
{s.banner()}
## Qué es esto

Es un sistema de alertas que revisa las compras del Estado peruano y marca los casos que conviene
mirar con más cuidado: compras partidas para evitar un concurso, concursos con una sola oferta,
contratos que crecen demasiado, precios muy por encima de lo normal, entre otros. Cada alerta
viene con la razón por la que saltó y con lo que un revisor debería pedir primero. Está pensado
para gerentes de logística, de control interno o de administración que necesitan decidir qué
expedientes revisar, sin tener que saber estadística ni programación.

## Una alerta de ejemplo

!!! example "Caso inventado para explicar cómo funciona"
    **Lo que pasó.** Entre el 3 y el 22 de mayo, la *Municipalidad Distrital de Villa Ejemplo
    (entidad inventada)* hizo cinco compras de servicios de transporte a *Transportes Ficticios
    S.A.C. (proveedor inventado)*. Cada una costó entre S/ 36,700 y S/ 40,300, justo debajo de
    S/ 41,200: el monto a partir del cual la ley exige un procedimiento competitivo. Ese monto
    equivale a 8 UIT (Unidad Impositiva Tributaria, un valor de referencia que el Estado fija cada
    año; en 2024 era S/ 5,150).

    **Por qué saltó la señal.** Cinco compras al mismo proveedor, del mismo rubro, en menos de un
    mes y todas pegadas al límite. Juntas suman S/ 192,000, casi cinco veces el límite: si se
    hubieran pedido de una vez, la ley habría exigido un concurso con varios competidores. Por eso
    la señal [{s.controls['C01']['name'].lower()}](senales/{SLUGS['C01']}.md) le dio a cada compra
    prioridad media.

    **Qué haría un revisor.** Pediría los requerimientos de las cinco compras para ver si eran una
    sola necesidad, revisaría quién autorizó cada orden y si hubo cotizaciones de otros
    proveedores. Si era una sola necesidad partida en cinco, es una observación de control. Si
    eran necesidades distintas que surgieron en momentos distintos, archiva la alerta como falsa
    alarma y anota el motivo.

## Las cifras principales

- **Periodo revisado:** de {st['y0']} a {st['y1']} {t}
- **Procesos de compra revisados:** {num(st['total'])}, de los cuales {num(st['competitive'])} fueron concursos abiertos {t}
- **Monto adjudicado:** {soles(st['amount'])} {t}
- **Entidades públicas:** {num(st['entities'])}, que en este sitio solo se muestran agrupadas por tipo {t}
- **Procesos con al menos una alerta:** {num(st['with_alert'])}, es decir {per(st['with_alert'], st['total'])} procesos {t}
- **Procesos de prioridad alta** (los primeros que conviene revisar): {num(st['p1'])} {t}
- **Señales funcionando:** {n_sig} que revisan cada proceso, más una que revisa el conjunto de montos de cada entidad

{_img("assets/charts/alertas_por_senal.png", "Procesos marcados por cada señal",
      "cada barra es una señal y su largo es la cantidad de procesos que marcó. Que una señal marque muchos procesos no la hace más importante: las más frecuentes suelen ser también las que más falsas alarmas dan, y por eso pesan menos en la prioridad.")}
## Por dónde seguir

- [Las señales en lenguaje simple](senales/index.md): qué busca cada una, un ejemplo y qué hacer cuando aparece.
- [¿Funciona?](funciona.md): cómo se comprobó que las señales encuentran lo que deben y cuántas falsas alarmas dan.
- [De dónde salen los datos](datos.md): la fuente, su calidad y lo que este proyecto no es.
- [Glosario](glosario.md): cada término y cada sigla explicados con un ejemplo.
- [Metodología](metodologia/index.md): las fórmulas y decisiones, para quien las quiera.
"""


def _fp_text(s: Site, cid: str) -> str:
    fp = s.fp_share(cid)
    if s.controls[cid]["level"] == "aggregate":
        return "No aplica: revisa el conjunto de montos de cada entidad, no procesos"
    if fp is None:
        return "Sin medir"
    return f"{round(100 * fp)} de cada 100 alertas"


def signals_index(s: Site, st: dict) -> str:
    rows = []
    for cid, c in s.controls.items():
        rows.append({
            "Señal": f"[{c['name']}]({SLUGS[cid]}.md) <small>{cid}</small>",
            "Qué riesgo busca": c["risk_mitigated"].strip(),
            "Ejemplo": c["plain_example_line"],
            "Qué tan seguido es falsa alarma*": _fp_text(s, cid),
            "Qué hacer cuando aparece": c["plain_action"],
        })
    table = _md_table(pd.DataFrame(rows))
    ent = entity_table(s)
    seg = s.q("""SELECT p.segment, count(DISTINCT p.ocid) AS n, count(DISTINCT r.ocid) AS f
                 FROM f_process p LEFT JOIN risk_scores r USING (ocid) GROUP BY 1""")
    seg = seg[seg.n >= 30].copy()
    seg["Rubro"] = seg.segment.map(segment_label)
    seg["Procesos"] = seg.n.map(num)
    seg["Con alerta"] = [per(f, n) for f, n in zip(seg.f, seg.n, strict=True)]
    seg = seg.assign(_r=seg.f / seg.n).sort_values(["_r", "Rubro"], ascending=[False, True])
    meth = s.q("""SELECT p.procurement_method AS m, count(DISTINCT p.ocid) AS n, count(DISTINCT r.ocid) AS f
                  FROM f_process p LEFT JOIN risk_scores r USING (ocid) GROUP BY 1 ORDER BY n DESC, m""")
    meth["Tipo de proceso"] = meth.m.map(lambda x: METHOD_ES.get(x, "otro"))
    meth["Procesos"] = meth.n.map(num)
    meth["Con alerta"] = [per(f, n) for f, n in zip(meth.f, meth.n, strict=True)]
    pr = s.catalog["risk_score"]["review_priority"]
    return f"""# Las señales en lenguaje simple

{AVISO}
{s.banner()}
Cada señal es una regla escrita que revisa todos los procesos de compra y marca los que se salen
de lo normal en un aspecto concreto. Ninguna prueba que haya algo irregular: indica dónde conviene
mirar primero.

{table}

\\* Medido con los casos sembrados en los datos simulados: de cada 100 alertas de la señal, cuántas
cayeron en procesos que no tenían nada raro. Ver [¿Funciona?](../funciona.md).

## Cómo se decide qué revisar primero

Un proceso puede tener varias señales a la vez. Cada señal suma a un puntaje de 0 a 100: las
señales que casi nunca se equivocan suman más y las que dan muchas falsas alarmas suman menos.
Varias señales juntas suben mucho el puntaje, porque es poco probable que todas tengan una
explicación inocente a la vez.

| Prioridad | Puntaje | Qué hacer | Procesos {s.tag} |
|---|---|---|---|
| Alta | {pr['P1'].split('-')[0].strip()} | revisar dentro del ciclo | {num(st['p1'])} |
| Media | {pr['P2'].split(' - ')[0].strip()} | revisar una muestra | {num(st['p2'])} |
| Baja | {pr['P3'].split('-')[0].strip()} | solo seguimiento | {num(st['with_alert'] - st['p1'] - st['p2'])} |

{_img("../assets/charts/puntaje.png", "Distribución del puntaje",
      "cada barra cuenta los procesos con alerta según su puntaje. A la derecha de la línea están los de prioridad alta.")}
## Dónde y cuándo aparecen las alertas

{_img("../assets/charts/tendencia.png", "Procesos con alerta por mes",
      "cada punto es un mes y su altura indica, de cada 100 procesos de ese mes, cuántos tuvieron al menos una alerta. Una subida brusca en un mes merece una pregunta: ¿cambió algo en la forma de comprar o en la publicación de los datos?")}
### Por tipo de entidad

Las entidades se agrupan por tipo; nunca se muestra una entidad individual. Los grupos con menos de
{s.k} entidades se suman a «Otras entidades» para que ninguna se pueda reconocer.

{_md_table(ent)}

### Por tipo de proceso

{_md_table(meth[["Tipo de proceso", "Procesos", "Con alerta"]])}

### Por rubro

Rubros con al menos 30 procesos, ordenados de mayor a menor proporción de alertas.

{_md_table(seg[["Rubro", "Procesos", "Con alerta"]])}
"""


def entity_table(s: Site) -> pd.DataFrame:
    e = s.q("""SELECT p.buyer_id, any_value(pr.buyer_name) AS name, count(DISTINCT p.ocid) AS n,
                      count(DISTINCT r.ocid) AS f
               FROM f_process p
               LEFT JOIN (SELECT ocid, any_value(buyer_name) AS buyer_name FROM processes GROUP BY 1) pr
                      USING (ocid)
               LEFT JOIN risk_scores r USING (ocid) GROUP BY 1""")
    e["tipo"] = e.name.map(entity_type)
    e["entidades"] = 1
    g = e.groupby("tipo", as_index=False)[["entidades", "n", "f"]].sum()
    g = k_anonymous(g, "tipo", "entidades", s.k, ["n", "f"])
    g = g.assign(_r=g.f / g.n).sort_values(["_r", "tipo"], ascending=[False, True])
    g.to_csv(s.data / "alertas_por_tipo_de_entidad.csv", index=False,
             columns=["tipo", "entidades", "n", "f"], header=["tipo", "entidades", "procesos", "con_alerta"])
    return pd.DataFrame({
        "Tipo de entidad": g.tipo, "Entidades": g.entidades.map(num), "Procesos": g.n.map(num),
        "Con alerta": [per(f, n) for f, n in zip(g.f, g.n, strict=True)],
    })


def signal_page(s: Site, cid: str, st: dict, charts: dict) -> str:
    c = s.controls[cid]
    t = s.tag
    checks = "\n".join(f"{k}. {x}" for k, x in enumerate(c["plain_check"], start=1))
    normal = "\n".join(f"- {x}" for x in c["expected_false_positives"]["causes"])
    ch = charts.get(cid)
    if c["level"] == "aggregate":
        b = st["benford"]
        count = (f"Se revisaron {num(b['tested'])} entidades con suficientes montos {t}. Con la regla "
                 f"clásica, {num(b['nigrini'])} parecerían alejarse de Benford; después de descontar lo "
                 f"que el puro azar produce con su cantidad de montos, quedan **{num(b['flagged'])}** {t}. "
                 "Este control nunca marca un contrato: solo sirve para decidir dónde planificar una "
                 "auditoría.")
    else:
        n = st["flagged"].get(cid, 0)
        yrs = st["years"][st["years"].control_id == cid]
        by_year = "; ".join(f"{y}: {num(v)}" for y, v in zip(yrs.year, yrs.n, strict=True))
        count = (f"Marcó **{num(n)} procesos**, es decir {per(n, st['total'])} procesos revisados {t}."
                 + (f" Por año: {by_year}." if by_year else ""))
        if cid == "C01" and st["minor"] == 0:
            count += (" **Esta fuente no incluye compras menores**, así que la señal no tiene con "
                      "qué trabajar: hace falta el registro de órdenes de compra y de servicio.")
        fp = s.fp_share(cid)
        if fp is not None:
            count += (f"\n\nEn la prueba con casos sembrados, de cada 100 alertas de esta señal unas "
                      f"**{round(100 * fp)}** cayeron en procesos que no tenían nada raro "
                      "(ver [¿Funciona?](../funciona.md)).")
    chart = ""
    if ch:
        chart = _img(f"../assets/charts/{ch['img']}", ch["title"], ch["how"])
        if "img2" in ch:
            chart += "\n" + _img(f"../assets/charts/{ch['img2']}", ch["title2"], ch["how2"])
    return f"""# {c['name']}

<small>Señal {cid} · responsable sugerido: {c['owner_role']} · se revisa con frecuencia {c['frequency']}</small>

{AVISO}
{s.banner()}
## Qué busca

{c['plain_what'].strip()}

## Por qué importa

{c['plain_why'].strip()}

## Un ejemplo concreto

!!! example "Caso inventado para explicar la señal"
    {c['plain_example'].strip()}

## Cuántas veces apareció

{count}

{chart}
## Qué revisar primero

{checks}

## Cuándo es normal que salte

Estas situaciones disparan la señal sin que haya nada irregular. Antes de escalar una alerta,
descarte cada una:

{normal}

{technical(s, cid)}"""


def technical(s: Site, cid: str) -> str:
    c = s.controls[cid]
    params = []
    resolved = s.params[cid]
    for name, p in c["parameters"].items():
        val = resolved[name]
        if isinstance(val, dict):
            val = "; ".join(f"{k}: {v.get('value', v) if isinstance(v, dict) else v}" for k, v in val.items())
        origin = (f"`thresholds.yaml: {p['ref']}`" if "ref" in p
                  else "valor del catálogo" + (f" ({p['note']})" if p.get("note") else ""))
        params.append({"parámetro": f"`{name}`", "valor": val, "unidad": p.get("unit", ""),
                       "origen": origin})
    sql = (s.cfg.root / c["sql"]).read_text(encoding="utf-8").strip()
    val = ""
    if s.metrics is not None and cid in set(s.metrics.control_id):
        r = s.metrics.set_index("control_id").loc[cid]
        val = (f"\n**Validación con datos simulados:** casos sembrados {int(r.injected)}, encontrados "
               f"{int(r.detected)}; alertas {int(r.alerts)}, de las cuales {int(r.on_background)} cayeron "
               f"sobre procesos sin patrón sembrado.\n")
    body = f"""**Regla exacta.** {c['rule'].strip()}

**Umbral.** {c['threshold']}

**Objetivo de control.** {c['control_objective'].strip()}

**Evidencia que genera.** {c['evidence']}

**Falsas alarmas esperadas (antes de medir).** {c['expected_false_positives']['rate_band']}

**Peso en el puntaje.** {c['weight']}: {c['weight_rationale']}

**Referencia metodológica.** {c['ocp_reference']}
{val}
**Parámetros**

{_md_table(pd.DataFrame(params))}

**Consulta SQL que ejecuta el motor** (`{c['sql']}`)

```sql
{sql}
```
"""
    return _details("Detalle técnico", body)


def works_page(s: Site) -> str:
    m = s.metrics
    parts = [f"""# ¿Funciona?

{AVISO}
Para saber si una señal funciona hay que conocer la respuesta de antemano, y en los datos reales
nadie la conoce. Por eso se comprobó de dos formas: **sembrando casos de riesgo inventados** en un
conjunto de datos simulados para ver si las señales los encuentran, y **revisando a mano y a
ciegas** una muestra de alertas, como lo haría un auditor.

!!! note "Esta página usa datos simulados"
    Toda esta página se calculó con los datos simulados, incluso cuando el resto del sitio ya
    muestra datos reales: solo en datos simulados se sabe qué casos son irregulares.

## 1. ¿Encuentra los casos sembrados?
"""]
    if m is None:
        parts.append("\nTodavía no hay resultados de validación.\n")
    else:
        lines = []
        for r in m.itertuples():
            name = s.controls[r.control_id]["short_title"].lower()
            found = "los encontró todos" if r.detected == r.injected else f"encontró {r.detected}"
            fp = round(100 * r.background_fp_share)
            if fp >= 60:
                why = "por eso esta señal pesa poco cuando aparece sola"
            elif fp >= 30:
                why = "por eso conviene mirarla junto con otras señales"
            else:
                why = "es de las señales más precisas"
            lines.append(f"- **{s.controls[r.control_id]['short_title']}.** Sembramos {r.injected} casos "
                         f"de {name} y {found}. De cada 100 alertas de esta señal, unas {fp} resultan "
                         f"normales: {why}.")
        parts.append("\n".join(lines) + "\n")
        parts.append("""
Una advertencia importante: **los casos sembrados son más fáciles de encontrar que los reales**,
porque se inventaron limpios y bien marcados. Estas cifras son un techo: en datos reales la
detección será menor.
""")
    if s.priority is not None:
        p = s.priority.set_index("priority")
        p1, p3 = p.loc["P1"], p.loc["P3"]
        parts.append(f"""
## 2. ¿Ordena bien la fila de revisión?

Cada señal sola se equivoca seguido; combinadas, aciertan mucho más. De los procesos que quedaron
en **prioridad alta**, {round(p1.pct_injected)} de cada 100 eran casos sembrados. En **prioridad baja**,
solo {round(p3.pct_injected)} de cada 100. Es decir: si un revisor empieza por la prioridad alta,
casi todo lo que mire valdrá la pena.
""")
    if s.benford_v is not None:
        b = s.benford_v.set_index("scope")
        other = b.loc["other entities"]
        inj = b.loc["injected entity"]
        parts.append(f"""
## 3. ¿Y la prueba de los montos (ley de Benford)?

Una entidad inventada tenía todos sus montos fabricados. Con la regla clásica, {int(other.nigrini_nonconformity)} de
{int(other.scopes_tested)} entidades **normales** habrían parecido sospechosas: con unos cientos de
montos, el puro azar ya produce esas diferencias. Después de descontar el azar, la prueba
{"marcó a la entidad con montos fabricados" if inj.flagged_beyond_noise else "no marcó a la entidad con montos fabricados"}
y {_count_es(int(other.flagged_beyond_noise))}. Sin esa corrección, la prueba habría
acusado al azar.
""")
    if s.dq_v is not None:
        parts.append(f"""
## 4. ¿Detecta los datos defectuosos?

También se sembraron {int(s.dq_v.injected.sum())} errores de datos (procesos duplicados, montos
negativos o absurdos, montos en dólares, fechas imposibles, procesos sin entidad). La revisión de
calidad encontró **{int(s.dq_v.detected.sum())}** y los apartó antes de correr las señales.
""")
    if s.review is not None and "verdict" in s.review:
        rv = s.review.copy()
        blind = rv[rv.blind.astype(bool) & rv.verdict.notna()]
        truth_pos = blind.truly_positive.astype(bool)
        said_pos = blind.verdict.eq("merece revisión")
        agree = int((truth_pos == said_pos).sum())
        fp_total = int((~truth_pos).sum())
        fp_caught = int(((~truth_pos) & (~said_pos)).sum())
        not_blind = rv[~rv.blind.astype(bool)]
        tab = pd.DataFrame({
            "Caso": rv.case,
            "Señal": rv.control_id.map(lambda c: s.controls[c]["short_title"]),
            "Rubro": rv.segment.astype(str).str.zfill(2).map(segment_label),
            "Veredicto del revisor": rv.verdict.fillna(""),
            "Por qué": rv.reason.fillna(""),
            "Qué era en realidad": rv.ground_truth.map(_truth_es) if "ground_truth" in rv else "",
        })
        parts.append(f"""
## 5. Revisión a mano y a ciegas

Se tomaron {len(rv)} alertas al azar (dos de cada señal más las de mayor puntaje). Para cada una se
miró solo lo que un revisor tendría a mano (los montos, las fechas, cómo se compara la entidad con
el resto del país) y se escribió un veredicto **antes** de saber si era un caso sembrado:

- **merece revisión**: el contexto no explica la señal;
- **probable falsa alarma**: el contexto da una explicación normal.

**Resultado.** Los veredictos a ciegas coincidieron con la realidad en **{agree} de {len(blind)}** casos.
De las {fp_total} alertas que en realidad eran falsas alarmas, el revisor descartó {fp_caught} solo con
el contexto; las demás tenían otras señales a la vez y merecían una mirada, como pasaría en una
auditoría real.{f" El caso {', '.join(not_blind.case)} se juzgó después de ver la respuesta y no se cuenta." if len(not_blind) else ""}

**Lo que cambió por esta revisión:** la señal de demora en la firma dejó de mirar las compras
menores, porque una orden de compra no tiene firma de contrato. Además quedó escrito que la señal
de plazo corto no se puede priorizar bien hasta verificar los plazos legales en días hábiles, y que
la señal de postor único se revisa sola solo cuando la entidad está por encima del promedio del país.

{_md_table(tab)}
""")
    parts.append("\nLas tablas completas, con todas las columnas, están en la [metodología](metodologia/index.md).\n")
    return "".join(parts)


def _count_es(n: int) -> str:
    if n == 0:
        return "a ninguna entidad normal"
    return "a 1 entidad normal" if n == 1 else f"a {n} entidades normales"


def _truth_es(v: str) -> str:
    if not isinstance(v, str) or v.startswith("background"):
        return "proceso normal (sin caso sembrado)"
    return ", ".join(PATTERN_ES.get(x, x) for x in v.split("+"))


def data_page(s: Site) -> str:
    dq = pd.read_csv(s.cfg.path("outputs") / "quality" / "dq_summary.csv")
    vol = pd.read_csv(s.cfg.path("outputs") / "quality" / "dq_volumes.csv").set_index("layer")["n"]
    dq_tab = pd.DataFrame({"Problema encontrado": dq.check, "Registros": dq.records.map(num),
                           "Qué se hizo": dq.effect})
    if s.synthetic:
        src = f"""Por ahora, **datos simulados**. Se generaron con un programa que imita la forma en que el
Estado publica sus compras en OCDS (Open Contracting Data Standard, el formato internacional para
publicar datos de contrataciones públicas): convocatorias, ofertas, adjudicaciones, contratos y
modificaciones. Son {num(vol.get('processes kept (one per OCID)', 0))} procesos de 40 entidades
inventadas, en los que se sembraron a propósito casos de riesgo y errores de datos para comprobar
que el sistema los encuentra.

Para que nadie confunda un dato simulado con uno real, los nombres son del tipo «Synthetic
Entity 001» y los números de RUC (Registro Único de Contribuyentes) simulados se construyeron con
un dígito de control inválido: no pueden coincidir con ninguna empresa real.

El generador es simple y deja algunas huellas: por ejemplo, topa los montos de las compras
menores en 97% del límite, lo que crea un pico artificial en el gráfico de compras partidas.

**Los datos reales ya están conectados.** El proyecto incluye un flujo automático que descarga
las compras publicadas por el OECE (Organismo Especializado para las Contrataciones Públicas
Eficientes) desde el registro de Open Contracting Partnership, corre todas las señales y publica
este sitio. Cuando corra, este texto cambiará solo."""
    else:
        dl = s.meta.get("download") or {}
        files = pd.DataFrame([f for f in dl.get("files", [])
                              if f.get("status") in ("descargado", "en caché")])
        ftab = ""
        if len(files):
            ftab = _md_table(pd.DataFrame({
                "Año": files.year, "Tamaño": (files.bytes / 1e6).round(1).astype(str) + " MB",
                "Descargado el": files.downloaded_at.map(fecha)}))
        who = ("el OECE (Organismo Especializado para las Contrataciones Públicas Eficientes), antes "
               "llamado OSCE (Organismo Supervisor de las Contrataciones del Estado), a través del "
               "sistema SEACE (Sistema Electrónico de Contrataciones del Estado)"
               if s.meta.get("source") == "oece" else
               "Perú Compras (la central de compras del Estado, que gestiona los acuerdos marco)")
        src = f"""**{s.label[0].upper() + s.label[1:]}.** Los publica {who}, en formato OCDS (Open
Contracting Data Standard, el formato internacional para publicar datos de contrataciones
públicas), y los distribuye el registro de datos de Open Contracting Partnership.
Son {num(vol.get('processes kept (one per OCID)', 0))} procesos después de quitar duplicados.

{ftab}

Antes de guardar nada, los proveedores que son personas naturales se reemplazan por un código
anónimo: su nombre y su documento no llegan a ninguna tabla ni a este sitio."""
    return f"""# De dónde salen los datos

{AVISO}
{s.banner()}
## La fuente

{src}

## La calidad de los datos

Antes de revisar las compras se revisan los datos: un control es tan bueno como la información
que usa. Estos son los problemas encontrados y qué se hizo con cada uno {s.tag}:

{_md_table(dq_tab)}

Cuando un dato está dañado se aparta solo ese dato: por ejemplo, un monto negativo no se usa para
comparar precios, pero el proceso sigue revisándose en las señales que no usan montos.

## Qué no es este proyecto

- **No es una auditoría ni una acusación.** Una alerta es una razón para mirar un expediente,
  nunca un hallazgo. Muchas alertas tienen explicaciones normales.
- **No es asesoría legal.** Algunos límites legales usados aquí todavía están por verificar en la
  norma oficial (los plazos mínimos para ofertar y el tope de las adendas).
- **No es un ranking.** No hay listas de proveedores, funcionarios ni entidades «más riesgosas», y
  no las habrá.
- **No ve todo.** No tiene datos de apelaciones, no convierte montos en dólares y cuenta los
  plazos en días calendario, no hábiles. Si la fuente no publica las compras menores, la señal de
  compras partidas no puede funcionar.
- **No reemplaza al revisor.** Ordena la fila de expedientes; la conclusión la saca una persona
  con el expediente en la mano.

## Cómo se protegen los datos personales

Los proveedores que son personas naturales (su número de contribuyente empieza con 10, 15 o 17) se reemplazan, al
momento de leer los datos, por un código anónimo que no se puede revertir sin una clave secreta.
Antes de publicar este sitio, una prueba automática revisa que no aparezca el nombre de ningún
proveedor, funcionario o persona, ni el nombre de ninguna entidad pública; si aparece uno, el sitio
no se publica.
"""


GLOSSARY = [
    ("UIT (Unidad Impositiva Tributaria)",
     "Valor de referencia en soles que el Estado fija cada año y que se usa para expresar multas, "
     "impuestos y límites legales.",
     "En 2025 una UIT valía S/ 5,350, así que el límite de 8 UIT para una compra menor era S/ 42,800."),
    ("OCDS (Open Contracting Data Standard)",
     "El formato internacional para publicar datos de contrataciones públicas. Ordena cada compra "
     "en etapas: planificación, convocatoria, ofertas, adjudicación, contrato y ejecución.",
     "Gracias a OCDS, una compra del Perú y una de Colombia se pueden leer con el mismo programa."),
    ("OECE (Organismo Especializado para las Contrataciones Públicas Eficientes)",
     "La entidad que supervisa las contrataciones del Estado peruano desde 2025; antes se llamaba "
     "OSCE (Organismo Supervisor de las Contrataciones del Estado). Publica las compras del SEACE "
     "(Sistema Electrónico de Contrataciones del Estado).",
     "Las licitaciones de un gobierno regional aparecen en el SEACE y el OECE las publica en OCDS."),
    ("Perú Compras",
     "La central de compras del Estado. Gestiona los acuerdos marco: catálogos de productos con "
     "precios ya negociados de los que las entidades compran directamente.",
     "Una municipalidad compra computadoras del catálogo de Perú Compras sin hacer su propio concurso."),
    ("Código UNSPSC (United Nations Standard Products and Services Code)",
     "Un código internacional que clasifica todo lo que se puede comprar. Los dos primeros dígitos "
     "son el «segmento» o rubro; los siguientes afinan hasta el producto.",
     "El segmento 43 es «equipos informáticos y de telecomunicaciones»; dentro de él hay una clase "
     "para computadoras portátiles."),
    ("RUC (Registro Único de Contribuyentes)",
     "El número de 11 dígitos que identifica a una empresa o persona ante la SUNAT (Superintendencia "
     "Nacional de Aduanas y de Administración Tributaria). Si empieza con 10, 15 o 17 es de una "
     "persona natural; si empieza con 20, de una empresa.",
     "Un RUC 20… es de una sociedad; un RUC 10… es de una persona, y aquí se reemplaza por un código anónimo."),
    ("Postor",
     "Empresa o persona que presenta una oferta en un concurso.",
     "Si tres empresas presentan oferta, el concurso tuvo tres postores."),
    ("Adjudicación",
     "La decisión de la entidad que elige al ganador de un concurso. Después viene la firma del contrato.",
     "El comité adjudica el 10 de mayo y el contrato se firma el 20 de mayo."),
    ("Adenda",
     "Una modificación a un contrato ya firmado: más cantidad, más plazo o más monto.",
     "Un contrato de S/ 100,000 con una adenda de S/ 20,000 termina en S/ 120,000: creció 20%."),
    ("Compra menor",
     "Compra de hasta 8 UIT que la ley permite hacer sin un concurso, pidiendo cotizaciones.",
     "Comprar útiles de oficina por S/ 3,000 no requiere licitación."),
    ("Índice de concentración (HHI, índice de Herfindahl-Hirschman)",
     "Un número de 0 a 10,000 que mide qué tan repartido está el gasto entre proveedores. Cerca de 0: "
     "muchos proveedores con partes parecidas. 10,000: un solo proveedor se lleva todo. Por encima "
     "de 2,500 se considera muy concentrado.",
     "Si dos proveedores se reparten un rubro mitad y mitad, el índice es 5,000 (50² + 50²)."),
    ("Ley de Benford",
     "Una regularidad de las cifras naturales: alrededor de 30 de cada 100 empiezan con 1 y menos de "
     "5 de cada 100 con 9. Las cifras inventadas suelen repartir los dígitos de forma más pareja.",
     "Si en una entidad solo 11 de cada 100 montos empiezan con 1, vale la pena preguntar por qué, "
     "pero la diferencia por sí sola no prueba nada."),
    ("Mediana",
     "El valor del medio cuando se ordenan los datos de menor a mayor. A diferencia del promedio, no "
     "la mueven unos pocos valores extremos.",
     "Si cinco entidades pagan S/ 10, 11, 12, 13 y 90 por un mismo artículo, la mediana es S/ 12."),
    ("Falso positivo (falsa alarma)",
     "Una alerta que salta en un caso que resulta normal al revisarlo. Toda señal da algunas; lo "
     "importante es saber cuántas y por qué.",
     "La señal de postor único marca una compra de equipos médicos muy especializados: solo hay un "
     "fabricante en el país, así que es una falsa alarma."),
    ("Caso sembrado",
     "Un caso de riesgo inventado y puesto a propósito en los datos simulados, para comprobar si las "
     "señales lo encuentran.",
     "Se sembraron 102 compras partidas; la señal de compras partidas encontró las 102."),
    ("Puntaje de prioridad",
     "Un número de 0 a 100 que combina las señales de un proceso para decidir qué revisar primero. No "
     "mide culpa: ordena la fila de trabajo.",
     "Un proceso con tres señales a la vez suele quedar en prioridad alta (50 o más)."),
    ("OCP (Open Contracting Partnership)",
     "Una organización internacional que promueve la transparencia en las compras públicas. Creó el "
     "estándar OCDS y mantiene un registro con los datos que publican los países.",
     "Las alertas de este proyecto se basan en su guía de señales de riesgo («banderas rojas»)."),
]


def glossary(s: Site) -> str:
    items = "\n".join(f"## {term}\n\n{definition}\n\n*Ejemplo:* {ex}\n" for term, definition, ex in GLOSSARY)
    return f"""# Glosario

Cada término y cada sigla que aparece en el sitio, explicado en palabras simples y con un ejemplo.

{items}"""


def methodology(s: Site) -> str:
    rs = s.catalog["risk_score"]
    weights = pd.DataFrame([{"señal": c["name"], "código": c["id"], "peso": c["weight"],
                             "por qué": c["weight_rationale"]} for c in s.catalog["controls"]])
    combos = s.q("""SELECT controls AS combinación, count(*) AS procesos, round(avg(score), 1) AS puntaje_medio
                    FROM risk_scores WHERE n_controls >= 2 GROUP BY 1
                    ORDER BY procesos DESC, combinación LIMIT 12""")
    parts = [f"""# Metodología

Esta sección es para quien quiera revisar cómo se calcula todo. El resto del sitio se puede leer
sin ella.

- [Calidad del dato: detalle técnico](calidad.md)
- [Registro de decisiones](decisiones.md): cada decisión de diseño con su porqué.
- El catálogo completo de controles está en `controls/catalog.yaml` y las reglas en `controls/sql/`
  del repositorio.

## Fuente de los datos

{s.label}. Estructura: OCDS (Open Contracting Data Standard), «compiled releases», aplanadas en
tablas relacionales en DuckDB (`processes`, `items`, `parties`, `bids`, `awards`, `contracts`,
`amendments`). Las señales leen una capa limpia (`f_process`, `f_award`, `f_item`, `f_bid`,
`f_contract`) que aplica las revisiones de calidad.

## Puntaje de prioridad

**Fórmula:** `{rs['formula']}`

{rs['rationale'].strip()}

La severidad de cada regla (0 a 1) es la distancia desde su umbral; por ejemplo, una adenda de
+100% con un tope de 25% tiene severidad (1.00 − 0.25) / 0.75 = 1. Por cada proceso entra solo la
alerta más fuerte de cada señal.

{_md_table(weights)}

### Combinaciones de señales más frecuentes

{_md_table(combos)}
"""]
    if s.metrics is not None:
        mt = s.metrics.rename(columns={
            "control_id": "código", "injected_pattern": "patrón sembrado", "injected": "sembrados",
            "detected": "encontrados", "recall": "recall", "alerts": "alertas",
            "on_target_pattern": "sobre su patrón", "on_other_injected_pattern": "sobre otro patrón",
            "on_background": "sobre el fondo", "precision_vs_target": "precisión (su patrón)",
            "background_fp_share": "proporción sobre el fondo",
            "background_alert_rate_pct": "% del fondo marcado"})
        parts.append(f"""
## Validación: tablas completas (datos simulados)

{_md_table(mt)}
""")
    if s.priority is not None:
        parts.append("\n### Casos sembrados por prioridad\n\n" + _md_table(s.priority.rename(columns={
            "priority": "prioridad", "processes": "procesos", "with_injected_pattern": "con caso sembrado",
            "pct_injected": "% sembrado"})) + "\n")
    if s.benford_v is not None:
        parts.append("\n### Benford\n\n" + _md_table(s.benford_v.rename(columns={
            "scope": "alcance", "scopes_tested": "conjuntos probados",
            "nigrini_nonconformity": "no conformes (Nigrini)",
            "flagged_beyond_noise": "marcados más allá del azar", "mean_mad": "MAD media",
            "mean_mad_null": "MAD media esperada por azar"})) + "\n")
    if s.dq_v is not None:
        parts.append("\n### Defectos de datos sembrados\n\n" + _md_table(s.dq_v.rename(columns={
            "defect": "defecto", "check_id": "revisión", "injected": "sembrados", "detected": "encontrados",
            "flagged_total": "marcados en total"})) + "\n")
    return "".join(parts)
