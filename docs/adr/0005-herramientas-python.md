# ADR-0005 — uv, Ruff y pytest como herramientas de desarrollo

- **Fecha:** 2026-11-05
- **Estado:** aceptada
- **Etapa:** E0 (T1)

## Contexto

T1 pide un gestor de dependencias y formateo y linting de Python. La versión de Python por componente todavía no está decidida: depende de T2. Por eso esta decisión cubre las herramientas de desarrollo, no la versión mínima de cada componente en el Nano.

## Opciones consideradas

1. **uv + `uv.lock`:** un solo binario que instala Python y dependencias, con archivo de bloqueo multiplataforma. Es rápido y ya estaba instalado en la máquina de desarrollo. Es una herramienta joven y no sirve para Python 3.6.
2. **Poetry:** maduro y con bloqueo, pero más lento, y Python se instala aparte.
3. **pip + pip-tools:** lo más simple y compatible con Python antiguo, pero Python se instala aparte y hay que mantener un entorno y archivos de requisitos a mano.

Para linting y formato, **Ruff** reemplaza a la vez a flake8, isort y black con una sola herramienta y configuración. Para pruebas, **pytest**, con el marcador `nano` para excluir por defecto lo que requiere el Nano.

## Decisión

Se usan **uv** con `uv.lock` versionado, **Ruff** y **pytest**. `requires-python = ">=3.10"` y Python 3.12 en desarrollo son provisionales hasta el ADR de T2.

## Consecuencias

- Con `uv` y `make` basta para preparar un entorno de desarrollo; `make test` y `make lint` usan `--locked`, así que fallan si el bloqueo quedó desactualizado.
- Si T2 deja algún componente en Python 3.6, estas herramientas no alcanzan para él: habría que correr sus pruebas en 3.6, con versiones antiguas de pytest, y ajustar `requires-python` y `target-version` de Ruff. El ADR de T2 debe resolverlo.
- Para saber si fue buena decisión: si el despliegue al Nano (T12) puede partir de este bloqueo sin mantener una segunda lista de dependencias.

## Evidencia

Versiones instaladas el 2026-11-05 en macOS arm64: uv 0.13.1, Ruff 0.17.4, pytest 9.2.0, Python 3.12.14. Resultado de `make test` y `make lint` en `docs/bitacora/2026-11-05-t1-repo.md`.
