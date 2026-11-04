# Power BI model

The Power BI version mirrors the pipeline. The SQL controls compute the alerts, and Power BI only
reads, filters and aggregates them. Every measure is in [`measures.dax`](measures.dax).

> **Signals, never accusations.** Every report page carries the `Disclaimer` card. There are no
> visuals that rank suppliers, officials or named people. Entities appear only aggregated, by
> type, segment, method or month.

## 1. Get the data

```bash
make pipeline          # writes outputs/powerbi/*.csv (git-ignored: alert-level data)
```

In Power BI Desktop: *Get data → Text/CSV* for each file in `outputs/powerbi/`. Alternatively,
use *Folder* and split by file name. Set `date` columns to Date and `is_competitive` / `flag` /
`is_natural_person` to True/False.

## 2. Star schema

```
                 dim_date (date)            dim_control (control_id)
                      │ 1                          │ 1
                      │                            │
                      ▼ *                          ▼ *
dim_entity ──1──*  fact_process (ocid) ──1──*  fact_alert
(entity_key)          │ *     │ 1  ──1──1  fact_risk_score
                      │       │ 1  ──1──*  fact_contract
dim_method ──1────────┘       │ 1  ──1──*  fact_dq_issue
dim_segment ──1───────────────┘
dim_supplier ──1──* fact_process (supplier_key)

fact_benford  - standalone (aggregate test; never related to processes)
```

| From | To | Cardinality | Filter direction |
|---|---|---|---|
| `fact_process[date]` | `dim_date[date]` | many-to-one | single |
| `fact_process[entity_key]` | `dim_entity[entity_key]` | many-to-one | single |
| `fact_process[method]` | `dim_method[method]` | many-to-one | single |
| `fact_process[segment]` | `dim_segment[segment]` | many-to-one | single |
| `fact_process[supplier_key]` | `dim_supplier[supplier_key]` | many-to-one | single |
| `fact_alert[ocid]` | `fact_process[ocid]` | many-to-one | single (process → alert) |
| `fact_alert[control_id]` | `dim_control[control_id]` | many-to-one | single |
| `fact_risk_score[ocid]` | `fact_process[ocid]` | one-to-one | single (process → score) |
| `fact_contract[ocid]` | `fact_process[ocid]` | many-to-one | single |
| `fact_dq_issue[ocid]` | `fact_process[ocid]` | many-to-one | single |

Mark `dim_date` as the date table. Hide every key column in report view. Hide `dim_supplier` and
`fact_process[supplier_key]` entirely. They exist only so that `[HHI]` can iterate suppliers, and
no visual may put suppliers on an axis.

## 3. Suggested pages

1. **Overview** - cards for `[Processes]`, `[Awarded Amount (PEN)]`, `[% Processes Flagged]`,
   `[P1 Processes]` and `[Disclaimer]`; a bar of `[Flagged Processes]` by `dim_control[name]`.
2. **Data quality** - `[DQ Critical Issues]` and `[DQ Warning Issues]` by `fact_dq_issue[check_name]`.
3. **One page per signal** - the distribution of its metric, for example `[HHI]` by
   `dim_entity[entity_type]` × `dim_segment`, `[Single-Bid Rate]` by `dim_method`, or
   `[Median Days Award to Signature]` by month. Use the control's slicers, and put its owner
   role and expected false-positive band in a text box from `dim_control`.
4. **Trends** - `[% Processes Flagged]` and `[% Flagged YoY (pp)]` by `dim_date[year_month]`.
5. **Risk score** - a histogram of `fact_risk_score[score]` and a matrix of
   `fact_risk_score[controls]` × `[Processes]`. Add a `dim_control` slicer to see
   `[Risk Score (recomputed)]` without a given control.

## 4. Equivalence with the pipeline

| Pipeline | Power BI |
|---|---|
| `alerts` table (engine) | `fact_alert` (imported, not recomputed) |
| noisy-OR score in `engine.compute_risk_scores` | `[Risk Score (recomputed)]` |
| HHI in `controls/sql/c04_supplier_concentration.sql` | `[HHI]` |
| single-bid rate used in the case review | `[Single-Bid Rate]`, `[Single-Bid Rate vs National]` |
| `aggregate_tests` (Benford) | `fact_benford`, `[Benford MAD (all awards)]` |

The rules themselves (thresholds, windows, clusters) are not re-implemented in DAX. That is
deliberate: a control is written once, in the catalog, and the BI layer reads its output.

## 5. Privacy

Natural persons are already pseudonymised in the CSVs (`NP-<hash>`). The CSVs are alert-level,
so keep the `.pbix` internal, or publish only pages built from aggregated visuals.
