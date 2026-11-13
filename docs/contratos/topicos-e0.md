# Contrato: tópicos de E0 — v0.3

## Convenciones

- Forma: `sancho/<dueño>/<capacidad>/<tipo>/<nombre>`.
- **El dueño es el componente que implementa la capacidad.** Publica sus eventos y recibe sus comandos.
- **Eventos** (`evt`): hechos ocurridos, en pasado. Solo los publica el dueño.
- **Comandos** (`cmd`): pedidos al dueño, en imperativo. Los publican otros componentes autorizados por ACL.
- El campo `type` del sobre es `<capacidad>.<nombre>` (por ejemplo, `vision.person_entered`). En los mensajes de salud es `sys.health`.

## Tópicos

| Tópico | Tipo | Publica | Recibe | Payload |
|---|---|---|---|---|
| `sancho/body/vision/evt/person_entered` | evento | body | brain | `track_id` (string), `confidence` (0–1), `bbox` ([x, y, w, h] normalizados 0–1), `first_seen_ts` y `frame_ts` (opcionales; ver *Marcas para medir latencia*) |
| `sancho/body/vision/evt/person_left` | evento | body | brain | `track_id`, `duration_s` (número) |
| `sancho/body/speech/cmd/say` | comando | brain | body | `say_id` (UUID), `text` (string), `lang` (`es`, `en`, `pt`), `priority` (`normal`, `high`) |
| `sancho/body/speech/evt/status` | evento | body | brain | `say_id`, `state` (`started`, `finished`, `error`), `error` (string, opcional). `started` se publica cuando empieza a sonar el audio, después de la síntesis |
| `sancho/sys/<componente>/health` | estado retenido | cada servicio | todos | `status` (`online`, `offline`), `version` (string), `uptime_s` (número), `last_will` (booleano, opcional) |

## Marcas para medir latencia

`person_entered` lleva dos marcas opcionales, en el mismo formato que `ts` del sobre. El cuerpo debe enviarlas siempre que pueda obtenerlas:

- `first_seen_ts`: momento de captura del primer cuadro en que se detectó a esa persona (`track_id`).
- `frame_ts`: momento de captura del cuadro que confirmó la entrada al superar la histéresis.

Ambas son momentos de **captura** del cuadro, no de su procesamiento, convertidos a UTC con el reloj del sistema. Se cumple `first_seen_ts` ≤ `frame_ts` ≤ `ts`. Ninguna mide el retardo del propio sensor, que queda fuera de lo que el software puede ver.

## Salud y *last will*

Publican salud los **servicios**: `body`, `brain` y `sim`, que reemplaza a `body` y usa `sancho/sys/body/health`. Las **herramientas** (`recorder`, `replay`, `eval`) no publican salud: corren por sesión y no hay nada que dependa de ellas.

- **Al conectarse:** el servicio publica `health` con `status: online` y *retain*.
- ***Last will*:** al conectarse, registra un mensaje en su tópico de salud con `status: offline`, `last_will: true`, `uptime_s: 0` y *retain*, dentro del sobre común.
- **Marcas del *last will*:** el broker entrega el mensaje tal como se registró, así que su `ts` es el momento de la conexión, no el de la caída. El momento de la caída es cuando se recibe el mensaje. Nadie debe calcular duraciones ni latencias con ese `ts`.
- **Cierre ordenado:** el broker descarta el *last will* en una desconexión normal. Antes de desconectarse, el servicio publica `status: offline` con *retain*, con su `ts` y `uptime_s` reales y sin `last_will`.

## ACL de E0

| Componente | Entorno | Puede publicar | Puede suscribirse |
|---|---|---|---|
| body | producción y pruebas | `sancho/body/+/evt/#`, `sancho/sys/body/health` | `sancho/body/+/cmd/#`, `sancho/sys/#` |
| brain | producción y pruebas | `sancho/body/+/cmd/#`, `sancho/sys/brain/health` | `sancho/body/+/evt/#`, `sancho/sys/#` |
| recorder | producción y pruebas | nada | todo `sancho/#` |
| sim | solo pruebas | lo mismo que body | lo mismo que body |
| replay | solo pruebas | `sancho/body/+/evt/#` | nada |
| eval | solo pruebas | todo `sancho/#` | todo `sancho/#` |

El broker de producción, en el Nano, no tiene credenciales para los componentes de "solo pruebas": podrían hacerse pasar por el cuerpo.

## Reglas

- Ningún mensaje contiene imágenes, video ni audio.
- `bbox` y `confidence` son metadatos; no permiten reconstruir la imagen.
