# ADR-0015 — Banco de evaluación: estado limpio por caso y reglas de verificación

- **Fecha:** 2026-11-15
- **Estado:** aceptada (2026-11-17)
- **Etapa:** E0 (T11)

## Contexto

T11 pide un runner que cargue los casos de `casos-banco.md`, inyecte eventos y verifique mensajes esperados y prohibidos dentro de un plazo. Al implementarlo aparecieron tres puntos que el contrato v0.2 no fijaba:

- **`expect.count`:** podía leerse como «exactamente» o como «al menos». El primer ejemplo del contrato combina `expect count: 1` con `forbid count_gt: 1`, y esa combinación solo tiene sentido si `expect` es un mínimo.
- **Qué componentes nombra `stop`/`start`,** y quién recibe `given.config`.
- **Qué pasa con un caso mal configurado:** ¿falla el sistema o falla el caso?

Además había que decidir cómo lograr el «estado limpio» que pide el contrato.

## Opciones consideradas

Estado limpio:

1. **Un broker y componentes nuevos por caso:** aislamiento total, sin retenidos ni estado de la regla de un caso a otro. Cuesta el arranque de cada caso: menos de 1 s en el NUC y unos 8 s en el Nano en modo 5 W, casi todo la importación de Python.
2. **Un broker para todo el banco, reiniciando solo los componentes:** más rápido, pero hay que borrar los retenidos a mano y un caso que deja el broker en mal estado contamina a los siguientes.

`expect.count`:

1. **Mínimo** (el máximo va en `forbid`): coincide con el ejemplo del contrato y separa «debe pasar» de «no debe pasar».
2. **Exacto:** más estricto, pero vuelve redundante el `forbid` del propio ejemplo.

## Decisión

- **Opción 1 para el estado limpio:** cada caso corre en su propio broker de pruebas desechable (`deploy/broker/local.py`), con el orquestador y el cuerpo simulado recién arrancados. El runner usa el rol `eval`.
- **`expect.count` es un mínimo** y `forbid.count_gt` un máximo. Se cuentan todos los mensajes del tópico que no sean retenidos, válidos o no, incluidos los inyectados por el caso. La coincidencia de `payload` es parcial.
- **Componentes:** `brain` y `body`. En el NUC, `body` es el cuerpo simulado. `given.config` se valida con `BrainConfig`; una clave desconocida es un **error** del caso (`error`), distinto de un fallo del sistema (`fail`).
- **Duración:** el caso dura hasta su mayor `within_ms` o su último `at_ms`, y se verifica al final.
- **Resultados:** `eval/results/<fecha UTC>-<commit>.json`, con resumen, cada verificación con lo observado, la máquina y si el árbol tenía cambios sin commit. Se versionan en git.
- El contrato pasa a **`casos-banco.md` v0.3** (cambio compatible: aclara la semántica y no cambia el formato).

## Consecuencias

- Cada caso también deja su grabación (`recording.jsonl`) y los logs de cada componente en `.sim/bench/`, para investigar un fallo.
- El banco tarda más que con un broker compartido. En el NUC son 35 s; en el Nano, seis casos tardan 84 s.
- Un caso que espera «exactamente uno» debe declarar las dos cosas, `expect count: 1` y `forbid count_gt: 1`, como el ejemplo del contrato.
- `eval/` está en `PROTECTED_PATHS`. T11 pide explícitamente crear allí el runner y los casos; cambios posteriores siguen la regla de rutas protegidas.

## Evidencia

- En el Nano (modo 5 W), 2026-11-15: `python -m eval --no-save` pasa 6/6 casos. Los casos duran entre 9 y 21 s, casi todo el arranque de los componentes. En el caso de mensajes inválidos, el log del orquestador muestra el rechazo de los dos mensajes y luego el saludo a la entrada válida.
- En el NUC (x86_64), 2026-11-17: `make bench` pasa 6/6 casos en 35 s (entre 3,6 y 9,8 s por caso).
- Pruebas: `tests/test_bench.py` (reglas de verificación y dos casos completos contra el broker real).
