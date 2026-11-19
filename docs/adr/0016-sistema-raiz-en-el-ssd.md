# ADR-0016 — Sistema raíz del Nano en el SSD, con el arranque en la microSD

- **Fecha:** 2026-11-17
- **Estado:** aceptada (2026-11-18)
- **Etapa:** E0 (T3)

## Contexto

T3 pide que el sistema raíz del Nano esté en el SSD de 250 GB; el cargador de arranque puede quedar en la microSD. La microSD (14,4 GB) está al 93 %, y desde T2 los datos de Docker ya viven en la partición `sancho-root` del SSD (100 GB, ext4), montada en `/mnt/sancho-root` como solución provisional (`docker_on_ssd.sh`).

Restricciones encontradas al revisar el Nano (L4T R32.7.6, kernel 4.9.337):

- El Nano A02 no arranca directamente desde USB con este L4T: U-Boot lee `/boot/extlinux/extlinux.conf`, el kernel y el initrd de la microSD.
- El initrd de serie ya trae el firmware del controlador USB (`xusb.bin`) y sabe montar `root=PARTUUID=…`. Reintenta durante 10 s; si no lo logra, se queda en una consola sin volver a la microSD.
- `sudo` pide contraseña, así que los pasos que necesitan permisos de administrador los ejecuta el usuario.
- El SSD estaba conectado a través de tres concentradores USB, a 480 Mb/s (USB 2.0). Desde el 2026-11-19 usa un conector USB 3 (5000 Mb/s).

## Opciones consideradas

1. **Raíz en el SSD con `root=PARTUUID=` en una entrada nueva de `extlinux.conf`**, con kernel e initrd en la microSD. No hace falta recompilar nada ni flashear la QSPI. La entrada original queda como respaldo. Contra: `/boot` del SSD deja de ser el que arranca, y una actualización del kernel por apt rompería la coincidencia entre el kernel y sus módulos.
2. **Arranque directo desde USB** (sin microSD): exige cambiar el cargador en la QSPI y flashear desde un equipo x86 con SDK Manager. Más frágil, difícil de revertir y sin beneficio para E0.
3. **`root=/dev/sda1`:** igual que la 1, pero depende del orden en que aparecen los discos; un segundo disco USB lo cambiaría.

## Decisión

Opción 1, con `deploy/nano/root_on_ssd.sh`:

- **`copy`:** copia el sistema en marcha a `sancho-root` con `rsync -aAXH -x`, sin tocar `/var/lib/docker`: los datos de Docker ya están en el SSD justo en esa ruta, así que no hay que volver a descargar imágenes.
- **Adaptación de la copia:** el `fstab` del SSD deja de montarse a sí mismo y monta la microSD en `/mnt/microsd`; Docker vuelve a su ruta por omisión; se retira el *drop-in* provisional; y los paquetes del kernel, initrd y cargador quedan **retenidos** (`apt-mark hold`) en el SSD.
- **`switch`:** última copia con Docker detenido, y una entrada `ssd` con `root=PARTUUID=` pasa a ser la `DEFAULT`. La entrada `primary` (microSD) queda intacta.
- **`rollback`:** vuelve a `DEFAULT primary`.

## Consecuencias

- La microSD solo se lee al arrancar; el sistema, los logs y Docker escriben en el SSD.
- El sistema de la microSD queda como estaba el día de la copia: sirve de respaldo, pero no se actualiza.
- **Si el Nano no arranca desde el SSD**, no hay vuelta automática. Se saca la microSD, se pone en el lector SD del NUC y se cambia `DEFAULT ssd` por `DEFAULT primary` en `boot/extlinux/extlinux.conf`.
- Cualquier cambio de kernel, initrd o `extlinux.conf` se hace en `/mnt/microsd/boot`, no en `/boot`. Los paquetes retenidos impiden que apt lo haga por error. R32.7.6 es la última versión de JetPack 4, así que retenerlos cuesta poco.
- **El Nano depende del SSD para funcionar.** Si el concentrador USB pierde alimentación, se cae todo el sistema y no solo Docker. Con la fuente de barril eso debería dejar de ser un riesgo; hasta entonces, modo 5 W.
- La línea de comandos del kernel lleva dos `root=`: el `root=/dev/mmcblk0p1` que agrega el cargador en `${cbootargs}` y el `root=PARTUUID=` de la entrada. Funciona porque gana el último, tanto en el kernel como en el `init` del initrd (`tail -1`).
- Queda por medir el tiempo de arranque con más de un reinicio (n = 1 en cada configuración).

## Evidencia

- Initrd de serie (`/boot/initrd`, L4T R32.7.6): contiene `lib/firmware/tegra21x_xusb_firmware`, y su `init` monta `root=PARTUUID=…` con 50 intentos de 0,2 s.
- Arranque actual desde la microSD: `systemd-analyze` da 18,1 s de kernel y 17,4 s de espacio de usuario (35,4 s en total), modo 5 W.
- La edición de `extlinux.conf` y la adaptación de la copia se probaron sobre copias en RAM en el Nano, con su Python 3.6: el resultado es idempotente, la entrada `primary` queda intacta y la retención de paquetes solo afecta a la copia.
- `copy` (2026-11-18, modo 5 W): 12,8 GB a 18,7 MB/s, unos 11 minutos. La copia se revisó antes de cambiar la entrada: módulos `4.9.337-tegra` iguales al kernel, permisos de `sudo`, `/etc/shadow` y `/tmp` intactos, 6 paquetes retenidos solo en la copia.
- **Prueba de reinicio** tras `switch`:
  - El initrd encontró `PARTUUID=3cf7cc7e-…` a los 2,0 s y montó la raíz a los 5,4 s.
  - `findmnt /` da `/dev/sda1` y la microSD queda en `/mnt/microsd`.
  - Docker usa `/var/lib/docker` con sus datos y el contenedor `sancho-broker` volvió solo; un cliente con el rol `recorder` se conectó con sus credenciales de producción.
  - `wlan0` recibió 192.168.0.122, la IP reservada.
- Arranque desde el SSD: 5,5 s de kernel y 13,4 s de espacio de usuario, **18,9 s** en total, frente a 35,4 s desde la microSD; Docker tarda 4,5 s en lugar de 10 s. Con n = 1 no se sabe cuánto del kernel (18,1 s frente a 5,5 s) se debe al disco y cuánto a otra cosa del arranque anterior.
- Con el conector USB 3 (2026-11-19, modo 5 W): lectura secuencial de 266–268 MB/s, escritura de 235–240 MB/s (E/S directa, 3 corridas) y arranque en **13,1 s**, sin cambiar la configuración.
