# Bitácora — 2026-11-13 — Contratos implementados

- **Etapa:** E0
- **Tareas de la spec:** T5

## Qué se intentó

1. Verificar en el Nano que Pydantic v2 y PyYAML se instalan con Python 3.12 desde ruedas binarias, antes de elegirlos (ADR-0013, aceptada).
2. Implementar `contracts/`:
   - `types.py`: marcas de tiempo exactas (`…T18:20:00.123Z`) y UUID v4 canónicos.
   - `envelope.py`: el sobre común.
   - `topics.py`: tópicos y payloads de E0, incluido el orden `first_seen_ts` ≤ `frame_ts` ≤ `ts` y que un *last will* sea `offline` con `uptime_s` 0.
   - `bus.py`: `make_message`, `encode`, `decode` y `receive`. Este último registra el rechazo y devuelve `None` en lugar de lanzar la excepción.
   - `traces.py` y `cases.py`: trazas y casos del banco.
3. Probar cada contrato con mensajes válidos e inválidos. Las pruebas leen los ejemplos de `docs/contratos/`, así que si un ejemplo y el código dejan de coincidir, una prueba falla.

## Qué se midió

| Prueba | Resultado |
|---|---|
| Instalación en el Nano (Python 3.12.15, modo 5W) | `pydantic-core` 2.50.4 en rueda binaria sobre glibc 2.27, sin compilar |
| Importación de `pydantic` en el Nano | 1,51 s en frío; 0,27 s en caliente |
| Importación de `yaml` en el Nano | 0,32 s en frío; 0,08 s en caliente |
| Validación de un modelo estricto desde JSON en el Nano | 12,8 µs por mensaje |
| `make test` en la máquina de desarrollo | 132 pruebas pasan (99 nuevas de contratos) |

## Qué falló y por qué

- **El ejemplo de `trace_id` de los contratos no era un UUID v4 válido** (`…-4a3b-2c1d-…`: la variante `2` no es la de RFC 4122). Apareció en cuanto las pruebas leyeron los ejemplos de los contratos. Se corrigió en `sobre.md`, `trazas.md` y `grabaciones.md`. Es una corrección de ejemplos, no un cambio de contrato, así que las versiones no cambian.
- El modo no estricto de Pydantic acepta `"0.9"` como número y `1` como booleano. Se usa el modo estricto. Las marcas de tiempo y los UUID llevan validadores propios, para exigir la forma exacta en cualquier modo.

## Supuestos confirmados o refutados

Ninguno de §18.

## Decisiones tomadas

- ADR-0013 (aceptada): Pydantic v2 en modo estricto y PyYAML con `safe_load`. Los mensajes y las trazas ignoran campos desconocidos; los casos del banco los rechazan, para detectar erratas.
- `encode` publica el payload tal como está en el sobre, para que un componente pueda reenviar un mensaje de una versión menor más nueva sin perder campos.
- Las referencias de las trazas (`inputs`, `outputs`) solo admiten `message_ids`, para que una traza no pueda copiar el contenido de un mensaje.
- `source` no se valida contra el tópico: no autentica nada. Eso lo hacen la ACL y, en E4, la firma.

## Pendientes para la próxima sesión

- Correr las pruebas de contratos en el Nano cuando exista el despliegue (T12).
- Los componentes (T6, T7) deben usar `contracts.bus.receive` para todo lo que reciben y registrar el rechazo como traza `kind: error`.

## Notas para artículos

- Que las pruebas lean los ejemplos de la documentación encontró un error en el primer intento: documentación y código se vigilan mutuamente.
