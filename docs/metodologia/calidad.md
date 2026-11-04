# Calidad del dato: detalle técnico

**Fuente:** Plan C - synthetic OCDS dataset with injected risk patterns (seeded, offline)

Cada revisión se ejecuta sobre las tablas aplanadas de OCDS (Open Contracting Data Standard, el
estándar internacional de datos abiertos de contrataciones). La columna «qué se hace» dice cómo
trata la capa analítica los registros encontrados. Las revisiones críticas sacan el registro, o
solo el campo dañado, de las vistas `f_*` que leen todas las señales; las menores solo se informan.

## Volúmenes a lo largo del proceso

| capa | cantidad |
|---|---|
| publicaciones (crudas) | 12577 |
| procesos conservados (uno por OCID) | 12562 |
| procesos en la capa analítica | 12554 |
| adjudicaciones en la capa analítica | 12554 |
| adjudicaciones con monto utilizable | 12533 |
| contratos en la capa analítica | 12554 |

## Revisiones

| código | revisión | gravedad | registros | qué se hace |
|---|---|---|---|---|
| DQ01 | Proceso publicado más de una vez | menor | 15 | Se conserva solo la publicación más reciente de cada proceso. |
| DQ02 | Proceso sin entidad compradora identificada | crítico | 8 | El proceso queda fuera de todas las señales (no hay a quién atribuirlo). |
| DQ03 | Adjudicación sin proveedor | crítico | 0 | La adjudicación queda fuera de las señales que miran al proveedor. |
| DQ04 | Monto adjudicado negativo o cero | crítico | 10 | Se descarta el monto; el proceso sigue en las señales que no usan montos. |
| DQ05 | Monto adjudicado absurdo | crítico | 5 | Se descarta el monto (más de 100 veces el valor estimado o más de S/ 10,000,000,000). |
| DQ06 | Adjudicación en una moneda distinta al sol | crítico | 6 | Se descarta el monto (no se intenta convertir la moneda). |
| DQ07 | Plazo de ofertas que termina antes de empezar | crítico | 3 | Se descartan las fechas del plazo (el proceso no entra a la señal de plazo corto). |
| DQ08 | Adjudicación fechada antes del cierre de ofertas | menor | 0 | Solo se informa. |
| DQ09 | Contrato firmado antes de su adjudicación | crítico | 10 | Se descarta la fecha de firma (el proceso no entra a la señal de demora en la firma). |
| DQ10 | Fecha fuera de un rango creíble | menor | 0 | Solo se informa (rango de 2000-01-01 a 2030-12-31). |
| DQ11 | Identificador de adjudicación repetido en un proceso | menor | 0 | Solo se informa. |
| DQ12 | Mismo participante registrado con nombres distintos | menor | 0 | Solo se informa (las variantes de nombre son comunes en los registros). |
| DQ13 | Artículo sin clasificación | menor | 0 | El artículo no entra a la señal de precios atípicos. |
| DQ14 | Contrato que no corresponde a ninguna adjudicación | menor | 0 | Solo se informa. |
| DQ15 | Número de postores distinto al de ofertas publicadas | menor | 0 | Solo se informa; se usa el número de postores distintos cuando está disponible. |

## Campos vacíos (última publicación de cada proceso)

Las fechas del plazo de ofertas están vacías, como es de esperar, en las compras menores y
directas, que no tienen convocatoria.

| tabla | campo | filas | vacíos | % vacíos |
|---|---|---|---|---|
| processes | buyer_id | 12562 | 8 | 0.06 |
| processes | procurement_method | 12562 | 0 | 0.0 |
| processes | method_details | 12562 | 0 | 0.0 |
| processes | main_category | 12562 | 0 | 0.0 |
| processes | tender_amount | 12562 | 0 | 0.0 |
| processes | tender_start | 12562 | 6880 | 54.77 |
| processes | tender_end | 12562 | 6880 | 54.77 |
| processes | number_of_tenderers | 12562 | 0 | 0.0 |
| awards | supplier_id | 12562 | 0 | 0.0 |
| awards | amount | 12562 | 0 | 0.0 |
| awards | award_date | 12562 | 0 | 0.0 |
| contracts | date_signed | 12562 | 0 | 0.0 |
| contracts | amount | 12562 | 0 | 0.0 |
| items | classification_id | 16278 | 0 | 0.0 |
| items | quantity | 16278 | 0 | 0.0 |
| items | unit_amount | 16278 | 0 | 0.0 |
