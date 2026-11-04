# ¿Funciona?

!!! warning "Señales, nunca acusaciones"
    Una alerta significa **«este caso merece revisión»**, no «hay una irregularidad». Este sitio
    no nombra ni ordena a ningún proveedor, funcionario o persona; las entidades públicas solo
    aparecen agrupadas.

Para saber si una señal funciona hay que conocer la respuesta de antemano, y en los datos reales
nadie la conoce. Por eso se comprobó de dos formas: **sembrando casos de riesgo inventados** en un
conjunto de datos simulados para ver si las señales los encuentran, y **revisando a mano y a
ciegas** una muestra de alertas, como lo haría un auditor.

!!! note "Esta página usa datos simulados"
    Toda esta página se calculó con los datos simulados, incluso cuando el resto del sitio ya
    muestra datos reales: solo en datos simulados se sabe qué casos son irregulares.

## 1. ¿Encuentra los casos sembrados?
- **Compras partidas.** Sembramos 102 casos de compras partidas y los encontró todos. De cada 100 alertas de esta señal, unas 7 resultan normales: es de las señales más precisas.
- **Un solo postor.** Sembramos 60 casos de un solo postor y los encontró todos. De cada 100 alertas de esta señal, unas 82 resultan normales: por eso esta señal pesa poco cuando aparece sola.
- **Plazo de ofertas muy corto.** Sembramos 50 casos de plazo de ofertas muy corto y los encontró todos. De cada 100 alertas de esta señal, unas 52 resultan normales: por eso conviene mirarla junto con otras señales.
- **Concentración en un proveedor.** Sembramos 143 casos de concentración en un proveedor y los encontró todos. De cada 100 alertas de esta señal, unas 68 resultan normales: por eso esta señal pesa poco cuando aparece sola.
- **Ganador repetido.** Sembramos 89 casos de ganador repetido y los encontró todos. De cada 100 alertas de esta señal, unas 19 resultan normales: es de las señales más precisas.
- **Contratos que crecen.** Sembramos 30 casos de contratos que crecen y los encontró todos. De cada 100 alertas de esta señal, unas 49 resultan normales: por eso conviene mirarla junto con otras señales.
- **Precios atípicos.** Sembramos 40 casos de precios atípicos y encontró 38. De cada 100 alertas de esta señal, unas 5 resultan normales: es de las señales más precisas.
- **Demora en la firma.** Sembramos 30 casos de demora en la firma y los encontró todos. De cada 100 alertas de esta señal, unas 42 resultan normales: por eso conviene mirarla junto con otras señales.

Una advertencia importante: **los casos sembrados son más fáciles de encontrar que los reales**,
porque se inventaron limpios y bien marcados. Estas cifras son un techo: en datos reales la
detección será menor.

## 2. ¿Ordena bien la fila de revisión?

Cada señal sola se equivoca seguido; combinadas, aciertan mucho más. De los procesos que quedaron
en **prioridad alta**, 83 de cada 100 eran casos sembrados. En **prioridad baja**,
solo 11 de cada 100. Es decir: si un revisor empieza por la prioridad alta,
casi todo lo que mire valdrá la pena.

## 3. ¿Y la prueba de los montos (ley de Benford)?

Una entidad inventada tenía todos sus montos fabricados. Con la regla clásica, 7 de
15 entidades **normales** habrían parecido sospechosas: con unos cientos de
montos, el puro azar ya produce esas diferencias. Después de descontar el azar, la prueba
marcó a la entidad con montos fabricados
y a ninguna entidad normal. Sin esa corrección, la prueba habría
acusado al azar.

## 4. ¿Detecta los datos defectuosos?

También se sembraron 57 errores de datos (procesos duplicados, montos
negativos o absurdos, montos en dólares, fechas imposibles, procesos sin entidad). La revisión de
calidad encontró **57** y los apartó antes de correr las señales.

## 5. Revisión a mano y a ciegas

Se tomaron 20 alertas al azar (dos de cada señal más las de mayor puntaje). Para cada una se
miró solo lo que un revisor tendría a mano (los montos, las fechas, cómo se compara la entidad con
el resto del país) y se escribió un veredicto **antes** de saber si era un caso sembrado:

- **merece revisión**: el contexto no explica la señal;
- **probable falsa alarma**: el contexto da una explicación normal.

**Resultado.** Los veredictos a ciegas coincidieron con la realidad en **15 de 19** casos.
De las 7 alertas que en realidad eran falsas alarmas, el revisor descartó 4 solo con
el contexto; las demás tenían otras señales a la vez y merecían una mirada, como pasaría en una
auditoría real. El caso R20 se juzgó después de ver la respuesta y no se cuenta.

**Lo que cambió por esta revisión:** la señal de demora en la firma dejó de mirar las compras
menores, porque una orden de compra no tiene firma de contrato. Además quedó escrito que la señal
de plazo corto no se puede priorizar bien hasta verificar los plazos legales en días hábiles, y que
la señal de postor único se revisa sola solo cuando la entidad está por encima del promedio del país.

