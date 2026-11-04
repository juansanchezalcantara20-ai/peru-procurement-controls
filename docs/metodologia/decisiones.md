# Registro de decisiones

Cada decisión de diseño con su porqué. Las decisiones nuevas se agregan al final de la sección de
su fase. Esta página es técnica: está pensada para quien quiera auditar cómo se construyó el
proyecto.

## Fase 0 · Enfoque

**D01. Señales, nunca acusaciones.** Cada salida dice que una alerta *merece revisión*. No hay
rankings de proveedores, funcionarios ni personas con nombre propio; las entidades públicas solo
aparecen en vistas agregadas. *Por qué:* un control marca una desviación frente a un patrón
esperado. Decidir si es una irregularidad le toca a un revisor con el expediente en la mano, nunca
a un tablero.

**D02. Inglés para todo lo visible (reemplazada por D35).** *Por qué:* era un requisito de la
primera vuelta, pensado para lectores fuera del Perú. Los nombres oficiales peruanos
(*Contratación menor*, *Licitación pública*) quedaban en español porque traducir nombres legales
pierde precisión.

## Fase 1 · Ingesta y calidad del dato

**D03. Lo que corrió de verdad fue el Plan C (datos simulados).** La política de red de la sesión
bloqueó `data.open-contracting.org`, el portal del OECE y `datosabiertos.gob.pe` (HTTP 403 en el
proxy). Los Planes A y B quedaron programados (`procontrol/download.py`,
`--source oece|perucompras|auto`), pero no se ejecutaron aquí. *Por qué:* era mejor entregar un
proceso que corre de punta a punta y es honesto sobre sus datos que quedarse detenido. Además, los
datos simulados dan algo que los reales no dan: una verdad conocida contra la cual medir los
controles (Fase 4). La segunda vuelta (D40) traslada la descarga real a GitHub Actions.

**D04. Los identificadores de publicación no se escribieron de memoria (actualizada por D40).**
En la primera vuelta `config/settings.yaml` dejó `publication_id: null`. *Por qué:* no se pudo abrir
el registro para confirmarlos, y escribirlos de memoria rompía la regla de «nada de memoria».
En la segunda vuelta el dueño del proyecto entregó los identificadores 135 (OECE) y 78 (Perú
Compras).

**D05. DuckDB como almacén.** *Por qué:* es un solo archivo, sin servidor y con SQL completo
(funciones de ventana, `arg_max`, JSON). Lee Parquet o CSV si los datos crecen, y Power BI puede
leer los CSV exportados. El SQL de cada control se puede llevar a la mayoría de los almacenes.

**D06. «Compiled releases», una fila por objeto, con la clave `release_key`.** Cada fila aplanada
guarda el número de línea de su release de origen. *Por qué:* los releases duplicados del mismo
OCID deben quedar visibles para el paso de calidad (DQ01). La eliminación de duplicados (gana la
`date` más reciente) se hace después, en `dq_kept_releases`.

**D07. Dos capas: tablas crudas y vistas limpias `f_*`.** Los controles nunca leen tablas crudas.
*Por qué:* si un defecto se corrige en un lugar, todos los controles heredan la corrección. Los
defectos críticos anulan solo el campo roto cuando se puede (un monto negativo no saca al proceso
del control de postor único). Así se conserva toda la evidencia que los datos permiten.

**D08. Sin conversión de moneda.** Las adjudicaciones que no están en soles se marcan (DQ06) y su
monto se excluye. *Por qué:* la publicación no dice qué tipo de cambio usar, y los controles de
montos comparan contra umbrales en soles. Convertir mal es peor que dejar el monto fuera.

**D09. Monto «absurdo» = más de 100 veces el valor estimado, o más de S/ 10,000 millones.**
*Por qué:* un tope fijo solo no detecta errores de unidad (céntimos por soles) en procesos chicos, y
una proporción sola no detecta procesos sin valor estimado. Ambas son elecciones analíticas,
documentadas en `quality.py`.

**D10. Seudonimizar a las personas naturales al ingresar los datos, con HMAC-SHA256.** Los
proveedores cuyo RUC empieza con 10, 15 o 17 (emitidos a personas), o cuyo identificador es un
DNI, reciben `id = NP-<primeros 16 hexadecimales de HMAC(clave, documento)>`, un nombre genérico
y ningún número de documento. *Por qué:* el hash simple de un DNI de 8 dígitos se revierte por
fuerza bruta; un hash con clave no, sin la clave. Es determinista, así que se puede seguir
agregando. Hacerlo al ingresar significa que ningún paso posterior puede filtrar el original. La
clave se lee de `PROCONTROL_SALT` y nunca se escribe en disco. La muestra versionada se
seudonimiza igual.

