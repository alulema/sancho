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

Las instrucciones para correr la simulación y desplegar al Nano se agregan durante E0.
