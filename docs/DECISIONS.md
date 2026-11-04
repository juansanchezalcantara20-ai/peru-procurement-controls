# Decision log

Every design decision, with the reason behind it. Newest decisions are appended at the end of each
phase section.

## Phase 0 · Framing

**D01 - Signals, never accusations.** Every output says an alert *deserves a review*. There are
no rankings of suppliers, officials or named people; public entities appear only in aggregated
views. *Why:* a control flags a deviation from an expected pattern. Whether it is an
irregularity is for a reviewer with the case file to decide, never for a dashboard.

**D02 - English for everything visible.** *Why:* it was a project requirement, and recruiters and
reviewers outside Peru can read it. Spanish appears only for official Peruvian names (e.g.
*Contratación menor*, *Licitación pública*), because translating legal names loses precision.

## Phase 1 · Ingestion and data quality

**D03 - Plan C (synthetic data) is what actually ran.** The session's network policy denied
`data.open-contracting.org`, the OECE portal and `datosabiertos.gob.pe` (HTTP 403 at the proxy).
Plans A and B are fully coded (`procontrol/download.py`, `--source oece|perucompras|auto`), but
they were never executed here. *Why:* it was better to ship a pipeline that runs end to end and is honest
about its data than to stall. The synthetic dataset also gives what real data cannot: a known
ground truth to measure the controls against (Phase 4).

**D04 - Registry publication ids are not hard-coded.** `config/settings.yaml` leaves
`publication_id: null` (status `to_verify`). *Why:* I could not open the registry to confirm them,
and writing ids from memory would break rule "no thresholds or facts from memory".

**D05 - DuckDB as the warehouse.** *Why:* it is a single file with no server and full SQL
(window functions, `arg_max`, JSON). It reads Parquet/CSV if the data grows, and Power BI can
read the exported CSVs. The SQL of each control is portable to most warehouses.

**D06 - Compiled releases, one row per object, keyed by `release_key`.** Every flattened row
keeps the line number of its source release. *Why:* duplicate releases for the same OCID must
stay visible to the data-quality step (DQ01). Deduplication (latest `date` wins) happens
afterwards, in `dq_kept_releases`.

**D07 - Two layers: raw tables and the clean `f_*` views.** Controls never read raw tables.
*Why:* if a data defect fixed in one place, every control inherits the fix. Critical defects null
only the broken field when possible (a negative amount does not remove the process from the
single-bid control). That keeps as much evidence as the data allows.

**D08 - No FX conversion.** Non-PEN awards are flagged (DQ06) and their amount is excluded.
*Why:* the publication does not say which exchange rate to use, and the amount controls compare
against PEN thresholds. Getting a conversion wrong is worse than leaving the amount out.

**D09 - "Absurd" amount = more than 100x the tender estimate, or more than S/ 10 billion.**
*Why:* a fixed cap alone misses unit errors (cents vs soles) in small processes, and a ratio alone
misses processes with no estimate. Both are analytical choices, documented in `quality.py`.

**D10 - Pseudonymise natural persons at ingestion with HMAC-SHA256.** Suppliers whose RUC starts
with 10, 15 or 17 (issued to individuals), or whose identifier scheme is a DNI, get
`id = NP-<first 16 hex of HMAC(key, document)>`, a generic name and no document number. The
other fields are kept as published. *Why:* a plain hash of an 8-digit DNI can be reversed by
brute force, while a keyed hash cannot without the key. It is deterministic, so aggregation still
works. Doing it at ingestion means no later step can leak the original. The key is read from
`PROCONTROL_SALT` and never written to disk. The versioned sample is pseudonymised the same way.

**D11 - Synthetic identifiers can never collide with real ones.** Every synthetic RUC has a
deliberately wrong SUNAT check digit (tested), names are "Synthetic Entity/Supplier NNN" or
"Persona Sintética NNNN", and the OCID prefix `ocds-synthpe` is not registered. *Why:* rule 1
allows public or synthetic data only. A random RUC that happened to be valid could point at a
real taxpayer.

**D12 - Thresholds live in `config/thresholds.yaml` with source, date and status.** Only the UIT
values for 2024-2026 and the 8 UIT minor-purchase limit could be checked during the session, in
secondary sources (legal press and law-firm bulletins, 2026-11-04). Everything else is
`to_verify` or `methodological`. The pipeline prints every `to_verify` item on each run, and
`procontrol to-verify` lists them. *Why:* a threshold written from memory looks authoritative,
and that makes it dangerous.

**D13 - Minimum submission periods are in calendar days.** The regulation sets them in business
days, which needs a holiday calendar. The placeholders are conservative and marked `to_verify`.
*Why:* a calendar-day threshold under-flags. The control errs towards fewer false positives until
the business-day rule is implemented.
