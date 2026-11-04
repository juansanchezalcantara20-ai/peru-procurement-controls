"""End-to-end pipeline: acquire -> ingest -> quality -> signals -> validate -> report."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
from pathlib import Path

import duckdb

from .config import Config
from .download import DownloadError, download, write_sample
from .gates import write_protected_names
from .ingest import ingest_files
from .privacy import Pseudonymiser
from .quality import run_quality, write_quality_report
from .synthetic import generate

log = logging.getLogger("procontrol")

SOURCE_LABELS = {
    "synthetic": "Plan C - synthetic OCDS dataset with injected risk patterns (seeded, offline)",
    "oece": "Plan A - OECE OCDS publication (OCP Data Registry)",
    "perucompras": "Plan B - Perú Compras OCDS publication (OCP Data Registry)",
}


class Pipeline:
    def __init__(self, cfg: Config | None = None, years: list[int] | None = None):
        self.cfg = cfg or Config.load()
        self.years = years
        self.state_file = self.cfg.path("outputs") / "run_metadata.json"
        self.meta: dict = {}

    # -- steps ------------------------------------------------------------------------------
    def acquire(self) -> list[Path]:
        source = self.cfg.settings["source"]
        order = ["oece", "perucompras", "synthetic"] if source == "auto" else [source]
        errors = []
        for src in order:
            if src == "synthetic":
                info = generate(self.cfg)
                self.meta.update(source="synthetic", synthetic=info)
                self.meta.pop("download", None)
                return [Path(info["path"])]
            try:
                paths, record = download(self.cfg, src, self.years)
                self.meta.update(source=src, files=[str(p) for p in paths], download=record)
                return paths
            except DownloadError as exc:
                log.warning("La fuente %s no está disponible: %s", src, exc)
                errors.append(f"{src}: {exc}")
        raise DownloadError("Ninguna fuente de datos está disponible. " + " | ".join(errors))

    def connect(self) -> duckdb.DuckDBPyConnection:
        wh = self.cfg.path("warehouse")
        wh.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(wh))

    def pseudonymiser(self) -> Pseudonymiser:
        priv = self.cfg.settings["privacy"]
        return Pseudonymiser(natural_prefixes=tuple(priv["natural_person_ruc_prefixes"]),
                             env_var=priv["salt_env_var"])

    def run(self, steps: list[str] | None = None) -> dict:
        steps = steps or ["acquire", "ingest", "quality", "signals", "validate", "report"]
        for item in self.cfg.to_verify():
            log.warning("umbral por verificar: %s", item)
        paths: list[Path] = []
        pseudo = self.pseudonymiser()
        if "acquire" in steps:
            paths = self.acquire()
        else:
            self._load_meta()
            paths = self._existing_raw()
        con = self.connect()
        try:
            if "ingest" in steps:
                names: set[str] = set()
                self.meta["ingest_counts"] = ingest_files(con, paths, pseudo, names)
                allowed = self.cfg.settings.get("site", {}).get("allowed_institution_names", [])
                self.meta["protected_names"] = write_protected_names(
                    names, self.cfg.path("warehouse").parent / "protected_names.txt", allowed)
                write_sample(paths[0], self.cfg.path("sample_dir") / f"{self.meta['source']}_sample.jsonl",
                             pseudo, n=50)
            if "quality" in steps:
                results = run_quality(con)
                write_quality_report(results, self.cfg.path("outputs") / "quality",
                                     self.cfg.path("docs"),
                                     SOURCE_LABELS[self.meta["source"]])
            for step in ("signals", "validate", "report"):
                if step in steps:
                    if importlib.util.find_spec(f"procontrol.{_MODULES[step]}") is None:
                        log.info("el paso %s aún no existe; se omite", step)
                        continue
                    mod = importlib.import_module(f"procontrol.{_MODULES[step]}")
                    self.meta[step] = mod.run(self.cfg, con, self.meta)
        finally:
            con.close()
        self._save_meta()
        return self.meta

    # -- metadata ---------------------------------------------------------------------------
    def _existing_raw(self) -> list[Path]:
        src = self.meta.get("source", self.cfg.settings["source"])
        if src == "synthetic":
            return [self.cfg.path("raw_dir") / "synthetic" / "releases.jsonl.gz"]
        return sorted((self.cfg.path("raw_dir") / src).glob("*.jsonl.gz"))

    def _load_meta(self) -> None:
        if self.state_file.exists():
            self.meta = json.loads(self.state_file.read_text())

    def _save_meta(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in self.meta.items() if k != "files"}
        if "synthetic" in keep:
            keep["synthetic"] = {k: v for k, v in keep["synthetic"].items() if k != "path"}
        self.state_file.write_text(json.dumps(keep, indent=2, default=str) + "\n")


_MODULES = {"signals": "engine", "validate": "validation", "report": "report"}
