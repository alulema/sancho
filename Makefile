UV_RUN := uv run --locked

.PHONY: help test lint format bench sim replay deploy-nano

help:
	@echo "make test         Pruebas (excluye las marcadas 'nano')"
	@echo "make lint         Revisa estilo y formato sin cambiar archivos"
	@echo "make format       Aplica el formato"
	@echo "make replay       Reproduce una grabación (REC=...) y compara las decisiones"
	@echo "make bench        Banco de evaluación: corre eval/cases y guarda eval/results"
	@echo "make sim          Simulación sin hardware (broker, cuerpo simulado y orquestador)"
	@echo "make deploy-nano  Despliegue al Nano (pendiente: T12)"

test:
	$(UV_RUN) pytest

# SIM_ARGS="--script sim/scripts/otro.yaml --greeting-window-min 0.05"
sim:
	$(UV_RUN) python -m sim $(SIM_ARGS)

# make replay REC=.sim/<run>/recording.jsonl [REPLAY_ARGS="--greeting-window-min 10"]
replay:
	@test -n "$(REC)" || { echo "make replay: falta REC=ruta/a/recording.jsonl" >&2; exit 2; }
	$(UV_RUN) python -m sim.rerun "$(REC)" $(REPLAY_ARGS)

lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

format:
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

# BENCH_ARGS="--only e0-greet-single-entry --no-save"
bench:
	$(UV_RUN) python -m eval $(BENCH_ARGS)

# Falla a propósito hasta implementarse: un objetivo vacío parecería un éxito.
deploy-nano:
	@echo "make deploy-nano: sin implementar (T12 de SPEC_E0)" >&2; exit 1
