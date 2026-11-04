"""Every signal has small synthetic cases that must fire and cases that must not."""

import math

import numpy as np
import pytest
from helpers import release, warehouse

from procontrol.config import Config
from procontrol.engine import Control, build_reference_tables, load_catalog, resolve_params, run_control

CFG = Config.load()
CATALOG = load_catalog(CFG)
LIMIT_2025 = CFG.minor_limit_pen(2025)  # 8 UIT x 5,350


def fire(releases, control_id):
    con = warehouse(releases)
    build_reference_tables(con, CFG, CATALOG)
    spec = next(c for c in CATALOG["controls"] if c["id"] == control_id)
    return run_control(con, CFG, Control(spec, resolve_params(spec, CFG)))


def flagged(releases, control_id):
    return set(fire(releases, control_id)["ocid"])


def minor(ocid, day, amount, supplier="PE-RUC-20111111110", cls="44100000"):
    return release(ocid, method="direct", details="Contratación menor", supplier=supplier,
                   amount=amount, published=day, tender_days=None, cls=cls)


# C01 split purchases ------------------------------------------------------------------------
def test_c01_fires_on_cluster_just_below_limit():
    rels = [minor(f"s{k}", f"2025-05-{1 + 4 * k:02d}", 0.92 * LIMIT_2025) for k in range(3)]
    assert flagged(rels, "C01") == {"s0", "s1", "s2"}


def test_c01_quiet_when_spread_out_small_or_different_supplier():
    spread = [minor(f"s{k}", f"2025-{1 + 3 * k:02d}-01", 0.92 * LIMIT_2025) for k in range(3)]
    small = [minor(f"m{k}", f"2025-05-{1 + k:02d}", 0.40 * LIMIT_2025) for k in range(3)]
    other = [minor(f"o{k}", f"2025-05-{1 + k:02d}", 0.92 * LIMIT_2025, supplier=f"PE-RUC-2011111111{k}")
             for k in range(3)]
    assert flagged(spread + small + other, "C01") == set()


def test_c01_two_purchases_are_not_enough():
    rels = [minor(f"s{k}", f"2025-05-{1 + k:02d}", 0.95 * LIMIT_2025) for k in range(2)]
    assert flagged(rels, "C01") == set()


# C02 single bid ----------------------------------------------------------------------------
def test_c02_single_bid():
    rels = [
        release("one", bidders=["PE-RUC-20111111110"]),
        release("two", bidders=["PE-RUC-20111111110", "PE-RUC-20222222220"]),
        release("direct", method="direct", details="Contratación directa"),
    ]
    assert flagged(rels, "C02") == {"one"}


# C03 short submission period ---------------------------------------------------------------
def test_c03_short_period_uses_method_minimum():
    rels = [
        release("short", details="Licitación pública", tender_days=5),
        release("ok", details="Licitación pública", tender_days=30),
        release("subasta_ok", details="Subasta inversa electrónica", tender_days=6),
        release("unknown_short", details="Other method", tender_days=7),   # default 15
        release("direct", method="direct", tender_days=1),
    ]
    assert flagged(rels, "C03") == {"short", "unknown_short"}


# C04 concentration -------------------------------------------------------------------------
def _cell(prefix, suppliers):
    return [release(f"{prefix}{k}", supplier=s, amount=50_000, published=f"2025-{1 + k % 12:02d}-03")
            for k, s in enumerate(suppliers)]


def test_c04_fires_on_dominant_supplier():
    sups = ["PE-RUC-20111111110"] * 12 + [f"PE-RUC-2099999999{k}" for k in range(4)]
    out = flagged(_cell("c", sups), "C04")
    assert out == {f"c{k}" for k in range(12)}


def test_c04_quiet_on_balanced_or_small_cell():
    balanced = _cell("b", [f"PE-RUC-209999{k:05d}" for k in range(16)])
    small = _cell("s", ["PE-RUC-20111111110"] * 8)  # below min_awards
    assert flagged(balanced, "C04") == set() and flagged(small, "C04") == set()


