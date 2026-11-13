# ADR-0014 — Mosquitto 2.1 en contenedor, paho-mqtt y credenciales generadas desde el contrato

- **Fecha:** 2026-11-13
- **Estado:** aceptada
- **Etapa:** E0 (T4)

## Contexto

T4 pide Mosquitto en el Nano, escuchando solo en la red local, con usuario y contraseña por componente, ACL por tópico y *last will*. Las pruebas de aceptación necesitan un broker real.

- El `apt` del Nano (Ubuntu 18.04) solo ofrece **Mosquitto 1.4.15**, de 2018 y sin soporte, sin MQTT v5 ni los códigos de motivo con que el broker avisa que rechazó una publicación.
- En el NUC (Ubuntu 26.04) el paquete trae 2.0.22, pero **su perfil de AppArmor solo le deja leer archivos en `/etc/mosquitto`**, así que no puede arrancar un broker de pruebas con una configuración temporal.
- La ACL ya está fijada en `topicos-e0.md` (ADR-0006), con roles distintos en producción y en pruebas.

## Opciones consideradas

Broker:

1. **Mosquitto 1.4.15 de `apt` en el Nano:** sin contenedor, pero antiguo, sin parches de seguridad y distinto del de las pruebas.
2. **`eclipse-mosquitto:2.1.2-alpine` en Docker, fijada por digest, en el Nano y en las pruebas:** la misma versión en todas partes, con MQTT v5. Depende de Docker, que ya funciona en el Nano con el runtime de NVIDIA (T2).
3. **Compilar Mosquitto 2 en el Nano:** versión actual sin contenedor, pero hay que mantener la compilación.

Cliente: **paho-mqtt 2.x** (Eclipse, Python puro, MQTT v5) frente a `aiomqtt`, que obliga a que todo el componente sea asíncrono, y `gmqtt`, menos usado.

Contraseñas: generar el archivo con `mosquitto_passwd`, que exige tener el binario donde se genera, o calcular en Python el mismo formato `$7$` (PBKDF2-SHA512).

## Decisión

Aceptada por el usuario el 2026-11-13.

- **Broker:** opción 2, `eclipse-mosquitto` 2.1.2 fijada por digest de índice multiarquitectura (`sha256:75d6662d…`), en el Nano y en las pruebas.
- **Cliente:** paho-mqtt 2.2 con MQTT v5 y QoS 1, envuelto en `contracts.service.BusService`, que valida todo lo que publica y recibe, registra el *last will*, publica `online` en cada (re)conexión y un `offline` real al cerrar.
- **Configuración generada:** `deploy/broker/broker_config.py` escribe `mosquitto.conf`, `acl`, `passwd` y una contraseña por rol a partir de `contracts/acl.py`. Una prueba compara `contracts/acl.py` con la tabla del contrato, así que no pueden divergir. Las contraseñas se generan al azar, se guardan con permisos `0600` fuera de git y no se regeneran salvo con `--rotate`.
- **Límites:** `allow_anonymous false` y `max_packet_size 65536`. El límite de tamaño entra al contrato (`topicos-e0.md` v0.4) y lo aplica también `encode`, para que nadie pueda poner una imagen en el bus.

## Consecuencias

- Las pruebas del broker corren donde haya Docker y la imagen ya descargada; **nunca la descargan solas**. Sin ella se saltan con el comando `docker pull` en el motivo. También se puede usar un binario nativo con `MOSQUITTO=…`.
- **Mosquitto con `acl_file` acepta cualquier suscripción** (SUBACK `Granted QoS 1`) y filtra cada mensaje al entregarlo. La garantía real, que nada llegue a quien no tiene permiso de lectura, está probada; un componente no puede fiarse del SUBACK para saber si tiene permiso.
- Las publicaciones prohibidas reciben PUBACK `0x87 Not authorized` y no se entregan. `BusService` además las rechaza antes de enviarlas.
- Sin TLS, las contraseñas viajan en claro por la red local. Es lo que admite E0 (`docs/diseno.md` §5.9: autenticación y solo red local); TLS llega con la exposición que lo requiera.
- **En el Nano** escucha en `127.0.0.1` y en la interfaz `wlan0` (`bind_interface`), no en las redes de Docker. `bind_interface` toma la IP al arrancar, así que conviene reservarla en el router. La supervisión con systemd es de T12.

## Evidencia

En el NUC (Ubuntu 26.04, Docker 29.7.2), 2026-11-13: 41 pruebas de aceptación contra el broker en contenedor pasan en 25 s:

- Un cliente sin credenciales, con contraseña equivocada o con usuario desconocido es rechazado.
- Cada rol publica en sus tópicos, y recibe `0x87` en 9 combinaciones ajenas.
- Al matar con `SIGKILL` un servicio (`brain` o `body`), su *last will* aparece en menos de 2 s, valida contra el contrato y queda retenido para quien se suscriba después.
- El broker de producción no acepta a `sim`, `replay` ni `eval`.

En el Nano (modo 5W), `deploy/broker/smoke_check.py` con las credenciales de producción: 8/8 comprobaciones, *last will* 0,02 s después de `SIGKILL`. Desde el NUC, sin credenciales: `Not authorized`.

Las suscripciones fuera de permiso se aceptan pero no entregan nada (sonda en `tests/test_broker.py::test_role_does_not_receive_outside_its_topics`). Bitácora: `docs/bitacora/2026-11-13-t4-bus.md`.
