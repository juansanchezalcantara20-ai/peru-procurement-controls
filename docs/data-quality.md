# Data quality report

> **Signals, never accusations.** An alert means *"this deserves a review"*, not *"there is an
> irregularity"*. That applies to data-quality findings too: a defect is usually a publication or
> capture problem, not misconduct.

**Source:** Plan C - synthetic OCDS dataset with injected risk patterns (seeded, offline)

Before controlling the data, we control its quality. Every check below is executed on the
flattened OCDS tables; its *effect* column says what the analytical layer does with the records it
finds. **42** records hit critical checks and **15** hit warning checks.

## Volumes through the pipeline

| layer | n |
|---|---|
| releases (raw) | 12580 |
| processes kept (one per OCID) | 12565 |
| processes in analytical layer | 12557 |
| awards in analytical layer | 12557 |
| awards with usable amount | 12536 |
| contracts in analytical layer | 12557 |

## Checks

| check_id | check | severity | records | effect |
|---|---|---|---|---|
| DQ01 | Duplicate OCID (more than one release per process) | warning | 15 | Only the latest release per OCID is kept (ties: last line in file). |
| DQ02 | Missing buyer identifier | critical | 8 | Process excluded from every control (no entity to attribute it to). |
| DQ03 | Award without supplier | critical | 0 | Award excluded from supplier-based controls. |
| DQ04 | Negative or zero award amount | critical | 10 | Award amount set to NULL in the analytical layer. |
| DQ05 | Absurd award amount | critical | 5 | Award amount set to NULL (>100x tender estimate or >S/ 10,000,000,000). |
| DQ06 | Award currency is not PEN | critical | 6 | Amount set to NULL (no FX conversion is attempted). |
| DQ07 | Tender period ends before it starts | critical | 3 | Tender period set to NULL (excluded from the submission-period control). |
| DQ08 | Award dated before the bid deadline | warning | 0 | Reported only. |
| DQ09 | Contract signed before its award | critical | 10 | Signature date set to NULL (excluded from the award-to-signature control). |
| DQ10 | Date outside the plausible range | warning | 0 | Reported only (range 2000-01-01 to 2030-12-31). |
| DQ11 | Duplicate award identifier within a process | warning | 0 | Reported only. |
| DQ12 | Same party id with different names | warning | 0 | Reported only (name variants are common in registries). |
| DQ13 | Item without classification | warning | 0 | Item excluded from the category-median price control. |
| DQ14 | Contract whose awardID matches no award | warning | 0 | Reported only. |
| DQ15 | numberOfTenderers disagrees with published bids | warning | 0 | Reported only; the analytical layer uses the count of distinct bidders when available. |

## Field completeness (latest release per OCID)

Tender periods are expected to be empty for minor and direct purchases, which have no call for
bids; their missing rate therefore mirrors the share of non-competitive processes.

| table | field | rows | missing | missing_pct |
|---|---|---|---|---|
| processes | buyer_id | 12565 | 8 | 0.06 |
| processes | procurement_method | 12565 | 0 | 0.0 |
| processes | method_details | 12565 | 0 | 0.0 |
| processes | main_category | 12565 | 0 | 0.0 |
| processes | tender_amount | 12565 | 0 | 0.0 |
| processes | tender_start | 12565 | 6883 | 54.78 |
| processes | tender_end | 12565 | 6883 | 54.78 |
| processes | number_of_tenderers | 12565 | 0 | 0.0 |
| awards | supplier_id | 12565 | 0 | 0.0 |
| awards | amount | 12565 | 0 | 0.0 |
| awards | award_date | 12565 | 0 | 0.0 |
| contracts | date_signed | 12565 | 0 | 0.0 |
| contracts | amount | 12565 | 0 | 0.0 |
| items | classification_id | 16291 | 0 | 0.0 |
| items | quantity | 16291 | 0 | 0.0 |
| items | unit_amount | 16291 | 0 | 0.0 |

## How the checks feed the controls

* Critical findings remove the record, or only the broken field, from the `f_*` views that every
  control reads. A negative amount, for example, does not remove the process from the single-bid
  control, but it is excluded from Benford and from the price-outlier control.
* Warnings are reported only. They are listed so the data owner can fix them at source.
* The full list of offending records is in the `dq_issues` table of the DuckDB warehouse. Only the
  counts are versioned in `outputs/quality/`.
