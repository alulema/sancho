# ADR-0004 — El asistente se llama Sancho

- **Fecha:** 2026-11-04
- **Estado:** aceptada
- **Etapa:** previa a E0

## Contexto

El proyecto usaba el nombre provisional "Faro". El nombre afecta el repositorio, el prefijo de los tópicos MQTT, la palabra de activación y la narrativa del blog, el libro y el curso. Se quería evitar "Jarvis", porque muchas personas construyen sus propias versiones con ese nombre, y transmitir la idea de un **ayudante** más que de un mayordomo.

## Opciones consideradas

1. **Sancho:** el escudero de Don Quijote; sentido práctico frente al soñador.
2. **Chasqui:** mensajeros del Tahuantinsuyo.
3. **Quipu:** registros con nudos de los incas.
4. **Melquíades:** el gitano de *Cien años de soledad*.
5. **Platero:** el burro compañero de Juan Ramón Jiménez.

## Decisión

El asistente se llama **Sancho**.

## Consecuencias

- Repositorio: `github.com/alulema/sancho`.
- Prefijo de tópicos MQTT: `sancho/` (antes `faro/`). Los contratos v0.1 ya usan el nuevo prefijo.
- Palabra de activación: **"Oye, Sancho"**, porque una palabra de dos sílabas sola se detecta peor (supuesto S22, se mide en E2).
- Narrativa: el asistente equilibra al soñador con sentido práctico, en línea con los principios de "garantías del sistema" y "medir antes de afirmar".
- Conocido: en partes de Latinoamérica "el Sancho" tiene un doble sentido coloquial. Se acepta.
- Pendiente: la personalidad visual de la cara (personaje original).
