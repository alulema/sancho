UV_RUN := uv run --locked

.PHONY: help test lint format bench sim deploy-nano

help:
	@echo "make test         Pruebas (excluye las marcadas 'nano')"
	@echo "make lint         Revisa estilo y formato sin cambiar archivos"
	@echo "make format       Aplica el formato"
	@echo "make bench        Banco de evaluación (pendiente: T11)"
	@echo "make sim          Simulación sin hardware (broker, cuerpo simulado y orquestador)"
	@echo "make deploy-nano  Despliegue al Nano (pendiente: T12)"

test:
	$(UV_RUN) pytest

# SIM_ARGS="--script sim/scripts/otro.yaml --greeting-window-min 0.05"
sim:
	$(UV_RUN) python -m sim $(SIM_ARGS)

lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

format:
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

# Fallan a propósito hasta implementarse: un objetivo vacío parecería un éxito.
bench:
	@echo "make bench: sin implementar (T11 de SPEC_E0)" >&2; exit 1

deploy-nano:
	@echo "make deploy-nano: sin implementar (T12 de SPEC_E0)" >&2; exit 1
