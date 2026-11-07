# Bitácora — 2026-11-06 — Corrección de contratos

- **Etapa:** E0
- **Tareas de la spec:** preparación de T4, T5, T9 y T11

## Qué se intentó

Corregir los vacíos y contradicciones de los contratos v0.1 antes de escribir código, mientras el Nano espera la fuente de barril y el cable del SSD.

## Qué se midió

Nada: solo cambió documentación. Ningún cambio se ha comprobado contra un broker todavía; eso ocurre en T4, T9 y T11.

## Qué falló y por qué

Los contratos v0.1 se contradecían o no alcanzaban para las tareas de la spec:

- `recorder` no podía publicar, pero todo componente debía publicar salud.
- `body` podía publicar sus propios comandos.
- T9 no tenía rol, formato de grabación ni reglas de reproducción.
- El `ts` del *last will* parecía la hora de la caída, pero es la de la conexión.
- Los casos del banco no podían expresar un mensaje inválido ni un componente caído, dos casos que T11 exige.

## Supuestos confirmados o refutados

Ninguno en esta sesión.

## Decisiones tomadas

- ADR-0006: ACL con privilegio mínimo y roles por entorno.
- ADR-0007: *last will* en el sobre común, con marcas de la conexión.
- ADR-0008: formato de grabación y reglas de reproducción.
- ADR-0009: pasos nuevos en los casos del banco.
- `topicos-e0.md` y `casos-banco.md` pasan a v0.2; se agrega `grabaciones.md` v0.1. `sobre.md` no cambia.

## Pendientes para la próxima sesión

- Queda abierto cómo medir la parte de detección en la latencia (T10): el `ts` de `person_entered` es posterior a la detección y a la histéresis.
- Queda abierta la discrepancia de S6 (GPU o cámara CSI) y de S7 (dice E0, pero ninguna tarea lo incluye).

## Notas para artículos

- Un *last will* es un mensaje escrito antes de morir: todo lo que dice describe el momento en que se escribió.
- Leer un contrato contra sus pruebas de aceptación encontró contradicciones antes de que existiera una línea de código.