def test_c04_quiet_when_one_large_contract_dominates():
    sups = [f"PE-RUC-209999{k:05d}" for k in range(16)]
    rels = _cell("x", sups)
    rels[0]["awards"][0]["value"]["amount"] = 5_000_000  # one big award, single contract
    rels[0]["tender"]["value"]["amount"] = 5_000_000
    assert flagged(rels, "C04") == set()


# C05 repeated winner -----------------------------------------------------------------------
WIN = "PE-RUC-20111111110"
RIVAL = "PE-RUC-20222222220"


def test_c05_repeated_winner_fires():
    rels = [release(f"w{k}", supplier=WIN, bidders=[WIN, RIVAL]) for k in range(6)]
    assert flagged(rels, "C05") == {f"w{k}" for k in range(6)}


def test_c05_quiet_when_win_rate_low():
    wins = [release(f"w{k}", supplier=WIN, bidders=[WIN, RIVAL]) for k in range(6)]
    losses = [release(f"l{k}", supplier=RIVAL, bidders=[WIN, RIVAL]) for k in range(6)]
    out = fire(wins + losses, "C05")
    assert WIN not in set(out["supplier_id"])


def test_c05_quiet_below_min_wins():
    rels = [release(f"w{k}", supplier=WIN, bidders=[WIN, RIVAL]) for k in range(5)]
    assert flagged(rels, "C05") == set()


# C06 amendments ----------------------------------------------------------------------------
def test_c06_amendment_increase():
    rels = [
        release("big", amount=100_000, amendments=[("2025-06-01", 110_000), ("2025-07-01", 150_000)]),
        release("small", amount=100_000, amendments=[("2025-06-01", 110_000)]),
        release("none", amount=100_000),
    ]
    out = fire(rels, "C06")
    assert set(out["ocid"]) == {"big"}
    assert math.isclose(out["severity"].iloc[0], (0.5 - 0.25) / 0.75, abs_tol=1e-4)


# C07 price outlier -------------------------------------------------------------------------
def test_c07_price_outlier():
    base = [release(f"p{k}", unit=100 + k, qty=10, amount=1000 + 10 * k, cls="42100000")
            for k in range(20)]
    rels = base + [
        release("hi", unit=500, qty=10, amount=5000, cls="42100000"),
        release("mild", unit=200, qty=10, amount=2000, cls="42100000"),
        release("lonely", unit=9999, qty=1, amount=9999, cls="99100000"),  # class too small
    ]
    assert flagged(rels, "C07") == {"hi"}


# C08 Benford (aggregate) -------------------------------------------------------------------
def _amount_releases(amounts):
    return [release(f"b{k}", amount=float(a), published=f"2025-{1 + k % 12:02d}-05")
            for k, a in enumerate(amounts)]


@pytest.mark.parametrize("kind,expected", [("benford", False), ("uniform", True)])
def test_c08_benford_population_test(kind, expected):
    rng = np.random.default_rng(3)
    n = 1500
    if kind == "benford":
        amounts = 10 ** rng.uniform(3, 7, size=n)          # log-uniform => Benford
    else:
        amounts = rng.uniform(10_000, 99_999, size=n)      # uniform leading digits
    out = fire(_amount_releases(amounts), "C08")
    overall = out[out.scope_type == "all"].iloc[0]
    assert bool(overall["flag"]) is expected
    assert "ocid" not in out.columns  # never an individual alert


# C09 award-to-signature delay --------------------------------------------------------------
def test_c09_delay():
    rels = [
        release("late", award="2025-04-01", signed="2025-07-15"),
        release("ok", award="2025-04-01", signed="2025-04-10"),
        release("bad_dates", award="2025-04-01", signed="2025-01-01"),  # DQ09, excluded
        release("minor_late", method="direct", tender_days=None, award="2025-04-01", signed="2025-08-01"),
    ]
    assert flagged(rels, "C09") == {"late"}
