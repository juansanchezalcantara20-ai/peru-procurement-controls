# Metodología

Esta sección es para quien quiera revisar cómo se calcula todo. El resto del sitio se puede leer
sin ella.

- [Calidad del dato: detalle técnico](calidad.md)
- [Registro de decisiones](decisiones.md): cada decisión de diseño con su porqué.
- El catálogo completo de controles está en `controls/catalog.yaml` y las reglas en `controls/sql/`
  del repositorio.

## Fuente de los datos

datos simulados. Estructura: OCDS (Open Contracting Data Standard), «compiled releases», aplanadas en
tablas relacionales en DuckDB (`processes`, `items`, `parties`, `bids`, `awards`, `contracts`,
`amendments`). Las señales leen una capa limpia (`f_process`, `f_award`, `f_item`, `f_bid`,
`f_contract`) que aplica las revisiones de calidad.

## Puntaje de prioridad

**Fórmula:** `puntaje = 100 × (1 − Π_c (1 − peso_c × severidad_c)), sobre las alertas del proceso`

Cada alerta se trata como una evidencia independiente de que un proceso merece revisión. La combinación «noisy-OR» mantiene el puntaje entre 0 y 100, lo hace crecer con cada señal adicional y se satura en lugar de sumar en línea recta: diez señales débiles no superan a dos fuertes. El peso de un control es su especificidad: qué tan probable es que una alerta de ese control, sola, valga el tiempo de un revisor, dado su perfil esperado de falsas alarmas. La severidad (0 a 1, calculada por cada regla) mide cuánto se pasó el caso de su umbral. Las pruebas agregadas (Benford) nunca entran al puntaje porque no dicen nada de un proceso individual.

La severidad de cada regla (0 a 1) es la distancia desde su umbral; por ejemplo, una adenda de
+100% con un tope de 25% tiene severidad (1.00 − 0.25) / 0.75 = 1. Por cada proceso entra solo la
alerta más fuerte de cada señal.

| señal | código | peso | por qué |
|---|---|---|---|
| Compras partidas para no hacer concurso | C01 | 0.55 | Patrón fuerte cuando aparece, pero las compras recurrentes legítimas son comunes. |
| Un solo postor en un concurso abierto | C02 | 0.35 | Muy frecuente y muchas veces estructural; evidencia débil sola, valiosa combinada. |
| Plazo demasiado corto para presentar ofertas | C03 | 0.5 | Específica y accionable cuando el plazo se compara con el mínimo correcto. |
| Un proveedor concentra las compras de una entidad | C04 | 0.3 | Indicador estructural de la celda, no prueba sobre el proceso individual. |
| El mismo ganador una y otra vez en la misma entidad | C05 | 0.45 | Usa el comportamiento de las ofertas, no solo los resultados; razonablemente específica. |
| Contratos que crecen demasiado después de firmados | C06 | 0.6 | Impacto económico directo y referencia legal clara una vez verificado el tope. |
| Precios muy por encima de lo que pagan otros | C07 | 0.5 | El precio es donde está el dinero; la mezcla dentro de las clases limita la especificidad. |
| Montos que no parecen naturales (ley de Benford) | C08 | 0.0 | Prueba agregada: excluida del puntaje por proceso por diseño. |
| Demora inusual entre la adjudicación y la firma del contrato | C09 | 0.4 | Clara y barata de revisar, pero las apelaciones son una causa legítima frecuente. |

### Combinaciones de señales más frecuentes

| combinación | procesos | puntaje_medio |
|---|---|---|
| C04,C05 | 85 | 49.5 |
| C02,C04 | 24 | 40.5 |
| C02,C07 | 20 | 61.5 |
| C02,C03 | 17 | 51.0 |
| C02,C04,C05 | 13 | 62.1 |
| C01,C04 | 12 | 50.0 |
| C03,C04 | 7 | 34.1 |
| C02,C06 | 6 | 47.3 |
| C04,C07 | 5 | 40.2 |
| C02,C05 | 3 | 51.0 |
| C02,C09 | 3 | 51.8 |
| C03,C06 | 3 | 28.6 |

## Validación: tablas completas (datos simulados)

| código | patrón sembrado | sembrados | encontrados | recall | alertas | sobre su patrón | sobre otro patrón | sobre el fondo | precisión (su patrón) | proporción sobre el fondo | % del fondo marcado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | split_purchase | 102 | 102 | 1.0 | 113 | 102 | 3 | 8 | 0.903 | 0.071 | 0.07 |
| C02 | single_bid | 60 | 60 | 1.0 | 810 | 60 | 89 | 661 | 0.074 | 0.816 | 5.95 |
| C03 | short_submission_period | 50 | 50 | 1.0 | 134 | 50 | 14 | 70 | 0.373 | 0.522 | 0.63 |
| C04 | supplier_concentration | 143 | 143 | 1.0 | 572 | 143 | 37 | 392 | 0.25 | 0.685 | 3.53 |
| C05 | repeated_winner | 89 | 89 | 1.0 | 201 | 89 | 74 | 38 | 0.443 | 0.189 | 0.34 |
| C06 | amendment_increase | 30 | 30 | 1.0 | 72 | 30 | 7 | 35 | 0.417 | 0.486 | 0.32 |
| C07 | price_outlier | 40 | 38 | 0.95 | 218 | 38 | 170 | 10 | 0.174 | 0.046 | 0.09 |
| C09 | award_signature_delay | 30 | 30 | 1.0 | 53 | 30 | 1 | 22 | 0.566 | 0.415 | 0.2 |

### Casos sembrados por prioridad

| prioridad | procesos | con caso sembrado | % sembrado |
|---|---|---|---|
| P1 | 178 | 147 | 82.6 |
| P2 | 1205 | 332 | 27.6 |
| P3 | 554 | 63 | 11.4 |

### Benford

| alcance | conjuntos probados | no conformes (Nigrini) | marcados más allá del azar | MAD media | MAD media esperada por azar |
|---|---|---|---|---|---|
| all awards | 1 | 0 | 1 | 0.0077 | 0.0021 |
| injected entity | 1 | 1 | 1 | 0.0293 | 0.0078 |
| other entities | 15 | 7 | 0 | 0.0154 | 0.012 |

### Defectos de datos sembrados

| defecto | revisión | sembrados | encontrados | marcados en total |
|---|---|---|---|---|
| duplicate_ocid | DQ01 | 15 | 15 | 15 |
| missing_buyer_id | DQ02 | 8 | 8 | 8 |
| negative_award_amount | DQ04 | 10 | 10 | 10 |
| absurd_award_amount | DQ05 | 5 | 5 | 5 |
| non_pen_currency | DQ06 | 6 | 6 | 6 |
| tender_end_before_start | DQ07 | 3 | 3 | 3 |
| contract_signed_before_award | DQ09 | 10 | 10 | 10 |