**D11. Los identificadores simulados nunca pueden coincidir con reales.** Cada RUC simulado tiene
a propósito un dígito verificador de SUNAT inválido (probado), los nombres son «Synthetic
Entity/Supplier NNN» o «Persona Sintética NNNN» y el prefijo de OCID `ocds-synthpe` no está
registrado. *Por qué:* la regla 1 permite solo datos públicos o simulados. Un RUC aleatorio que
resultara válido podría apuntar a un contribuyente real.

**D12. Los umbrales viven en `config/thresholds.yaml` con fuente, fecha y estado.** Durante la
sesión solo se pudieron comprobar, en fuentes secundarias (prensa jurídica y boletines de estudios
de abogados, 2026-11-04), los valores de la UIT 2024-2026 y el límite de compra menor de 8 UIT. Todo
lo demás está `to_verify` o es `methodological`. El proceso imprime cada `to_verify` en cada
corrida, y `procontrol to-verify` los lista. *Por qué:* un umbral escrito de memoria parece
autorizado, y eso lo hace peligroso.

**D13. Los plazos mínimos de ofertas están en días calendario.** El reglamento los fija en días
hábiles, lo que exige un calendario de feriados. Los valores de referencia son conservadores y
están `to_verify`. *Por qué:* un umbral en días calendario marca de menos. El control prefiere
pocas falsas alarmas hasta implementar la regla de días hábiles.

## Fase 2 · Catálogo de controles

**D14. El catálogo es YAML más un archivo SQL por control.** El YAML guarda la documentación que
espera un auditor: objetivo, riesgo, regla exacta, umbral, frecuencia, rol dueño, evidencia,
falsas alarmas esperadas, peso. El SQL es la regla ejecutable. *Por qué:* los revisores leen el
YAML y los ingenieros el SQL, y ninguno tiene que mantenerse sincronizado con código en otro
lugar. Las pruebas comprueban que cada `$parametro` del SQL esté declarado en el catálogo.

**D15. Los parámetros son literales (`value`) o referencias a `thresholds.yaml` (`ref`).** Las
cifras legales siempre son referencias. Las de política interna (ventana de 30 días, 3 veces la
mediana) son literales con una `note`. *Por qué:* mantiene clara la línea entre lo que dice la ley
y lo que decidió el dueño del control.

**D16. Las referencias de OCP se citan solo donde calzan.** Los códigos de Cardinal se dan solo
para R003 (plazo corto) y R018 (un solo postor), cuyas definiciones se revisaron. Los demás
controles siguen el concepto de la guía *Red Flags for Integrity* de OCP, y el catálogo dice que
son una operacionalización propia. *Por qué:* un código de indicador equivocado confundiría al
auditor que lo busque.

**D17. La tasa esperada de falsas alarmas se declara antes de medirla.** Cada control declara una
banda a priori y sus causas legítimas típicas, y la Fase 4 la mide con datos simulados. *Por qué:*
el dueño del control se compromete de antemano con el ruido esperado. Si lo medido se aleja mucho,
eso le indica que debe recalibrar.

**D18. La regla de compras partidas se ancla en el límite de compra menor (8 UIT).** Busca compras
entre 80% y 100% del límite, al menos 3 en 30 días, mismo comprador, proveedor y segmento UNSPSC,
cuya suma supera el límite. *Por qué:* el límite de 8 UIT era el único umbral de procedimiento que
se pudo comprobar en la sesión, y es donde más se fracciona. Pero la publicación OCDS real puede no
incluir las compras menores; si no las incluye, este control necesita el conjunto de órdenes de
compra (ver «Qué no es este proyecto»).

## Fase 3 · Motor de señales

