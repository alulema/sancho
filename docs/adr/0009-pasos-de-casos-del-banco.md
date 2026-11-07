# ADR-0009 — Los casos del banco pueden inyectar mensajes crudos y detener componentes

- **Fecha:** 2026-11-06
- **Estado:** aceptada
- **Etapa:** E0

## Contexto

T11 exige los casos "mensaje inválido" y "componente caído", pero `casos-banco.md` v0.1 solo permitía publicar un payload dentro de un sobre válido. El contrato tampoco definía desde cuándo cuenta `within_ms`, cómo escribir condiciones sobre el payload ni cómo probar la reentrada "tras N minutos" sin esperar minutos reales.

## Opciones consideradas

Para los mensajes inválidos:

1. **Campos para alterar el sobre:** cubre sobres inválidos, pero no JSON roto, y crece con cada variante.
2. **Paso `publish_raw` con texto literal:** cubre todos los casos con una sola acción.

Para los componentes caídos:

1. **Simular la caída publicando `status: offline`:** es simple, pero no prueba el *last will* ni el comportamiento real ante una caída.
2. **Pasos `stop` y `start` que actúan sobre el proceso:** prueban la caída real, a cambio de que el runner controle los procesos.

Para las ventanas de tiempo:

1. **Reloj simulado en el orquestador:** es rápido, pero agrega código solo para las pruebas.
2. **Ventanas configurables con decimales:** usa el mismo código de producción y el caso tarda unos segundos.

## Decisión

- `when` admite cuatro acciones: `publish`, `publish_raw`, `stop` (`abrupt` o `clean`) y `start`.
- El runner no valida lo que inyecta.
- `expect` y `forbid` admiten `payload` como coincidencia parcial.
- `within_ms` cuenta desde el inicio del caso, y los retenidos que entrega el broker al suscribirse no cuentan.
- Las duraciones de `given.config` admiten decimales.

`casos-banco.md` pasa a v0.2. Se considera compatible: un caso v0.1 con `publish` sigue siendo válido.

## Consecuencias

- El caso de componente caído comprueba de verdad el *last will*, y el de mensaje inválido comprueba que el componente sigue respondiendo.
- El runner debe arrancar y detener componentes, no solo hablar con el bus, así que tendrá que saber cómo se levanta cada uno en `make sim`.
- El banco no verifica que el rechazo quede registrado. Eso lo cubren las pruebas de T5.

## Evidencia

Revisión de T11 y del contrato v0.1. La aceptación se comprueba en T11.
