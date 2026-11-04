# Control catalog

!!! warning "Signals, never accusations"
    An alert means *"this deserves a review"*, not *"there is an irregularity"*. No supplier,
    official or person is ranked or named; public entities appear only in aggregated views.


Every control is defined once, in `controls/catalog.yaml`, with its exact rule in
`controls/sql/`. The engine runs them from there; this page is generated from the same file.
Catalog owner: **Jefatura de Control Interno / Auditoría continua**. Review cycle: Trimestral, y después de cualquier cambio en la ley de contrataciones o en los umbrales.

| control | name | frequency | owner role | weight | expected FP | processes flagged |
|---|---|---|---|---|---|---|
| [C01](c01.md) | Compras partidas para no hacer concurso | mensual | Responsable de Logística/Abastecimiento, con Control Interno | 0.55 | media-alta (entre 30 y 60 de cada 100 alertas resultan normales) | 113 |
| [C02](c02.md) | Un solo postor en un concurso abierto | mensual | Responsable de Logística/Abastecimiento | 0.35 | alta (entre 50 y 80 de cada 100 alertas resultan normales) | 810 |
| [C03](c03.md) | Plazo demasiado corto para presentar ofertas | semanal (durante la convocatoria) | Responsable de Logística; secretaría del comité de selección | 0.5 | media (entre 20 y 40 de cada 100 alertas resultan normales) | 134 |
| [C04](c04.md) | Un proveedor concentra las compras de una entidad | trimestral | Responsable de la categoría de compra; Control Interno | 0.3 | media-alta (entre 30 y 60 de cada 100 alertas resultan normales) | 572 |
| [C05](c05.md) | El mismo ganador una y otra vez en la misma entidad | trimestral | Control Interno; Responsable de Logística | 0.45 | media (entre 25 y 50 de cada 100 alertas resultan normales) | 201 |
| [C06](c06.md) | Contratos que crecen demasiado después de firmados | mensual | Administrador del contrato; Control Interno | 0.6 | media (entre 20 y 40 de cada 100 alertas resultan normales) | 72 |
| [C07](c07.md) | Precios muy por encima de lo que pagan otros | mensual | Responsable de la categoría de compra; control de costos | 0.5 | media-alta (entre 30 y 60 de cada 100 alertas resultan normales) | 218 |
| [C08](c08.md) | Montos que no parecen naturales (ley de Benford) | anual | Auditoría Interna (revisión analítica) | 0.0 | alta para entidades individuales (hay razones estructurales frecuentes) | aggregate test |
| [C09](c09.md) | Demora inusual entre la adjudicación y la firma del contrato | mensual | Administrador del contrato | 0.4 | media (entre 20 y 40 de cada 100 alertas resultan normales) | 53 |
