# SPEC E0 — Esqueleto vertical

> Referencia: `docs/diseno.md` §12 (E0), §5.9, §6.12, §9.3, §14.
> Estado: lista para implementar.

## Objetivo

Que algo funcione **de punta a punta en pocas semanas** sobre una base mínima pero correcta: **al entrar al estudio, el asistente detecta a una persona y la saluda en voz alta**, con la latencia medida y el flujo completo trazado.

## Alcance

**Incluido**
- Estructura del repo, herramientas y comandos de desarrollo.
- Bus MQTT local con autenticación.
- Implementación de los contratos v0 (`docs/contratos/`).
- Agente de cuerpo mínimo: cámara → detección de persona/rostro → evento; TTS local para hablar.
- Orquestador mínimo: recibe el evento y decide saludar con una regla.
- Mocks para correr toda la cadena en el NUC sin hardware.
- Grabación y reproducción de eventos del bus.
- Logs estructurados, trazas y medición de latencia.
- Banco de evaluación mínimo.
- Construcción y despliegue al Nano.
- Primeros ADR y bitácora.

**Fuera de alcance (no implementar en E0)**
- Reconocimiento de **quién** es la persona (E1). En E0 solo se detecta que hay alguien.
- Guardar rostros, embeddings o cualquier dato biométrico en disco (requiere el cifrado de E1).
- Cualquier llamada a la nube, LLM o API externa (E2).
- Micrófono, wake word o STT (E2).
- Pantalla, servos o cabeza (E3).
- TLS en MQTT, CA local y protocolo de descubrimiento implementado (E6). En E0 el protocolo solo se **especifica** (ya está en `docs/contratos/descriptor-nodo.md`).
- TensorRT y aceleración por GPU para la detección: se aceptan detectores en CPU. La GPU llega en E1.

## Decisiones ya tomadas

| Decisión | Valor |
|---|---|
| Placa | Jetson Nano A02, JetPack 4.6, un solo puerto CSI (ADR-0001); única plataforma en E0 (ADR-0003) |
| Alimentación | Hasta reemplazar la fuente de barril de 5 V 4 A, el Nano opera por micro-USB en modo de 5 W (`sudo nvpmodel -m 1`) |
| Cámara | Raspberry Pi Camera V2.1 (IMX219), fija |
| Bus | MQTT con Mosquitto |
| Lenguaje | Python |
| Repo | Monorepo con la estructura de `CLAUDE.md` |
| Identificadores | En inglés; documentación en español |
| Prefijo de tópicos | `sancho/` |

## Decisiones abiertas que no bloquean E0

- Dónde corre el cerebro a largo plazo.
- Servidor de llaves (Tang) para E1: **el NUC queda descartado** porque se apaga a diario. Opciones a evaluar antes de E1: otro equipo siempre encendido (router compatible o una placa pequeña) o frase de paso manual al arrancar.

## Restricción: el NUC se apaga a diario

- El NUC es solo máquina de **desarrollo**. Ningún componente de uso diario puede depender de él.
- Todo lo que el asistente necesite para funcionar a diario corre en el Nano (o, en el futuro, en otro equipo siempre encendido).
- Registrada en ADR-0002.

## Tareas

Cada tarea termina con su criterio de aceptación cumplido y, cuando aplique, un ADR o una entrada de bitácora.

### T1 — Repo y herramientas
- Estructura de carpetas de `CLAUDE.md`, `README.md`, `.gitignore` (incluye secretos, modelos descargados y grabaciones), `PROTECTED_PATHS`.
- Gestor de dependencias y formateo/linting de Python.
- `Makefile` con: `make test`, `make bench`, `make sim`, `make deploy-nano`.
- **Aceptación:** `make test` corre en el NUC (aunque haya pocas pruebas) y falla si una prueba falla.

### T2 — Viabilidad de Python moderno en el Nano (supuesto S6)
- Verificar si es posible correr en el Nano un contenedor ARM64 con Python ≥ 3.10 **con acceso a la cámara CSI** (GStreamer/`nvarguscamerasrc`).
- Si no es viable, documentar la alternativa elegida. Como el NUC se apaga a diario, **el cerebro también debe poder correr en el Nano** antes del MVP diario de E2. Opciones: Python moderno compilado o instalado fuera de contenedor; o el agente de cuerpo en Python 3.6 y el cerebro en Python moderno sin acceso a la cámara. Correr el cerebro en el NUC solo se acepta como solución temporal de desarrollo.
- **Aceptación:** ADR con la versión de Python por componente y la evidencia (comandos ejecutados y resultado). Entrada de bitácora con el supuesto S6 confirmado o refutado.

### T3 — Sistema en el SSD
- Sistema raíz del Nano en el SSD de 250 GB (el cargador de arranque puede quedar en la microSD si el método lo requiere).
- **Aceptación:** el Nano arranca con el sistema raíz en el SSD; método documentado en un ADR; prueba de reinicio exitosa.

