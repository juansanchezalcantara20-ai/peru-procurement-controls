"""Flatten OCDS compiled releases (JSON Lines) into relational tables in DuckDB.

Tables (one row per object, every row keyed by ``release_key`` = line number in the source so
duplicate releases stay visible to the data-quality step):

    releases    ocid, release_id, release_date
    processes   tender-level fields (buyer, method, category, tender value and period)
    items       awarded items (fallback: tender items) with classification, quantity, unit price
    parties     every party in the release, natural persons already pseudonymised
    bids        bids.details (fallback: tender.tenderers without amounts)
    awards      one row per award x supplier
    contracts   contracts with their awardID and signature date
    amendments  contract amendments with the amended total when published

Natural persons are pseudonymised here, before the first write (see ``privacy.py``).
"""

from __future__ import annotations

import gzip
import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

import duckdb
import pandas as pd

from .privacy import Pseudonymiser

log = logging.getLogger(__name__)

SCHEMA = {
    "releases": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("release_id", "VARCHAR"),
        ("release_date", "TIMESTAMP"),
    ],
    "processes": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("buyer_id", "VARCHAR"),
        ("buyer_name", "VARCHAR"), ("tender_id", "VARCHAR"), ("title", "VARCHAR"),
        ("procurement_method", "VARCHAR"), ("method_details", "VARCHAR"),
        ("main_category", "VARCHAR"), ("tender_amount", "DOUBLE"), ("tender_currency", "VARCHAR"),
        ("date_published", "TIMESTAMP"), ("tender_start", "TIMESTAMP"), ("tender_end", "TIMESTAMP"),
        ("number_of_tenderers", "INTEGER"), ("tender_status", "VARCHAR"),
    ],
    "items": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("source", "VARCHAR"),
        ("award_id", "VARCHAR"), ("item_id", "VARCHAR"), ("classification_id", "VARCHAR"),
        ("description", "VARCHAR"), ("quantity", "DOUBLE"), ("unit_amount", "DOUBLE"),
        ("currency", "VARCHAR"),
    ],
    "parties": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("party_id", "VARCHAR"),
        ("name", "VARCHAR"), ("ruc", "VARCHAR"), ("roles", "VARCHAR"),
        ("is_natural_person", "BOOLEAN"),
    ],
    "bids": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("bid_id", "VARCHAR"),
        ("supplier_id", "VARCHAR"), ("amount", "DOUBLE"), ("currency", "VARCHAR"),
        ("bid_date", "TIMESTAMP"), ("status", "VARCHAR"),
    ],
    "awards": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("award_id", "VARCHAR"),
        ("supplier_id", "VARCHAR"), ("amount", "DOUBLE"), ("currency", "VARCHAR"),
        ("award_date", "TIMESTAMP"), ("status", "VARCHAR"),
    ],
    "contracts": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("contract_id", "VARCHAR"),
        ("award_id", "VARCHAR"), ("amount", "DOUBLE"), ("currency", "VARCHAR"),
        ("date_signed", "TIMESTAMP"), ("status", "VARCHAR"),
    ],
    "amendments": [
        ("release_key", "BIGINT"), ("ocid", "VARCHAR"), ("contract_id", "VARCHAR"),
        ("amendment_id", "VARCHAR"), ("amendment_date", "TIMESTAMP"),
        ("amended_amount", "DOUBLE"), ("description", "VARCHAR"),
    ],
}


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    for table, cols in SCHEMA.items():
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {t}' for c, t in cols)})")


def _amount(obj: dict | None) -> tuple[float | None, str | None]:
    if not isinstance(obj, dict):
        return None, None
    amt = obj.get("amount")
    try:
        amt = float(amt) if amt is not None else None
    except (TypeError, ValueError):
        amt = None
    return amt, obj.get("currency")


