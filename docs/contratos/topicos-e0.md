# Contrato: tópicos de E0 — v0.1

## Convenciones

- Forma: `sancho/<dueño>/<capacidad>/<tipo>/<nombre>`.
- **El dueño es el componente que implementa la capacidad.** Publica sus eventos y recibe sus comandos.
- **Eventos** (`evt`): hechos ocurridos, en pasado. Solo los publica el dueño.
- **Comandos** (`cmd`): pedidos al dueño, en imperativo. Los publican otros componentes autorizados por ACL.
- El campo `type` del sobre es `<capacidad>.<nombre>` (por ejemplo, `vision.person_entered`).

## Tópicos

| Tópico | Tipo | Publica | Recibe | Payload |
|---|---|---|---|---|
| `sancho/body/vision/evt/person_entered` | evento | body | brain | `track_id` (string), `confidence` (0–1), `bbox` ([x, y, w, h] normalizados 0–1) |
| `sancho/body/vision/evt/person_left` | evento | body | brain | `track_id`, `duration_s` (número) |
| `sancho/body/speech/cmd/say` | comando | brain | body | `say_id` (UUID), `text` (string), `lang` (`es`, `en`, `pt`), `priority` (`normal`, `high`) |
| `sancho/body/speech/evt/status` | evento | body | brain | `say_id`, `state` (`started`, `finished`, `error`), `error` (string, opcional) |
| `sancho/sys/<componente>/health` | estado retenido | cada componente | todos | `status` (`online`, `offline`), `version` (string), `uptime_s` (número) |

## Salud y *last will*

- Al conectarse, cada componente publica `health` con `status: online` y el indicador *retain*.
- Cada componente registra un *last will* en `sancho/sys/<componente>/health` con `status: offline` y *retain*.

## ACL de E0

| Componente | Puede publicar | Puede suscribirse |
|---|---|---|
| body | `sancho/body/#`, `sancho/sys/body/health` | `sancho/body/+/cmd/#`, `sancho/sys/#` |
| brain | `sancho/body/+/cmd/#`, `sancho/sys/brain/health` | `sancho/body/+/evt/#`, `sancho/sys/#` |
| sim | lo mismo que body | lo mismo que body |
| eval | todo `sancho/#` (solo en el entorno de pruebas) | todo `sancho/#` |
| recorder | nada | todo `sancho/#` |

## Reglas

- Ningún mensaje contiene imágenes, video ni audio.
- `bbox` y `confidence` son metadatos; no permiten reconstruir la imagen.