| Caso | Señal | Rubro | Veredicto del revisor | Por qué | Qué era en realidad |
|---|---|---|---|---|---|
| R01 | Compras partidas | Servicios de transporte | merece revisión | 5 compras de transporte entre 89% y 98% del límite dentro de la ventana (4.7 veces el límite en total); 5 de las 6 compras menores del proveedor en la entidad ese año están en este grupo. El transporte no es un consumible mensual fijo. | compras partidas (sembrado) |
| R02 | Compras partidas | Equipos informáticos y de telecomunicaciones | merece revisión | 4 compras de equipos informáticos entre 85% y 94% del límite, 3.5 veces el límite en total; son todas las compras menores del proveedor en la entidad. Un equipo es una necesidad puntual, no recurrente. | compras partidas (sembrado) |
| R03 | Un solo postor | Obras de construcción | merece revisión | El postor único por sí solo no llama la atención (la entidad tiene 16 de cada 100 procesos de ese método con postor único, frente a 19 en el país), pero el proceso también tiene señales de concentración, ganador repetido y precio atípico. | proceso normal (sin caso sembrado) |
| R04 | Un solo postor | Combustibles y lubricantes | probable falsa alarma | Compra de combustible; la tasa de postor único de la entidad (14 de cada 100) está por debajo de la nacional (19) y no hay otra señal. Calza con un mercado pequeño estructural. | proceso normal (sin caso sembrado) |
| R05 | Un solo postor | Papel y útiles de papel | merece revisión | El papel lo venden muchas empresas, y aun así la entidad tiene 30 de cada 100 procesos de este método con postor único, frente a 19 en el país (44 procesos). Revisar las bases y la difusión de la entidad. | proceso normal (sin caso sembrado) |
| R06 | Plazo de ofertas muy corto | Combustibles y lubricantes | probable falsa alarma | 3 días frente a un mínimo provisional de 5 en una comparación de precios, que es un método rápido. El faltante es pequeño, el mínimo aún está por verificar (días hábiles o calendario) y no hay otra señal. | plazo corto (sembrado) |
| R07 | Plazo de ofertas muy corto | Alimentos y bebidas | probable falsa alarma | Mismo caso en una subasta inversa: 3 días frente a un mínimo provisional de 5, entidad con baja tasa de postor único (4 de cada 100), sin otra señal. | proceso normal (sin caso sembrado) |
| R08 | Concentración en un proveedor | Servicios de transporte | merece revisión | Rubro de transporte con un índice de concentración de 8,456 (de un máximo de 10,000): un proveedor tiene 29 de 33 adjudicaciones y 92 de cada 100 soles. | concentración (sembrado) |
| R09 | Concentración en un proveedor | Servicios de gestión y consultoría | probable falsa alarma | Índice de concentración de 3,063 con 23 proveedores; el principal llega a 52 de cada 100 soles con solo 3 adjudicaciones, así que uno o dos contratos grandes de consultoría mueven el índice. Es la causa conocida de «un contrato grande». | proceso normal (sin caso sembrado) |
| R10 | Ganador repetido | Equipos informáticos y de telecomunicaciones | merece revisión | 10 licitaciones ganadas de 10 en las que ofertó, en la misma entidad y el mismo año. | ganador repetido (sembrado) |
| R11 | Ganador repetido | Combustibles y lubricantes | merece revisión | 22 de 22 subastas inversas ganadas en una entidad, junto con concentración y postor único. | concentración (sembrado) |
| R12 | Ganador repetido | Servicios de transporte | merece revisión | 14 de 14 concursos públicos ganados, junto con concentración y postor único. | concentración (sembrado) |
| R13 | Ganador repetido | Equipos informáticos y de telecomunicaciones | merece revisión | 12 victorias en 14 ofertas en subastas inversas; sin otra señal puede ser un proveedor eficiente, pero la cantidad de victorias justifica mirar las ofertas perdedoras. | proceso normal (sin caso sembrado) |
| R14 | Contratos que crecen | Servicios de gestión y consultoría | merece revisión | El monto modificado subió 114% en dos adendas, en un proceso que además tuvo un solo postor. | contrato que crece (sembrado) |
| R15 | Contratos que crecen | Alimentos y bebidas | probable falsa alarma | Una adenda de +36% en un contrato de alimentos, 11 puntos sobre un tope que también está por verificar, puntaje bajo y sin otra señal. Calza con una ampliación de cantidades aprobada; verificar la resolución. | entidad con montos inventados (sembrado) |
| R16 | Contratos que crecen | Servicios de transporte | merece revisión | +57% en dos adendas en un contrato que además tuvo un plazo de ofertas corto. | contrato que crece (sembrado) |
| R17 | Precios atípicos | Alimentos y bebidas | merece revisión | Precio unitario 4.9 veces la mediana de la clase (325 artículos). La entidad paga 28% más que la mediana en todos sus artículos, lo que apunta a un problema de precios o de datos de toda la entidad que merece una revisión. | entidad con montos inventados (sembrado) |
| R18 | Precios atípicos | Alimentos y bebidas | merece revisión | Precio unitario 6.1 veces la mediana de la misma clase, en la misma entidad con precios sobre la mediana en general. | entidad con montos inventados (sembrado) |
| R19 | Demora en la firma | Servicios de ingeniería | merece revisión | 126 días entre la adjudicación y la firma de un servicio de ingeniería. Una apelación lo explicaría, pero no se publican datos de apelaciones, así que la revisión es barata y necesaria. | demora en la firma (sembrado) |
| R20 | Demora en la firma | Papel y útiles de papel | merece revisión | 131 días entre la adjudicación y la firma en una subasta inversa de papel, un contrato simple donde las apelaciones son raras. Mismo criterio que el otro caso de C09: es barato revisar si hubo apelación. | demora en la firma (sembrado) |

Las tablas completas, con todas las columnas, están en la [metodología](metodologia/index.md).
