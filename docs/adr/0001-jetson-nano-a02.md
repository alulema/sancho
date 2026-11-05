# ADR-0001 — La placa es un Jetson Nano A02 con un solo puerto CSI

- **Fecha:** 2026-11-03
- **Estado:** aceptada
- **Etapa:** previa a E0

## Contexto

El Jetson Nano Developer Kit existe en dos versiones de placa base: A02, con un puerto de cámara CSI, y B01, con dos. La versión define si es posible el estéreo casero con dos cámaras IMX219 y cuántas cámaras CSI puede tener el cuerpo del estudio.

## Opciones consideradas

No aplica: es un hecho del hardware disponible. Se verificó contando los conectores de cámara de la placa: hay uno solo.

## Decisión

Se trabaja con un Jetson Nano A02 (GPU Maxwell, CPU ARM Cortex-A57 de cuatro núcleos, 4 GB) y un único puerto CSI.

## Consecuencias

- La cámara IMX219 en el puerto CSI es la **cámara principal fija** del estudio.
- El **estéreo casero con dos IMX219 queda descartado** en el Nano. La profundidad para el brazo (E11) se resolverá con una cámara de estéreo activo (OAK-D Pro o RealSense D435).
- Cualquier cámara adicional en el Nano (por ejemplo, una cámara propia en la cabeza) tendrá que ser USB.
- El supuesto S9 del diseño (disparidad estéreo con VPI en el Nano) deja de aplicar.

## Evidencia

Inspección física de la placa: un solo conector de cámara.
