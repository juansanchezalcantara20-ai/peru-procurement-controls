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

## Phase 2 · Control catalog

**D14 - The catalog is YAML plus one SQL file per control.** The YAML holds the control
documentation an auditor expects: objective, risk, exact rule, threshold, frequency, owner role,
evidence, expected false positives, weight. The SQL file is the executable rule. *Why:* reviewers
read the YAML and engineers read the SQL, and neither has to be kept in sync with code elsewhere.
The tests check that every `$parameter` in the SQL is declared in the catalog.

**D15 - Parameters are either literal (`value`) or references into `thresholds.yaml` (`ref`).**
Legal figures are always references. Internal-policy figures (window of 30 days, ratio 3x the
median) are literals with a `note`. *Why:* this keeps a clear line between what the law says and
what the control owner decided.

**D16 - OCP references are cited only where they fit.** Cardinal codes are given only for R003
(short submission period) and R018 (single bid), whose definitions I checked. The other
controls follow the concept of the OCP *Red Flags for Integrity* guide, and the catalog says
they are this project's own operationalisation. *Why:* a wrong indicator code would mislead an
auditor who looks it up.

**D17 - The expected false-positive rate is stated before measuring it.** Each control declares
an a-priori band and its typical legitimate causes, and Phase 4 measures it on synthetic data.
*Why:* a control owner commits to the expected noise up front. If the measured rate is far
off, that tells them to recalibrate.

**D18 - Split-purchase rule anchored on the minor-purchase limit (8 UIT).** It looks for
purchases at 80-100% of the limit, at least 3 of them in 30 days, same buyer, supplier and UNSPSC
segment, with a combined total above the limit. *Why:* the 8 UIT limit is the only procedure
threshold that could be checked during the session, and it is where splitting is most common.
The real OCDS feed may not include minor purchases, though. If it does not, this control needs
the purchase-order dataset (see Scope & limitations).

## Phase 3 · Signal engine

**D19 - One calibration round on synthetic data, documented.** The parameters were written
a priori. After the first run, three were changed: C05 win rate 0.80 → 0.60 (two injected
pairs had rates of 0.6-0.7 because the supplier also lost elsewhere), and C04 got
`min_awards` 10 → 15 plus a new `min_top_awards = 3`. Before that change, 111 of 125 small
background cells exceeded HHI 2,500 because one large contract dominated them. *Why:*
calibrating on the same data you then report on is circular. The changes are few and argued
from mechanism, not from the score. Real calibration needs real data and reviewed cases.

**D20 - Benford compares the MAD with its sampling-noise expectation.** Nigrini's fixed MAD
ranges assume large samples. Under an exact Benford distribution, the expected MAD for sample
size n is (1/9) Σ_d √(2 p_d (1 − p_d) / (π n)), which is 0.0136 at n = 300, already above the
0.012 "acceptable" bound. Simulation (20,000 draws per n, from n = 150 to n = 5,000) gave a 99th
percentile of 1.72x and a 99.9th percentile of about 2.0x that expectation, stable across n.
The control reports Nigrini's class and flags a scope only when MAD > 2x the noise expectation.
*Why:* without this correction most entities with a few hundred awards would look
"nonconforming" from noise alone. That would be exactly the kind of false accusation this
project exists to avoid.

**D21 - Composite score = noisy-OR of weight x severity, one term per control.** For each
process, only the strongest alert of each control enters, as
`100 · (1 − Π(1 − w·s))`. Weights express specificity, i.e. how often an alert from that
control alone is worth a review. They are set from the expected false-positive bands, not fitted.
*Why:* the score stays bounded, rises with independent evidence and saturates. It is also easy
to explain line by line to an audit committee. Benford has weight 0 by design.

**D22 - Published outputs are aggregated only.** `outputs/` and the site contain counts by
control, month, method, segment and priority, plus a distribution of how alerts spread across
entities, without naming any entity. Alert-level tables (OCIDs, supplier ids, evidence) stay in
the local DuckDB warehouse, which is git-ignored. *Why:* rule 2 says no rankings, and entities
appear only in aggregates. A file listing flagged OCIDs is one join away from a ranking.

**D23 - Entity-level and cell-level patterns are attached to processes.** HHI flags the
processes awarded to the dominant supplier of the cell. Repeated-winner and split-purchase
alerts flag every member process. *Why:* a reviewer works on case files, so an alert has to
point at one. The cell-level evidence travels in the `evidence` JSON.
