# Bitácora — 2026-11-13 — Python moderno con la cámara CSI, fuera de contenedor

- **Etapa:** E0
- **Tareas de la spec:** T2 (parcial)

## Qué se intentó

Probar la vía "Python moderno instalado fuera de contenedor" de T2 mientras no hay espacio para contenedores (la microSD está al 91 %).

1. En `~/t2-probe`, en el Nano: uv 0.13.1 (binario estático musl, checksum verificado con `sha256sum -c`), y con él Python 3.12.15 y un entorno virtual.
2. Ruedas binarias (`--only-binary :all:`) de numpy y `opencv-python-headless` para Python 3.12.
3. `deploy/nano/camera_probe.py`: lanza `gst-launch-1.0` con `nvarguscamerasrc → nvvidconv → fdsink` y lee los cuadros BGRx por un pipe. El intérprete no necesita enlaces de GStreamer. Los cuadros se descartan en memoria; no se escribe nada a disco.
4. La misma prueba con el Python 3.6 del sistema, como línea base.

## Qué se midió

Condiciones de todas las corridas: modo de energía **MAXN** (`pmode:0000`, 4 núcleos) **por micro-USB**, en reposo antes de cada corrida, temperatura de CPU de 30 a 31 °C, sin advertencias de bajo voltaje en `dmesg`. Captura del sensor a 1280×720 y 30 cps, escalada por `nvvidconv`. Corridas de 12 s (2 s de calentamiento); n = 1 por configuración.

| Configuración | Cuadros | cps medidos | CPU de Python | CPU de GStreamer |
|---|---|---|---|---|
| Python 3.12.15, numpy 2.5.4, 640×360 | 360/360 | 30,01 | 4,61 s (≈ 38 % de un núcleo) | 1,75 s (≈ 15 %) |
| Python 3.6.9, numpy 1.13.3, 640×360 | 360/360 | 30,01 | 3,64 s (≈ 30 %) | 1,73 s (≈ 14 %) |
| Python 3.12.15, numpy 2.5.4, 1280×720 | 360/360 | 28,13 | 12,34 s (≈ 97 %) | 2,56 s (≈ 20 %) |

La CPU de Python incluye una copia BGR y un promedio de brillo por cuadro, propios de la prueba. El brillo varió entre 60 y 126, así que los cuadros traen imagen real.

Otros resultados:

| Prueba | Resultado |
|---|---|
| Python 3.12.15 en glibc 2.27 | Funciona (`python-build-standalone`, `aarch64-gnu`) |
| `opencv-python-headless` 5.0.0.93 en 3.12 | Se instala e importa; trae `cv2.dnn`; **sin GStreamer** |
| Espacio usado por `~/t2-probe` | 280 MB; quedan 1,1 GB libres |

## Qué falló y por qué

- `curl` no está instalado en el Nano; se usó `wget`.
- A 1280×720, Python 3.12 no sostiene 30 cps: el proceso queda limitado por la CPU (≈ 97 % de un núcleo) en el trabajo por cuadro de la prueba. Para la detección de T6 conviene capturar a la resolución que usa el detector y escalar con `nvvidconv`, que no consume CPU.
- Python 3.12 usó más CPU que 3.6 a 640×360 (4,61 s frente a 3,64 s). Con una sola corrida no se sabe si es ruido, numpy 2.5 o el intérprete.

## Supuestos confirmados o refutados

| Supuesto (§18 del diseño) | Resultado | Evidencia |
|---|---|---|
| S6 (Python moderno con la cámara CSI) | **Confirmado fuera de contenedor.** En contenedor, sin verificar | Las corridas de arriba |

## Decisiones tomadas

- ADR-0012 (aceptada): Python 3.12 para todos los componentes de E0, con la cámara a través de un proceso de GStreamer.

## Pendientes para la próxima sesión

- Probar la vía en contenedor cuando el sistema esté en el SSD (T3).
- Medir cuántos cps logra un detector DNN de OpenCV en CPU con Python 3.12 (T6).
- Limpieza en el Nano: `~/t2-probe` y el enlace `~/.local/bin/python3.12` que creó `uv python install`.

## Notas para artículos

- La manera más simple de usar la cámara CSI desde Python moderno fue no enlazar GStreamer: un `gst-launch` en un proceso aparte, escribiendo cuadros en un pipe.
- El Python 3.12 de `python-build-standalone` corre sobre la glibc 2.27 de Ubuntu 18.04 sin compilar nada.