### T4 — Bus MQTT
- Mosquitto en el Nano, escuchando solo en la red local.
- Autenticación por usuario y contraseña por componente; ACL básica por tópico (cada componente publica solo en sus tópicos).
- Mensajes de salud con *last will* (`docs/contratos/topicos-e0.md`).
- **Aceptación:** un cliente sin credenciales es rechazado; un componente no puede publicar en tópicos ajenos; al matar un componente, su *last will* aparece en el bus.

### T5 — Contratos implementados
- Paquete `contracts/` con modelos y validación para: sobre común, tópicos de E0, formato de trazas y formato de casos del banco.
- Todo mensaje publicado o recibido pasa por esta validación.
- **Aceptación:** pruebas que verifican mensajes válidos e inválidos para cada contrato; un mensaje inválido se rechaza y se registra, no rompe el componente.

### T6 — Agente de cuerpo mínimo (Nano)
- Captura de la cámara CSI.
- Detección de persona o rostro en CPU (por ejemplo, el detector DNN de OpenCV). Medir y anotar cuadros por segundo.
- Seguimiento simple e **histéresis**: un solo `person_entered` por entrada, y `person_left` al salir.
- Suscripción a `speech/cmd/say` y reproducción con TTS local (Piper u otro que funcione en el Nano; registrar en un ADR).
- Publicación de `speech/status`.
- **Ninguna imagen se guarda ni se publica.**
- **Aceptación:** al entrar una persona, se publica un solo `person_entered`; al recibir `say`, se oye la frase y se publica `finished`.

### T7 — Orquestador mínimo
- Suscripción a `person_entered`.
- Regla L0: si no se saludó en los últimos N minutos (configurable), publica `speech/cmd/say` con un saludo genérico.
- Escribe una traza por decisión (`docs/contratos/trazas.md`).
- **Aceptación:** una entrada produce un saludo; dos entradas seguidas dentro de N minutos producen uno solo; cada decisión tiene su traza.

### T8 — Mocks y simulación
- Cámara simulada: emite `person_entered` y `person_left` desde un guion o un video de prueba.
- TTS simulado: registra la frase y publica `finished` tras un retardo configurable.
- `make sim` levanta broker, cuerpo simulado y orquestador en el NUC.
- **Aceptación:** la cadena completa funciona en el NUC sin hardware.

### T9 — Grabación y reproducción del bus
- Herramienta que graba los mensajes del bus a JSONL y los reproduce respetando los tiempos relativos.
- **Aceptación:** una sesión grabada en el Nano se reproduce en el NUC y produce las mismas decisiones del orquestador.

### T10 — Observabilidad y latencia
- Logs estructurados en JSON.
- Latencia de punta a punta: desde la marca de tiempo de `person_entered` hasta el `started` de `speech/status`. Reporte con p50 y p95.
- Registro de CPU, RAM, temperatura y **modo de energía** (5 W o 10 W) del Nano durante la prueba. Las mediciones en modos distintos no se comparan entre sí.
- **Aceptación:** reporte de latencia generado a partir de una sesión real en el Nano, guardado en `docs/bitacora/`.

### T11 — Banco de evaluación mínimo
- Runner que carga casos (`docs/contratos/casos-banco.md`), inyecta eventos en el bus y verifica los mensajes esperados y prohibidos dentro de un plazo.
- Al menos cinco casos: entrada simple, dos entradas seguidas, salida y reentrada tras N minutos, mensaje inválido, componente caído.
- `make bench` corre el banco y produce un resumen.
- **Aceptación:** el banco pasa en el NUC con mocks; los resultados se versionan.

### T12 — Construcción y despliegue al Nano
- Imágenes o paquetes para ARM64 según lo decidido en T2.
- `make deploy-nano` copia y levanta los componentes del Nano por SSH; supervisión con systemd y reinicio automático.
- **Aceptación:** tras reiniciar el Nano, todo vuelve a funcionar sin intervención.

### T13 — Documentación del proceso
- ADR-0001 (ya escrito) y los ADR que surjan de T2, T3, T6 y cualquier otra decisión.
- Entradas de bitácora por sesión.
- `README.md` con cómo correr la simulación y cómo desplegar.
- **Aceptación:** cada decisión tomada en E0 tiene su ADR.

## Criterio de terminado de E0

- Al entrar al estudio, el asistente detecta a una persona y saluda en voz alta.
- Latencia de punta a punta medida (p50 y p95) en el Nano.
- La cadena completa funciona en el NUC con mocks.
- El banco de evaluación corre y pasa.
- Tras un reinicio del Nano, todo arranca solo.
- Pruebas de seguridad de E0 (`docs/diseno.md` §5.8, fila de red local): cliente sin credenciales rechazado, publicación en tópico ajeno rechazada.
- ADR escritos para cada decisión y bitácora al día.

## Mediciones para la bitácora (material de artículos)

- Cuadros por segundo de la detección en CPU en el Nano.
- Latencia de punta a punta (p50, p95) y su desglose: detección → bus → decisión → TTS.
- CPU, RAM y temperatura del Nano con la cadena activa.
- Resultado del supuesto S6 (Python moderno con cámara CSI).
- Tiempo de arranque tras reinicio.
