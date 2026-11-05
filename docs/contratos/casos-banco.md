# Contrato: casos del banco de evaluación — v0.1

Un caso describe una situación, lo que se inyecta en el bus y lo que debe (o no debe) ocurrir.

- Formato: YAML, un archivo por caso en `eval/cases/`.
- El runner arranca de un estado limpio, aplica `given`, inyecta `when` y verifica `expect` y `forbid`.

```yaml
id: e0-greet-twice-within-window
version: 0.1
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
| `when` | Mensajes a inyectar, con tiempo relativo en milisegundos |
| `expect` | Mensajes que deben aparecer: tópico, cantidad, plazo y, opcionalmente, condiciones sobre el payload |
| `forbid` | Mensajes que no deben aparecer |

Los resultados de cada corrida (caso, resultado, tiempos) se guardan en `eval/results/` con la fecha y el commit.