**D19. Una ronda de calibración sobre datos simulados, documentada.** Los parámetros se
escribieron a priori. Tras la primera corrida se cambiaron tres: la tasa de éxito de C05 bajó de
0.80 a 0.60 (dos pares sembrados tenían tasas de 0.6-0.7 porque el proveedor también perdía en
otros procesos), y C04 subió `min_awards` de 10 a 15 y sumó `min_top_awards = 3`. Antes de ese
cambio, 111 de 125 celdas pequeñas sin patrón superaban un HHI de 2,500 porque un contrato grande
las dominaba. *Por qué:* calibrar con los mismos datos sobre los que luego se informa es circular.
Los cambios son pocos y se argumentan por mecanismo, no por el resultado. Una calibración real
necesita datos reales y casos revisados.

**D20. Benford compara la MAD con lo que el azar del muestreo produciría.** Los rangos fijos de
Nigrini suponen muestras grandes. Si los montos siguieran exactamente a Benford, la MAD esperada
para una muestra de tamaño n es (1/9) Σ_d √(2 p_d (1 − p_d) / (π n)), que vale 0.0136 con n = 300:
ya por encima del límite «aceptable» de 0.012. Una simulación (20,000 sorteos por cada n, de 150 a
5,000) dio un percentil 99 de 1.72 veces y un percentil 99.9 de unas 2.0 veces ese valor, estable
en todo n. El control informa la clase de Nigrini y marca un conjunto solo si la MAD supera 2 veces
lo esperado por azar. *Por qué:* sin esta corrección, la mayoría de las entidades con unos cientos
de montos parecerían «no conformes» por puro azar. Sería justo el tipo de acusación falsa que este
proyecto existe para evitar.

**D21. Puntaje compuesto = «noisy-OR» de peso × severidad, un término por control.** Por cada
proceso entra solo la alerta más fuerte de cada control: `100 · (1 − Π(1 − p·s))`. Los pesos
expresan especificidad: qué tan seguido una alerta de ese control, sola, vale una revisión. Se
fijaron según las bandas esperadas de falsas alarmas, no se ajustaron a los datos. *Por qué:* el
puntaje queda acotado, sube con evidencia independiente y se satura. Además se explica línea por
línea a un comité de auditoría. Benford pesa 0 por diseño.

**D22. Lo que se publica es solo agregado.** `outputs/` y el sitio contienen conteos por control,
mes, método, segmento y prioridad, más una distribución de cómo se reparten las alertas entre
entidades, sin nombrar ninguna. Las tablas a nivel de alerta (OCID, proveedores, evidencia) se
quedan en el almacén DuckDB local, ignorado por git. *Por qué:* la regla 2 prohíbe rankings y las
entidades solo aparecen agregadas. Un archivo con los OCID marcados está a un cruce de convertirse
en ranking.

**D23. Los patrones de entidad y de celda se asignan a procesos.** El HHI marca los procesos
adjudicados al proveedor dominante de la celda. Las alertas de ganador repetido y de compras
partidas marcan cada proceso miembro. *Por qué:* un revisor trabaja con expedientes, así que una
alerta tiene que apuntar a uno. La evidencia de la celda viaja en el JSON `evidence`.

## Fase 4 · Validación de los controles

**D24. En datos simulados, «falso positivo» significa «alerta sobre el fondo».** El fondo se
genera sin intención de riesgo, así que una alerta sobre él es falsa alarma por construcción. El
recall se mide por patrón sembrado. La precisión se informa dos veces: frente al patrón propio del
control y como proporción de alertas sobre el fondo neutro. Algunos patrones sembrados producen
mecánicamente la señal de otro control: los montos fabricados crean precios atípicos y el dominio
forzado crea ganadores repetidos. La revelación los cuenta de forma explícita (`AFFECTS` en
`validation.py`) en lugar de esconderlos. *Por qué:* un solo número de precisión halagaría a los
controles o los castigaría por detectar un solapamiento real.

**D25. La revisión de casos es a ciegas, y cambió el diseño.** Se tomaron 20 alertas (2 por
control por proceso más los procesos con mayor puntaje), con un sorteo con semilla para que la
muestra sea reproducible. Cada una se juzgó solo con el contexto de la hoja de trabajo, los
veredictos se escribieron en `docs/validation/review_judgments.yaml` y la revelación se calculó
después. Resultados: (1) C09 ahora excluye las compras menores o directas, porque una orden de
compra no tiene paso de firma. Se aplicó, se volvió a sortear la muestra y se juzgó el caso nuevo;
su verdad se vio antes de juzgarlo, así que está marcado `blind: false` y queda fuera del conteo de
acuerdos. (2) C03 no se puede priorizar por el tamaño del faltante hasta verificar los mínimos en
días hábiles, porque la revisión descartó un caso sembrado. (3) C02 se revisa solo junto con otras
señales o cuando la tasa de postor único de la entidad supera la nacional para el método. *Por
qué:* un control cuyas alertas nadie ha mirado es una lista de alarmas, no un control.

