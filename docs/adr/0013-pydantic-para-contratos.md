# ADR-0013 — Pydantic v2 y PyYAML para implementar los contratos

- **Fecha:** 2026-11-13
- **Estado:** aceptada
- **Etapa:** E0 (T5)

## Contexto

T5 pide un paquete `contracts/` con modelos y validación para el sobre, los tópicos de E0, las trazas y los casos del banco. Todo mensaje publicado o recibido pasa por esa validación, y uno inválido se rechaza y se registra sin romper el componente. Con Python 3.12 en todos los componentes (ADR-0012) se pueden usar librerías actuales, siempre que sus ruedas binarias funcionen en el Nano (aarch64, glibc 2.27). Los casos del banco son YAML.

## Opciones consideradas

1. **Pydantic v2:** modelos tipados con validación declarativa, modo estricto y exportación a JSON Schema. Es la librería más conocida para esto, lo que ayuda al material educativo. Depende de `pydantic-core`, compilado en Rust: hay que verificar la rueda en el Nano. Su importación tarda unos cientos de milisegundos.
2. **msgspec:** más rápido y estricto por defecto, pero menos conocido, y sus mensajes de error son más pobres.
3. **JSON Schema con `jsonschema`:** esquemas independientes del lenguaje, pero los modelos tipados habría que escribirlos aparte, y las reglas que cruzan campos (`first_seen_ts` ≤ `frame_ts` ≤ `ts`) no se expresan bien.
4. **Validación a mano con `dataclasses`:** sin dependencias, pero mucho más código propio que probar.

Para YAML, **PyYAML** con `safe_load`, que no construye objetos de Python arbitrarios.

## Decisión

Se usan **Pydantic v2 en modo estricto** y **PyYAML** (`safe_load`), aceptado por el usuario el 2026-11-13.

- **Modo estricto:** no se convierten tipos. `"0.9"` no es un número y `1` no es un booleano. Se rechazan `NaN` e infinitos.
- **Marcas de tiempo e identificadores con validadores propios:** las marcas deben tener exactamente la forma `AAAA-MM-DDTHH:MM:SS.mmmZ` y los UUID deben ser v4 en su forma canónica, como dice `docs/contratos/README.md`.
- **Campos desconocidos:** se ignoran en los mensajes del bus y en las trazas, como piden las reglas de los contratos. En los casos del banco se rechazan, porque los escribe una persona y una errata (`whitin_ms`) no debe pasar en silencio.
- **Versiones:** se acepta cualquier versión menor de la mayor que se implementa (`0.x`). Las menores solo agregan campos opcionales.
- **`source` no se valida contra el tópico:** el campo lo declara quien publica y no autentica nada; quién puede publicar dónde lo decide la ACL del broker y, desde E4, la firma `sig`.

## Consecuencias

- Los componentes usan una sola API (`contracts.bus`) para codificar y decodificar, y no pueden publicar un mensaje que no valide.
- El arranque de cada servicio paga la importación de Pydantic: ≈ 0,27 s en caliente y ≈ 1,5 s en frío en el Nano en 5W. Es aceptable para servicios de larga duración, no para herramientas que se lanzan por mensaje.
- Hay que corregir los ejemplos de los contratos cuyo UUID no era v4 válido (`trace_id` de los ejemplos tenía la variante `2`). No cambia ningún contrato, solo sus ejemplos.
- Si la validación se volviera un cuello de botella (no debería, a ≈ 13 µs por mensaje), msgspec queda como alternativa.

## Evidencia

En el Nano (Python 3.12.15, modo 5W, 2026-11-13): `uv pip install --only-binary :all: pydantic==2.14.3 pyyaml==6.0.3` instala `pydantic-core` 2.50.4 desde una rueda binaria sobre glibc 2.27. `python -X importtime`: `pydantic` 1,51 s en frío y 0,27 s en caliente; `yaml` 0,32 s y 0,08 s. Validar un modelo estricto de dos campos desde JSON: 12,8 µs por mensaje (10 000 iteraciones).
