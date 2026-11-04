"""Gates run on the BUILT site before it can be published.

1. Readability (``check_readability``): outside the «Detalle técnico» folds and the Metodología
   section there must be no code blocks, no words with underscores (variable names), no English
   sentences, and every known acronym must be explained the first time it appears on a page.
2. Privacy (``check_privacy``): no supplier, official, natural person or public entity name may
   appear anywhere in the site, and entity groups must hold at least k entities.

Names are never stored in clear text: ingestion keeps only keyed hashes of the normalised names
(``protected_names.txt``); the gate hashes every word sequence of the site the same way and looks
for collisions. Error messages never print a matched name.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from .labels import strip_accents
from .privacy import DEMO_KEY

TECH_TITLE = "Detalle técnico"
EXCLUDED_DIRS = {"metodologia"}

ACRONYMS = ["UIT", "OCDS", "OECE", "OSCE", "SEACE", "RUC", "DNI", "UNSPSC", "HHI", "OCP", "SUNAT",
            "MAD", "CUBSO"]

# Proper names of standards, documents and tools that are allowed in their original language.
PROPER_NAMES = [
    "Open Contracting Data Standard", "Open Contracting Partnership", "Red Flags for Integrity",
    "Giving the green light to open data solutions", "United Nations Standard Products and Services Code",
    "Claude Code", "GitHub Actions", "GitHub Pages", "GitHub", "Power BI", "noisy-OR", "Benford's Law",
    "Material for MkDocs", "MkDocs",
]
EN_STOP = {"the", "and", "of", "is", "are", "with", "for", "this", "that", "from", "which", "will",
           "be", "not", "to", "in", "by", "on", "it", "an", "as", "or", "at", "have", "has", "was",
           "were", "its", "their", "these", "those", "can", "should", "would", "into", "than"}
ES_STOP = {"el", "la", "los", "las", "de", "del", "y", "en", "que", "por", "para", "con", "un", "una",
           "es", "se", "no", "lo", "su", "sus", "al", "como", "más", "o", "son", "pero", "si", "este",
           "esta", "ese", "esa", "cada", "entre", "sin", "sobre", "ya", "muy"}
# Content words that only appear when a page slipped back into English.
EN_STRONG = {"overview", "alerts", "processes", "flagged", "supplier", "suppliers", "buyer",
             "threshold", "signals", "validation", "decisions", "priority", "review", "evidence",
             "entities", "amount", "amounts", "awarded", "tender", "bidder", "bidders", "quality",
             "share", "rate", "count", "month", "year", "score", "weight", "rule"}
BLOCKS = ["p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "summary",
          "blockquote", "dt", "dd"]
UNDERSCORE = re.compile(r"\b[A-Za-z0-9]+_[A-Za-z0-9_]+\b")


@dataclass
class Problem:
    page: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.page}: {self.detail}"


# -- shared parsing ---------------------------------------------------------------------------------
def _pages(site: Path) -> Iterable[Path]:
    return sorted(p for p in site.rglob("*.html") if "assets" not in p.relative_to(site).parts)


def _rel(site: Path, page: Path) -> str:
    return str(page.relative_to(site))


def _content(html: str, drop_technical: bool) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("article") or soup.body or soup
    for tag in root.find_all(["script", "style", "svg", "noscript"]):
        tag.decompose()
    for a in root.select("a.headerlink"):
        a.decompose()
    if drop_technical:
        for det in root.find_all("details"):
            summ = det.find("summary")
            if summ and summ.get_text(" ", strip=True).startswith(TECH_TITLE):
                det.decompose()
    return root


def _clean_proper(text: str) -> str:
    for name in PROPER_NAMES:
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return text


# -- readability ------------------------------------------------------------------------------------
def readability_problems(page: str, html: str) -> list[Problem]:
    root = _content(html, drop_technical=True)
    out: list[Problem] = []
    for tag in root.find_all(["pre", "code"]):
        out.append(Problem(page, "código", f"bloque de código fuera de «{TECH_TITLE}»: "
                                           f"{tag.get_text(' ', strip=True)[:40]!r}"))
    text = root.get_text(" ", strip=True)
    for m in UNDERSCORE.finditer(text):
        out.append(Problem(page, "guion bajo", f"palabra con guion bajo {m.group(0)!r}"))
    for block in root.find_all(BLOCKS):
        if block.find(BLOCKS):  # judge the innermost blocks only
            continue
        raw = _clean_proper(block.get_text(" ", strip=True))
        words = re.findall(r"[a-záéíóúñü']+", raw.lower())
        en = sum(w in EN_STOP for w in words)
        es = sum(w in ES_STOP for w in words)
        strong = sorted({w for w in words if w in EN_STRONG})
        if (en >= 3 and en > es) or strong:
            out.append(Problem(page, "inglés", f"texto en inglés: {raw[:70]!r}"))
    flat = _clean_proper(text)
    for acr in ACRONYMS:
        m = re.search(rf"(?<![A-Za-z]){acr}(?![A-Za-z])", flat)
        if not m:
            continue
        after = flat[m.end():].lstrip()
        before = flat[:m.start()].rstrip()
        if not (after.startswith("(") or before.endswith("(")):
            out.append(Problem(page, "sigla", f"«{acr}» aparece sin explicar la primera vez: "
                                              f"{flat[max(0, m.start() - 30):m.end() + 30]!r}"))
    return out


def check_readability(site: Path) -> list[Problem]:
    problems: list[Problem] = []
    for page in _pages(site):
        rel = _rel(site, page)
        if set(Path(rel).parts) & EXCLUDED_DIRS:
            continue
        problems += readability_problems(rel, page.read_text(encoding="utf-8"))
    return problems


# -- privacy ----------------------------------------------------------------------------------------
def normalise_name(text: str) -> str:
    text = strip_accents(text).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_protectable(norm: str) -> bool:
    """Only names specific enough to be matched without flooding the gate with common words."""
    return len(norm) >= 10 and len(norm.split()) >= 2


def _key() -> bytes:
    return (os.environ.get("PROCONTROL_SALT") or DEMO_KEY).encode("utf-8")


def name_hash(norm: str, key: bytes | None = None) -> str:
    return hmac.new(key or _key(), norm.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def write_protected_names(names: set[str], path: Path, allowed: Iterable[str] = ()) -> int:
    allow = {normalise_name(a) for a in allowed}
    key = _key()
    hashes = sorted({name_hash(n, key) for n in (normalise_name(x) for x in names)
                     if is_protectable(n) and n not in allow})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(hashes) + "\n", encoding="utf-8")
    return len(hashes)


IDENTIFIER_PATTERNS = [
    ("RUC", re.compile(r"(?<!\d)(10|15|17|20)\d{9}(?!\d)")),
    ("identificador de parte", re.compile(r"PE-RUC-\d")),
    ("seudónimo de persona", re.compile(r"\bNP-[0-9a-f]{16}\b")),
    ("identificador de proceso", re.compile(r"\bocds-[a-z0-9]{5,8}-[a-z0-9-]*\d")),
]


def _site_texts(site: Path) -> Iterable[tuple[str, str]]:
    for page in _pages(site):
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "lxml")
        for tag in soup.find_all(["script", "style", "svg"]):
            tag.decompose()
        alts = " ".join(img.get("alt", "") for img in soup.find_all("img"))
        yield _rel(site, page), soup.get_text(" ", strip=True) + " " + alts
    for f in sorted(site.rglob("*")):
        if f.suffix in {".json", ".csv", ".txt", ".xml"} and "assets" not in f.relative_to(site).parts:
            yield _rel(site, f), f.read_text(encoding="utf-8", errors="ignore")


def privacy_problems(site: Path, protected: set[str], max_words: int = 14) -> list[Problem]:
    key = _key()
    out: list[Problem] = []
    for rel, text in _site_texts(site):
        for label, pat in IDENTIFIER_PATTERNS:
            if pat.search(text):
                out.append(Problem(rel, "privacidad", f"aparece un {label}"))
        if not protected:
            continue
        words = normalise_name(text).split()
        hits = 0
        for i in range(len(words)):
            for n in range(2, max_words + 1):
                if i + n > len(words):
                    break
                cand = " ".join(words[i:i + n])
                if len(cand) >= 10 and name_hash(cand, key) in protected:
                    hits += 1
        if hits:
            out.append(Problem(rel, "privacidad",
                               f"aparece {hits} vez/veces el nombre de un proveedor, funcionario, "
                               "persona o entidad (el nombre no se imprime para no difundirlo)"))
    return out


def group_size_problems(csv: Path, count_col: str, k: int) -> list[Problem]:
    if not csv.exists():
        return []
    df = pd.read_csv(csv)
    small = df[df[count_col] < k]
    return [Problem(csv.name, "privacidad", f"un grupo agregado tiene menos de {k} entidades")
            for _ in range(len(small))]


def check_privacy(site: Path, names_file: Path | None, outputs: Path, k: int) -> list[Problem]:
    protected: set[str] = set()
    if names_file and names_file.exists():
        protected = {h for h in names_file.read_text(encoding="utf-8").split() if h}
    problems = privacy_problems(site, protected)
    problems += group_size_problems(outputs / "distributions" / "alertas_por_tipo_de_entidad.csv",
                                    "entidades", k)
    if names_file is not None and not names_file.exists():
        problems.append(Problem(str(names_file), "privacidad",
                                "no se encontró la lista de nombres protegidos: corra primero el proceso"))
    return problems