**D26. Con datos reales, el mismo protocolo sin revelación.** La hoja de trabajo
(`outputs/private/review_worksheet.csv`) está a nivel de alerta y la ignora git. Solo se publica la
tabla anónima de veredictos. *Por qué:* la regla 2 sigue valiendo cuando la revisión es a mano.

## Fase 5 · Sitio y Power BI

**D27. MkDocs Material, no Quarto.** *Por qué:* todo el proceso es Python, MkDocs se instala con pip
sin otro binario y GitHub Pages lo construye en un solo trabajo. El sitio se genera desde el
almacén y el catálogo en cada corrida, así que ninguna página se aparta de los controles que de
verdad corrieron.

**D28. Gráficos estáticos más el CSV detrás de cada uno.** Cada gráfico es un PNG que dibuja
matplotlib en el proceso, y sus datos agrupados se publican en `outputs/distributions/`. *Por qué:*
los gráficos se reproducen en la CI y el CSV es la vista de tabla accesible. Una sola serie por
gráfico evita leyendas, y los umbrales se dibujan y rotulan en el gráfico. Los colores vienen de la
paleta de referencia validada (una serie azul y un umbral naranja).

**D29. Cada gráfico muestra la población, nunca la lista de alertas.** Cada página de señal muestra
la distribución de la cantidad medida para *todos* los procesos, con el umbral encima. *Por qué:*
un revisor juzga un umbral viendo dónde corta la distribución. Una lista de casos marcados además
rompería la regla 2.

**D30. Las entidades de Benford se dibujan anónimas.** El gráfico de Benford muestra cada entidad
como un punto sin rótulo: su MAD observada frente a la MAD esperada por azar. *Por qué:* la regla 2
dice que las entidades solo aparecen agregadas, y el punto del gráfico es el método (azar contra
señal), no nombrar a nadie.

**D31. Power BI lee las alertas; no vuelve a programar las reglas.** Se importa `fact_alert`, y el
DAX recalcula solo agregados: tasas, HHI y el puntaje «noisy-OR» para simular qué pasa sin un
control. *Por qué:* un control se escribe una vez. Dos implementaciones de una regla terminarían
discrepando.

**D32. Las extracciones para Power BI las ignora git.** Están a nivel de alerta (OCID, claves de
proveedor seudonimizadas). *Por qué:* las mismas reglas de privacidad y de no publicar rankings
aplican a la capa de BI, y `MODEL.md` dice que el `.pbix` es interno.

## Fase 6 · Cierre

**D33. Resultados publicados reproducibles bit a bit.** Las severidades se redondean a 4
decimales, porque las sumas en paralelo de DuckDB no son asociativas. Cada `ORDER BY` detrás de una
tabla publicada tiene un desempate determinista. Dos corridas seguidas producen el mismo Markdown y
los mismos CSV (comprobado con md5). La CI compara los archivos de resultados con valores enteros
contra los versionados. *Por qué:* un control cuyo resultado cambia entre corridas idénticas no se
puede auditar.

**D34. El README dice qué se usó de verdad.** Los datos fueron simulados y los descargadores no se
ejecutaron contra el registro. 8 umbrales siguen por verificar y hubo una ronda de calibración.
*Por qué:* quien lee un repositorio de portafolio evalúa criterio, y exagerar la evidencia sería
la peor señal posible.

## Segunda vuelta · Español, lectores no técnicos y datos reales

**D35. Todo lo que lee una persona va en español (reemplaza D02).** Sitio, README, catálogo,
títulos y ejes de gráficos, encabezados de tablas, avisos, mensajes del programa y del pull
request. Quedan en inglés: los nombres de variables, funciones, columnas y claves del YAML (son
código), los comentarios y docstrings dentro del código Python (los lee quien programa), los
mensajes de commit y los nombres propios de estándares y documentos citados («Open Contracting Data
Standard», «Red Flags for Integrity»). *Por qué:* el lector principal ahora es un gerente peruano
de logística, control interno o administración. Traducir los identificadores del código no le
sirve a ese lector y rompería la compatibilidad con los datos OCDS, cuyos campos están en inglés.
