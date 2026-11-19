# ADR-0018 — Voz local: Piper en un proceso aparte, voz es_ES-davefx-medium

- **Fecha:** 2026-11-19
- **Estado:** aceptada (2026-11-19)
- **Etapa:** E0 (T6)

## Contexto

T6 pide reproducir `say` con TTS local en el Nano («Piper u otro que funcione en el Nano; registrar en un ADR») y publicar `speech/status`. Sin nube en E0, y sin guardar audio en disco.

Restricciones encontradas:

- **Altavoz:** USB (Jieli «UACDemoV1.0»), que no es la salida por omisión del sistema. Es pequeño: casi no reproduce graves (330 Hz apenas se oye). A 100 % de volumen distorsionó y el Nano se apagó; probablemente fue una caída de tensión, porque se alimenta por micro-USB.
- **Licencia:** `piper-tts` 1.8 es **GPL-3.0-or-later**, y también lo es `espeak-ng`, que convierte texto en fonemas. El repositorio no tiene licencia todavía, y el proyecto se publicará (blog, libro, curso).

## Opciones consideradas

1. **Voz:** dos voces medias de Piper, oídas por el usuario en el altavoz:
   - `es_MX-ald-medium`: 2,1 s hasta el primer audio, 1,13× tiempo real; se entrecorta.
   - `es_ES-davefx-medium`: 1,0 s hasta el primer audio, 0,77× tiempo real. **El usuario la entiende mejor.**
2. **Cómo usar Piper:**
   - Importarlo en el agente del cuerpo: más simple, pero el agente sería probablemente una obra derivada de código GPL.
   - Tratar todo el repositorio como GPL-3.0: decide hoy la licencia del proyecto entero.
   - Correrlo en **un proceso aparte, comunicado por tubos**: se considera agregación, y además aísla los fallos.

## Decisión

- **Voz:** `es_ES-davefx-medium` (dataset CC0), en `~/sancho/models` vía `deploy/nano/fetch_models.py`.
- **Piper en un proceso aparte** (decisión del usuario, 2026-11-19):
  - `body/tts_worker.py` es el **único** archivo que importa Piper y lleva `SPDX-License-Identifier: GPL-3.0-or-later`.
  - El cuerpo habla con él por el protocolo de `body/ttsproto.py`: pedidos JSON por stdin y cuadros binarios por stdout.
  - El worker carga la voz una sola vez, antes de que el cuerpo se anuncie en el bus, y se relanza si muere.
- **Reproducción:**
  - El audio va del worker a `paplay --latency-msec=200` por memoria, hacia el *sink* del altavoz (`--sink` o `SANCHO_SINK`).
  - El búfer por omisión de `paplay` (~2 s) atrasaba `finished` unos 2 s; con 200 ms suena sin cortes.
  - `started` se publica al entregar el primer trozo de audio (Piper sintetiza por oraciones); `finished`, cuando `paplay` termina.
- **Volumen:** 70 % en PulseAudio, elegido por el usuario. No se sube más mientras el Nano se alimente por micro-USB.

## Consecuencias

- El resto del cuerpo, y del repositorio, puede tener la licencia que el usuario elija. Una prueba en el Nano verifica que solo `tts_worker.py` importa Piper.
- Un fallo de síntesis publica `state: error` y no tumba la cámara.
- La voz tarda 6–7 s en cargar al arrancar el cuerpo, que solo se anuncia en el bus cuando está lista.
- El primer audio llega unos 0,7 s después del `say` con la CPU libre, y 1,5–1,6 s en la sesión real. Un saludo que empieza con una oración corta («¡Hola!») suena antes.
- Sin graves en este altavoz: la voz suena delgada pero se entiende.
- Queda por medir en T10 por qué `started` → `finished` varió entre 4,1 y 6,2 s para la misma frase de 2,8 s.

## Evidencia

Bitácora `2026-11-19-t6-cuerpo.md`.

- **Síntesis, frase de 2,8 s, modo 5 W:**
  - Sola: 0,76–0,81× tiempo real.
  - Con el detector en paralelo: 2,05–2,36×.
  - Con el detector en `nice 19`: 0,95–1,01×.
- **`paplay`:** de `started` a `finished` hay 5,6 s con el búfer por omisión y 3,5 s con 200 ms.
- **Licencias:** `piper-tts` 1.8.0 GPL-3.0-or-later; voz davefx, dataset CC0; onnxruntime MIT.
