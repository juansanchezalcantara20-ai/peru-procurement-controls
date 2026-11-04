"""Plan C: synthetic OCDS releases for Peruvian-style public procurement.

The generator produces compiled OCDS releases (tender, bids, awards, contracts, amendments) with
a fixed seed, then injects known risk patterns and data-quality defects. Every injection is
recorded in a ground-truth file so the controls can be validated against a known answer.

Nothing here refers to real entities or people:
* buyers and suppliers are called "Synthetic Entity NNN" / "Synthetic Supplier NNNN";
* natural persons are called "Persona Sintética NNNN";
* every RUC is generated with a deliberately *wrong* check digit, so it can never coincide with
  a real taxpayer number;
* the OCID prefix ``ocds-synthpe`` is not a registered prefix.
"""

from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .config import Config

OCID_PREFIX = "ocds-synthpe"

SEGMENTS = {
    # segment code: (label, main category, median unit price PEN, unit)
    "14": ("Paper materials", "goods", 25.0, "ream"),
    "15": ("Fuels and lubricants", "goods", 16.0, "gallon"),
    "42": ("Medical equipment and supplies", "goods", 1800.0, "unit"),
    "43": ("IT and telecom equipment", "goods", 3200.0, "unit"),
    "44": ("Office equipment and supplies", "goods", 140.0, "unit"),
    "50": ("Food and beverages", "goods", 14.0, "kg"),
    "51": ("Drugs and pharmaceuticals", "goods", 38.0, "box"),
    "76": ("Cleaning services", "services", 6200.0, "month"),
    "78": ("Transport services", "services", 2900.0, "trip"),
    "80": ("Management and consulting services", "services", 9000.0, "month"),
    "81": ("Engineering services", "services", 15000.0, "deliverable"),
    "92": ("Security services", "services", 7400.0, "month"),
    "72": ("Construction works", "works", 48000.0, "work package"),
}

# method label: (OCDS procurementMethod, share of processes, mean number of extra bidders)
METHODS = {
    "Contratación menor": ("direct", 0.50, 0.0),
    "Comparación de precios": ("open", 0.08, 1.9),
    "Subasta inversa electrónica": ("open", 0.12, 2.4),
    "Adjudicación simplificada": ("open", 0.17, 1.7),
    "Licitación pública": ("open", 0.04, 2.8),
    "Concurso público": ("open", 0.04, 2.6),
    "Contratación directa": ("limited", 0.05, 0.0),
}
COMPETITIVE = {m for m, v in METHODS.items() if v[0] in ("open", "selective")}

BUYER_TYPES = [
    "Ministry", "Regional Government", "Provincial Municipality", "District Municipality",
    "Public Hospital", "Public University", "Executing Unit", "Regulatory Agency",
]


# ---------------------------------------------------------------------------------------------
# identifiers
# ---------------------------------------------------------------------------------------------
_RUC_WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def ruc_check_digit(first10: str) -> int:
    """Official RUC modulus-11 check digit (SUNAT algorithm)."""
    total = sum(int(d) * w for d, w in zip(first10, _RUC_WEIGHTS, strict=True))
    r = 11 - (total % 11)
    return {10: 0, 11: 1}.get(r, r)


def synthetic_ruc(prefix: str, rng: np.random.Generator) -> str:
    """An 11-digit RUC-shaped string whose check digit is deliberately invalid."""
    body = prefix + "".join(str(d) for d in rng.integers(0, 10, size=8))
    wrong = (ruc_check_digit(body) + 1 + int(rng.integers(0, 8))) % 10
    if wrong == ruc_check_digit(body):  # pragma: no cover - defensive
        wrong = (wrong + 1) % 10
    return body + str(wrong)


def is_valid_ruc(ruc: str) -> bool:
    return len(ruc) == 11 and ruc.isdigit() and ruc_check_digit(ruc[:10]) == int(ruc[10])


# ---------------------------------------------------------------------------------------------
# internal records
# ---------------------------------------------------------------------------------------------
@dataclass
class Bid:
    supplier: str
    amount: float


