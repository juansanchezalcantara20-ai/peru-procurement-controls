# Composite risk score

!!! warning "Signals, never accusations"
    An alert means *"this deserves a review"*, not *"there is an irregularity"*. No supplier,
    official or person is ranked or named; public entities appear only in aggregated views.


**Formula:** `puntaje = 100 × (1 − Π_c (1 − peso_c × severidad_c)), sobre las alertas del proceso`

Cada alerta se trata como una evidencia independiente de que un proceso merece revisión. La combinación «noisy-OR» mantiene el puntaje entre 0 y 100, lo hace crecer con cada señal adicional y se satura en lugar de sumar en línea recta: diez señales débiles no superan a dos fuertes. El peso de un control es su especificidad: qué tan probable es que una alerta de ese control, sola, valga el tiempo de un revisor, dado su perfil esperado de falsas alarmas. La severidad (0 a 1, calculada por cada regla) mide cuánto se pasó el caso de su umbral. Las pruebas agregadas (Benford) nunca entran al puntaje porque no dicen nada de un proceso individual.

Each rule computes the severity (0-1) as the distance past its threshold. For example, an
amendment at +100% against a 25% cap has severity (1.00 - 0.25) / 0.75 = 1. Only the
strongest alert of each control counts for a process.

## Weights

| control | name | weight | rationale |
|---|---|---|---|
| C01 | Compras partidas para no hacer concurso | 0.55 | Patrón fuerte cuando aparece, pero las compras recurrentes legítimas son comunes. |
| C02 | Un solo postor en un concurso abierto | 0.35 | Muy frecuente y muchas veces estructural; evidencia débil sola, valiosa combinada. |
| C03 | Plazo demasiado corto para presentar ofertas | 0.5 | Específica y accionable cuando el plazo se compara con el mínimo correcto. |
| C04 | Un proveedor concentra las compras de una entidad | 0.3 | Indicador estructural de la celda, no prueba sobre el proceso individual. |
| C05 | El mismo ganador una y otra vez en la misma entidad | 0.45 | Usa el comportamiento de las ofertas, no solo los resultados; razonablemente específica. |
| C06 | Contratos que crecen demasiado después de firmados | 0.6 | Impacto económico directo y referencia legal clara una vez verificado el tope. |
| C07 | Precios muy por encima de lo que pagan otros | 0.5 | El precio es donde está el dinero; la mezcla dentro de las clases limita la especificidad. |
| C08 | Montos que no parecen naturales (ley de Benford) | 0.0 | Prueba agregada: excluida del puntaje por proceso por diseño. |
| C09 | Demora inusual entre la adjudicación y la firma del contrato | 0.4 | Clara y barata de revisar, pero las apelaciones son una causa legítima frecuente. |

## Review priority

* **P1**: >= 50  - revisar dentro del ciclo
* **P2**: 25-50 - revisar por muestreo
* **P3**: < 25  - solo monitorear

![Risk score distribution](assets/charts/risk_score.png)

| priority | processes | mean_score | mean_controls |
|---|---|---|---|
| P1 | 178 | 57.4 | 1.69 |
| P2 | 1205 | 35.4 | 1.09 |
| P3 | 554 | 9.7 | 1.02 |

## Most frequent combinations of signals

Processes where several independent controls fire together are the best use of a reviewer's
time, because each extra signal makes a legitimate explanation less likely.

| controls | processes | mean_score |
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

*The score orders the review queue. It does not measure wrongdoing.*
