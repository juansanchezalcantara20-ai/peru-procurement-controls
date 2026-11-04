# Modelo de Power BI

La versión en Power BI refleja el proceso. Los controles en SQL calculan las alertas; Power BI solo
las lee, las filtra y las agrega. Todas las medidas están en [`measures.dax`](measures.dax).

> **Señales, nunca acusaciones.** Cada página del informe lleva la tarjeta `Aviso`. No hay visuales
> que ordenen proveedores, funcionarios ni personas con nombre propio. Las entidades aparecen solo
> agregadas, por tipo, segmento, método o mes.

## 1. Obtener los datos

```bash
make pipeline          # escribe outputs/powerbi/*.csv (ignorados por git: datos a nivel de alerta)
```

En Power BI Desktop: *Obtener datos → Texto/CSV* para cada archivo de `outputs/powerbi/`, o
*Carpeta* y separar por nombre de archivo. Ponga las columnas `date` como Fecha y `is_competitive`,
`flag` e `is_natural_person` como Verdadero/Falso.

## 2. Esquema en estrella

```
                 dim_date (date)            dim_control (control_id)
                      │ 1                          │ 1
                      ▼ *                          ▼ *
dim_entity ──1──*  fact_process (ocid) ──1──*  fact_alert
(entity_key)          │ *     │ 1  ──1──1  fact_risk_score
                      │       │ 1  ──1──*  fact_contract
dim_method ──1────────┘       │ 1  ──1──*  fact_dq_issue
dim_segment ──1───────────────┘
dim_supplier ──1──* fact_process (supplier_key)

fact_benford  - independiente (prueba agregada; nunca se relaciona con procesos)
```

| Desde | Hacia | Cardinalidad | Dirección del filtro |
|---|---|---|---|
| `fact_process[date]` | `dim_date[date]` | muchos a uno | única |
| `fact_process[entity_key]` | `dim_entity[entity_key]` | muchos a uno | única |
| `fact_process[method]` | `dim_method[method]` | muchos a uno | única |
| `fact_process[segment]` | `dim_segment[segment]` | muchos a uno | única |
| `fact_process[supplier_key]` | `dim_supplier[supplier_key]` | muchos a uno | única |
| `fact_alert[ocid]` | `fact_process[ocid]` | muchos a uno | única (proceso → alerta) |
| `fact_alert[control_id]` | `dim_control[control_id]` | muchos a uno | única |
| `fact_risk_score[ocid]` | `fact_process[ocid]` | uno a uno | única (proceso → puntaje) |
| `fact_contract[ocid]` | `fact_process[ocid]` | muchos a uno | única |
| `fact_dq_issue[ocid]` | `fact_process[ocid]` | muchos a uno | única |

Marque `dim_date` como tabla de fechas. Oculte todas las columnas clave en la vista de informe.
Oculte `dim_supplier` y `fact_process[supplier_key]` por completo: existen solo para que
`[Índice de concentración (HHI)]` recorra proveedores, y ningún visual puede poner proveedores en un eje.

## 3. Páginas sugeridas

1. **Resumen**: tarjetas de `[Procesos]`, `[Monto adjudicado (S/)]`, `[% Procesos con alerta]`,
   `[Procesos prioridad P1]` y `[Aviso]`; barras de `[Procesos con alerta]` por `dim_control[name]`.
2. **Calidad del dato**: `[Problemas de datos críticos]` y `[Problemas de datos menores]` por
   `fact_dq_issue[check_name]`.
3. **Una página por señal**: la distribución de su medida, por ejemplo
   `[Índice de concentración (HHI)]` por `dim_entity[entity_type]` × `dim_segment`,
   `[Tasa de postor único]` por `dim_method` o `[Días hasta la firma (mediana)]` por mes. Agregue
   un cuadro de texto con el rol dueño y la banda esperada de falsas alarmas de `dim_control`.
4. **Tendencias**: `[% Procesos con alerta]` y `[Cambio frente al año anterior (puntos)]` por
   `dim_date[year_month]`.
5. **Puntaje de riesgo**: histograma de `fact_risk_score[score]` y una matriz de
   `fact_risk_score[controls]` × `[Procesos]`. Agregue un segmentador de `dim_control` para ver
   `[Puntaje recalculado]` sin un control.

## 4. Equivalencia con el proceso

| Proceso | Power BI |
|---|---|
| tabla `alerts` (motor) | `fact_alert` (importada, no recalculada) |
| puntaje «noisy-OR» en `engine.compute_risk_scores` | `[Puntaje recalculado]` |
| HHI en `controls/sql/c04_supplier_concentration.sql` | `[Índice de concentración (HHI)]` |
| tasa de postor único usada en la revisión de casos | `[Tasa de postor único]`, `[Postor único frente al país]` |
| `aggregate_tests` (Benford) | `fact_benford`, `[Desviación Benford (todas las adjudicaciones)]` |

Las reglas (umbrales, ventanas, grupos) no se vuelven a programar en DAX. Es deliberado: un
control se escribe una vez, en el catálogo, y la capa de BI lee su resultado.

## 5. Privacidad

Las personas naturales ya vienen seudonimizadas en los CSV (`NP-<hash>`). Los CSV están a nivel de
alerta: mantenga el `.pbix` interno o publique solo páginas hechas con visuales agregados.
