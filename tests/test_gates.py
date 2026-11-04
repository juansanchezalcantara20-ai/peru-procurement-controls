"""The readability and privacy gates must fail on bad pages and pass on good ones."""

from pathlib import Path

import pytest

from procontrol.gates import (
    check_privacy,
    check_readability,
    name_hash,
    normalise_name,
    readability_problems,
    write_protected_names,
)

ROOT = Path(__file__).resolve().parents[1]


def page(body: str) -> str:
    return f"<html><body><nav>Overview processes</nav><article>{body}</article></body></html>"


def kinds(body: str) -> set[str]:
    return {p.kind for p in readability_problems("x.html", page(body))}


def test_clean_spanish_page_passes():
    body = ("<h1>Compras partidas</h1><p>Varias compras pequeñas al mismo proveedor, cada una justo "
            "debajo del límite de 8 UIT (Unidad Impositiva Tributaria).</p>"
            "<p>Datos en formato OCDS (Open Contracting Data Standard), publicados por Open "
            "Contracting Partnership.</p>")
    assert kinds(body) == set()


@pytest.mark.parametrize("body,kind", [
    ("<p>La columna method_details define el método.</p>", "guion bajo"),
    ("<pre><code>SELECT 1</code></pre>", "código"),
    ("<p>Use <code>procontrol run</code> para correrlo.</p>", "código"),
    ("<p>This is the list of processes that were flagged by the engine.</p>", "inglés"),
    ("<table><tr><th>alerts</th></tr></table>", "inglés"),
    ("<p>El límite es de 8 UIT por compra.</p>", "sigla"),
])
def test_bad_pages_fail(body, kind):
    assert kind in kinds(body)


def test_technical_fold_is_exempt():
    body = ("<p>Texto simple en español para el lector.</p>"
            "<details><summary>Detalle técnico</summary><pre><code>SELECT min_wins FROM t</code></pre>"
            "<p>The rule uses the HHI and the threshold.</p></details>")
    assert kinds(body) == set()


def test_other_folds_are_not_exempt():
    body = "<details><summary>Más</summary><p>La variable min_wins vale 6.</p></details>"
    assert "guion bajo" in kinds(body)


def test_navigation_is_not_judged():
    # the nav of the fixture says "Overview processes" but only the article counts
    assert kinds("<p>Todo en orden para el lector.</p>") == set()


def test_methodology_pages_are_exempt(tmp_path):
    (tmp_path / "metodologia").mkdir()
    (tmp_path / "metodologia" / "index.html").write_text(page("<pre>SELECT f_award</pre>"))
    (tmp_path / "index.html").write_text(page("<p>Página simple en español.</p>"))
    assert check_readability(tmp_path) == []


def _site_with(tmp_path, text: str) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(page(f"<p>{text}</p>"))
    return site


def test_privacy_blocks_protected_names(tmp_path):
    names = tmp_path / "names.txt"
    write_protected_names({"Juana Pérez Quispe", "Transportes del Sur S.A.C.", "SA"}, names)
    site = _site_with(tmp_path, "El contrato lo ganó TRANSPORTES DEL SUR S.A.C. en mayo.")
    problems = check_privacy(site, names, tmp_path, k=3)
    assert any(p.kind == "privacidad" for p in problems)
    assert all("Transportes" not in str(p) for p in problems)  # never prints the name


def test_privacy_allows_listed_institutions(tmp_path):
    names = tmp_path / "names.txt"
    write_protected_names({"Organismo Supervisor de las Contrataciones del Estado"}, names,
                          allowed=["Organismo Supervisor de las Contrataciones del Estado"])
    site = _site_with(tmp_path, "Antes se llamaba Organismo Supervisor de las Contrataciones del Estado.")
    assert check_privacy(site, names, tmp_path, k=3) == []


@pytest.mark.parametrize("text", ["RUC 20123456789", "proveedor NP-0123456789abcdef",
                                  "proceso ocds-dgv273-seacev3-12345", "PE-RUC-20123456789"])
def test_privacy_blocks_identifiers(tmp_path, text):
    names = tmp_path / "names.txt"
    write_protected_names(set(), names)
    site = _site_with(tmp_path, text)
    assert check_privacy(site, names, tmp_path, k=3)


def test_privacy_ignores_glossary_anchor(tmp_path):
    names = tmp_path / "names.txt"
    write_protected_names({"Empresa Cualquiera SAC"}, names)
    site = _site_with(tmp_path, '<a href="#ocds-open-contracting-data-standard">OCDS</a>')
    assert check_privacy(site, names, tmp_path, k=3) == []


def test_small_entity_groups_fail(tmp_path):
    names = tmp_path / "names.txt"
    write_protected_names({"Empresa Cualquiera SAC"}, names)
    (tmp_path / "distributions").mkdir()
    (tmp_path / "distributions" / "alertas_por_tipo_de_entidad.csv").write_text(
        "tipo,entidades,procesos,con_alerta\nMinisterios,2,40,3\n")
    site = _site_with(tmp_path, "Texto sin nombres.")
    assert check_privacy(site, names, tmp_path, k=3)


def test_normalisation_ignores_case_accents_and_punctuation():
    assert normalise_name("Perú  Compras, S.A.") == "PERU COMPRAS S A"
    assert name_hash("ABC DEF GHI", b"k") == name_hash(normalise_name("abc def, ghi"), b"k")


SITE = ROOT / "site"


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="el sitio no está construido")
def test_built_site_passes_readability():
    assert [str(p) for p in check_readability(SITE)] == []
