# ADR-0003 — Seguir con el Jetson Nano; otras plataformas solo con disparadores medidos

- **Fecha:** 2026-11-03
- **Estado:** aceptada
- **Etapa:** previa a E0

## Contexto

La fuente de barril de 5 V 4 A del Nano falló. Por un momento pareció que la placa no arrancaba, y se evaluaron alternativas: Raspberry Pi 5 (con o sin aceleradores Hailo), Orange Pi 5 (RK3588S con NPU de 6 TOPS) y Jetson Orin Nano Super. El Nano arranca por micro-USB, aunque con energía limitada.

## Opciones consideradas

1. **Migrar ya a otra plataforma:** resuelve las limitaciones de JetPack 4.6, pero implica gasto y cambios antes de tener mediciones.
2. **Seguir con el Nano y definir cuándo incorporar cada plataforma:** permite avanzar sin gasto y decidir con datos.

## Decisión

Se sigue con el Jetson Nano como única plataforma. Las alternativas quedan registradas con su rol previsto y sus disparadores en `docs/diseno.md` §10.6:

- **Raspberry Pi 5:** núcleo siempre encendido (cerebro, memoria cifrada, bus, servidor de llaves).
- **Orange Pi 5:** candidata económica para el cuerpo si el foco es visión.
- **Orin Nano Super:** cuerpo si el brazo (E11) o el LLM local son prioridad.

## Consecuencias

- Hasta reemplazar la fuente de barril, el Nano opera en modo de 5 W por micro-USB; toda medición registra el modo de energía.
- El código mantiene la separación cuerpo-cerebro por el bus para que sumar plataformas no exija rediseño.
- El resultado de T2 de E0 (Python moderno en el Nano) puede activar el disparador del Raspberry Pi 5.

## Evidencia

- La fuente de barril dejó de funcionar; el Nano arranca por micro-USB.
- Fuentes consultadas sobre las alternativas: reseña del AI HAT+ 2 en Tom's Hardware y CNX Software (enero de 2026), y benchmarks del RK3588 en tinycomputers.io.
