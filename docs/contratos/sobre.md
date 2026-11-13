# Contrato: sobre común de mensajes — v0.1

Todo mensaje publicado en el bus va dentro de este sobre, serializado como JSON.

```json
{
  "v": "0.1",
  "id": "2f6c1a2e-8a7b-4c1d-9e0f-3b5a6c7d8e9f",
  "ts": "2026-11-03T18:20:00.123Z",
  "source": "body",
  "type": "vision.person_entered",
  "trace_id": "9a8b7c6d-5e4f-4a3b-8c1d-0e9f8a7b6c5d",
  "payload": {}
}
```

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `v` | string | sí | Versión del sobre |
| `id` | UUID | sí | Identificador único del mensaje |
| `ts` | string | sí | Momento en que se generó el mensaje, en UTC |
| `source` | string | sí | Componente que publica (`body`, `brain`, `sim`, `eval`, …) |
| `type` | string | sí | Tipo de mensaje; coincide con el tópico (ver `topicos-e0.md`) |
| `trace_id` | UUID | sí | Une todos los mensajes y trazas de un mismo flujo. Lo crea quien inicia el flujo y lo propagan los demás |
| `causation_id` | UUID | no | `id` del mensaje que provocó este |
| `payload` | objeto | sí | Contenido específico del tipo |
| `sig` | string | no | **Reservado para E4** (identidad firmada en el bus). En E0 no se usa |

## Latencia

La latencia de punta a punta se calcula con `ts` y `trace_id`: desde el `ts` del mensaje que inicia el flujo hasta el `ts` del mensaje que lo cierra. Los relojes del Nano y del NUC deben estar sincronizados (NTP) para medir entre máquinas; si no, la medición se hace en una sola máquina.
