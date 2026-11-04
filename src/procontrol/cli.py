"""Command line entry point: ``procontrol run`` reproduces everything."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config
from .pipeline import Pipeline

STEPS = ["acquire", "ingest", "quality", "signals", "validate", "report"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="procontrol", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the pipeline (all steps by default)")
    run.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    run.add_argument("--source", choices=["synthetic", "oece", "perucompras", "auto"],
                     help="override config/settings.yaml source")
    sub.add_parser("to-verify", help="list thresholds still marked to_verify")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = Config.load()
    if args.cmd == "to-verify":
        for item in cfg.to_verify():
            print(item)
        return 0
    if args.source:
        cfg.settings["source"] = args.source
    meta = Pipeline(cfg).run(args.steps)
    print(f"done - source: {meta.get('source')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
