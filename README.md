# Controles sobre las compras públicas del Perú

**Analítica de control continuo sobre las compras públicas peruanas.** Convierte los datos de
compras en *controles*: reglas escritas que detectan señales de riesgo, cada una con su umbral, su
rol dueño, la evidencia que genera y su tasa esperada de falsas alarmas, igual que trabaja un área
de control interno o de auditoría continua.

> **Señales, nunca acusaciones.** Una alerta significa *«este caso merece revisión»*, no *«hay una
> irregularidad»*. No se ordena ni se nombra a ningún proveedor, funcionario ni persona. Las
> entidades públicas aparecen solo en vistas agregadas. Las personas naturales se reemplazan por
> un seudónimo antes de guardar cualquier dato.

> **Datos usados hasta ahora: simulados (Plan C).** El entorno donde se construyó el proyecto no
> tenía acceso al registro de Open Contracting Partnership ni al portal del OECE (Organismo
> Especializado para las Contrataciones Públicas Eficientes). Todos los resultados versionados
> vienen de un conjunto simulado con estructura OCDS (2024-2025, 12,500 procesos, 40 entidades) con
> patrones de riesgo sembrados a propósito, que no describe a ninguna entidad real. **Los datos
> reales ya están conectados** mediante un flujo de GitHub Actions (ver «Datos reales» más abajo).
> El sitio dice «(datos simulados)» junto a cada cifra hasta que ese flujo corra; después cambia
> solo a «datos reales del OECE, descargados el [fecha]».

**Sitio:** https://juansanchezalcantara20-ai.github.io/peru-procurement-controls/

## Resumen ejecutivo

| | |
|---|---|
| **Qué incluye** | 15 revisiones de calidad del dato, 9 controles (8 por proceso y Benford como prueba sobre el conjunto), un puntaje de riesgo compuesto, la validación de los propios controles, un sitio web y un modelo para Power BI |
| **Primero la calidad del dato** | Se detectaron los 57 defectos de datos sembrados (duplicados, montos negativos o absurdos, moneda distinta al sol, fechas incoherentes, entidad faltante). Los defectos críticos se excluyen campo por campo antes de correr cualquier control |
| **Detección** | Encuentra entre 95 y 100 de cada 100 casos sembrados en cada señal ([validación](docs/funciona.md)) |
| **Ruido, medido** | De cada 100 alertas, entre 5 (precios atípicos) y 82 (un solo postor) caen sobre procesos normales. Cada control declaró su banda esperada *antes* de medirla |
| **Priorización** | 83 de cada 100 procesos de prioridad alta (P1) tienen un patrón sembrado, frente a 11 de cada 100 en prioridad baja (P3). La precisión viene de combinar señales |
| **Revisión de casos** | 20 alertas revisadas a ciegas. 15 de 19 veredictos ciegos coinciden con la verdad. La revisión cambió un control (la demora en la firma ahora excluye las compras menores) |
| **Honestidad** | 8 umbrales legales siguen «por verificar» y se imprimen en cada corrida; la única ronda de calibración está documentada ([D19](docs/metodologia/decisiones.md)) |

**Tres patrones agregados que vale la pena mirar** (con datos simulados: ilustran el método, no
describen al Perú):

1. **Los umbrales fijos de Benford acusan al azar.** Con unos cientos de montos por entidad, los
   rangos de Nigrini califican de «no conformes» a 8 de 16 entidades. Al corregir por el azar del
   muestreo queda exactamente una: la entidad sembrada.
2. **El postor único es frecuente, y por eso pesa poco solo.** Salta en 6 de cada 100 procesos
   normales (en las adjudicaciones simplificadas, 19 de cada 100 tienen un solo postor). Se revisa
   solo junto con otras señales o si la entidad está por encima del promedio nacional.
3. **La concentración y el ganador repetido van juntos.** Son el par de señales que más veces
   salta a la vez (101 procesos). Cada una sola hace ruido; juntas forman la mayor parte de la cola
   de prioridad alta.

## Cómo correrlo

Un solo comando reproduce todo: instalación, proceso, revisiones de código, pruebas y sitio.