@dataclass
class Item:
    cls: str
    qty: int
    unit: float


@dataclass
class Proc:
    ocid: str
    buyer: str
    year: int
    segment: str
    method: str
    items: list[Item]
    tender_start: datetime
    tender_end: datetime | None
    bids: list[Bid]
    award_date: datetime
    contract_signed: datetime
    amendments: list[dict] = field(default_factory=list)
    currency: str = "PEN"

    @property
    def estimate(self) -> float:
        return sum(i.qty * i.unit for i in self.items)

    @property
    def winner(self) -> Bid:
        return min(self.bids, key=lambda b: b.amount)

    @property
    def competitive(self) -> bool:
        return self.method in COMPETITIVE


# ---------------------------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------------------------
class SyntheticGenerator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        s = cfg.settings["synthetic"]
        self.rng = np.random.default_rng(int(s["seed"]))
        self.years = [int(y) for y in cfg.settings["years"]]
        self.n_buyers = int(s["n_buyers"])
        self.n_suppliers = int(s["n_suppliers"])
        self.np_share = float(s["natural_person_share"])
        self.ppby = int(s["processes_per_buyer_year"])
        self.uit = cfg.uit_by_year()
        self.simplified_upper_uit = float(
            cfg.thresholds["synthetic_procedure_bands_uit"]["simplified_upper"]
        )
        self.truth: list[dict] = []
        self.dq_truth: list[dict] = []
        self._seq = 0

    # -- helpers ----------------------------------------------------------------------------
    def limit(self, year: int) -> float:
        return self.cfg.minor_limit_pen(year)

    def _ocid(self) -> str:
        self._seq += 1
        return f"{OCID_PREFIX}-{self._seq:06d}"

    def _rand_dt(self, year: int) -> datetime:
        start = datetime(year, 1, 2, 8, 0)
        return start + timedelta(
            days=int(self.rng.integers(0, 355)), minutes=int(self.rng.integers(0, 600))
        )

    # -- master data ------------------------------------------------------------------------
    def build_master(self) -> None:
        rng = self.rng
        self.buyers = []
        for i in range(1, self.n_buyers + 1):
            btype = BUYER_TYPES[(i - 1) % len(BUYER_TYPES)]
            segs = list(rng.choice(list(SEGMENTS), size=int(rng.integers(5, 9)), replace=False))
            self.buyers.append(
                {
                    "id": f"PE-RUC-{synthetic_ruc('20', rng)}",
                    "name": f"Synthetic Entity {i:03d} ({btype})",
                    "type": btype,
                    "segments": segs,
                    "seg_w": rng.dirichlet(np.ones(len(segs)) * 1.5),
                    "size": float(rng.lognormal(0, 0.35)),
                }
            )
        self.suppliers = []
        seg_codes = list(SEGMENTS)
        for j in range(1, self.n_suppliers + 1):
            natural = rng.random() < self.np_share
            prefix = "10" if natural else "20"
            ruc = synthetic_ruc(prefix, rng)
            name = (
                f"Persona Sintética {j:04d}" if natural else f"Synthetic Supplier {j:04d} S.A.C."
            )
            k = 1 if rng.random() < 0.7 else 2
            self.suppliers.append(
                {
                    "id": f"PE-RUC-{ruc}",
                    "ruc": ruc,
                    "name": name,
                    "natural": natural,
                    "segments": list(rng.choice(seg_codes, size=k, replace=False)),
                    "pop": float(rng.pareto(1.6) + 1.0),
                }
            )
        self.by_segment: dict[str, list[dict]] = {s: [] for s in SEGMENTS}
        for sup in self.suppliers:
            for s in sup["segments"]:
                self.by_segment[s].append(sup)
        # buyer-specific affinity to each supplier (gives realistic, uneven market shares)
        self.affinity = {
            b["id"]: rng.gamma(0.6, 1.0, size=len(self.suppliers)) for b in self.buyers
        }
        self.sup_index = {s["id"]: k for k, s in enumerate(self.suppliers)}
        self.classes = {
            seg: [
                (f"{seg}{f:02d}0000", SEGMENTS[seg][2] * float(self.rng.lognormal(0, 0.7)))
                for f in range(10, 16)
            ]
            for seg in SEGMENTS
        }
        self.class_price = {c: p for seg in self.classes.values() for c, p in seg}

    # -- process generation -----------------------------------------------------------------
    def _pick_suppliers(self, buyer: dict, segment: str, n: int) -> list[str]:
        pool = self.by_segment[segment]
        w = np.array(
            [s["pop"] * self.affinity[buyer["id"]][self.sup_index[s["id"]]] for s in pool]
        )
        w = w / w.sum()
        n = min(n, len(pool))
        idx = self.rng.choice(len(pool), size=n, replace=False, p=w)
        return [pool[i]["id"] for i in idx]

    def _target_amount(self, method: str, year: int) -> float:
        rng, uit, lim = self.rng, self.uit[year], self.limit(year)
        if method == "Contratación menor":
            if rng.random() < 0.06:  # legitimately close to the limit
                return float(rng.uniform(0.80, 0.99) * lim)
            return float(min(rng.lognormal(np.log(9000), 0.9), 0.97 * lim))
        if method in ("Licitación pública", "Concurso público"):
            lo, hi = self.simplified_upper_uit * uit, 6000 * uit
        elif method == "Contratación directa":
            lo, hi = lim, 2000 * uit
        else:
            lo, hi = lim * 1.02, self.simplified_upper_uit * uit
        return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))

    def _items(self, segment: str, target: float) -> list[Item]:
        rng = self.rng
        n = 1 if rng.random() < 0.8 else int(rng.integers(2, 4))
        shares = rng.dirichlet(np.ones(n) * 2)
        chosen = rng.choice(len(self.classes[segment]), size=n, replace=False)
        items = []
        for share, ci in zip(shares, chosen, strict=True):
            cls, base = self.classes[segment][ci]
            unit = round(base * float(rng.lognormal(0, 0.33)), 2)
            qty = max(1, int(round(target * share / unit)))
            items.append(Item(cls, qty, unit))
        return items

    def _submission_days(self, method: str) -> int:
        mins = self.cfg.thresholds["min_submission_days"]["by_method"]
        floor = int(mins.get(method, {}).get("value", 15))
        if self.rng.random() < 0.015:  # natural short periods (urgency, data entry, re-calls)
            return max(1, floor - int(self.rng.integers(1, max(2, floor // 2 + 1))))
        return floor + int(self.rng.gamma(2.0, 4.0))

    def new_process(
        self, buyer: dict, year: int, method: str | None = None, segment: str | None = None,
        start: datetime | None = None, target: float | None = None,
        supplier: str | None = None,
    ) -> Proc:
        rng = self.rng
        if segment is None:
            segment = str(rng.choice(buyer["segments"], p=buyer["seg_w"]))
        if method is None:
            labels = list(METHODS)
            p = np.array([METHODS[m][1] for m in labels])
            method = str(rng.choice(labels, p=p / p.sum()))
            if SEGMENTS[segment][1] == "works" and method == "Concurso público":
                method = "Licitación pública"
            if SEGMENTS[segment][1] != "works" and method == "Licitación pública":
                method = "Concurso público" if SEGMENTS[segment][1] == "services" else method
        target = target if target is not None else self._target_amount(method, year)
        items = self._items(segment, target)
        lim = self.limit(year)
        if method == "Contratación menor":
            # keep minor purchases at or below the limit
            while sum(i.qty * i.unit for i in items) > 0.995 * lim:
                big = max(items, key=lambda i: i.qty * i.unit)
                if big.qty > 1:
                    big.qty = max(1, int(big.qty * 0.8))
                else:
                    big.unit = round(big.unit * 0.8, 2)
        start = start or self._rand_dt(year)
        estimate = sum(i.qty * i.unit for i in items)
        if method in COMPETITIVE:
            days = self._submission_days(method)
            end = start + timedelta(days=days)
            n_bids = 1 + int(rng.poisson(METHODS[method][2]))
            bidders = self._pick_suppliers(buyer, segment, n_bids)
            bids = [Bid(s, round(estimate * float(rng.lognormal(-0.05, 0.08)), 2)) for s in bidders]
            award = end + timedelta(days=int(rng.integers(3, 21)))
        else:
            end = None
            who = supplier or self._pick_suppliers(buyer, segment, 1)[0]
            bids = [Bid(who, round(estimate, 2))]
            award = start + timedelta(days=int(rng.integers(0, 4)))
        if supplier and method in COMPETITIVE:
            self.force_winner_bid(bids, supplier)
        if rng.random() < 0.01:
            sign_days = int(rng.integers(30, 95))
        elif method in COMPETITIVE or method == "Contratación directa":
            sign_days = int(min(rng.lognormal(np.log(7), 0.7), 55))
        else:
            sign_days = int(rng.integers(0, 6))
        proc = Proc(
            ocid=self._ocid(), buyer=buyer["id"], year=year, segment=segment, method=method,
            items=items, tender_start=start, tender_end=end, bids=bids, award_date=award,
            contract_signed=award + timedelta(days=sign_days),
        )
        if method in COMPETITIVE and rng.random() < 0.09:
            increase = float(rng.uniform(0.02, 0.24)) if rng.random() > 0.08 else float(
                rng.uniform(0.25, 0.40)
            )
            self._add_amendments(proc, increase)
        # award value rescaling keeps item unit prices consistent with the awarded amount
        return proc

    @staticmethod
    def force_winner_bid(bids: list[Bid], supplier: str) -> None:
        low = min(b.amount for b in bids)
        mine = [b for b in bids if b.supplier == supplier]
        if mine:
            mine[0].amount = round(low * 0.98, 2)
        else:
            loser = max(bids, key=lambda b: b.amount)
            loser.supplier = supplier
            loser.amount = round(low * 0.98, 2)

    def _add_amendments(self, proc: Proc, increase: float) -> None:
        base = proc.winner.amount
        n = 1 if self.rng.random() < 0.7 else 2
        steps = np.sort(self.rng.uniform(0, 1, size=n - 1)).tolist() + [1.0]
        when = proc.contract_signed
        proc.amendments = []
        for k, frac in enumerate(steps, start=1):
            when = when + timedelta(days=int(self.rng.integers(20, 120)))
            proc.amendments.append(
                {
                    "id": f"{proc.ocid}-amend-{k}",
                    "date": when,
                    "new_total": round(base * (1 + increase * frac), 2),
                    "description": "Additional goods/services and deadline extension",
                }
            )

    def generate_background(self) -> list[Proc]:
        procs: list[Proc] = []
        for year in self.years:
            for buyer in self.buyers:
                n = int(self.rng.poisson(self.ppby * buyer["size"]))
                procs.extend(self.new_process(buyer, year) for _ in range(n))
        return procs

    # -- risk-pattern injection -------------------------------------------------------------
    def _mark(self, pattern: str, ocid: str, note: str = "") -> None:
        self.truth.append({"pattern": pattern, "ocid": ocid, "note": note})

    def inject(self, procs: list[Proc]) -> list[Proc]:
        rng = self.rng
        used: set[str] = set()
        buyers = {b["id"]: b for b in self.buyers}

        def pick(cands: list[Proc], n: int) -> list[Proc]:
            cands = [p for p in cands if p.ocid not in used]
            idx = rng.choice(len(cands), size=min(n, len(cands)), replace=False)
            chosen = [cands[i] for i in idx]
            used.update(p.ocid for p in chosen)
            return chosen

        competitive = [p for p in procs if p.competitive]

        # Benford: one buyer whose amounts are "invented" (leading digits ~ uniform)
        sizes: dict[str, int] = {}
        for p in procs:
            sizes[p.buyer] = sizes.get(p.buyer, 0) + 1
        benford_buyer = buyers[max(sizes, key=sizes.get)]  # largest buyer: enough amounts to test
        self.benford_buyer = benford_buyer["id"]
        for p in procs:
            if p.buyer != benford_buyer["id"]:
                continue
            old = p.estimate
            k = int(np.floor(np.log10(max(old, 1.0))))
            cap = 0.995 * self.limit(p.year) if p.method == "Contratación menor" else np.inf
            for _ in range(50):
                new = float(rng.uniform(1, 10)) * 10**k
                if new <= cap:
                    break
            else:
                new = float(rng.uniform(1, cap / 10**k)) * 10**k
            factor = new / old
            for it in p.items:
                it.unit = round(it.unit * factor, 2)
            for b in p.bids:
                b.amount = round(b.amount * factor, 2)
            for a in p.amendments:
                a["new_total"] = round(a["new_total"] * factor, 2)
            used.add(p.ocid)
            self._mark("benford_fabricated_amounts", p.ocid, "buyer-level pattern")

        # 1. split purchases: clusters of 3-5 minor purchases just under the limit
        for c in range(25):
            buyer = self.buyers[int(rng.integers(0, len(self.buyers)))]
            while buyer["id"] == self.benford_buyer:
                buyer = self.buyers[int(rng.integers(0, len(self.buyers)))]
            year = int(rng.choice(self.years))
            segment = str(rng.choice(buyer["segments"]))
            supplier = self._pick_suppliers(buyer, segment, 1)[0]
            start = self._rand_dt(year)
            for k in range(int(rng.integers(3, 6))):
                when = start + timedelta(days=int(rng.integers(0, 21)), hours=k)
                target = float(rng.uniform(0.85, 0.985)) * self.limit(year)
                p = self.new_process(
                    buyer, year, method="Contratación menor", segment=segment, start=when,
                    target=target, supplier=supplier,
                )
                # set the exact amount just under the limit
                tot = p.estimate
                for it in p.items:
                    it.unit = round(it.unit * target / tot, 2)
                p.bids = [Bid(supplier, round(p.estimate, 2))]
                procs.append(p)
                used.add(p.ocid)
                self._mark("split_purchase", p.ocid, f"cluster {c:02d}")

        # 2. single bidder in competitive processes
        for p in pick([p for p in competitive if len(p.bids) >= 2], 60):
            p.bids = [p.winner]
            self._mark("single_bid", p.ocid)

        # 3. abnormally short submission period
        for p in pick(competitive, 50):
            p.tender_end = p.tender_start + timedelta(days=int(rng.integers(1, 4)), hours=3)
            if p.award_date < p.tender_end:
                p.award_date = p.tender_end + timedelta(days=3)
                p.contract_signed = p.award_date + timedelta(days=5)
            self._mark("short_submission_period", p.ocid)

        # 4. concentration: one supplier takes ~85% of a buyer x segment x year cell
        cells: dict[tuple, list[Proc]] = {}
        for p in procs:
            if p.ocid not in used and p.buyer != self.benford_buyer:
                cells.setdefault((p.buyer, p.segment, p.year), []).append(p)
        big = [k for k, v in cells.items() if len(v) >= 18]
        for ci in rng.choice(len(big), size=min(6, len(big)), replace=False):
            key = big[ci]
            buyer = buyers[key[0]]
            dominant = self._pick_suppliers(buyer, key[1], 1)[0]
            for p in cells[key]:
                if p.ocid in used or rng.random() > 0.85:
                    continue
                if p.competitive:
                    self.force_winner_bid(p.bids, dominant)
                else:
                    p.bids = [Bid(dominant, p.bids[0].amount)]
                used.add(p.ocid)
                self._mark("supplier_concentration", p.ocid, f"{key[1]}-{key[2]}")

        # 5. same winner repeated at the same buyer (competitive processes)
        for _ in range(10):
            buyer = self.buyers[int(rng.integers(0, len(self.buyers)))]
            if buyer["id"] == self.benford_buyer:
                continue
            year = int(rng.choice(self.years))
            pool = [
                p for p in competitive if p.buyer == buyer["id"] and p.year == year
                and len(p.bids) >= 2
            ]
            if len(pool) < 10:
                continue
            seg = pool[0].segment
            supplier = self._pick_suppliers(buyer, seg, 1)[0]
            for p in pick(pool, int(rng.integers(7, 11))):
                self.force_winner_bid(p.bids, supplier)
                self._mark("repeated_winner", p.ocid, supplier[-6:])

        # 6. amendments that raise the amount well above the cap
        for p in pick([p for p in competitive if not p.amendments], 30):
            self._add_amendments(p, float(rng.uniform(0.35, 1.2)))
            self._mark("amendment_increase", p.ocid)

        # 7. unit price outliers vs. category median
        for p in pick(competitive, 40):
            it = p.items[int(rng.integers(0, len(p.items)))]
            factor = float(rng.uniform(4, 12))
            added = it.qty * it.unit * (factor - 1)
            it.unit = round(it.unit * factor, 2)
            for b in p.bids:
                b.amount = round(b.amount + added, 2)
            self._mark("price_outlier", p.ocid, f"x{factor:.1f}")

        # 9. abnormal award-to-signature time
        for p in pick(competitive, 30):
            p.contract_signed = p.award_date + timedelta(days=int(rng.integers(90, 221)))
            for k, a in enumerate(p.amendments):
                a["date"] = p.contract_signed + timedelta(days=30 * (k + 1))
            self._mark("award_signature_delay", p.ocid)

        self.used = used
        return procs

    # -- OCDS rendering ---------------------------------------------------------------------
    def to_release(self, p: Proc) -> dict:
        sup = {s["id"]: s for s in self.suppliers}
        buyer = next(b for b in self.buyers if b["id"] == p.buyer)
        win = p.winner
        award_amount = win.amount
        scale = award_amount / p.estimate if p.estimate else 1.0
        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S-05:00")  # noqa: E731
        party_ids = {b.supplier for b in p.bids}
        parties = [
            {
                "id": buyer["id"], "name": buyer["name"],
                "identifier": {"scheme": "PE-RUC", "id": buyer["id"].split("-")[-1]},
                "roles": ["buyer", "procuringEntity"],
            }
        ]
        for sid in sorted(party_ids):
            s = sup[sid]
            roles = ["tenderer"] + (["supplier"] if sid == win.supplier else [])
            parties.append(
                {
                    "id": sid, "name": s["name"],
                    "identifier": {"scheme": "PE-RUC", "id": s["ruc"]}, "roles": roles,
                }
            )
        items = [
            {
                "id": str(k), "description": f"{SEGMENTS[p.segment][0]} - class {it.cls}",
                "classification": {"scheme": "UNSPSC", "id": it.cls},
                "quantity": it.qty,
                "unit": {"name": SEGMENTS[p.segment][3],
                         "value": {"amount": it.unit, "currency": p.currency}},
            }
            for k, it in enumerate(p.items, start=1)
        ]
        award_items = [
            {**i, "unit": {**i["unit"], "value": {
                "amount": round(i["unit"]["value"]["amount"] * scale, 2),
                "currency": p.currency}}}
            for i in items
        ]
        tender = {
            "id": f"{p.ocid}-tender",
            "title": f"{SEGMENTS[p.segment][0]} for Synthetic Entity",
            "status": "complete",
            "procurementMethod": METHODS[p.method][0],
            "procurementMethodDetails": p.method,
            "mainProcurementCategory": SEGMENTS[p.segment][1],
            "value": {"amount": round(p.estimate, 2), "currency": p.currency},
            "numberOfTenderers": len(p.bids),
            "tenderers": [{"id": b.supplier, "name": sup[b.supplier]["name"]} for b in p.bids],
            "items": items,
            "datePublished": iso(p.tender_start),
        }
        if p.tender_end is not None:
            tender["tenderPeriod"] = {"startDate": iso(p.tender_start), "endDate": iso(p.tender_end)}
        bids = {
            "details": [
                {
                    "id": f"{p.ocid}-bid-{k}", "status": "valid",
                    "date": iso(p.tender_end or p.tender_start),
                    "tenderers": [{"id": b.supplier, "name": sup[b.supplier]["name"]}],
                    "value": {"amount": b.amount, "currency": p.currency},
                }
                for k, b in enumerate(p.bids, start=1)
            ]
        }
        award_id = f"{p.ocid}-award-1"
        contract = {
            "id": f"{p.ocid}-contract-1", "awardID": award_id, "status": "active",
            "dateSigned": iso(p.contract_signed),
            "value": {"amount": award_amount, "currency": p.currency},
        }
        if p.amendments:
            contract["amendments"] = [
                {
                    "id": a["id"], "date": iso(a["date"]), "description": a["description"],
                    # Synthetic extension field: contract total after the amendment.
                    "x_amendedValue": {"amount": a["new_total"], "currency": p.currency},
                }
                for a in p.amendments
            ]
        last = max([p.contract_signed] + [a["date"] for a in p.amendments])
        return {
            "ocid": p.ocid, "id": f"{p.ocid}-{last:%Y%m%d}", "date": iso(last),
            "tag": ["compiled"], "initiationType": "tender",
            "parties": parties,
            "buyer": {"id": buyer["id"], "name": buyer["name"]},
            "tender": tender, "bids": bids,
            "awards": [{
                "id": award_id, "status": "active", "date": iso(p.award_date),
                "value": {"amount": award_amount, "currency": p.currency},
                "suppliers": [{"id": win.supplier, "name": sup[win.supplier]["name"]}],
                "items": award_items,
            }],
            "contracts": [contract],
        }

    # -- data-quality defects ---------------------------------------------------------------
    def inject_dq(self, releases: list[dict]) -> list[dict]:
        rng = self.rng
        clean = [r for r in releases if r["ocid"] not in self.used]
        order = rng.permutation(len(clean)).tolist()
        cursor = iter(order)

        def take(n: int) -> list[dict]:
            return [clean[next(cursor)] for _ in range(n)]

        def mark(check: str, r: dict) -> None:
            self.dq_truth.append({"defect": check, "ocid": r["ocid"]})

        for r in take(10):
            r["awards"][0]["value"]["amount"] *= -1
            mark("negative_award_amount", r)
        for r in take(5):
            r["awards"][0]["value"]["amount"] *= 1_000_000
            mark("absurd_award_amount", r)
        for r in take(12):
            if "tenderPeriod" in r["tender"]:
                tp = r["tender"]["tenderPeriod"]
                tp["endDate"], tp["startDate"] = tp["startDate"], tp["endDate"]
                mark("tender_end_before_start", r)
        for r in take(10):
            r["contracts"][0]["dateSigned"] = "2019-01-01T00:00:00-05:00"
            mark("contract_signed_before_award", r)
        for r in take(8):
            r["buyer"] = {"name": r["buyer"]["name"]}
            mark("missing_buyer_id", r)
        for r in take(6):
            r["awards"][0]["value"]["currency"] = "USD"
            mark("non_pen_currency", r)
        for r in take(15):
            releases.append(json.loads(json.dumps(r)))
            mark("duplicate_ocid", r)
        return releases

    # -- main -------------------------------------------------------------------------------
    def run(self, out_dir: Path) -> dict:
        self.build_master()
        procs = self.inject(self.generate_background())
        releases = [self.to_release(p) for p in procs]
        releases = self.inject_dq(releases)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "releases.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            for r in releases:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        _write_csv(out_dir / "ground_truth.csv", self.truth, ["pattern", "ocid", "note"])
        _write_csv(out_dir / "dq_ground_truth.csv", self.dq_truth, ["defect", "ocid"])
        return {
            "releases": len(releases), "processes": len(procs),
            "injected": len(self.truth), "dq_defects": len(self.dq_truth), "path": str(path),
        }


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def generate(cfg: Config, out_dir: Path | None = None) -> dict:
    out_dir = out_dir or cfg.path("raw_dir") / "synthetic"
    return SyntheticGenerator(cfg).run(out_dir)


if __name__ == "__main__":  # pragma: no cover
    print(generate(Config.load()))
