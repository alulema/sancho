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
| `make bench`, `make sim`, `make deploy-nano` | Pendientes (T11, T8 y T12); por ahora fallan con un aviso |

Las pruebas que requieren el Nano llevan `@pytest.mark.nano`; se corren allí con `uv run pytest -m nano`.

Las pruebas del bus (`tests/test_broker.py`) levantan un broker Mosquitto real con la misma imagen que usa el Nano. Necesitan Docker y la imagen ya descargada; nunca la descargan solas, y sin ella se saltan indicando el comando:

```
docker pull eclipse-mosquitto@sha256:75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98
```

Con `MOSQUITTO=/ruta/a/mosquitto` usan un binario nativo en su lugar.

Las instrucciones para correr la simulación y desplegar al Nano se agregan durante E0.
