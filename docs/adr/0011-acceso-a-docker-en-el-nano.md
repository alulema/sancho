# ADR-0011 — El usuario `alulema` usa Docker sin sudo en el Nano

- **Fecha:** 2026-11-13
- **Estado:** aceptada
- **Etapa:** E0 (T2, T12)

## Contexto

T2 y T12 necesitan correr Docker en el Nano desde la máquina de desarrollo por SSH. El usuario `alulema` no estaba en el grupo `docker`, y sudo pide contraseña. Pertenecer al grupo `docker` equivale a tener acceso de root.

## Opciones consideradas

1. **Agregar `alulema` al grupo `docker`:** permite automatizar por SSH. La llave SSH sin frase de paso de la máquina de desarrollo pasa a dar acceso de root sin contraseña.
2. **Correr cada comando de Docker con sudo, a mano:** la contraseña sigue protegiendo el acceso de root, pero cada paso exige intervención humana, y T12 pide un despliegue automático.

## Decisión

Se agrega `alulema` al grupo `docker` (opción 1), por decisión del usuario.

## Consecuencias

- T2 y T12 se pueden automatizar por SSH.
- Quien obtenga la llave SSH de la máquina de desarrollo obtiene root en el Nano. El riesgo adicional es bajo mientras el Nano solo sea accesible desde la red local y `alulema` ya tenga sudo, pero hay que revisarlo antes de E6, cuando llega el acceso remoto (§5.9).
- Los servicios de producción no deben correr como `alulema` ni depender de este acceso; T12 define sus propios usuarios.

## Evidencia

`id -nG` el 2026-11-05: `alulema` no estaba en `docker`, y `docker info` falló con `permission denied`. El 2026-11-13, tras `sudo usermod -aG docker alulema`, `id -nG` incluye `docker` y `docker info` responde sin sudo: Docker 20.10.21, `overlay2`, runtime `nvidia` disponible y `runc` por defecto.
