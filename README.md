# Peru procurement controls

Continuous-control analytics on Peruvian public procurement (OCDS): data quality, a written
control catalog and a signal engine.

> **Signals, never accusations.** An alert means *"this deserves a review"*, not *"there is an
> irregularity"*. No supplier, official or person is ranked or named. Public entities appear
> only in aggregated views.

> **Data actually used: synthetic (Plan C).** The network policy of the build environment
> blocked the OCP Data Registry and the OECE portal. All results in this repository come from a
> seeded synthetic OCDS dataset with injected, known risk patterns. The download code for the
> real publications (Plan A: OECE; Plan B: Perú Compras) is included but has not been run.

## Status

| Phase | Content | State |
|---|---|---|
| 1 | Ingestion (OCDS → DuckDB) and data-quality report | done |
| 2 | Control catalog (9 controls) | done |
| 3 | Signal engine + composite risk score | done |
| 4 | Validation (injected patterns + blind case review) | done |
| 5 | MkDocs site + Power BI model | done |

## Run it

```bash
make all          # install, run the pipeline, lint, test, build the site
```

or step by step:

```bash
python -m pip install -e ".[dev]"
python -m procontrol run                 # synthetic data (default)
python -m procontrol run --source oece   # Plan A, after setting the publication id
python -m procontrol to-verify           # thresholds still to verify
python -m pytest
```

## Layout

```
config/       settings.yaml (source, paths) and thresholds.yaml (every legal threshold + source)
src/procontrol/
  synthetic.py  Plan C generator with injected risk patterns and ground truth
  download.py   Plan A/B downloader (OCP Data Registry)
  ingest.py     OCDS → relational tables in DuckDB
  privacy.py    keyed pseudonymisation of natural persons
  quality.py    15 data-quality checks and the clean analytical layer (f_* views)
data/sample/  small pseudonymised sample (raw data is git-ignored)
outputs/      aggregated, versioned results
docs/         site source, DECISIONS.md
```

## How this was built

I built this repository by directing Claude Code (Anthropic's coding agent). I set the
objectives, the rules, the control design and the acceptance criteria, and the agent wrote the
code, tests and documentation under those constraints. Every design decision is logged with its
reason in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Scope & limitations

* Synthetic data only so far (see above). Nothing here describes any real Peruvian entity.
* Most legal thresholds are marked `to_verify` in `config/thresholds.yaml`.
