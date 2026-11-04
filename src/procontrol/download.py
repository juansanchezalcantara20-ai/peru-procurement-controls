"""Plan A / Plan B: download Peruvian OCDS publications from the OCP Data Registry.

The registry (https://data.open-contracting.org) serves each publication as one compiled-release
JSON Lines file per year. Publication ids must be filled in ``config/settings.yaml`` after looking
them up on the registry search page; they are not hard-coded from memory.

Raw downloads go to ``data/raw/<source>/`` which is git-ignored (files are hundreds of MB).
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from .config import Config
from .privacy import Pseudonymiser, pseudonymise_release

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


def registry_urls(cfg: Config, source: str) -> list[tuple[int, str]]:
    reg = cfg.settings["registry"]
    pub = reg["publications"][source]["publication_id"]
    if not pub:
        raise DownloadError(
            f"No publication_id configured for '{source}'. Look it up at "
            "https://data.open-contracting.org/en/search/ and set it in config/settings.yaml."
        )
    return [
        (int(y), reg["base_url"].format(publication_id=pub, year=y))
        for y in cfg.settings["years"]
    ]


def download(cfg: Config, source: str, timeout: int = 60) -> list[Path]:
    out_dir = cfg.path("raw_dir") / source
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for year, url in registry_urls(cfg, source):
        dest = out_dir / f"{year}.jsonl.gz"
        if dest.exists() and dest.stat().st_size > 0:
            log.info("cached %s", dest)
            paths.append(dest)
            continue
        log.info("downloading %s", url)
        try:
            with requests.get(url, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
                tmp.rename(dest)
        except requests.RequestException as exc:
            raise DownloadError(f"{source} {year}: {exc}") from exc
        paths.append(dest)
    return paths


def write_sample(src: Path, dest: Path, pseudo: Pseudonymiser, n: int = 200) -> Path:
    """Write the first ``n`` releases of a JSON Lines(.gz) file as a small versioned sample.

    Natural persons are pseudonymised before writing, so the sample is safe to commit.
    """
    import gzip
    import json

    opener = gzip.open if str(src).endswith(".gz") else open
    dest.parent.mkdir(parents=True, exist_ok=True)
    with opener(src, "rt", encoding="utf-8") as fin, open(dest, "w", encoding="utf-8") as fout:
        for k, line in enumerate(fin):
            if k >= n:
                break
            rel = pseudonymise_release(json.loads(line), pseudo)
            fout.write(json.dumps(rel, ensure_ascii=False) + "\n")
    return dest