def _ts(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/Lima").tz_localize(None)
    return ts


def iter_releases(paths: Iterable[Path]) -> Iterator[dict]:
    """Yield releases from JSON Lines(.gz) files. Malformed lines are skipped and counted; a
    truncated archive stops with a clear message."""
    for path in paths:
        opener = gzip.open if str(path).endswith(".gz") else open
        bad = 0
        try:
            with opener(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        bad += 1
                        continue
                    # Accept release packages and record packages as well as bare releases.
                    if "releases" in obj and isinstance(obj["releases"], list):
                        yield from obj["releases"]
                    elif "records" in obj:
                        for rec in obj["records"]:
                            if "compiledRelease" in rec:
                                yield rec["compiledRelease"]
                    else:
                        yield obj
        except (EOFError, OSError) as exc:
            raise RuntimeError(f"El archivo {path.name} está incompleto o dañado ({exc}). "
                               "Bórrelo de data/raw y vuelva a descargarlo.") from exc
        if bad:
            log.warning("%s: se omitieron %s líneas que no eran JSON válido.", path.name, bad)


def flatten(releases: Iterable[dict], pseudo: Pseudonymiser, names: set[str] | None = None,
            start: int = 1) -> dict[str, list[tuple]]:
    """Flatten releases. If ``names`` is given, every person/organisation name seen in the raw
    data (parties, contact points, buyer, tenderers, suppliers) is added to it, before
    pseudonymisation, so the privacy gate can later check that none reaches the site."""
    rows: dict[str, list[tuple]] = {t: [] for t in SCHEMA}
    for key, rel in enumerate(releases, start=start):
        ocid = rel.get("ocid")
        if names is not None:
            _collect_names(rel, names)
        rows["releases"].append((key, ocid, rel.get("id"), _ts(rel.get("date"))))

        # parties first, so references can be resolved (and pseudonymised) consistently
        resolved: dict[str, str] = {}
        for party in rel.get("parties") or []:
            ident = party.get("identifier") or {}
            p = pseudo.party(party.get("id"), party.get("name"), ident.get("scheme"),
                             ident.get("id"))
            resolved[party.get("id")] = p.id
            rows["parties"].append((key, ocid, p.id, p.name, p.ruc,
                                    "|".join(party.get("roles") or []), p.is_natural_person))

        def ref(org: dict | None, _resolved: dict = resolved) -> str | None:
            if not org:
                return None
            pid = org.get("id")
            if pid in _resolved:
                return _resolved[pid]
            return pseudo.party(pid, org.get("name"), None, None).id or None

        buyer = rel.get("buyer") or {}
        tender = rel.get("tender") or {}
        tp = tender.get("tenderPeriod") or {}
        t_amt, t_cur = _amount(tender.get("value"))
        n_ten = tender.get("numberOfTenderers")
        rows["processes"].append((
            key, ocid, buyer.get("id"), buyer.get("name"), tender.get("id"), tender.get("title"),
            tender.get("procurementMethod"), tender.get("procurementMethodDetails"),
            tender.get("mainProcurementCategory"), t_amt, t_cur,
            _ts(tender.get("datePublished")), _ts(tp.get("startDate")), _ts(tp.get("endDate")),
            int(n_ten) if isinstance(n_ten, int | float) else None, tender.get("status"),
        ))

        details = (rel.get("bids") or {}).get("details") or []
        if details:
            for bid in details:
                amt, cur = _amount(bid.get("value"))
                for org in bid.get("tenderers") or [None]:
                    rows["bids"].append((key, ocid, bid.get("id"), ref(org), amt, cur,
                                         _ts(bid.get("date")), bid.get("status")))
        else:
            for k, org in enumerate(tender.get("tenderers") or [], start=1):
                rows["bids"].append((key, ocid, f"tenderer-{k}", ref(org), None, None, None,
                                     None))

        award_items_seen = False
        for award in rel.get("awards") or []:
            amt, cur = _amount(award.get("value"))
            for org in award.get("suppliers") or [None]:
                rows["awards"].append((key, ocid, award.get("id"), ref(org), amt, cur,
                                       _ts(award.get("date")), award.get("status")))
            for it in award.get("items") or []:
                award_items_seen = True
                rows["items"].append(_item_row(key, ocid, "award", award.get("id"), it))
        if not award_items_seen:
            for it in tender.get("items") or []:
                rows["items"].append(_item_row(key, ocid, "tender", None, it))

        for c in rel.get("contracts") or []:
            amt, cur = _amount(c.get("value"))
            rows["contracts"].append((key, ocid, c.get("id"), c.get("awardID"), amt, cur,
                                      _ts(c.get("dateSigned")), c.get("status")))
            for a in c.get("amendments") or []:
                a_amt, _ = _amount(a.get("x_amendedValue") or a.get("value"))
                rows["amendments"].append((key, ocid, c.get("id"), a.get("id"),
                                           _ts(a.get("date")), a_amt, a.get("description")))
    return rows


def _item_row(key: int, ocid: str, source: str, award_id: str | None, it: dict) -> tuple:
    cls = (it.get("classification") or {}).get("id")
    unit_amt, cur = _amount((it.get("unit") or {}).get("value"))
    qty = it.get("quantity")
    try:
        qty = float(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty = None
    return (key, ocid, source, award_id, it.get("id"), cls, it.get("description"), qty,
            unit_amt, cur)


def _collect_names(rel: dict, names: set[str]) -> None:
    for party in rel.get("parties") or []:
        if party.get("name"):
            names.add(party["name"])
        cp = party.get("contactPoint") or {}
        if cp.get("name"):
            names.add(cp["name"])
    for org in [rel.get("buyer") or {}, *((rel.get("tender") or {}).get("tenderers") or [])]:
        if org.get("name"):
            names.add(org["name"])
    for award in rel.get("awards") or []:
        for org in award.get("suppliers") or []:
            if org.get("name"):
                names.add(org["name"])


def load(con: duckdb.DuckDBPyConnection, rows: dict[str, list[tuple]],
         create: bool = True) -> dict[str, int]:
    if create:
        create_schema(con)
    counts = {}
    for table, cols in SCHEMA.items():
        df = pd.DataFrame(rows[table], columns=[c for c, _ in cols])
        if len(df):
            con.register("_df", df)
            con.execute(f"INSERT INTO {table} SELECT * FROM _df")
            con.unregister("_df")
        counts[table] = len(df)
    return counts


def ingest_files(con: duckdb.DuckDBPyConnection, paths: list[Path], pseudo: Pseudonymiser,
                 names: set[str] | None = None, batch: int = 20_000) -> dict[str, int]:
    """Stream the files in batches so multi-GB real publications fit in memory."""
    create_schema(con)
    totals = dict.fromkeys(SCHEMA, 0)
    chunk: list[dict] = []
    key = 1

    def flush() -> None:
        nonlocal key
        counts = load(con, flatten(chunk, pseudo, names, start=key), create=False)
        for t, n in counts.items():
            totals[t] += n
        key += len(chunk)
        chunk.clear()

    for rel in iter_releases(paths):
        chunk.append(rel)
        if len(chunk) >= batch:
            flush()
    if chunk:
        flush()
    return totals
