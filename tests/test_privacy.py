from helpers import release, warehouse

from procontrol.privacy import Pseudonymiser, pseudonymise_release

PERSON = "PE-RUC-10456789012"


def test_natural_person_is_hashed_deterministically():
    p = Pseudonymiser(key="k")
    a = p.party(PERSON, "Juana Pérez", "PE-RUC", "10456789012")
    b = Pseudonymiser(key="k").party(PERSON, "Juana Pérez", "PE-RUC", "10456789012")
    assert a.is_natural_person and a.id == b.id and a.id.startswith("NP-")
    assert "Juana" not in a.name and a.ruc is None


def test_key_changes_the_token():
    a = Pseudonymiser(key="k1").party(PERSON, "x", "PE-RUC", "10456789012")
    b = Pseudonymiser(key="k2").party(PERSON, "x", "PE-RUC", "10456789012")
    assert a.id != b.id


def test_company_is_not_hashed():
    p = Pseudonymiser(key="k").party("PE-RUC-20123456789", "Company", "PE-RUC", "20123456789")
    assert not p.is_natural_person and p.name == "Company" and p.ruc == "20123456789"


def test_dni_scheme_is_natural():
    assert Pseudonymiser(key="k").is_natural("PE-DNI", "45678901")


def test_no_personal_data_reaches_the_warehouse():
    rel = release("ocds-t-1", supplier=PERSON, supplier_name="Juana Pérez")
    con = warehouse([rel])
    dump = str(con.execute("SELECT * FROM parties").fetchall())
    dump += str(con.execute("SELECT * FROM awards").fetchall())
    dump += str(con.execute("SELECT * FROM bids").fetchall())
    assert "Juana" not in dump and "10456789012" not in dump
    assert con.execute("SELECT count(*) FROM awards WHERE supplier_id LIKE 'NP-%'").fetchone()[0] == 1


def test_sample_writer_pseudonymises_json():
    rel = pseudonymise_release(release("ocds-t-1", supplier=PERSON, supplier_name="Juana Pérez"),
                               Pseudonymiser(key="k"))
    assert "Juana" not in str(rel) and "10456789012" not in str(rel)
