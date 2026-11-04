"""Command line entry point: ``procontrol run`` reproduces everything."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
from .pipeline import Pipeline

STEPS = ["acquire", "ingest", "quality", "signals", "validate", "report"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="procontrol", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="corre el proceso (todos los pasos por defecto)")
    run.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    run.add_argument("--source", choices=["synthetic", "oece", "perucompras", "auto"],
                     help="reemplaza la fuente de config/settings.yaml")
    sub.add_parser("to-verify", help="lista los umbrales que siguen marcados to_verify")
    leg = sub.add_parser("legibilidad", help="revisa que el sitio construido se lea sin saber programar")
    leg.add_argument("site", nargs="?", default="site")
    pri = sub.add_parser("privacidad", help="revisa que el sitio construido no nombre a nadie")
    pri.add_argument("site", nargs="?", default="site")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config.load()
    if args.cmd == "to-verify":
        for item in cfg.to_verify():
            print(item)
        return 0
    if args.cmd in ("legibilidad", "privacidad"):
        return run_gate(cfg, args.cmd, Path(args.site))
    if args.source:
        cfg.settings["source"] = args.source
    meta = Pipeline(cfg).run(args.steps)
    print(f"listo - fuente: {meta.get('source')}")
    return 0


def run_gate(cfg: Config, gate: str, site: Path) -> int:
    from .gates import check_privacy, check_readability

    if not site.exists():
        print(f"No existe la carpeta del sitio construido: {site}. Corra antes «mkdocs build».")
        return 2
    if gate == "legibilidad":
        problems = check_readability(site)
        ok = "Prueba de legibilidad superada: el sitio se lee sin saber programar."
    else:
        k = int(cfg.settings.get("site", {}).get("min_entities_per_group", 3))
        names = cfg.path("warehouse").parent / "protected_names.txt"
        problems = check_privacy(site, names, cfg.path("outputs"), k)
        ok = "Prueba de privacidad superada: el sitio no nombra a ningún proveedor, persona ni entidad."
    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} problema(s). El sitio NO debe publicarse hasta corregirlos.")
        return 1
    print(ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
