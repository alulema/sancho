# Bitácora — 2026-11-13 — Orquestador mínimo y simulación sin hardware

- **Etapa:** E0
- **Tareas de la spec:** T7 y T8

## Qué se intentó

1. **Regla L0 (`brain/greeter.py`):** saluda a quien entra si nadie fue saludado en los últimos `greeting_window_min` minutos (10 por omisión). Es una función pura con reloj inyectado, así que se prueba sin bus ni esperas. El saludo continúa el flujo del evento: mismo `trace_id`, y `causation_id` igual al `id` de `person_entered`.
2. **Servicio del orquestador (`python -m brain`):** se suscribe a `person_entered`, decide, publica `say` y escribe una traza `decision` / `greet_on_entry` por cada evento, también cuando decide no saludar. `BrainConfig` admite exactamente las claves que un caso del banco puede poner en `given.config`, y rechaza cualquier otra.
3. **Trazas en archivo (`contracts.traces.TraceWriter`):** un archivo JSONL por componente y día UTC, validado línea por línea y escrito de inmediato.
4. **Cuerpo simulado (`python -m sim.body`, rol `sim`):**
   - Una cámara que reproduce un guion YAML (`sim/scripts/`) y publica `person_entered` con `first_seen_ts` y `frame_ts`, y `person_left` con la duración real.
   - Un TTS que registra la frase, espera un retardo de síntesis, publica `started`, espera la duración del habla y publica `finished`. Escribe la traza `action` / `speak`.
5. **`make sim` (`python -m sim`):**
   - Levanta un broker de pruebas desechable, el orquestador y el cuerpo simulado.
   - Imprime lo que cruza el bus y un resumen con las decisiones y la latencia de entrada a `started`.
   - Deja logs y trazas en `.sim/`.
6. El lanzador del broker de las pruebas pasó a `deploy/broker/local.py`, para que lo usen tanto las pruebas como `make sim`.

## Qué se midió

En el NUC (x86_64, Ubuntu 26.04), broker en contenedor:

| Prueba | Resultado |
|---|---|
| `make test` | 223 pasan en 40 s (34 nuevas, 3 de ellas de la cadena completa contra el broker real) |
| `make sim` con `dos-entradas.yaml` | 2 entradas, 1 saludo, 1 `started`, 1 `finished`, 2 decisiones con traza (`say_greeting` y `ignore`, la segunda «greeted 5.0 s ago»); ambos servicios cierran con `offline` real, sin *last will* |
| Entrada → `started` en la simulación | 246 ms, de los cuales 200 ms son la síntesis simulada. **No es una medida del sistema real**: la de T10 se hace en el Nano |
| Duración de la decisión de saludar | 42 ms, casi todo la espera del PUBACK (QoS 1) del `say`. Decidir no saludar no publica nada y tarda menos de 1 ms |
| Ventana de 0,02 min (1,2 s) con entradas separadas 1,6 s | 2 saludos (prueba `test_chain_greets_again_after_the_window`) |

## Qué falló y por qué

- **Publicar desde un handler bloquea el componente.** paho entrega los mensajes en su hilo de red, y ese mismo hilo es el que procesa el PUBACK. Si un handler publica y espera la confirmación, el hilo se espera a sí mismo. Se detectó al diseñar el orquestador y no en producción: `BusService.publish` ahora falla con un error claro si se llama desde un handler (hay una prueba para eso). Los componentes usan `Inbox`, que encola el mensaje con su hora de recepción, y lo procesan en su propio hilo.
- **`python -m sim.body` no hacía nada y salía con código 0.** Al módulo le faltaba el `if __name__ == "__main__"`. Las pruebas de la cadena completa lo detectaron porque cuentan mensajes y no solo códigos de salida.

## Supuestos confirmados o refutados

Ninguno de §18.

## Decisiones tomadas

Ninguna requiere ADR: no cambian contratos ni agregan librerías.

- **La ventana empieza cuando el saludo se publica**, no cuando llega la entrada, y las entradas ignoradas no la alargan. Si publicar falla, se registra una traza `error` hija de la decisión y la siguiente entrada vuelve a intentar.
- **La cámara simulada usa guiones, no un video de prueba.** La spec admite cualquiera de los dos. Un guion es determinista, se lee en el repo y no pone archivos de video en disco (CLAUDE.md). El formato de los guiones es interno de `sim/`, no un contrato entre componentes.
- El cuerpo simulado publica con `source: "sim"` y usa `sancho/sys/body/health`, como pide `topicos-e0.md`. Sus trazas llevan `component: "sim"`.

## Pendientes para la próxima sesión

- T9 (grabación y reproducción) y T11 (banco), que se apoyan en lo de hoy: el banco puede pasarle `given.config` a `BrainConfig` sin traducirla.
- Logs estructurados en JSON (T10). Por ahora los servicios escriben texto.
- El orquestador ignora `person_left` y `speech/status`. E0 no los necesita para decidir.

## Notas para artículos

- Que una prueba de la cadena verifique los mensajes y no solo los códigos de salida evitó dar por buena una simulación que no hacía nada.
- El bloqueo por publicar desde un callback es un clásico de los clientes MQTT con hilo de red propio. Convertirlo en un error inmediato es mejor que documentarlo.