```bash
make all
```

Paso a paso:

```bash
python -m pip install -e ".[dev]"
```

```bash
python -m procontrol run                    # datos simulados (por defecto, sin internet, con semilla fija)
```

```bash
python -m procontrol run --source oece      # datos reales del OECE (publicación 135 del registro)
```

```bash
python -m procontrol to-verify              # umbrales que siguen por verificar
```

```bash
python -m pytest && python -m ruff check src tests && python -m mkdocs serve
```

Defina `PROCONTROL_SALT` con un valor secreto antes de procesar datos reales: es la clave del hash
que seudonimiza a las personas naturales.

## Datos reales: cómo lanzar el flujo desde GitHub

El flujo **«Datos reales»** descarga las compras del OECE (publicación 135 del registro de Open
Contracting Partnership) o de Perú Compras (publicación 78), corre todas las señales, revisa el
sitio y lo publica. Corre solo el día 3 de cada mes; para lanzarlo a mano:

1. Entre al repositorio en GitHub y abra la pestaña **Actions**.
2. En la lista de la izquierda elija **Datos reales**.
3. A la derecha pulse **Run workflow**. Deje la rama `main`, la fuente `oece` y los años
   `2024 2025` (o cámbielos), y pulse el botón verde **Run workflow**.
4. Espere. La primera vez puede tardar entre 30 minutos y un par de horas, porque los archivos
   pesan varios GB. Puede cerrar la página; GitHub le avisará por correo si falla.
5. Cuando los dos pasos («Descargar, procesar y revisar» y «Publicar el sitio») estén en verde,
   abra el sitio: el aviso de arriba debe decir «Datos reales del OECE…, descargados el [fecha]».

Opcional pero recomendable: en **Settings → Secrets and variables → Actions → New repository
secret**, cree un secreto llamado `PROCONTROL_SALT` con cualquier texto largo y secreto. Si no
existe, el flujo genera una clave al azar en cada corrida, lo que también protege a las personas
naturales; el secreto solo sirve para que los seudónimos sean los mismos entre corridas.

### Qué hacer si falla

Abra la corrida en rojo y luego el paso marcado con una ✗. El mensaje está en español. **Si algo
falla, el sitio no se publica y sigue mostrando la versión anterior**: nunca queda a medias.

| Paso en rojo | Qué significa | Qué hacer |
|---|---|---|
| Descargar los datos reales… con «No se pudo descargar… después de 5 intentos» | Corte de red o registro saturado | Volver a lanzarlo en unas horas (**Re-run all jobs**) |
| Descargar… con «No se descargó ningún año» | Esos años no existen en la publicación | Ver en data.open-contracting.org qué años hay y lanzarlo con esos años |
| Descargar… con «no aparece en el registro» | Cambió el número de la publicación | Buscar el número nuevo en el registro y cambiarlo en `config/settings.yaml` |
| Descargar… con «está dañado o incompleto» | El archivo llegó cortado | Volver a lanzarlo |
| Liberar espacio / proceso con «No space left on device» | Los años pedidos no caben en el disco | Lanzarlo con un solo año (por ejemplo `2025`) |
| Prueba de legibilidad del sitio | Algún texto nuevo quedó con código, inglés o una sigla sin explicar | El mensaje dice la página y el texto; corregirlo en `src/procontrol/report.py` o en `controls/catalog.yaml` |
| Candado de privacidad | El sitio iba a mostrar el nombre de un proveedor, persona o entidad | **No forzar la publicación.** El mensaje dice la página (no el nombre); revisar qué texto lo trae |
| Publicar el sitio | Pages no está activado | Settings → Pages → Source: «GitHub Actions», y relanzar |

En cada corrida, en la parte de abajo de la página de la corrida, queda un archivo
**registro-de-la-corrida** con lo que se descargó (años, tamaño, fecha y huella de cada archivo).

El flujo **«Sitio con datos simulados»** sigue publicando el sitio simulado cada vez que cambia
`main`, pero deja de hacerlo en cuanto el sitio publicado tiene datos reales: no los pisa.

