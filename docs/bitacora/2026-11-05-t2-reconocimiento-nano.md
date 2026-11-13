# Bitácora — 2026-11-05 — Reconocimiento del Nano para T2

- **Etapa:** E0
- **Tareas de la spec:** T2 (no iniciada), con hallazgos para T3, T6 y T10

## Qué se intentó

Inspeccionar el Nano por SSH, solo con lectura y sin sudo, antes de la prueba de contenedores de T2. No se cambió nada en la placa.

## Qué se midió

| Medición | Valor | Condiciones |
|---|---|---|
| Sistema | L4T R32.7.6, Ubuntu 18.04.6, kernel 4.9.337-tegra, glibc 2.27 | Placa A02 según el device tree |
| Python del sistema | 3.6.9; OpenCV 4.1.1 con GStreamer 1.14.5 | |
| Modo de energía | `pmode:0000` (MAXN), 4 núcleos activos | Sin carga; fuente de alimentación sin confirmar |
| Memoria | 3,9 GB en total, 3,4 GB disponibles | Sin carga |
| Disco raíz | microSD de 14,4 GB, 90 % usado, 1,4 GB libres | `/usr` ocupa 9,9 GB |
| Docker | 20.10.21, `nvidia-docker2` 2.8.0, runtime `nvidia` configurado | Sin imágenes verificadas |
| Red | Solo Wi-Fi (`wlan0`) | |
| Audio | HDMI (`tegra-hda`) e I2S; sin jack ni audio USB | Monitor BenQ G615HDPL presente |

El modo de energía se lee sin sudo en `/var/lib/nvpmodel/status`, lo que sirve para T10.

## Qué falló y por qué

- **La cámara no se detecta.** No existe `/dev/video*`. En `dmesg`: `tegra-vii2c 546c0000.i2c: no acknowledge from address 0x10` e `imx219: probe of 6-0010 failed with error -121`. El driver y el device tree cargan, pero el sensor no responde por I2C. Apunta a hardware (cable, conector o cámara), sin confirmar todavía.
- **El SSD no estaba conectado en la primera inspección.** Al conectarlo apareció como `/dev/sda`, con tres diferencias frente a lo esperado:
  - Mide 250 GB (HIKSEMI MD202, puente Realtek 0bda:9210), no los 500 GB de la spec y del diseño.
  - Tiene una partición NTFS sin montar (`sda1`). No se montó ni se modificó, y su contenido es desconocido.
  - Negocia a 480 Mb/s con `usb-storage`, sin UAS, a través de una cadena de concentradores (Prolific 067b:2586 y Genesys 05e3:0610) que incluye un adaptador USB-C. El bus de 5 Gb/s del Nano queda sin usar. Junto a él apareció y se desconectó en menos de un segundo otro dispositivo de almacenamiento (Norelsys NS1081); no se investigó.
- **El usuario `alulema` no está en el grupo `docker`.** No se pudo consultar el daemon sin sudo.
- **El modo de energía no coincide con la spec,** que pide 5 W mientras el Nano se alimente por micro-USB. Hay que confirmar con qué fuente está.

## Supuestos confirmados o refutados

| Supuesto (§18 del diseño) | Resultado | Evidencia |
|---|---|---|
| S6 (contenedores con Python moderno) | Sin verificar | Bloqueado por la cámara, el espacio en disco y el acceso a Docker |

## Decisiones tomadas

Ninguna. Queda por proponer hacer T3 antes de la prueba de contenedores de T2, porque 1,4 GB libres probablemente no alcanzan para las imágenes.

## Pendientes para la próxima sesión

- Revisar el cable y el conector de la cámara, y repetir la detección.
- Conectar el SSD y confirmar la fuente de alimentación.
- Decidir el acceso a Docker.

## Notas para artículos

- El primer resultado de "Python moderno en un Nano" no vino del software: el sensor no responde y el disco está casi lleno.
