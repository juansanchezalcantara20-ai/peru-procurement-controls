"""Spanish labels and plain-language formatting shared by the site, the gates and Power BI."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

SEGMENT_ES = {
    "10": "Animales y plantas vivas", "11": "Minerales y materias primas", "12": "Químicos",
    "13": "Resinas y cauchos", "14": "Papel y útiles de papel", "15": "Combustibles y lubricantes",
    "20": "Maquinaria minera", "21": "Maquinaria agrícola", "22": "Maquinaria de construcción",
    "23": "Maquinaria industrial", "24": "Equipos de almacenaje y transporte de carga",
    "25": "Vehículos y repuestos", "26": "Equipos eléctricos y de energía",
    "27": "Herramientas", "30": "Materiales de construcción", "31": "Componentes y suministros",
    "39": "Iluminación y accesorios eléctricos", "40": "Climatización y tuberías",
    "41": "Equipos de laboratorio", "42": "Equipos y suministros médicos",
    "43": "Equipos informáticos y de telecomunicaciones", "44": "Útiles y equipos de oficina",
    "45": "Equipos de imprenta y audiovisuales", "46": "Equipos de defensa y seguridad",
    "47": "Artículos de limpieza", "48": "Equipos de servicio de alimentos y deporte",
    "49": "Equipos recreativos y deportivos", "50": "Alimentos y bebidas",
    "51": "Medicamentos y productos farmacéuticos", "52": "Electrodomésticos y muebles domésticos",
    "53": "Ropa, calzado y artículos personales", "55": "Publicaciones impresas",
    "56": "Muebles", "60": "Material educativo", "70": "Servicios agrícolas y ambientales",
    "71": "Servicios de minería y petróleo", "72": "Obras de construcción",
    "73": "Servicios de producción industrial", "76": "Servicios de limpieza",
    "77": "Servicios ambientales", "78": "Servicios de transporte",
    "80": "Servicios de gestión y consultoría", "81": "Servicios de ingeniería",
    "82": "Servicios editoriales y de diseño", "83": "Servicios públicos (agua, luz, telecomunicaciones)",
    "84": "Servicios financieros y de seguros", "85": "Servicios de salud",
    "86": "Servicios educativos", "90": "Servicios de viaje y alimentación",
    "91": "Servicios personales", "92": "Servicios de seguridad y vigilancia",
    "93": "Servicios políticos y cívicos", "94": "Organizaciones y clubes", "95": "Terrenos y edificios",
}

ENTITY_TYPE_ES = {
    "Ministry": "Ministerios", "Regional Government": "Gobiernos regionales",
    "Provincial Municipality": "Municipalidades provinciales",
    "District Municipality": "Municipalidades distritales", "Public Hospital": "Hospitales",
    "Public University": "Universidades", "Executing Unit": "Unidades ejecutoras",
    "Regulatory Agency": "Organismos reguladores y supervisores",
}

# Keyword rules for real buyer names (order matters: first match wins).
ENTITY_RULES = [
    ("MUNICIPALIDAD DISTRITAL", "Municipalidades distritales"),
    ("MUNICIPALIDAD PROVINCIAL", "Municipalidades provinciales"),
    ("MUNICIPALIDAD METROPOLITANA", "Municipalidades provinciales"),
    ("MUNICIPALIDAD", "Municipalidades distritales"),
    ("GOBIERNO REGIONAL", "Gobiernos regionales"),
    ("REGION ", "Gobiernos regionales"),
    ("MINISTERIO PUBLICO", "Sistema de justicia"),
    ("SEGURO SOCIAL", "Seguridad social"),
    ("ESSALUD", "Seguridad social"),
    ("MINISTERIO", "Ministerios"),
    ("HOSPITAL", "Hospitales"),
    ("RED DE SALUD", "Hospitales"),
    ("SALUD", "Hospitales"),
    ("UNIVERSIDAD", "Universidades"),
    ("UNIDAD EJECUTORA", "Unidades ejecutoras"),
    ("SUPERINTENDENCIA", "Organismos reguladores y supervisores"),
    ("ORGANISMO SUPERVISOR", "Organismos reguladores y supervisores"),
    ("PROGRAMA", "Programas nacionales"),
    ("PROYECTO ESPECIAL", "Programas nacionales"),
    ("PODER JUDICIAL", "Sistema de justicia"),
    ("CORTE SUPERIOR", "Sistema de justicia"),
    ("EMPRESA", "Empresas del Estado"),
    ("S.A.", "Empresas del Estado"),
    ("INSTITUTO", "Institutos y otros organismos"),
    ("EJERCITO", "Fuerzas Armadas y Policía"),
    ("MARINA", "Fuerzas Armadas y Policía"),
    ("FUERZA AEREA", "Fuerzas Armadas y Policía"),
    ("POLICIA", "Fuerzas Armadas y Policía"),
]
OTHER_ENTITIES = "Otras entidades"

METHOD_ES = {
    "direct": "compra directa o menor", "limited": "contratación directa",
    "open": "procedimiento abierto", "selective": "procedimiento selectivo",
}

PATTERN_ES = {
    "split_purchase": "compras partidas (sembrado)",
    "single_bid": "un solo postor (sembrado)",
    "short_submission_period": "plazo corto (sembrado)",
    "supplier_concentration": "concentración (sembrado)",
    "repeated_winner": "ganador repetido (sembrado)",
    "amendment_increase": "contrato que crece (sembrado)",
    "price_outlier": "precio atípico (sembrado)",
    "award_signature_delay": "demora en la firma (sembrado)",
    "benford_fabricated_amounts": "entidad con montos inventados (sembrado)",
}

SLUGS = {
    "C01": "compras-partidas", "C02": "un-solo-postor", "C03": "plazo-corto",
    "C04": "concentracion", "C05": "ganador-repetido", "C06": "contratos-que-crecen",
    "C07": "precios-atipicos", "C08": "montos-poco-naturales", "C09": "demora-en-la-firma",
}

SOURCE_NAME = {"oece": "del OECE", "perucompras": "de Perú Compras"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def segment_label(code: str | None) -> str:
    if not code or code == "unknown":
        return "Sin clasificar"
    return SEGMENT_ES.get(str(code), f"Segmento {code}")


def entity_type(name: str | None) -> str:
    """Group a public entity into a broad type. Never returns the name itself."""
    if not name:
        return OTHER_ENTITIES
    m = re.search(r"\(([^)]*)\)\s*$", name)
    if m and m.group(1) in ENTITY_TYPE_ES:  # synthetic names: "Synthetic Entity 001 (Ministry)"
        return ENTITY_TYPE_ES[m.group(1)]
    up = strip_accents(name).upper()
    for key, label in ENTITY_RULES:
        if key in up:
            return label
    return OTHER_ENTITIES


def k_anonymous(df: pd.DataFrame, group_col: str, count_col: str, k: int,
                sum_cols: list[str]) -> pd.DataFrame:
    """Merge groups with fewer than k entities into «Otras entidades»; drop it if still < k."""
    df = df.copy()
    small = df[count_col] < k
    df.loc[small, group_col] = OTHER_ENTITIES
    out = df.groupby(group_col, as_index=False)[[count_col, *sum_cols]].sum()
    return out[out[count_col] >= k].reset_index(drop=True)


def per(n: float, d: float) -> str:
    """«82 de cada 100» (or «de cada 1,000» for small shares)."""
    if not d:
        return "0 de cada 100"
    share = 100 * n / d
    if share >= 1 or n == 0:
        return f"{round(share):,} de cada 100"
    per_k = round(1000 * n / d)
    return f"{per_k} de cada 1,000" if per_k >= 1 else "menos de 1 de cada 1,000"


def num(x: float) -> str:
    return f"{x:,.0f}"


def soles(x: float) -> str:
    if x >= 1e6:
        return f"S/ {x / 1e6:,.1f} millones"
    return f"S/ {x:,.0f}"


def fecha(d: str | date | None) -> str:
    if not d:
        return "fecha desconocida"
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return d.strftime("%d/%m/%Y")


def data_label(meta: dict) -> str:
    """The label that goes next to every main figure on the site."""
    src = meta.get("source", "synthetic")
    if src == "synthetic":
        return "datos simulados"
    when = (meta.get("download") or {}).get("downloaded_at")
    return f"datos reales {SOURCE_NAME.get(src, src)}, descargados el {fecha(when)}"