## Cómo funciona

```
obtener ─► ingresar ─► calidad ─► señales ─► validar ─► informe
 (A/B/C)   OCDS→DuckDB  15 revisiones,  motor desde   casos sembrados  sitio MkDocs,
           personas      vistas          el catálogo,  + revisión a     exportación
           naturales     limpias         puntaje       ciegas           para Power BI
           seudonimizadas
```

| Ruta | Contenido |
|---|---|
| `config/thresholds.yaml` | Cada umbral legal o metodológico con su fuente, fecha de revisión y estado |
| `controls/catalog.yaml` | **El catálogo de controles**: objetivo, riesgo, regla, umbral, frecuencia, rol dueño, evidencia, falsas alarmas esperadas, peso y textos en lenguaje simple |
| `controls/sql/` | La regla exacta de cada control; el motor la ejecuta con los parámetros del catálogo |
| `src/procontrol/` | `synthetic`, `download`, `ingest`, `privacy`, `quality`, `engine`, `validation`, `report`, `powerbi` |
| `docs/` | Fuente del sitio (páginas generadas por el proceso), [decisiones](docs/metodologia/decisiones.md), veredictos de la revisión de casos |
| `powerbi/` | [`measures.dax`](powerbi/measures.dax) y [`MODEL.md`](powerbi/MODEL.md) (esquema en estrella, relaciones, páginas) |
| `outputs/` | Solo resultados agregados y versionados. Los datos a nivel de alerta se quedan en el DuckDB local, ignorado por git |
| `data/sample/` | 50 releases seudonimizados. Los datos crudos se descargan o generan, nunca se suben |
| `tests/` | Más de 90 pruebas. Cada señal tiene casos pequeños que deben dispararla y otros que no; también se prueban el descargador (contra una imitación local del registro) y las dos revisiones del sitio |
| `.github/workflows/` | `ci.yml` (pruebas y revisiones del sitio en cada push), `datos-reales.yml` (datos reales, mensual o a mano), `pages.yml` (sitio simulado mientras no haya datos reales) |

### Las señales

| Señal | Qué busca | Referencia | Peso |
|---|---|---|---|
| Compras partidas (C01) | Varias compras justo bajo el límite de 8 UIT al mismo proveedor en pocos días | OCP, fraccionamiento | 0.55 |
| Un solo postor (C02) | Concursos abiertos con una sola oferta | OCP Cardinal R018 | 0.35 |
| Plazo de ofertas muy corto (C03) | Menos días que el mínimo del método para ofertar | OCP Cardinal R003 | 0.50 |
| Concentración en un proveedor (C04) | Un proveedor se lleva casi todo un rubro de una entidad (índice HHI) | OCP, concentración | 0.30 |
| Ganador repetido (C05) | El mismo proveedor gana casi todo lo que oferta en una entidad | OCP, ganador repetido | 0.45 |
| Contratos que crecen (C06) | Adendas que suben el monto sobre el tope | OCP, modificaciones | 0.60 |
| Precios atípicos (C07) | Precio unitario 3 o más veces el típico de su clase | OCP, precios | 0.50 |
| Montos poco naturales (C08) | Ley de Benford, solo sobre el conjunto | Nigrini (2012) | 0 |
| Demora en la firma (C09) | Más de 60 días entre la adjudicación y la firma | OCP, adjudicación | 0.40 |

### Datos personales

Los proveedores cuyo RUC empieza con 10, 15 o 17 (emitidos a personas), o cuyo identificador es un
DNI, se reemplazan *al ingresar los datos* por `NP-<HMAC-SHA256(clave, documento)[:16]>`, con un
nombre genérico y sin número de documento. Un hash con clave no se puede revertir probando todos los
DNI posibles, y sigue siendo determinista, así que se puede agregar. La muestra versionada pasa por
la misma seudonimización, y las pruebas comprueban que ningún nombre ni documento llegue al almacén
ni a los resultados ([D10](docs/metodologia/decisiones.md)).

## Qué demuestra este proyecto

