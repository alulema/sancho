# Contrato: trazas — v0.2

Cada decisión del asistente deja una traza. Es la base del registro auditable, del XAI y del banco de evaluación.

- Formato: JSON Lines, un registro por línea.
- Ubicación en E0: archivos locales por componente y día. (En E1 pasan a la partición cifrada).
- No contienen imágenes, audio ni secretos.

```json
{
  "v": "0.1",
  "ts": "2026-11-03T18:20:00.180Z",
  "trace_id": "9a8b7c6d-5e4f-4a3b-8c1d-0e9f8a7b6c5d",
  "span_id": "c1d2e3f4-0000-4000-8000-000000000001",
  "parent_span_id": null,
  "component": "brain",
  "kind": "decision",
  "name": "greet_on_entry",
  "level": "L0",
  "inputs": { "message_ids": ["2f6c1a2e-8a7b-4c1d-9e0f-3b5a6c7d8e9f"] },
  "decision": "say_greeting",
  "reason": "no greeting in the last 10 minutes",
  "alternatives": ["ignore"],
  "outputs": { "message_ids": ["5b4a3c2d-1e0f-4a9b-8c7d-6e5f4a3b2c1d"] },
  "duration_ms": 2.4,
  "cost": null
}
```

| Campo | Descripción |
|---|---|
| `trace_id` | El mismo del sobre del flujo |
| `span_id` / `parent_span_id` | Jerarquía de pasos dentro del flujo |
| `component` | Quién registra |
| `kind` | `decision`, `action`, `error`, `measurement` |
| `name` | Nombre estable del paso o regla |
| `level` | Nivel de enrutamiento (`L0`–`L3`); en E0 siempre `L0` |
| `inputs` / `outputs` | Referencias a mensajes, no copias de su contenido |
| `decision` / `reason` / `alternatives` | Qué se decidió, por qué y qué otras opciones había |
| `ts` | Inicio del paso: para un paso que responde a un mensaje, el momento en que se recibió |
| `duration_ms` | Tiempo del paso; el fin es `ts` + `duration_ms` |
| `cost` | Costo en dinero o tokens; `null` en E0 |

## Trazas que exige la medición de latencia de E0

| Componente | `kind` | `name` | `ts` | `inputs` / `outputs` |
|---|---|---|---|---|
| brain | `decision` | `greet_on_entry` | Recepción de `person_entered` | El evento / el `say`, si lo hubo |
| body | `action` | `speak` | Recepción de `say` | El `say` / los `status` publicados |
