# ADR-0002 — El NUC es solo máquina de desarrollo

- **Fecha:** 2026-11-03
- **Estado:** aceptada
- **Etapa:** previa a E0

## Contexto

El NUC con Ubuntu (x86_64) se usa para desarrollar con Claude Code, pero se apaga cada día al terminar la sesión de trabajo. El diseño consideraba usar un equipo siempre encendido como servidor de llaves (Tang) para desbloquear el SSD cifrado del Nano (E1), y como posible anfitrión de Kev en la fase A (E5).

## Opciones consideradas

1. **Dejar el NUC siempre encendido:** descartado por decisión del usuario.
2. **El NUC solo para desarrollo:** el asistente no depende de él para funcionar a diario.

## Decisión

El NUC es solo máquina de desarrollo, pruebas y simulación. Ningún componente de uso diario depende de él.

## Consecuencias

- El cerebro debe poder correr en el Nano antes del MVP diario de E2 (ver T2 de `SPEC_E0.md`).
- El NUC **no** puede ser el servidor de llaves. Antes de E1 hay que elegir entre otro equipo siempre encendido (router compatible o una placa pequeña) o una frase de paso manual al arrancar el Nano.
- Si Kev corre en el NUC durante la fase A, el motor de decisiones caerá a reglas conservadoras cuando el NUC esté apagado. Para uso diario continuo hará falta otro equipo o el Orin.

## Evidencia

Indicación del usuario: el NUC se apaga cada día después de la sesión de trabajo.
