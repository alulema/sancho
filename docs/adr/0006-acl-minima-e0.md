# ADR-0006 — ACL de E0 con privilegio mínimo y roles por entorno

- **Fecha:** 2026-11-06
- **Estado:** aceptada
- **Etapa:** E0

## Contexto

Revisar `topicos-e0.md` v0.1 mostró tres problemas en la ACL:

- `body` podía publicar en `sancho/body/#`, que incluye sus propios comandos, aunque los comandos deben venir de otros componentes.
- `recorder` no podía publicar nada, pero "cada componente" debía publicar salud y *last will*.
- La reproducción de T9 no tenía rol. Además, solo `eval` estaba limitado al entorno de pruebas, aunque `sim` también puede hacerse pasar por el cuerpo.

## Opciones consideradas

Para la salud del grabador:

1. **Darle permiso de publicar en su tópico de salud:** uniforme, pero un grabador comprometido podría escribir en el bus.
2. **Eximir a las herramientas de publicar salud:** el grabador conserva la garantía de solo lectura. Se pierde saber si está caído, algo de lo que nada depende en E0.

Para la reproducción:

1. **Reutilizar las credenciales de `sim`:** no agrega roles, pero `replay` podría publicar la salud del cuerpo sin necesitarlo.
2. **Rol propio `replay`:** solo publica eventos del cuerpo.

## Decisión

- `body` y `sim` publican solo en `sancho/body/+/evt/#` y en `sancho/sys/body/health`.
- Publican salud los servicios (`body`, `brain`, `sim`), no las herramientas (`recorder`, `replay`, `eval`).
- `replay` es un rol nuevo que publica solo eventos del cuerpo.
- `sim`, `replay` y `eval` existen solo en el entorno de pruebas; el broker de producción no tiene credenciales para ellos.
- En los mensajes de salud, `type` es `sys.health`, un valor que v0.1 no definía.

`topicos-e0.md` pasa a v0.2. Se considera compatible: un componente que cumplía la tabla de tópicos de v0.1 sigue cumpliéndola, y todavía no hay código que implemente el contrato.

## Consecuencias

- T4 debe generar dos configuraciones de ACL: producción y pruebas.
- T4 puede probar que `body` no publica en `cmd` y que `recorder` no publica en ningún tópico.
- La sesión de T9 se graba en producción y se reproduce solo en pruebas, como pide la spec.
- En el Nano no se podrán correr `make sim` ni `make bench` contra el broker de producción.

## Evidencia

Revisión del contrato v0.1; aún no hay mediciones. Las pruebas de aceptación son las de T4.
