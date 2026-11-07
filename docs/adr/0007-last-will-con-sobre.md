# ADR-0007 — El *last will* va en el sobre común, con marcas de la conexión

- **Fecha:** 2026-11-06
- **Estado:** aceptada
- **Etapa:** E0

## Contexto

El *last will* se registra al conectarse y el broker lo entrega sin cambios al caer el cliente. Por eso su `ts` y su `uptime_s` no pueden describir la caída, aunque el mensaje valide. Con `topicos-e0.md` v0.1, un consumidor podía creer que el componente cayó en el momento en que se conectó. Tampoco estaba escrito que una desconexión normal descarta el *last will*.

## Opciones consideradas

1. **Payload sin sobre para el *last will*:** evita el dato engañoso, pero rompe la regla de que todo mensaje va en el sobre y obliga a un caso especial en la validación.
2. **Quitar `ts` o volver opcional `uptime_s`:** es un cambio incompatible, y el sobre exige `ts`.
3. **Mantener el sobre y marcar el mensaje:** `last_will: true`, con `uptime_s: 0` y el `ts` de la conexión. Ambos son ciertos para el momento en que se generó el mensaje. El contrato prohíbe calcular duraciones con ellos.
4. **Un vigilante que publique la hora de caída:** da el dato real, pero agrega un componente que E0 no necesita.

## Decisión

Se elige la opción 3. Además, antes de una desconexión normal, cada servicio publica `status: offline` con marcas reales y sin `last_will`.

`topicos-e0.md` pasa a v0.2. `last_will` es un campo opcional nuevo, un cambio compatible.

## Consecuencias

- Todos los mensajes del bus pasan por la misma validación.
- La hora exacta de una caída solo la conoce quien estaba suscrito al recibir el mensaje. Quien se suscribe después recibe el retenido, sin esa hora.
- `last_will` permite distinguir una caída de un cierre ordenado.
- T4 debe probar que al matar un componente aparece su *last will* válido.

## Evidencia

Revisión del contrato v0.1. El comportamiento del broker se comprueba en T4.
