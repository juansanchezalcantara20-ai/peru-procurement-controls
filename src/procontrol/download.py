"""Plans A and B: download Peruvian OCDS publications from the OCP Data Registry.

How the registry serves files (checked against its source code, github.com/open-contracting/
data-registry, data_registry/views.py, on 2026-11-04):

* ``GET /en/publication/<id>/download?name=<file>`` where ``<file>`` matches
  ``(full|undated|YYYY).(jsonl.gz|csv.tar.gz|xlsx)``;
* 400 if the name is invalid, 404 "File not found" if that export does not exist (yet), otherwise
  a redirect to the downloads server (or the file itself);
* ``GET /en/publications.json`` lists every publication with title, country, date range and
  last retrieval date.

Each ``.jsonl.gz`` line is one OCDS compiled release. Raw files land in ``data/raw/<source>/``
(git-ignored); a log of what was downloaded is written next to them and summarised in the run
metadata. All user-facing messages are in Spanish.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from .config import Config
from .privacy import Pseudonymiser, pseudonymise_release

log = logging.getLogger(__name__)
USER_AGENT = "peru-procurement-controls/0.2 (+https://github.com/juansanchezalcantara20-ai/peru-procurement-controls)"


class DownloadError(RuntimeError):
    """Raised with a Spanish message that tells the user what happened and what to do."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def publication_info(cfg: Config, source: str, session: requests.Session) -> dict:
    """Confirm the publication exists in the registry; returns its metadata (or {} if unknown)."""
    reg = cfg.settings["registry"]
    pub_id = reg["publications"][source]["publication_id"]
    try:
        resp = session.get(reg["publications_api"], timeout=60)
        resp.raise_for_status()
        pubs = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("No se pudo leer la lista de publicaciones del registro (%s); se intenta la "
                    "descarga de todos modos.", exc)
        return {}
    match = next((p for p in pubs if int(p.get("id", -1)) == int(pub_id)), None)
    if match is None:
        raise DownloadError(
            f"La publicación {pub_id} no aparece en el registro de Open Contracting Partnership. "
            "Revise el número en config/settings.yaml (registry.publications) comparándolo con "
            "https://data.open-contracting.org/es/search/?q=peru")
    if (match.get("country") or "").lower() not in ("peru", "perú"):
        log.warning("La publicación %s es de «%s», no de Perú: revise el número.", pub_id,
                    match.get("country"))
    log.info("Publicación %s encontrada: %s (%s), datos de %s a %s, última actualización %s.",
             pub_id, match.get("title"), match.get("country"), match.get("date_from"),
             match.get("date_to"), match.get("last_retrieved"))
    return {k: match.get(k) for k in ("id", "title", "country", "date_from", "date_to",
                                      "last_retrieved", "source_url")}


def registry_urls(cfg: Config, source: str, years: list[int] | None = None) -> list[tuple[int, str]]:
    reg = cfg.settings["registry"]
    pub = reg["publications"][source]["publication_id"]
    if not pub:
        raise DownloadError(
            f"No hay número de publicación configurado para «{source}». Búsquelo en "
            "https://data.open-contracting.org/es/search/ y escríbalo en config/settings.yaml.")
    years = years or [int(y) for y in cfg.settings["years"]]
    return [(int(y), reg["base_url"].format(publication_id=pub, name=f"{y}.jsonl.gz")) for y in years]


def _check_gzip_jsonl(path: Path) -> None:
    with open(path, "rb") as fh:
        if fh.read(2) != b"\x1f\x8b":
            head = path.read_bytes()[:200].decode("utf-8", errors="replace")
            raise DownloadError(
                f"{path.name} no es un archivo comprimido válido; el servidor devolvió otra cosa "
                f"(inicio: {head[:80]!r}). Vuelva a lanzar el flujo más tarde.")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            first = fh.readline()
        json.loads(first)
    except (OSError, EOFError, ValueError) as exc:
        raise DownloadError(f"{path.name} está dañado o incompleto ({exc}). Bórrelo y vuelva a "
                            "lanzar el flujo.") from exc