| Lo que piden las vacantes | Dónde se ve |
|---|---|
| **Control interno y diseño de controles** | Cada control tiene objetivo, riesgo, regla, umbral, frecuencia, rol dueño, evidencia y falsas alarmas esperadas (`controls/catalog.yaml`). Los umbrales legales están separados de los de política interna |
| **Auditoría continua** | Los controles corren desde un catálogo en un proceso listo para correr de forma programada, generan evidencia por alerta y se resumen en una cola de revisión (P1/P2/P3) con un método de puntaje documentado |
| **Auditoría de procesos** | Una revisión de casos a ciegas con protocolo escrito, cuyos hallazgos cambiaron el diseño de un control. Tasas de falsas alarmas medidas, no solo conteos de alarmas |
| **Analítica de compras** | OCDS de punta a punta (convocatoria, ofertas, adjudicaciones, contratos, modificaciones), métodos de contratación peruanos, límites en UIT, HHI, comparación de precios unitarios, fraccionamiento |
| **Calidad y gobierno de datos** | 15 revisiones antes de cualquier control; exclusión campo por campo; un registro de umbrales con fuentes y estado de verificación; registro de decisiones; seudonimización de datos personales |
| **SQL** | Cada regla es un archivo SQL de DuckDB: uniones con ventanas para agrupar compras, HHI, medianas robustas, Benford con referencia de azar |
| **Python** | Un paquete con proceso completo, un generador con semilla y verdad conocida, un motor guiado por catálogo, pytest, ruff, CI y resultados reproducibles |
| **Análisis de riesgo y BI** | Un puntaje compuesto, métricas de validación, un sitio generado y un esquema en estrella para Power BI con medidas DAX |

## Cómo se construyó

Construí este repositorio dirigiendo a Claude Code (el agente de programación de Anthropic). Yo
definí los objetivos, las reglas duras (solo datos públicos o simulados, señales y no
acusaciones, seudonimización, umbrales con fuente, pruebas para cada señal) y el plan por fases. El
agente escribió el código, el SQL, las pruebas y la documentación dentro de esos límites, y anotó
cada decisión de diseño con su porqué en el [registro de decisiones](docs/metodologia/decisiones.md).
La revisión de casos a ciegas de la Fase 4 también se hizo en esa sesión, y el archivo de la
revisión lo dice.

## Alcance y limitaciones

* **Por ahora, solo datos simulados en el repositorio.** Los patrones, tasas y gráficos versionados
  ilustran el método y no dicen nada del Perú. El flujo de datos reales está listo pero no se pudo
  probar contra el registro desde el entorno de construcción; se probó contra una imitación local
  del registro. El generador es simple: montos con distribución log-normal, proveedores
  elegidos por afinidad ponderada, y los montos de compras menores topados en 97% del límite, lo
  que crea un pico visible en el gráfico de compras partidas.
* **La validación simulada es optimista.** Los casos sembrados son más limpios que los reales, así
  que la detección medida aquí es un techo. Hubo una ronda de calibración con los mismos datos
  ([D19](docs/metodologia/decisiones.md)).
* **Umbrales por verificar.** Solo se comprobaron la UIT 2024-2026 y el límite de compra menor de
  8 UIT, en fuentes secundarias. Los plazos mínimos de ofertas (días hábiles), el tope de adendas
  bajo la Ley 32069 y la UIT 2023 están «por verificar».
* **Supuestos sobre la publicación real que hay que comprobar.** Puede que las compras menores no
  estén en la publicación OCDS; si no están, la señal de compras partidas necesita el conjunto de
  órdenes de compra. Los montos modificados se leen de `amendments[].value` (o del campo simulado
  `x_amendedValue`). Las ofertas pueden venir solo como lista de postores, sin montos.
* **Sin conversión de moneda, sin calendario de días hábiles y sin datos de apelaciones.** Cada
  una de estas faltas limita lo que los controles pueden concluir.
* **No es asesoría legal ni una opinión de auditoría.** Una señal es una razón para mirar, nunca un
  hallazgo.

## Licencia

MIT. Ver [LICENSE](LICENSE).
