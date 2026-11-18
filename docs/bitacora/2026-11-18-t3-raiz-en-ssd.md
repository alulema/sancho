# Bitácora — 2026-11-18 — Sistema raíz del Nano en el SSD

- **Etapa:** E0
- **Tareas de la spec:** T3

## Qué se intentó

1. **Revisar qué permite el arranque del Nano** (L4T R32.7.6) antes de tocar nada. U-Boot lee `extlinux.conf`, el kernel y el initrd de la microSD. El initrd de serie ya trae el firmware USB y monta `root=PARTUUID=…`, así que no hay que recompilarlo ni flashear la QSPI.
2. **`deploy/nano/root_on_ssd.sh`** (ADR-0016), en pasos que no reinician el Nano:
   - `check`: muestra el plan sin cambiar nada.
   - `copy`: copia el sistema en marcha a `sancho-root`, sin tocar los datos de Docker que ya estaban allí, y adapta la copia.
   - `switch`: hace una última copia con Docker detenido y deja la entrada `ssd` como `DEFAULT`.
   - `rollback`: vuelve a la microSD.
3. **Probar las ediciones en RAM antes de correrlas de verdad**, con el Python 3.6 del Nano: la nueva entrada de `extlinux.conf` y los cambios a `fstab`, `daemon.json` y la selección de paquetes, aplicados sobre copias en `/dev/shm`.
4. **Ejecutarlo:** el usuario corrió `check`, `copy` y `switch` (sudo pide contraseña) y reinició. Antes de `switch` se revisó la copia en el SSD.

## Qué se midió

Modo 5 W, alimentación por micro-USB, SSD detrás de tres concentradores USB a 480 Mb/s.

| Prueba | Resultado |
|---|---|
| `copy` | 12,8 GB a 18,7 MB/s, unos 11 minutos |
| Arranque desde la microSD (antes) | 18,1 s de kernel + 17,4 s de espacio de usuario = **35,4 s** |
| Arranque desde el SSD (después) | 5,5 s + 13,4 s = **18,9 s**; Docker tarda 4,5 s (antes, 10 s) |
| Raíz encontrada y montada por el initrd | a los 2,0 s y a los 5,4 s |
| Después del reinicio | `/` en `/dev/sda1`, microSD en `/mnt/microsd`, `sancho-broker` arriba y acepta al rol `recorder`, IP 192.168.0.122 |

Con una sola medición de cada lado, la mitad de tiempo de arranque no basta para afirmar que el SSD arranca el doble de rápido: los 18,1 s de kernel del arranque anterior pueden tener otra causa. Se repetirá en los reinicios de T12.

## Qué falló y por qué

- **`re.split` con una búsqueda de ancho cero no divide en Python 3.6.** La primera versión partía `extlinux.conf` en entradas con `(?m)^(?=LABEL )`, que solo funciona desde Python 3.7. La prueba en RAM en el Nano lo habría detectado; se corrigió antes, al revisar el script.
- **Quedan dos `root=` en la línea de comandos del kernel.** El cargador agrega `root=/dev/mmcblk0p1` en `${cbootargs}` antes del nuestro. Funciona porque gana el último, pero conviene saberlo si algún día cambia el cargador.
- Al copiar archivos de `dpkg` para la prueba en RAM, los *locks* no se podían leer sin root; no afectaron la prueba.

## Supuestos confirmados o refutados

Ninguno de §18.

## Decisiones tomadas

- **ADR-0016 (aceptada):** raíz por `PARTUUID` en el SSD, con kernel, initrd y `extlinux.conf` en la microSD. La entrada `primary` queda como respaldo, y los paquetes del kernel y el arranque quedan retenidos en el SSD.
- Si el Nano no arranca desde el SSD, la vuelta atrás es poner la microSD en el lector SD del NUC y cambiar `DEFAULT`.

## Pendientes para la próxima sesión

- Probar el SSD conectado directo al puerto USB 3 del Nano en lugar de detrás del concentrador.
- Hacer persistente el *journal*, ahora que hay espacio.
- La microSD conserva el sistema anterior (13 GB) como respaldo; se puede limpiar cuando el SSD lleve un tiempo estable.

## Notas para artículos

- En el Nano A02 «arrancar desde el SSD» en realidad significa arrancar desde la microSD con la raíz en el SSD. La distinción importa para saber dónde vive `/boot`.
- Que los datos de Docker ya estuvieran en la ruta final (`var/lib/docker` de la partición) evitó volver a descargar imágenes. Haber pensado en T3 al escribir la solución provisional de T2 ahorró trabajo.
