# De dónde salen los datos

!!! warning "Señales, nunca acusaciones"
    Una alerta significa **«este caso merece revisión»**, no «hay una irregularidad». Este sitio
    no nombra ni ordena a ningún proveedor, funcionario o persona; las entidades públicas solo
    aparecen agrupadas.

!!! note "Datos simulados"
    Todas las cifras de este sitio vienen de **datos simulados**: un conjunto inventado con la
    misma estructura que las compras públicas reales, en el que se sembraron casos de riesgo a
    propósito para comprobar que las señales los encuentran. No describe a ninguna entidad real.
    Cuando corran los datos reales, este aviso cambiará solo.

## La fuente

Por ahora, **datos simulados**. Se generaron con un programa que imita la forma en que el
Estado publica sus compras en OCDS (Open Contracting Data Standard, el formato internacional para
publicar datos de contrataciones públicas): convocatorias, ofertas, adjudicaciones, contratos y
modificaciones. Son 12,562 procesos de 40 entidades
inventadas, en los que se sembraron a propósito casos de riesgo y errores de datos para comprobar
que el sistema los encuentra.

Para que nadie confunda un dato simulado con uno real, los nombres son del tipo «Synthetic
Entity 001» y los números de RUC (Registro Único de Contribuyentes) simulados se construyeron con
un dígito de control inválido: no pueden coincidir con ninguna empresa real.

El generador es simple y deja algunas huellas: por ejemplo, topa los montos de las compras
menores en 97% del límite, lo que crea un pico artificial en el gráfico de compras partidas.

**Los datos reales ya están conectados.** El proyecto incluye un flujo automático que descarga
las compras publicadas por el OECE (Organismo Especializado para las Contrataciones Públicas
Eficientes) desde el registro de Open Contracting Partnership, corre todas las señales y publica
este sitio. Cuando corra, este texto cambiará solo.

## La calidad de los datos

Antes de revisar las compras se revisan los datos: un control es tan bueno como la información
que usa. Estos son los problemas encontrados y qué se hizo con cada uno <small>(datos simulados)</small>:

| Problema encontrado | Registros | Qué se hizo |
|---|---|---|
| Proceso publicado más de una vez | 15 | Se conserva solo la publicación más reciente de cada proceso. |
| Proceso sin entidad compradora identificada | 8 | El proceso queda fuera de todas las señales (no hay a quién atribuirlo). |
| Adjudicación sin proveedor | 0 | La adjudicación queda fuera de las señales que miran al proveedor. |
| Monto adjudicado negativo o cero | 10 | Se descarta el monto; el proceso sigue en las señales que no usan montos. |
| Monto adjudicado absurdo | 5 | Se descarta el monto (más de 100 veces el valor estimado o más de S/ 10,000,000,000). |
| Adjudicación en una moneda distinta al sol | 6 | Se descarta el monto (no se intenta convertir la moneda). |
| Plazo de ofertas que termina antes de empezar | 3 | Se descartan las fechas del plazo (el proceso no entra a la señal de plazo corto). |
| Adjudicación fechada antes del cierre de ofertas | 0 | Solo se informa. |
| Contrato firmado antes de su adjudicación | 10 | Se descarta la fecha de firma (el proceso no entra a la señal de demora en la firma). |
| Fecha fuera de un rango creíble | 0 | Solo se informa (rango de 2000-01-01 a 2030-12-31). |
| Identificador de adjudicación repetido en un proceso | 0 | Solo se informa. |
| Mismo participante registrado con nombres distintos | 0 | Solo se informa (las variantes de nombre son comunes en los registros). |
| Artículo sin clasificación | 0 | El artículo no entra a la señal de precios atípicos. |
| Contrato que no corresponde a ninguna adjudicación | 0 | Solo se informa. |
| Número de postores distinto al de ofertas publicadas | 0 | Solo se informa; se usa el número de postores distintos cuando está disponible. |

Cuando un dato está dañado se aparta solo ese dato: por ejemplo, un monto negativo no se usa para
comparar precios, pero el proceso sigue revisándose en las señales que no usan montos.

## Qué no es este proyecto

- **No es una auditoría ni una acusación.** Una alerta es una razón para mirar un expediente,
  nunca un hallazgo. Muchas alertas tienen explicaciones normales.
- **No es asesoría legal.** Algunos límites legales usados aquí todavía están por verificar en la
  norma oficial (los plazos mínimos para ofertar y el tope de las adendas).
- **No es un ranking.** No hay listas de proveedores, funcionarios ni entidades «más riesgosas», y
  no las habrá.
- **No ve todo.** No tiene datos de apelaciones, no convierte montos en dólares y cuenta los
  plazos en días calendario, no hábiles. Si la fuente no publica las compras menores, la señal de
  compras partidas no puede funcionar.
- **No reemplaza al revisor.** Ordena la fila de expedientes; la conclusión la saca una persona
  con el expediente en la mano.

## Cómo se protegen los datos personales

Los proveedores que son personas naturales (su número de contribuyente empieza con 10, 15 o 17) se reemplazan, al
momento de leer los datos, por un código anónimo que no se puede revertir sin una clave secreta.
Antes de publicar este sitio, una prueba automática revisa que no aparezca el nombre de ningún
proveedor, funcionario o persona, ni el nombre de ninguna entidad pública; si aparece uno, el sitio
no se publica.
