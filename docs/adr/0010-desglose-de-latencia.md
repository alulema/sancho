# ADR-0010 — Marcas de tiempo para desglosar la latencia de E0

- **Fecha:** 2026-11-13
- **Estado:** aceptada
- **Etapa:** E0 (T10)

## Contexto

T10 define la latencia de punta a punta desde el `ts` de `person_entered` hasta el `started` de `speech/status`, y pide desglosarla en detección → bus → decisión → TTS. Con los contratos vigentes eso no es posible:

- El `ts` de `person_entered` se genera **después** de detectar y de aplicar la histéresis, así que la detección queda fuera de cualquier medición.
- No hay marcas de cuándo cada componente recibe un mensaje, así que el bus y la decisión no se pueden separar.
- No está definido qué significa `started`: ¿cuando llega el pedido, cuando termina la síntesis o cuando empieza a sonar?

## Opciones consideradas

1. **Medir solo lo que define la spec:** es simple, pero no responde la pregunta que importa, cuánto espera la persona, y deja el desglose incompleto.
2. **Marcas de captura en el evento y de recepción en las trazas:** agrega dos campos opcionales a `person_entered` y usa el `ts` de trazas que ya existen. Todas las marcas salen del mismo reloj del Nano.
3. **Medición externa:** grabar con otra cámara a la persona entrando y el audio, y contar cuadros. Es la única que incluye el sensor y el parlante, pero es manual y no sirve para cada corrida.

## Decisión

Se elige la opción 2. La opción 3 queda como validación opcional de una sola vez, útil para un artículo.

- `person_entered` lleva `first_seen_ts` y `frame_ts`, ambos momentos de captura (`topicos-e0.md` v0.3).
- `started` significa que empezó a sonar el audio.
- El `ts` de una traza marca el inicio del paso; en un paso que responde a un mensaje, su recepción. El cuerpo deja una traza `speak` al recibir `say` (`trazas.md` v0.2).

Ambos cambios son compatibles: campos opcionales nuevos y la precisión de un campo que ya existía.

## Desglose

Todas las marcas vienen del reloj del Nano, porque cuerpo, cerebro y broker corren allí.

| Tramo | Desde | Hasta |
|---|---|---|
| Histéresis | `first_seen_ts` | `frame_ts` |
| Inferencia y publicación | `frame_ts` | `ts` de `person_entered` |
| Bus, del cuerpo al cerebro | `ts` de `person_entered` | `ts` de la traza `greet_on_entry` |
| Decisión | `ts` de la traza `greet_on_entry` | `ts` del `say` |
| Bus, del cerebro al cuerpo | `ts` del `say` | `ts` de la traza `speak` |
| Síntesis y arranque del audio | `ts` de la traza `speak` | `ts` del `status` con `started` |

Se reportan p50 y p95 de cada tramo y de dos totales:

- **De punta a punta (spec):** del `ts` de `person_entered` al `started`. Es la métrica de aceptación de T10.
- **Percibida:** de `first_seen_ts` al `started`. Es lo más cercano a lo que espera la persona, sin contar el sensor ni el parlante.

## Consecuencias

- La histéresis aparece como un tramo propio. Bajarla acorta la espera, pero puede producir saludos falsos, y ese compromiso queda visible con números.
- El cuerpo tiene que convertir las marcas de los cuadros a UTC. Con `nvarguscamerasrc` hay que verificar en T6 qué reloj usan los buffers.
- Un ajuste de NTP durante una corrida puede deformar los tramos. El reporte debe registrar si el reloj estuvo sincronizado.
- Si la síntesis no es en streaming, el tramo de TTS incluye sintetizar toda la frase. Así se mide cuánto aportaría el streaming en E2.

## Evidencia

Revisión de T10 y de los contratos vigentes; aún no hay mediciones.
