import math
import re

import pandas as pd
import pytest
from helpers import release, warehouse

from procontrol.config import Config
from procontrol.engine import (
    REQUIRED_FIELDS,
    compute_risk_scores,
    load_catalog,
    resolve_params,
    run_all,
    validate_catalog,
)

CFG = Config.load()
CATALOG = load_catalog(CFG)


def test_catalog_has_minimum_controls_and_fields():
    ids = [c["id"] for c in CATALOG["controls"]]
    assert len(ids) >= 9 and len(set(ids)) == len(ids)
    for c in CATALOG["controls"]:
        for f in REQUIRED_FIELDS:
            assert c[f] not in (None, "", []), (c["id"], f)


def test_every_sql_parameter_is_defined_in_the_catalog():
    for spec in CATALOG["controls"]:
        sql = (CFG.root / spec["sql"]).read_text()
        used = set(re.findall(r"\$([A-Za-z_]\w*)", sql))
        assert used <= set(resolve_params(spec, CFG)), spec["id"]


def test_refs_resolve_to_thresholds_file():
    c06 = next(c for c in CATALOG["controls"] if c["id"] == "C06")
    assert resolve_params(c06, CFG)["cap"] == CFG.thresholds["amendment_increase_cap"]["value"]


def test_invalid_catalog_is_rejected():
    bad = {"controls": [dict(CATALOG["controls"][0], weight=2)]}
    with pytest.raises(ValueError):
        validate_catalog(bad, CFG)


def test_noisy_or_score():
    con = warehouse([release("x"), release("y")])
    con.execute("CREATE TABLE alerts AS SELECT * FROM (VALUES "
                "('A1','C02','x',NULL,NULL,2025,1.0,'k','{}',0.35),"
                "('A2','C03','x',NULL,NULL,2025,0.5,'k','{}',0.50),"
                "('A3','C03','x',NULL,NULL,2025,0.2,'k','{}',0.50),"   # weaker duplicate: ignored
                "('A4','C02','y',NULL,NULL,2025,1.0,'k','{}',0.35)) "
                "t(alert_id,control_id,ocid,buyer_id,supplier_id,year,severity,scope_key,evidence,weight)")
    s = compute_risk_scores(con, CATALOG).set_index("ocid")
    assert math.isclose(s.loc["x", "score"], round(100 * (1 - (1 - 0.35) * (1 - 0.25)), 1))
    assert s.loc["y", "score"] == 35.0 and s.loc["x", "n_controls"] == 2


def test_run_all_on_fixture():
    rels = [release("one", bidders=["PE-RUC-20111111110"]),
            release("late", award="2025-04-01", signed="2025-08-01",
                    bidders=["PE-RUC-20111111110", "PE-RUC-20222222220"])]
    res = run_all(warehouse(rels), CFG, CATALOG)
    got = set(zip(res["alerts"]["control_id"], res["alerts"]["ocid"], strict=True))
    assert ("C02", "one") in got and ("C09", "late") in got
    assert isinstance(res["risk_scores"], pd.DataFrame)
