# CLAUDE.md — Sancho

Asistente personal con presencia física en el estudio (cámara, voz, cara expresiva, cabeza articulada) y presencia digital en PC y teléfono. Proyecto personal de Alexis con un segundo objetivo de igual peso: ser una experiencia educativa documentada (blog, paper, libro, curso).

- **Diseño completo:** `docs/diseno.md`. Es la referencia; **no lo cargues entero en cada tarea**. Consulta solo la sección que necesites.
- **Lo que se implementa ahora:** la spec de la etapa actual en `docs/specs/`. **Etapa actual: E0** (`docs/specs/SPEC_E0.md`).
- **Contratos entre componentes:** `docs/contratos/`.

## Entornos

| Máquina | Arquitectura | Rol |
|---|---|---|
| NUC con Ubuntu | x86_64 | Desarrollo, pruebas, simulación con mocks |
| Jetson Nano Developer Kit **A02** | ARM64, JetPack 4.6 (Ubuntu 18.04), GPU Maxwell, 4 GB, **un solo puerto CSI** | Cuerpo del estudio y cerebro inicial |

- Todo lo que no dependa de hardware debe correr y probarse en el NUC con mocks.
- Lo que use la cámara CSI, la GPU o TensorRT solo se valida en el Nano. Márcalo así en las pruebas.
- JetPack 4.6 trae Python 3.6 y una pila CUDA antigua. **No asumas compatibilidad:** verifica y registra el resultado en la bitácora.
- Mientras el Nano se alimente por micro-USB, opera en modo de 5 W: registra el modo de energía en toda medición.
- **Plataformas futuras** (Raspberry Pi 5 como núcleo; Orange Pi 5 u Orin como cuerpo) están previstas en ADR-0003 y `docs/diseno.md` §10.6. **No las adelantes:** por ahora todo corre en el Nano.

## Principios que no se rompen

1. **Cuerpo y cerebro separados.** Se comunican solo por el bus MQTT, con los contratos de `docs/contratos/`. Nada de llamadas directas entre ellos.
2. **Garantías del sistema, no promesas del modelo.** Lo que el asistente no debe hacer lo impide el código (permisos, validación, límites), nunca un prompt.
3. **Seguridad antes de exposición.** Cada control entra justo antes de la exposición que mitiga (`docs/diseno.md` §5.9). No adelantes integraciones externas a su etapa.
4. **Medir antes de afirmar.** Si dices que algo es rápido o funciona, que haya una medición o una prueba que lo respalde.
5. **Decidir no es generar.** Lo que pueda resolverse con reglas, se resuelve con reglas.

## Reglas de seguridad

- **Nunca** subas secretos al repo (llaves, tokens, contraseñas, certificados privados). Usa variables de entorno o archivos ignorados por git, y documenta qué variable se necesita.
- **Ninguna llamada de red saliente** fuera de lo que la spec de la etapa permita. En E0 no hay llamadas a la nube.
- **Nunca** guardes imágenes, video ni audio crudos en disco ni en el bus. Solo eventos y metadatos.
- **Rutas protegidas:** las listadas en `PROTECTED_PATHS` (se crea en E0). Cambiarlas requiere que la spec lo pida explícitamente y que el cambio se señale en el resumen del PR.

## Cómo trabajar

- **Una etapa a la vez.** No implementes funciones de etapas futuras aunque parezcan fáciles. Si algo del diseño te parece necesario antes de tiempo, propónlo en lugar de hacerlo.
- **Contratos primero.** Si un cambio altera un mensaje, tópico o formato, actualiza primero el contrato (con su versión) y luego el código.
- **ADR por decisión relevante:** elegir una librería, cambiar un contrato, descartar una opción. Usa `docs/adr/0000-plantilla.md` y numera en orden.
- **Bitácora:** al terminar una sesión de trabajo, agrega una entrada en `docs/bitacora/` con lo intentado, lo medido y lo que falló. Los fallos también se registran: son material para los artículos.
- **Supuestos:** si confirmas o refutas un supuesto de `docs/diseno.md` §18, anótalo en la bitácora con la evidencia.
- **Pruebas:** todo componente nuevo trae pruebas que corren en el NUC. Las que requieren el Nano se marcan y se excluyen por defecto.
- Ante una ambigüedad en la spec, **pregunta** antes de elegir por tu cuenta si la decisión es difícil de revertir.

## Convenciones

- **Código e identificadores:** en inglés.
- **Documentación, ADR, bitácora y mensajes al usuario final:** en español.
- **Lenguaje principal:** Python. La versión mínima la fija el ADR correspondiente de E0, porque depende de lo que funcione en el Nano.
- **Prefijo de tópicos MQTT:** `sancho/` (ADR-0004).
- Los comandos de desarrollo (`make test`, `make bench`, `make sim`, `make deploy-nano`) se crean en E0. Hasta que existan, no los asumas.

## Estructura del repo (objetivo de E0)

```
CLAUDE.md
PROTECTED_PATHS
README.md
Makefile
docs/
  diseno.md          # diseño completo (referencia)
  specs/             # una spec por etapa
  contratos/         # contratos versionados entre componentes
  adr/               # registros de decisiones de arquitectura
  bitacora/          # bitácora de laboratorio
contracts/           # implementación de los contratos (modelos y validación)
body/                # agente de cuerpo (corre en el Nano)
brain/               # orquestador (corre en el Nano o en el NUC)
sim/                 # mocks y reproducción del bus
eval/                # banco de evaluación: runner y casos
deploy/              # imágenes, compose y despliegue al Nano
```
