# ADR-0012 — Python 3.12 para todos los componentes de E0

- **Fecha:** 2026-11-13
- **Estado:** aceptada
- **Etapa:** E0 (T2)

## Contexto

T2 pide fijar la versión de Python por componente, con evidencia de lo que funciona en el Nano. JetPack 4.6 trae Python 3.6.9 y OpenCV 4.1.1 con GStreamer, y la cámara CSI solo se usa por `nvarguscamerasrc`. Como el NUC se apaga a diario, el cerebro también tiene que correr en el Nano.

La vía en contenedor todavía no se pudo probar: la microSD tiene 1,1 GB libres y el SSD no está listo (T3).

## Opciones consideradas

1. **Todo en Python 3.6:** funciona con lo que trae JetPack, pero Python 3.6 no recibe actualizaciones desde 2021, y uv, Ruff, pytest y Pydantic actuales no lo soportan.
2. **Cuerpo en 3.6 y cerebro en Python moderno:** el cuerpo usa los enlaces del sistema, pero los contratos deben correr en dos versiones y hacen falta dos cadenas de herramientas.
3. **Todo en Python 3.12; el cuerpo lee la cámara por un proceso de `gst-launch`:** una sola versión y una sola cadena de herramientas. Se probó fuera de contenedor: 30 cps a 640×360 (bitácora del 2026-11-13).

## Decisión

Se elige la opción 3, aceptada por el usuario el 2026-11-13. Todos los componentes de E0 (`contracts`, `body`, `brain`, `sim`, `eval`) corren en Python 3.12: `requires-python = ">=3.12"`. Que corran dentro o fuera de un contenedor lo decide T12, después de probar la vía en contenedor en el SSD.

## Consecuencias

- T5 puede usar librerías actuales de validación.
- El cuerpo depende del binario `gst-launch-1.0` del sistema, no de enlaces de Python. Si el proceso de GStreamer muere, el cuerpo debe detectarlo y relanzarlo.
- OpenCV en Python 3.12 viene de la rueda de PyPI, sin GStreamer ni CUDA. Alcanza para la detección en CPU de E0.
- E1 (detección en la GPU) puede chocar con esto: los enlaces de TensorRT solo existen para Python 3.6 (S23). Si se confirma, la inferencia en GPU iría en un proceso aparte, sin cambiar la versión de los demás componentes.
- Hay que medir si Python 3.12 cuesta más CPU que 3.6 por cuadro: en una sola corrida usó 4,61 s frente a 3,64 s.

## Evidencia

`docs/bitacora/2026-11-13-t2-python-moderno.md`: comandos ejecutados, versiones y mediciones. Script de la prueba: `deploy/nano/camera_probe.py`.
