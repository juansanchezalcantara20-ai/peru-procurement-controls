# Control catalog

!!! warning "Signals, never accusations"
    An alert means *"this deserves a review"*, not *"there is an irregularity"*. No supplier,
    official or person is ranked or named; public entities appear only in aggregated views.


Every control is defined once, in `controls/catalog.yaml`, with its exact rule in
`controls/sql/`. The engine runs them from there; this page is generated from the same file.
Catalog owner: **Internal Control / Continuous Auditing lead**. Review cycle: Quarterly, and after any change in procurement law or thresholds.

| control | name | frequency | owner role | weight | expected FP | processes flagged |
|---|---|---|---|---|---|---|
| [C01](c01.md) | Split purchases below the minor-purchase limit | monthly | Procurement controller (Logistics/Abastecimiento) with Internal Control | 0.55 | medium-high (30-60% of alerts legitimate) | 113 |
| [C02](c02.md) | Single bidder in a competitive procedure | monthly | Procurement controller | 0.35 | high (50-80% legitimate) | 810 |
| [C03](c03.md) | Abnormally short submission period | weekly (during the call) | Procurement controller; Selection committee secretary | 0.5 | medium (20-40% legitimate) | 134 |
| [C04](c04.md) | Supplier concentration by entity and category (HHI) | quarterly | Category manager; Internal Control | 0.3 | medium-high (30-60% legitimate) | 572 |
| [C05](c05.md) | Same winner repeated at the same entity | quarterly | Internal Control; Procurement controller | 0.45 | medium (25-50% legitimate) | 201 |
| [C06](c06.md) | Contract amendments raising the amount above the cap | monthly | Contract administrator; Internal Control | 0.6 | medium (20-40% legitimate) | 72 |
| [C07](c07.md) | Unit price atypical against the category median | monthly | Category manager; Cost controller | 0.5 | medium-high (30-60% legitimate) | 218 |
| [C08](c08.md) | Benford's law on awarded amounts (aggregate test) | annual | Internal Audit (analytical review) | 0.0 | high for individual entities (structural reasons are common) | aggregate test |
| [C09](c09.md) | Atypical time between award and contract signature | monthly | Contract administrator | 0.4 | medium (20-40% legitimate) | 53 |
