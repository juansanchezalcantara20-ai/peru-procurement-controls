"""Tiny OCDS fixtures for unit tests: build releases by hand and load them into DuckDB."""

from __future__ import annotations

import duckdb

from procontrol.ingest import flatten, load
from procontrol.privacy import Pseudonymiser
from procontrol.quality import run_quality

BUYER = "PE-RUC-20000000001"


def iso(day: str, hour: int = 10) -> str:
    return f"{day}T{hour:02d}:00:00-05:00"


def release(
    ocid: str,
    *,
    buyer: str | None = BUYER,
    method: str = "open",
    details: str = "Adjudicación simplificada",
    supplier: str = "PE-RUC-20111111110",
    supplier_name: str = "Company A",
    bidders: list[str] | None = None,
    amount: float = 100_000.0,
    tender_amount: float | None = None,
    currency: str = "PEN",
    published: str = "2025-03-01",
    tender_days: int | None = 20,
    award: str | None = None,
    signed: str | None = None,
    cls: str = "43100000",
    qty: float = 10,
    unit: float | None = None,
    amendments: list[tuple[str, float]] | None = None,
) -> dict:
    import datetime as dt

    start = dt.date.fromisoformat(published)
    end = start + dt.timedelta(days=tender_days) if tender_days is not None else None
    award = award or str((end or start) + dt.timedelta(days=5))
    signed = signed or str(dt.date.fromisoformat(award) + dt.timedelta(days=5))
    bidders = bidders if bidders is not None else [supplier]
    unit = unit if unit is not None else amount / qty
    tender = {
        "id": f"{ocid}-t", "procurementMethod": method, "procurementMethodDetails": details,
        "mainProcurementCategory": "goods",
        "value": {"amount": tender_amount or amount, "currency": "PEN"},
        "numberOfTenderers": len(bidders),
        "tenderers": [{"id": b, "name": b} for b in bidders],
        "datePublished": iso(published),
    }
    if end is not None:
        tender["tenderPeriod"] = {"startDate": iso(published), "endDate": iso(str(end))}
    contract = {"id": f"{ocid}-c", "awardID": f"{ocid}-a", "dateSigned": iso(signed),
                "value": {"amount": amount, "currency": "PEN"}}
    if amendments:
        contract["amendments"] = [
            {"id": f"{ocid}-am{k}", "date": iso(d), "x_amendedValue": {"amount": v}}
            for k, (d, v) in enumerate(amendments)
        ]
    parties = [{"id": b, "name": supplier_name if b == supplier else b,
                "identifier": {"scheme": "PE-RUC", "id": b.split("-")[-1]},
                "roles": ["tenderer"]} for b in bidders]
    if buyer:
        parties.append({"id": buyer, "name": "Entity", "roles": ["buyer"]})
    return {
        "ocid": ocid, "id": f"{ocid}-r", "date": iso(signed), "tag": ["compiled"],
        "parties": parties,
        "buyer": {"id": buyer, "name": "Entity"} if buyer else {"name": "Entity"},
        "tender": tender,
        "bids": {"details": [
            {"id": f"{ocid}-b{k}", "tenderers": [{"id": b}],
             "value": {"amount": amount if b == supplier else amount * 1.1, "currency": "PEN"}}
            for k, b in enumerate(bidders)
        ]},
        "awards": [{
            "id": f"{ocid}-a", "date": iso(award), "status": "active",
            "value": {"amount": amount, "currency": currency},
            "suppliers": [{"id": supplier, "name": supplier_name}],
            "items": [{"id": "1", "classification": {"scheme": "UNSPSC", "id": cls},
                       "quantity": qty, "unit": {"value": {"amount": unit, "currency": "PEN"}}}],
        }],
        "contracts": [contract],
    }


def warehouse(releases: list[dict], key: str = "test-key") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    load(con, flatten(releases, Pseudonymiser(key=key)))
    run_quality(con)
    return con
