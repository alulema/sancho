# Sancho

Asistente personal con presencia física en el estudio y presencia digital en PC y teléfono, construido por etapas sobre un Jetson Nano.

- Diseño completo: [`docs/diseno.md`](docs/diseno.md)
- Etapa actual: **E0 — Esqueleto vertical** ([`docs/specs/SPEC_E0.md`](docs/specs/SPEC_E0.md))
- Contratos entre componentes: [`docs/contratos/`](docs/contratos/)
- Decisiones de arquitectura: [`docs/adr/`](docs/adr/)
- Bitácora de laboratorio: [`docs/bitacora/`](docs/bitacora/)

## Desarrollo

Requiere [uv](https://docs.astral.sh/uv/) y `make`. uv instala Python y las dependencias la primera vez.

| Comando | Qué hace |
|---|---|
| `make test` | Corre las pruebas, sin las que requieren el Nano |
| `make lint` | Revisa estilo y formato sin cambiar archivos |
| `make format` | Aplica el formato |
| `make sim` | Corre la cadena completa sin hardware: broker, cuerpo simulado y orquestador |
| `make replay REC=…` | Reproduce una grabación ante un orquestador nuevo y compara sus decisiones con las originales |
| `make bench` | Corre el banco de evaluación (`eval/cases/`) y guarda los resultados en `eval/results/` |
| `make deploy-nano` | Pendiente (T12); por ahora falla con un aviso |

Las pruebas que requieren el Nano llevan `@pytest.mark.nano`; se corren allí con `uv run pytest -m nano`.

Las pruebas del bus (`tests/test_broker.py`) levantan un broker Mosquitto real con la misma imagen que usa el Nano. Necesitan Docker y la imagen ya descargada; nunca la descargan solas, y sin ella se saltan indicando el comando:

```
docker pull eclipse-mosquitto@sha256:75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98
```

Con `MOSQUITTO=/ruta/a/mosquitto` usan un binario nativo en su lugar.

## Simulación

`make sim` levanta un broker de pruebas desechable (la misma imagen, con contraseñas nuevas en un directorio temporal que se borra al terminar), el orquestador (`python -m brain`) y el cuerpo simulado (`python -m sim.body`). El cuerpo simulado reproduce un guion de entradas y salidas, y su TTS solo registra la frase y publica `started` y `finished`. Muestra lo que pasa por el bus y un resumen; los logs y las trazas quedan en `.sim/<hora UTC>/`.

```
make sim
make sim SIM_ARGS="--greeting-window-min 0.05"
make sim SIM_ARGS="--script sim/scripts/otro.yaml"
```

Los guiones están en `sim/scripts/`; el formato se describe en `sim/script.py`. Necesita lo mismo que las pruebas del bus: Docker y la imagen ya descargada, o `MOSQUITTO=…`.

Cada simulación deja además su grabación, `recording.jsonl` (`docs/contratos/grabaciones.md`).

## Grabación y reproducción

- **Grabar** una sesión del bus, por ejemplo en el Nano con el rol `recorder` de producción. Se detiene con Ctrl-C o con `--duration-s`:

  ```
  python -m sim.recorder --password-file ~/sancho/broker/credentials/recorder --out recordings
  ```

- **Reproducir** una grabación ante un orquestador nuevo (en un broker de pruebas) y comparar sus decisiones con las trazas originales. Por omisión las busca en `traces/`, junto a la grabación:

  ```
  make replay REC=.sim/<corrida>/recording.jsonl
  make replay REC=recordings/x.jsonl REPLAY_ARGS="--traces ruta/a/trazas --greeting-window-min 10"
  ```

  Al orquestador hay que darle la misma configuración que tenía en la sesión original.

## Banco de evaluación

`make bench` corre cada caso de `eval/cases/` con un broker y componentes nuevos, y verifica `expect` y `forbid` (`docs/contratos/casos-banco.md`). Los resultados se guardan en `eval/results/<fecha>-<commit>.json` y se versionan. Con `BENCH_ARGS="--only <id> --no-save"` corre un solo caso sin guardar.

Las instrucciones para desplegar al Nano se agregan con T12.
