# Contrato: casos del banco de evaluación — v0.2

Un caso describe una situación, lo que se le hace al sistema y lo que debe (o no debe) ocurrir.

- Formato: YAML, un archivo por caso en `eval/cases/`.
- El runner arranca de un estado limpio, aplica `given`, ejecuta `when` y verifica `expect` y `forbid`.
- **Estado limpio:** broker sin mensajes retenidos y componentes recién arrancados con la configuración de `given`.

```yaml
id: e0-greet-twice-within-window
version: "0.2"
description: Dos entradas seguidas dentro de la ventana producen un solo saludo.
tags: [e0, greeting, hysteresis]
lang: es
given:
  config:
    greeting_window_min: 10
when:
  - at_ms: 0
    publish:
      topic: sancho/body/vision/evt/person_entered
      payload: { track_id: "t1", confidence: 0.92, bbox: [0.4, 0.3, 0.2, 0.3] }
  - at_ms: 3000
    publish:
      topic: sancho/body/vision/evt/person_left
      payload: { track_id: "t1", duration_s: 3 }
  - at_ms: 5000
    publish:
      topic: sancho/body/vision/evt/person_entered
      payload: { track_id: "t2", confidence: 0.90, bbox: [0.4, 0.3, 0.2, 0.3] }
expect:
  - topic: sancho/body/speech/cmd/say
    count: 1
    within_ms: 8000
forbid:
  - topic: sancho/body/speech/cmd/say
    count_gt: 1
    within_ms: 8000
```

| Campo | Descripción |
|---|---|
| `id` | Identificador estable; prefijo de etapa |
| `tags` | Para filtrar (`e0`, `security`, `latency`, …) |
| `lang` | Idioma del caso (`es`, `en`, `pt`); el banco crece en los tres |
| `given` | Configuración y estado inicial |
| `when` | Pasos a ejecutar, con tiempo relativo en milisegundos |
| `expect` | Mensajes que deben aparecer: tópico, cantidad, plazo y, opcionalmente, `payload` |
| `forbid` | Mensajes que no deben aparecer |

## Pasos de `when`

Cada paso lleva `at_ms` y exactamente una de estas acciones:

| Acción | Campos | Qué hace |
|---|---|---|
| `publish` | `topic`, `payload` | Envuelve el payload en un sobre válido y lo publica. **El runner no valida el payload**, para poder inyectar uno inválido |
| `publish_raw` | `topic`, `text` | Publica el texto tal cual, sin sobre. Sirve para JSON roto o sobres inválidos |
| `stop` | `component`, `mode` | Detiene un componente: `abrupt` lo mata sin aviso (dispara el *last will*) y `clean` pide un cierre ordenado |
| `start` | `component` | Arranca un componente detenido |

```yaml
# Un mensaje inválido se rechaza y el componente sigue funcionando.
when:
  - at_ms: 0
    publish_raw:
      topic: sancho/body/vision/evt/person_entered
      text: "{esto no es JSON"
  - at_ms: 500
    publish:
      topic: sancho/body/vision/evt/person_entered
      payload: { track_id: "t1", confidence: 0.92, bbox: [0.4, 0.3, 0.2, 0.3] }
expect:
  - topic: sancho/body/speech/cmd/say
    count: 1
    within_ms: 2000
```

```yaml
# Al caer el orquestador, su last will aparece en el bus y nadie saluda.
when:
  - at_ms: 0
    stop: { component: brain, mode: abrupt }
  - at_ms: 1000
    publish:
      topic: sancho/body/vision/evt/person_entered
      payload: { track_id: "t1", confidence: 0.92, bbox: [0.4, 0.3, 0.2, 0.3] }
expect:
  - topic: sancho/sys/brain/health
    payload: { status: offline, last_will: true }
    count: 1
    within_ms: 2000
forbid:
  - topic: sancho/body/speech/cmd/say
    count_gt: 0
    within_ms: 3000
```

## Verificación

- `within_ms` se cuenta desde el inicio del caso, es decir, desde `at_ms: 0`.
- `payload` en `expect` y `forbid` es una coincidencia parcial: los campos indicados deben ser iguales y los demás se ignoran.
- Solo cuentan los mensajes publicados después del inicio del caso. Los retenidos que el broker entrega al suscribirse no cuentan.
- Las duraciones de `given.config` admiten decimales, para probar ventanas sin esperar minutos reales: `greeting_window_min: 0.05` son 3 segundos.

Los resultados de cada corrida (caso, resultado, tiempos) se guardan en `eval/results/` con la fecha y el commit.
