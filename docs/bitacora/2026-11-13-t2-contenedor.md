# Bitácora — 2026-11-13 — SSD para Docker y cámara CSI desde un contenedor

- **Etapa:** E0
- **Tareas de la spec:** T2 (cierre de la prueba en contenedor), T3 (preparación provisional)

## Qué se intentó

1. **Formatear el SSD** (HIKSEMI MD202, 250 GB) con `deploy/nano/prepare_ssd.sh`: una partición de 100 GB, ext4, etiqueta `sancho-root`. El resto queda libre para la partición cifrada de E1.
2. **Llevar los datos de Docker al SSD**, mientras el sistema sigue en la microSD (91 %), con `deploy/nano/docker_on_ssd.sh`: montaje en `/mnt/sancho-root` por UUID con `nofail`, `data-root` en `/mnt/sancho-root/var/lib/docker` y un *drop-in* de systemd (`RequiresMountsFor`) para que Docker no arranque sin el SSD y escriba en la microSD. Es provisional: T3 lo deshace.
3. **Construir `deploy/nano/t2-container/Dockerfile`**: `l4t-base:r32.7.1`, Python 3.12.15 instalado con uv y numpy 2.5.4. Se corre con `--runtime nvidia -v /tmp/argus_socket:/tmp/argus_socket` y el mismo `camera_probe.py` de la prueba anterior.

## Qué se midió

Condiciones: modo **5W** (`nvpmodel -m 1`), alimentación por micro-USB, CPU a 40 °C al empezar. Captura a 1280×720 y 30 cps escalada a 640×360 por `nvvidconv`; 12 s por corrida, 2 s de calentamiento, n = 1.

| Configuración | Cuadros | cps medidos | CPU de Python | CPU de GStreamer |
|---|---|---|---|---|
| Contenedor, Python 3.12.15, runtime `nvidia` | 360/360 | 30,01 | 7,84 s (≈ 65 % de un núcleo) | 3,69 s (≈ 31 %) |
| Host, Python 3.12.15 (mismo modo, minutos después) | 360/360 | 30,01 | 5,30 s (≈ 44 %) | 2,08 s (≈ 17 %) |
| Contenedor **sin** runtime `nvidia` | 0/120 | — | — | `gst-launch` sale con código 1 |

| Prueba | Resultado |
|---|---|
| Tamaño de la imagen | 807 MB |
| Tiempo de construcción (con la base ya descargada) | ≈ 1 min |
| Escritura en el SSD por el hub USB-C | 480 Mb/s (USB 2.0), sin errores en `dmesg` |
| Modos del sensor que reporta Argus | 3264×2464 a 21 cps, 3264×1848 a 28, 1920×1080 a 30, 1640×1232 a 30, 1280×720 a 60 y a 120 |

## Qué falló y por qué

- **El Nano se apagó solo durante la primera construcción**, en modo MAXN por micro-USB: descargaba y descomprimía la imagen base mientras alimentaba y escribía el SSD. La sesión SSH terminó con `Connection reset by peer`. Lo más probable es una caída de voltaje, pero no se pudo confirmar: el *journal* no es persistente y se perdió el registro de ese arranque. En modo 5W la descarga y la construcción terminaron sin problemas.
- **Después del apagón, la imagen base quedó corrupta.** La segunda descarga reutilizó capas incompletas: la construcción falló en el primer `RUN` con `stat /bin/sh: no such file or directory`, y `docker image inspect` respondió `readlink …/overlay2/l: invalid argument`. Los sistemas de archivos estaban sanos (la microSD solo recuperó su *journal*; el SSD, sin errores). Se resolvió borrando la imagen con `docker rmi -f` e `image prune -af` y descargándola de nuevo. **Lección:** después de un corte de energía no se debe confiar en las imágenes de Docker; hay que verificarlas o descargarlas de nuevo.
- El `apt-get install` de GStreamer en el Dockerfile sobra: la imagen base ya trae `gstreamer1.0-tools` y `-plugins-base`.
- **El contenedor usó más CPU que el host** (Python 7,84 s frente a 5,30 s; GStreamer 3,69 s frente a 2,08 s). Con n = 1 no se sabe si es ruido, el arranque en frío del contenedor o un costo real del aislamiento. Queda por medir con varias corridas antes de T12.
- Se tomó una foto a 3264×2464 a pedido del usuario, para ver la resolución: se guardó solo en `/dev/shm` (RAM) en el Nano y en una carpeta temporal fuera del repo, y se borró después de verla. La imagen sale **invertida** (la cámara está montada al revés: se corrige con `flip-method=2` en `nvvidconv`) y con un **tinte magenta**, típico del IMX219 en Jetson sin el archivo de ajuste del ISP. Para detectar personas no impide nada, pero hay que corregirlo antes de mostrar imágenes o usar color.

## Supuestos confirmados o refutados

| Supuesto (§18 del diseño) | Resultado | Evidencia |
|---|---|---|
| S6 (Python moderno con la cámara CSI) | **Confirmado, dentro y fuera de contenedor** | Las corridas de arriba y las de `2026-11-13-t2-python-moderno.md` |

## Decisiones tomadas

- ADR-0012 se actualiza con la evidencia del contenedor. Dónde corre cada componente sigue en manos de T12.
- Las pruebas pesadas se hacen en modo 5W hasta que llegue la fuente de barril.

## Pendientes para la próxima sesión

- Repetir la comparación de CPU entre contenedor y host con varias corridas.
- Ajuste del ISP (tinte magenta) y orientación de la cámara: antes de usar color o mostrar imágenes.
- Hacer persistente el *journal* (`Storage=persistent`) para diagnosticar el próximo apagón.

## Notas para artículos

- El runtime `nvidia` es lo que hace funcionar la cámara en el contenedor: sin él, `nvarguscamerasrc` no existe dentro de la imagen.
- Un apagón no corrompió los sistemas de archivos, pero sí el almacén de capas de Docker, y el error (`/bin/sh` no existe) no apunta a la causa.
