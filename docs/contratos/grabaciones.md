# Contrato: grabaciones del bus — v0.1

Una grabación guarda los mensajes de una sesión para reproducirlos después (T9 de `SPEC_E0.md`).

- Formato: JSON Lines, un mensaje por línea, en `recordings/` (ignorada por git).
- Solo contiene mensajes del bus: ningún mensaje lleva imágenes, video ni audio.

```json
{"rec_v": "0.1", "t_ms": 1250, "topic": "sancho/body/vision/evt/person_entered", "retained": false, "message": {"v": "0.1", "id": "2f6c1a2e-8a7b-4c1d-9e0f-3b5a6c7d8e9f", "ts": "2026-11-03T18:20:00.123Z", "source": "body", "type": "vision.person_entered", "trace_id": "9a8b7c6d-5e4f-4a3b-8c1d-0e9f8a7b6c5d", "payload": {"track_id": "t1", "confidence": 0.92, "bbox": [0.4, 0.3, 0.2, 0.3]}}}
{"rec_v": "0.1", "t_ms": 1900, "topic": "sancho/body/vision/evt/person_entered", "retained": false, "raw": "{esto no es JSON"}
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `rec_v` | sí | Versión de este contrato |
| `t_ms` | sí | Milisegundos desde el inicio de la grabación, según el reloj del grabador |
| `topic` | sí | Tópico en que se recibió |
| `retained` | sí | Si el broker lo entregó como mensaje retenido |
| `message` | uno de los dos | El mensaje, si es un objeto JSON. Se guarda aunque no sea un sobre válido |
| `raw` | uno de los dos | El contenido como texto, si no es un objeto JSON |

El grabador guarda todo lo que recibe, sin validar: los mensajes inválidos también son parte de la sesión.

## Reproducción

La herramienta `replay` usa las credenciales de su rol (`topicos-e0.md`), que solo existen en el entorno de pruebas.

1. **Qué publica:** solo lo recibido en `sancho/body/+/evt/#` sin `retained`. Omite los comandos, porque son la salida del orquestador que se está probando, y los mensajes de salud.
2. **Cuándo:** respeta los intervalos de `t_ms`.
3. **Qué cambia en cada `message`:**
   - `ts`: se le suma un mismo desplazamiento, la diferencia entre el inicio de la reproducción y el `ts` del primer mensaje que se reproduce. Así se conservan las distancias exactas entre eventos, y las latencias medidas durante la reproducción tienen sentido.
   - `source`: pasa a ser `replay`.
4. **Qué no cambia:** `id`, `trace_id`, `causation_id`, `type` y `payload`, ni el contenido de `raw`, que se publica tal cual.

## Comparación de decisiones

Dos corridas toman las mismas decisiones si sus trazas `kind: decision` (`trazas.md`) coinciden en orden y en `name`, `decision` e `inputs.message_ids`. Los `outputs` no se comparan, porque cada corrida genera mensajes nuevos.

Para que sea determinista, **el orquestador calcula sus ventanas de tiempo con el `ts` de los eventos**, no con su reloj local.