def _download_one(session: requests.Session, url: str, dest: Path, retries: int,
                  timeout: int, backoff: float = 10.0) -> dict:
    """Stream ``url`` to ``dest`` with retries and resume. Returns a log entry."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    attempt, last_error, final_url = 0, "", url
    while attempt < retries:
        attempt += 1
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with session.get(url, stream=True, timeout=timeout, headers=headers,
                             allow_redirects=True) as resp:
                if resp.status_code == 404:
                    return {"status": "no existe", "http": 404, "attempts": attempt,
                            "final_url": resp.url}
                if resp.status_code == 400:
                    raise DownloadError(f"El registro rechazó el nombre de archivo pedido ({url}).")
                if resp.status_code == 416:  # range past the end: the .part is already complete
                    tmp.rename(dest)
                    break
                resp.raise_for_status()
                mode = "ab" if have and resp.status_code == 206 else "wb"
                with open(tmp, mode) as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        if chunk:
                            fh.write(chunk)
                final_url = resp.url
            tmp.rename(dest)
            break
        except DownloadError:
            raise
        except requests.RequestException as exc:
            last_error = str(exc)
            wait = min(300, backoff * 2 ** (attempt - 1))
            log.warning("Intento %s de %s falló para %s: %s. Reintento en %s s.", attempt, retries,
                        url, exc, wait)
            time.sleep(wait)
    else:
        raise DownloadError(
            f"No se pudo descargar {url} después de {retries} intentos (último error: "
            f"{last_error}). Suele ser un corte de red o el registro saturado: vuelva a lanzar el "
            "flujo más tarde.")
    _check_gzip_jsonl(dest)
    sha = hashlib.sha256()
    with open(dest, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            sha.update(chunk)
    return {"status": "descargado", "http": 200, "attempts": attempt,
            "final_url": final_url, "bytes": dest.stat().st_size,
            "sha256": sha.hexdigest()}


def download(cfg: Config, source: str, years: list[int] | None = None) -> tuple[list[Path], dict]:
    """Download the yearly files of ``source``; returns the paths and a download log."""
    reg = cfg.settings["registry"]
    retries = int(reg.get("retries", 5))
    timeout = int(reg.get("timeout_seconds", 120))
    out_dir = cfg.path("raw_dir") / source
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    info = publication_info(cfg, source, session)

    entries, paths = [], []
    for year, url in registry_urls(cfg, source, years):
        dest = out_dir / f"{year}.jsonl.gz"
        if dest.exists() and dest.stat().st_size > 0:
            log.info("Ya estaba descargado: %s", dest)
            entry = {"status": "en caché", "bytes": dest.stat().st_size}
        else:
            log.info("Descargando %s (año %s)…", url, year)
            entry = _download_one(session, url, dest, retries, timeout,
                                  float(reg.get("backoff_seconds", 10)))
        entry.update(year=year, url=url, downloaded_at=_now(), file=dest.name)
        entries.append(entry)
        if entry["status"] == "no existe":
            log.warning("El registro no tiene archivo para %s en esta publicación (puede que ese año "
                        "no tenga datos o que el registro lo esté regenerando).", year)
            continue
        paths.append(dest)
        log.info("Listo: %s (%.1f MB).", dest.name, dest.stat().st_size / 1e6)

    record = {"source": source, "publication": info, "downloaded_at": _now(), "files": entries}
    (out_dir / "registro_descargas.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not paths:
        raise DownloadError(
            f"No se descargó ningún año de la publicación {reg['publications'][source]['publication_id']}. "
            "Revise en https://data.open-contracting.org qué años están disponibles y lance el "
            "flujo con esos años.")
    return paths, record


def write_sample(src: Path, dest: Path, pseudo: Pseudonymiser, n: int = 200) -> Path:
    """Write the first ``n`` releases of a JSON Lines(.gz) file as a small versioned sample.

    Natural persons are pseudonymised before writing, so the sample is safe to commit.
    """
    opener = gzip.open if str(src).endswith(".gz") else open
    dest.parent.mkdir(parents=True, exist_ok=True)
    with opener(src, "rt", encoding="utf-8") as fin, open(dest, "w", encoding="utf-8") as fout:
        for k, line in enumerate(fin):
            if k >= n:
                break
            rel = pseudonymise_release(json.loads(line), pseudo)
            fout.write(json.dumps(rel, ensure_ascii=False) + "\n")
    return dest
