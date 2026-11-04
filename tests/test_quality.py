from helpers import release, warehouse


def issues(con):
    return dict(con.execute("SELECT check_id, count(*) FROM dq_issues GROUP BY 1").fetchall())


def test_clean_release_has_no_critical_issues():
    con = warehouse([release("ocds-t-1")])
    crit = con.execute("SELECT count(*) FROM dq_issues WHERE severity='critical'").fetchone()[0]
    assert crit == 0
    assert con.execute("SELECT count(amount) FROM f_award").fetchone()[0] == 1


def test_defects_are_detected_and_excluded():
    rels = [
        release("ocds-t-neg", amount=-5),
        release("ocds-t-abs", amount=1e12, tender_amount=1000),
        release("ocds-t-usd", currency="USD"),
        release("ocds-t-nobuyer", buyer=None),
        release("ocds-t-sign", award="2025-04-10", signed="2025-04-01"),
        release("ocds-t-dup"),
        release("ocds-t-dup"),
    ]
    rels[-1]["date"] = "2025-12-31T00:00:00-05:00"
    tp = rels[0]["tender"]["tenderPeriod"]
    tp["startDate"], tp["endDate"] = tp["endDate"], tp["startDate"]
    con = warehouse(rels)
    got = issues(con)
    for check in ("DQ01", "DQ02", "DQ04", "DQ05", "DQ06", "DQ07", "DQ09"):
        assert got.get(check, 0) >= 1, check
    # excluded from the analytical layer
    assert con.execute("SELECT count(*) FROM f_process WHERE ocid='ocds-t-nobuyer'").fetchone()[0] == 0
    usable = dict(con.execute("SELECT ocid, amount FROM f_award").fetchall())
    assert usable["ocds-t-neg"] is None and usable["ocds-t-abs"] is None and usable["ocds-t-usd"] is None
    assert con.execute("SELECT count(*) FROM f_process WHERE ocid='ocds-t-dup'").fetchone()[0] == 1
    assert con.execute(
        "SELECT date_signed FROM f_contract WHERE ocid='ocds-t-sign'").fetchone()[0] is None
