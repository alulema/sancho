# Contratos

Formatos que comparten los componentes. **El código implementa estos contratos; no al revés.**

| Contrato | Archivo | Versión |
|---|---|---|
| Sobre común de mensajes | `sobre.md` | 0.1 |
| Tópicos de E0 | `topicos-e0.md` | 0.2 |
| Trazas | `trazas.md` | 0.1 |
| Casos del banco de evaluación | `casos-banco.md` | 0.2 |
| Grabaciones del bus | `grabaciones.md` | 0.1 |
| Descriptor de nodo (especificado, se implementa en E6) | `descriptor-nodo.md` | 0.1 |

## Reglas

- Cada contrato tiene versión `MAYOR.MENOR`. Un cambio compatible (campo opcional nuevo) sube la menor; uno incompatible sube la mayor.
- Un cambio de contrato va con un ADR y se hace **antes** de cambiar el código.
- Los receptores ignoran campos desconocidos, y rechazan y registran mensajes que no validan, sin caerse.
- Las marcas de tiempo son ISO-8601 en UTC con milisegundos (`2026-11-03T18:20:00.123Z`).
- Los identificadores son UUID v4 salvo que el contrato diga otra cosa.
