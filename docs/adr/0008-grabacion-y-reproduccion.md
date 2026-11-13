# ADR-0008 — Formato de grabación y reglas de reproducción del bus

- **Fecha:** 2026-11-06
- **Estado:** aceptada
- **Etapa:** E0

## Contexto

T9 pide grabar el bus y reproducir una sesión en el NUC con las mismas decisiones del orquestador, pero ningún contrato definía el formato, qué se reproduce ni qué pasa con las marcas de tiempo. Reproducir también los `say` grabados duplicaría los comandos del orquestador que se está probando.

## Opciones consideradas

Para `ts` al reproducir:

1. **Conservar el original:** es la copia exacta, pero las latencias medidas contra mensajes nuevos no tendrían sentido.
2. **Poner la hora de publicación a cada mensaje:** es simple, pero la variación de tiempos podría cambiar una decisión cerca del límite de una ventana.
3. **Sumar un mismo desplazamiento a todos:** conserva las distancias exactas entre eventos y da latencias válidas.

Para `id`:

1. **Generar uno nuevo:** cada publicación sería única, pero las trazas no se podrían comparar con las originales.
2. **Conservarlo:** las trazas de ambas corridas apuntan a los mismos mensajes.

## Decisión

- Nuevo contrato `grabaciones.md` v0.1.
- Se reproducen solo los eventos del cuerpo no retenidos; los comandos y la salud se omiten.
- `ts` se desplaza (opción 3), `id` y `trace_id` se conservan, y `source` pasa a `replay`.
- El orquestador calcula sus ventanas con el `ts` de los eventos, no con su reloj local.
- Dos corridas coinciden si sus trazas de decisión coinciden en orden, `name`, `decision` e `inputs.message_ids`.

## Consecuencias

- La comparación de T9 se puede automatizar sin depender de la temporización exacta.
- El orquestador confía en el `ts` del publicador. Un cuerpo con el reloj mal, o comprometido, puede alterar las ventanas de saludo. En E0 solo afecta a saludar de más o de menos, y hay que revisarlo antes de usar ventanas para algo sensible.
- Un mismo `id` aparece en la corrida original y en la reproducción, así que no sirve como identificador único entre corridas.
- Los mensajes que no son JSON se guardan en `raw` y se reproducen tal cual, por lo que también se comprueba que siguen rechazándose.

## Evidencia

Revisión de T9 y de los contratos v0.1. La aceptación se comprueba en T9, con una sesión grabada en el Nano.
