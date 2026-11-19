# ADR-0017 — Detector de personas: NanoDet-Plus con onnxruntime, sin OpenCV

- **Fecha:** 2026-11-19
- **Estado:** aceptada (2026-11-19)
- **Etapa:** E0 (T6)

## Contexto

T6 pide detectar a una persona o un rostro en la CPU del Nano y medir los cuadros por segundo. El estudio tiene la entrada a unos 3 m de la cámara. Restricciones:

- Python 3.12 (ADR-0012), sin enlaces de GStreamer: la cámara llega por un `gst-launch-1.0` en otro proceso.
- Modo 5 W: dos núcleos Cortex-A57.
- glibc 2.27 (Ubuntu 18.04): muchas ruedas recientes ya no instalan.
- Ninguna imagen se guarda ni se publica.

## Opciones consideradas

Todas medidas en el Nano, modo 5 W, 2 hilos, con cuadros reales de la cámara:

1. **YuNet (rostros), con OpenCV 5.1 o 4.14:**
   - Velocidad: 25 cps a 320×180 y 7 cps a 640×360.
   - Con el usuario caminando desde la entrada, a 320×180 no detectó nada.
   - A 640×360 detectó caras de solo 7–8 % del ancho del cuadro, en pocos cuadros, y su tamaño no crecía al acercarse.
   - Solo funciona de frente.
2. **HOG de OpenCV (personas):** 2,6 cps a 640×360; OpenCV 5 ya no lo incluye.
3. **NanoDet-Plus 416 (COCO, clase persona), modelo de `opencv_zoo`, 3,8 MB, Apache-2.0:**
   - Inferencia: 205 ms con `cv2.dnn` 5.1, 337 ms con 4.14 y **181 ms con onnxruntime 1.28**.
   - Con la salida de OpenCV 5 el orden de las salidas cambia y el envoltorio de `opencv_zoo` falla.

## Decisión

**NanoDet-Plus 416 con onnxruntime, decodificado en numpy, sin OpenCV:**

- **Entrada:** GStreamer escala la cámara a 416×234 (`nvvidconv`) y limita a 10 cps (`videorate`). numpy rellena hasta 416×416 y normaliza.
- **Salida:** se decodifica solo la clase persona, con NMS propio. Umbral 0,35.
- **Cuadros:** un hilo lee la cámara sin pausa y el detector toma siempre el cuadro más reciente. Si la lectura y el detector fueran en serie, cada cuadro llegaría con el retraso de la inferencia anterior (~250 ms).
- **Histéresis** (`body/presence.py`): entrada con al menos 2 detecciones en 500 ms, sin huecos de más de 1 s; salida tras 3 s sin detecciones.
- **Mientras el cuerpo habla, no se detecta** (ver Consecuencias), y ese tiempo no cuenta como ausencia.
- **Versiones:** onnxruntime queda en `<1.29`; las versiones posteriores solo publican ruedas para glibc 2.28.
- **Modelos:** `deploy/nano/fetch_models.py` los descarga a `~/sancho/models` con su SHA-256 fijado. Solo se descargan al preparar el equipo, nunca en ejecución.

## Consecuencias

- Detecta a la persona entera: de espaldas, de lado y a 3 m. No sabe quién es; eso es de etapas posteriores.
- El cuerpo no depende de OpenCV ni de sus diferencias entre 4 y 5, y onnxruntime ya llega como dependencia de Piper (ADR-0018).
- Unos 3–4 cps en el agente (300 ms por cuadro con todo incluido) y alrededor de 1,5 núcleos. Alcanza para entradas y salidas, no para gestos.
- **Detección y voz compiten por los dos núcleos.** Con el detector activo, la síntesis pasa de 0,76× a 2,3× tiempo real y la voz se entrecorta. Por eso se pausa la detección mientras habla. Quien entre durante una frase se detecta al terminarla.
- `frame_ts` es la hora de **llegada** del cuadro al proceso, no la de captura: el tubo de GStreamer no trae marcas de tiempo. Llega tarde por el ISP, el escalado y el tubo; T10 debe estimar cuánto.
- E1 (detección en la GPU) puede reemplazar el detector sin cambiar el resto: `PersonDetector.detect` devuelve puntaje y caja normalizada.

## Evidencia

Bitácora `2026-11-19-t6-cuerpo.md`.

- **Caminata desde la entrada (3 m) hasta la cámara, 30 s:** persona detectada en 107 de 113 cuadros, puntaje 0,38–0,81. Los 6 fallos se concentraron en 2 s mientras caminaba.
- **Estudio vacío, 15 s:** 0 detecciones en 59 cuadros.
- **Sesión real con el orquestador:** un solo `person_entered` por entrada; hubo 5 entradas en 4 minutos.
- **Pruebas:** `tests/test_body.py` y `tests/test_body_detector.py` (en el NUC), y `tests/test_body_nano.py` (marcadas `nano`).
